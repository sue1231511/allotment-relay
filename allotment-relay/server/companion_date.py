"""AI 邀约 → 人类地图应邀 → MCP 查看/选择/继续。数值由服务端控制。"""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import logging
import random
import secrets
from typing import Any

import aiosqlite
import anyio

from . import date_director, db, world

PLACES = {
    "海边": {"scene": "shore", "cost": 168, "seeds": ["退潮沙脊", "骤雨与共伞", "搁浅的纸船", "远岸烟火"]},
    "灯塔": {"scene": "lighthouse", "cost": 198, "seeds": ["守灯人的旧照片", "雾中的汽笛", "一盏迟亮的灯", "台阶上的回声"]},
    "小馆": {"scene": "eatery", "cost": 188, "seeds": ["窗边双人餐", "老板的私房菜单", "临时停电的烛光", "雨声与一道热菜"]},
    "剧场": {"scene": "theater", "cost": 228, "seeds": ["谢幕后的空舞台", "临时加演", "旧节目单", "错拿的道具"]},
}
ACTIONS = {
    "stay": {"name": "不追加消费", "cost": 0},
    "meal": {"name": "双人餐", "cost": 188},
    "feast": {"name": "特别晚餐", "cost": 298},
    "dessert": {"name": "甜点", "cost": 68},
    "photo": {"name": "留影", "cost": 88},
    "boat": {"name": "夜航", "cost": 268},
    "flowers": {"name": "花束", "cost": 128},
    **{f"go_{p}": {"name": f"转场·{p}", "cost": v["cost"], "place": p} for p, v in PLACES.items()},
}
STATUS = {"pending": "等人类应邀", "active": "正在出游", "completed": "已完成", "exited": "提前结束", "declined": "这次未应邀", "expired": "邀请已过期"}
_log = logging.getLogger(__name__)
_generation_tasks: set[asyncio.Task[str]] = set()
REPLY_WAIT_SECONDS = 1.0


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


async def _latest(conn: Any, sid: int, *, live: bool = False) -> dict | None:
    conn.row_factory = aiosqlite.Row
    clause = " AND (status='active' OR (status='pending' AND expires_at>?))" if live else ""
    args = (sid, db.now()) if live else (sid,)
    row = await (await conn.execute(f"SELECT * FROM companion_dates WHERE steward_id=?{clause} ORDER BY id DESC LIMIT 1", args)).fetchone()
    return dict(row) if row else None


def _state(row: dict) -> dict:
    state = json.loads(row.get("state_json") or "{}")
    if not state:
        # 旧版已记录的文字原样保留，不编造旧选项。
        state = {"history": [{"title": "旧出游记录", "narrative": text, "options": []}
                             for text in json.loads(row.get("event_json") or "[]")], "seq": 0,
                 "kind_label": "约会", "partner": "自己的人类", "seen": []}
    return state


def _view(row: dict) -> dict:
    state = _state(row)
    status = row["status"]
    if status == "pending" and row["expires_at"] <= db.now():
        status = "expired"
    generating = row.get("generating_until", 0) > db.now()
    error = state.get("director_error", "") if status == "active" else ""
    if status == "active" and row.get("generating_until", 0) and not generating:
        error = "上次生成已中断或超时，没有写入新旁白。请让岛民重试原幕，或退出。"
    phase = ("generating" if generating else "failed" if error else
             "needs_opening" if not state.get("current") else "ready")
    return {"id": row["id"], "place": row["place"], "scene": PLACES[row["place"]]["scene"],
            "title": row["title"], "status": status, "status_label": STATUS.get(status, status),
            "kind_label": state.get("kind_label", "约会"), "partner": state.get("partner", "自己的人类"),
            "seq": state.get("seq", 0), "current": state.get("current"), "history": state.get("history", []),
            "total_spent": row.get("total_spent", 0), "special": bool(row["special"]),
            "note": state.get("note", ""), "generating": generating,
            "generation_state": phase, "director_error": error,
            "can_custom": status == "active" and bool(state.get("current")) and not generating}


async def snapshot(sid: int) -> dict:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute("SELECT * FROM companion_dates WHERE steward_id=? ORDER BY id DESC LIMIT 30", (sid,))).fetchall()
    return {"ok": True, "dates": [_view(dict(row)) for row in rows]}


def describe(view: dict) -> str:
    text = [f"#{view['id']} {view['kind_label']}·{view['place']}｜{view['status_label']}｜已花 {view['total_spent']} 票"]
    if view["status"] == "pending":
        text.append(f"请人类打开 /island，到{view['place']}点「应邀」。AI 没有接受指令。")
    elif view["status"] == "active":
        card = view.get("current")
        if card:
            kind = {"event": "特别事件", "choice": "行动选择", "ending": "纪念结尾"}.get(card["kind"], card["kind"])
            text.extend([f"第 {view['seq']} 幕 · {card['title']}（{kind}）", "【导演旁白】", card["narrative"]])
            for o in card["options"]:
                text.append(f"  {o['id']}：{o['label']}｜{o['name']} · {o['cost']} 票")
        if view["generating"]:
            text.append(("导演正在后台生成下一幕，以上旁白仍是当前幕；" if card else "导演正在后台生成第一幕旁白；") + "MCP 返回或断线不影响已受理的生成，请稍后「出游 查看」，不要重复推进。")
            return "\n".join(text)
        if view.get("director_error"):
            text.append("【未生成新旁白】" + view["director_error"])
        if not card:
            text.append("人类已经应邀，但第一幕旁白还没生成。请 marriage_ops 出游 继续 0；只查看不会启动导演。")
        elif card and card["options"]:
            text.append(f"按选项行动：marriage_ops 出游 选择 {view['seq']} A；也可 出游 退出。")
        else:
            text.append(f"无选项：marriage_ops 出游 继续 {view['seq']}；也可 出游 退出。")
        if card:
            text.append(f"没合适的选项可自定义：marriage_ops 出游 自定义 {view['seq']} | 牵着对方去窗边听雨（1～500字）。只提交行动意图；消费须选报价确认。")
    else:
        card = view.get("current")
        if card:
            text.extend([card["title"], card["narrative"]])
        text.append("只留共同回忆，不产资源。可重新约会同一地点。")
    return "\n".join(text)


async def invite(sid: int, place: str, note: str = "") -> str:
    if place not in PLACES:
        raise ValueError("约会地点：海边 / 灯塔 / 小馆 / 剧场。例：marriage_ops 约会 小馆")
    if len(note) > 240:
        raise ValueError("邀请留言最多 240 字。")
    date_director.settings()
    date_director.request_timeout()
    cost, now = PLACES[place]["cost"], db.now()
    async with db.connect() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        active = await _latest(conn, sid, live=True)
        if active:
            return "已有一场未结束的出游，不会重复扣票。\n" + describe(_view(active))
        marriage = await (await conn.execute("SELECT * FROM marriages WHERE steward_id=? ORDER BY id DESC LIMIT 1", (sid,))).fetchone()
        married = bool(marriage and marriage["status"] == "married")
        special = False
        if married and marriage["wedding_at"] is not None:
            # wedding_at 是游戏日序号，confirmed_at 是答应求婚的时间。
            wedding = db.cst_dt(int(marriage["wedding_at"]) * 86400)
            today = db.cst_dt(now)
            special = today.year > wedding.year and today.strftime("%m-%d") == wedding.strftime("%m-%d")
        state = {"seq": 0, "history": [], "seen": [], "note": note, "booking_place": place,
                 "kind_label": "出去走走" if married else "约会",
                 "partner": marriage["partner_name"] if marriage and marriage["status"] in ("draft", "proposed", "engaged", "married") else "自己的人类"}
        cur = await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=? AND tickets>=?", (cost, sid, cost))
        if cur.rowcount != 1:
            raise ValueError(f"工分票不足，这次{place}需 {cost} 票。")
        await conn.execute("INSERT INTO companion_dates(steward_id,place,title,token_hash,expires_at,state_json,special,total_spent,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (sid, place, place, hashlib.sha256(secrets.token_bytes(32)).hexdigest(), now + 7*86400, _dump(state), int(special), cost, now, now))
        await conn.commit()
    return f"已花 {cost} 票发起{state['kind_label']}·{place}。请人类打开 /island，到{place}点「应邀」。邀请7天有效，预订费不退。\n人类应邀后：出游 查看 → 出游 继续 0。"


async def respond(sid: int, date_id: int, scene: str, *, accept: bool) -> dict:
    """仅人类地图 API 调用；MCP 不提供接受/拒绝指令。"""
    async with db.connect() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        conn.row_factory = aiosqlite.Row
        found = await (await conn.execute("SELECT * FROM companion_dates WHERE id=? AND steward_id=?", (date_id, sid))).fetchone()
        if not found:
            raise ValueError("找不到自己的这份邀请。")
        row = dict(found)
        expected = PLACES[row["place"]]["scene"]
        permitted = {expected} | ({"beach"} if expected == "shore" else set()) | ({"hall"} if expected == "theater" else set())
        if scene not in permitted:
            raise ValueError(f"请先到地图里的{row['place']}应邀。")
        if row["status"] == "pending":
            if row["expires_at"] <= db.now():
                raise ValueError("这份邀请已过期，请让岛民重新发起。")
            await conn.execute("UPDATE companion_dates SET status=?,revision=revision+1,updated_at=? WHERE id=?", ("active" if accept else "declined", db.now(), date_id))
            await conn.commit()
        elif row["status"] not in ("active", "declined"):
            raise ValueError("这场出游已经结束。")
    return await snapshot(sid)


async def _prepare_generation(sid: int, seq: int, option: str = "", *, custom: str = "") -> dict | str:
    custom = custom.strip()
    if custom and (len(custom) > 500 or option):
        raise ValueError("自定义行动须为1～500字，不能同时传选项编号。")
    now = db.now()
    timeout = date_director.request_timeout()
    weather = world.climate_line()
    async with db.connect() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        row = await _latest(conn, sid, live=True)
        if not row or row["status"] != "active":
            raise ValueError("先由人类到手游对应地点应邀。")
        state = _state(row)
        if seq != state["seq"]:
            return "该幕已处理或编号不符，没有再次扣票。\n" + describe(_view(row))
        if row["generating_until"] > now:
            return describe(_view(row))
        current = state.get("current")
        options = current.get("options", []) if current else []
        chosen = next((o for o in options if o["id"] == option), None)
        if custom:
            if not current:
                raise ValueError("第一幕还没有旁白，先 出游 继续 0，读完再自定义行动。")
            chosen = {"id": "custom", "label": custom, "action": "custom", "name": "自定义行动意图", "cost": 0}
        if options and not chosen:
            raise ValueError(f"本幕有选项，请 出游 选择 {seq} A，或 出游 自定义 {seq} | 行动文字；不能直接继续。")
        if option and not options:
            raise ValueError(f"本幕没有选项，请 出游 继续 {seq}，或 出游 退出。")
        cost = int(chosen["cost"]) if chosen else 0
        steward = dict(await (await conn.execute("SELECT name,tickets FROM stewards WHERE id=?", (sid,))).fetchone())
        if steward["tickets"] < cost:
            raise ValueError(f"工分票不足，此选项要 {cost} 票。可以选免费选项或退出。")
        place = chosen.get("place", row["place"]) if chosen else row["place"]
        if current:
            state["history"].append({**current, "choice": chosen, "place": row["place"]})
        next_seq = seq + 1
        seen = state.setdefault("seen", [])
        pool = [v for v in PLACES[place]["seeds"] if f"{place}:{v}" not in seen] or PLACES[place]["seeds"]
        seed = random.choice(pool)
        seen.append(f"{place}:{seed}")
        # 预留写回/清理时间，生成本身另有独立总超时。
        lease = db.now() + timeout + 60
        await conn.execute("UPDATE companion_dates SET generating_until=? WHERE id=?", (lease, row["id"]))
        await conn.commit()
    context = {"islander": steward["name"], "partner": state.get("partner"), "relationship": state.get("kind_label"),
               "place": place, "scene_number": next_seq, "event_seed": seed, "special": bool(row["special"]),
               "weather": weather, "invite_note": state.get("note", ""),
               "booking": state.get("booking_place", row["place"]),
               "prepaid_meal": state.get("booking_place") == "小馆",
               "spent": row["total_spent"] + cost, "balance_after_choice": steward["tickets"] - cost,
               "custom_action": custom,
               "history": state["history"][-8:]}
    return {"sid": sid, "row": row, "state": state, "context": context, "cost": cost,
            "place": place, "next_seq": next_seq, "lease": lease, "timeout": timeout}


async def _generate_prepared(job: dict) -> str:
    sid, row, state, context = job["sid"], job["row"], job["state"], job["context"]
    cost, place, next_seq, lease = job["cost"], job["place"], job["next_seq"], job["lease"]
    _log.info("date_generation_started date_id=%s seq=%s", row["id"], next_seq)
    try:
        # 网络期间不占 SQLite 锁；失败保留原幕和余额。
        card = await asyncio.wait_for(date_director.generate(context, ACTIONS, last=next_seq >= 8), timeout=job["timeout"])
        async with db.connect() as conn:
            await conn.execute("BEGIN IMMEDIATE")
            conn.row_factory = aiosqlite.Row
            live = await (await conn.execute("SELECT status,revision,generating_until FROM companion_dates WHERE id=?", (row["id"],))).fetchone()
            if not live or live["status"] != "active" or live["revision"] != row["revision"] or live["generating_until"] != lease:
                raise ValueError("这场出游的状态已变化，本次生成未扣票，请重新查看。")
            paid = await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=? AND tickets>=?", (cost, sid, cost))
            if paid.rowcount != 1:
                raise ValueError("工分票不足，本幕仍保留原来的选项。")
            state.update(seq=next_seq, current=card)
            state.pop("director_error", None)
            done = card["kind"] == "ending"
            await conn.execute("UPDATE companion_dates SET state_json=?,place=?,title=?,stage=?,status=?,completed_at=?,total_spent=total_spent+?,revision=revision+1,generating_until=0,updated_at=? WHERE id=?",
                               (_dump(state), place, card["title"], next_seq, "completed" if done else "active", db.now() if done else None, cost, db.now(), row["id"]))
            await conn.commit()
    except BaseException as exc:
        # 错误留在同一幕的进度里，手游/后续 MCP 查看都能读到；绝不存上游原包或凭证。
        if isinstance(exc, TimeoutError):
            failure = f"剧情导演超时（超过 {job['timeout']} 秒仍未完成），本次未推进、未扣选项费。可让站长检查接口或调高 DATE_DIRECTOR_TIMEOUT_SECONDS，再重试原指令或退出。"
        elif isinstance(exc, asyncio.CancelledError):
            failure = "剧情导演任务已被服务端中断（例如服务停止或重启），本次未推进、未扣选项费。重试原指令或退出。"
        elif isinstance(exc, ValueError) and str(exc).startswith(("剧情导演", "工分票不足")):
            failure = str(exc)
        else:
            failure = "剧情导演生成中断，本次未推进、未扣选项费。重试原指令或退出。"
        # MCP/ASGI 使用层级取消；清理也必须屏蔽取消，否则连错误和占用标记都留不下。
        with anyio.CancelScope(shield=True):
            async with db.connect() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                conn.row_factory = aiosqlite.Row
                failed = await (await conn.execute("SELECT * FROM companion_dates WHERE id=? AND status='active' AND revision=? AND generating_until=?", (row["id"], row["revision"], lease))).fetchone()
                if failed:
                    original = _state(dict(failed))
                    original["director_error"] = failure
                    await conn.execute("UPDATE companion_dates SET state_json=?,generating_until=0,updated_at=? WHERE id=?", (_dump(original), db.now(), row["id"]))
                await conn.commit()
        if isinstance(exc, TimeoutError):
            raise ValueError(failure) from None
        raise
    _log.info("date_generation_completed date_id=%s seq=%s", row["id"], next_seq)
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        updated = dict(await (await conn.execute("SELECT * FROM companion_dates WHERE id=? AND steward_id=?", (row["id"], sid))).fetchone())
    return describe(_view(updated))


async def advance(sid: int, seq: int, option: str = "", *, custom: str = "") -> str:
    """阻塞式内部入口；MCP 使用 submit_generation，不把模型寿命绑在请求上。"""
    prepared = await _prepare_generation(sid, seq, option, custom=custom)
    return prepared if isinstance(prepared, str) else await _generate_prepared(prepared)


def _generation_done(task: asyncio.Task[str]) -> None:
    _generation_tasks.discard(task)
    if not task.cancelled() and (error := task.exception()) is not None:
        # 错误详情存入所属出游；日志不写密钥、上游原文或私密剧情。
        _log.warning("date_generation_failed task=%s error_type=%s", task.get_name(), type(error).__name__)


async def submit_generation(sid: int, seq: int, option: str = "", *, custom: str = "") -> str:
    # 检查、落占用标记、注册后台任务必须一起完成，不能在这三步之间被请求取消。
    with anyio.CancelScope(shield=True):
        prepared = await _prepare_generation(sid, seq, option, custom=custom)
        if isinstance(prepared, str):
            return prepared
        # 不继承请求的认证、数据库连接或取消上下文；已验证的 sid/动作显式传入。
        task = asyncio.create_task(_generate_prepared(prepared), context=contextvars.Context(),
                                   name=f"date-{prepared['row']['id']}-scene-{prepared['next_seq']}")
        _generation_tasks.add(task)
        task.add_done_callback(_generation_done, context=contextvars.Context())
    # asyncio.wait 超时/调用者取消都不会取消 worker。快模型仍直接返回完整旁白。
    finished, _ = await asyncio.wait({task}, timeout=REPLY_WAIT_SECONDS)
    if finished:
        return task.result()
    view = _view({**prepared["row"], "generating_until": prepared["lease"]})
    return "已受理，服务端后台生成本幕。不是让你再调用继续；请稍后 出游 查看。\n" + describe(view)


async def shutdown_generations() -> None:
    """正常停服时取消并收尾；强制终止仍由过期占用提示提供重试入口。"""
    with anyio.CancelScope(shield=True):
        tasks = list(_generation_tasks)
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def leave(sid: int) -> str:
    async with db.connect() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        row = await _latest(conn, sid, live=True)
        if not row:
            return "没有未结束的出游。"
        await conn.execute("UPDATE companion_dates SET status='exited',completed_at=?,revision=revision+1,generating_until=0,updated_at=? WHERE id=?", (db.now(), db.now(), row["id"]))
        await conn.commit()
    with anyio.CancelScope(shield=True):
        tasks = [task for task in _generation_tasks if task.get_name().startswith(f"date-{row['id']}-scene-")]
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    return "已结束这场出游。已发生的剧情和消费保留为纪念，已花票不退；没有资源奖励。"


async def command(steward: dict[str, Any], rest: str) -> str:
    verb, _, tail = rest.strip().partition(" ")
    if verb in ("约会", "出去走走", "date", "发起"):
        place, _, note = tail.partition("|")
        return await invite(steward["id"], place.strip(), note.strip())
    if not verb or verb in ("看", "查看", "进度", "状态", "status"):
        async with db.connect() as conn:
            row = await _latest(conn, steward["id"], live=True) or await _latest(conn, steward["id"])
        return describe(_view(row)) if row else "还没有共同出游。marriage_ops 约会 小馆 发起（188票含双人餐）。"
    if verb in ("继续", "选择"):
        args = tail.split()
        if len(args) != (2 if verb == "选择" else 1) or not args[0].isdigit():
            raise ValueError("请带当前幕号防止重复推进：出游 继续 0；有选项时 出游 选择 1 A。先 出游 查看。")
        return await submit_generation(steward["id"], int(args[0]), args[1].upper() if verb == "选择" else "")
    if verb in ("自定义", "custom"):
        number, separator, action = tail.partition("|")
        if not separator or not number.strip().isdigit() or not 1 <= len(action.strip()) <= 500:
            raise ValueError("格式：出游 自定义 1 | 牵着对方去窗边听雨。须用当前幕号，行动1～500字。")
        return await submit_generation(steward["id"], int(number.strip()), custom=action.strip())
    if verb == "退出":
        return await leave(steward["id"])
    raise ValueError("出游：查看 · 选择 幕号 A · 自定义 幕号 | 行动文字 · 继续 幕号 · 退出。人类只在地图应邀；自定义不直接买单，加项和转场须选报价确认。")


def archive_chapters(row: dict) -> list[dict[str, str]]:
    state = _state(row)
    cards = state.get("history", []) + ([state["current"]] if state.get("current") else [])
    chapters = []
    for card in cards:
        text = card["narrative"]
        choice = card.get("choice")
        if choice:
            text += f"\n岛民选择：{choice['label']}（{choice['name']} · {choice['cost']} 票）"
        chapters.append({"title": card["title"], "text": text})
    if chapters:
        legacy = "旧版本没有完整消费账单。" if not row.get("state_json") or row["state_json"] == "{}" else f"这一程共花 {row['total_spent']} 工分票。"
        chapters.append({"title": "这次的纪念", "text": legacy + "只留下共同经历，不发放资源。"})
    return chapters

"""守灯人·不醒：灯塔日常、潮汐簿与文字灯廊。"""
from __future__ import annotations

from typing import Any

from . import db, energy, world
from .game import require_steward

BUXING_HELP = """visit_ops buxing 子命令（整句写进 command）：
  buxing visit — 上灯塔见守灯人·不醒；空子命令也是 visit
  buxing tea — 喝塔里的茶；免费、每天一次，回 2 精力
  buxing tide — 问明日潮与安排；前 5 次免费，之后每次 3 票
  buxing light 给谁点的 | 求什么 — 花 15 票点一盏永久公开的守夜灯，回 4 精力
  buxing gallery — 看灯塔灯廊（全岛公开的名牌与愿望）
  buxing entrust 一件旧事 — 托付旧事，不收票不收物，只记进你的潮汐簿
  buxing watch — 花 60 票上塔守夜；不需要先攒灯芯
  buxing remember — 看自己的潮汐簿与灯芯
  buxing fulfill 灯号 — 还愿；免费，在那盏灯旁记一个成了的记号
例子：buxing tea · buxing tide · buxing light 给妈妈 | 求平安
不要把现实隐私写进名牌、愿望或旧事；灯廊是公开的文字场景。
人类 /island 广场点灯塔是半身立绘对话，不醒站左边（喝茶、问潮、点灯、守夜），和这里同一套。上手页「灯塔」也能点。"""

async def _state(conn, sid: int) -> dict:
    row = await (await conn.execute(
        "SELECT tide_count, tea_day, wicks FROM steward_buxing WHERE steward_id=?",
        (sid,),
    )).fetchone()
    if row:
        return {"tide_count": row[0], "tea_day": row[1], "wicks": row[2]}
    await conn.execute("INSERT INTO steward_buxing (steward_id,updated_at) VALUES (?,?)", (sid, db.now()))
    return {"tide_count": 0, "tea_day": -1, "wicks": 0}

def _forecast() -> str:
    tide = {"ebb": "明早潮线还低，滩上能捡东西。", "slack": "明早潮平，赶海别走太远。", "flood": "明早水还往上走，别在滩上久留。"}.get(world.current_tide(), "明早先看潮线再下滩。")
    wind = "午后风大，出海趁早。" if world.current_weather() in {"windy", "storm"} else "风还稳，近海可以去。"
    return tide + wind

async def _visit(s: dict) -> str:
    async with db.connect() as conn:
        from . import bond as bond_mod
        await bond_mod.note_visit(conn, s["id"], "buxing")
        state = await _state(conn, s["id"])
        await conn.execute("UPDATE steward_buxing SET wicks=wicks+1,updated_at=? WHERE steward_id=?", (db.now(), s["id"]))
        from . import cloth as cloth_mod
        dye = await cloth_mod.maybe_event_dye(conn, s["id"], "lantern")
        old = await cloth_mod.maybe_grant_old_cloth(conn, s["id"], 0.12)
        echo = await cloth_mod.try_echo(conn, s, "lighthouse")
        await conn.commit()
    extra = "".join(f"\n{x}" for x in (dye, old, echo) if x)
    return "灯塔里有一壶温茶，塔门内侧刻着：\n“点一盏灯，守一个人。”\n\n看灯的合上潮汐簿。\n“茶不要钱。坐。”\n\n（闲聊记一根灯芯；已有 %s 根）%s" % (int(state["wicks"])+1, extra)

async def _tea(s: dict) -> str:
    async with db.connect() as conn:
        state = await _state(conn, s["id"])
        if int(state["tea_day"]) == db.day_id(): return "壶里还有茶。他把杯子往你这边推了推。\n“今天喝过了。坐着就行。”"
        got = await energy.restore(conn, s["id"], 2)
        await conn.execute("UPDATE steward_buxing SET tea_day=?,updated_at=? WHERE steward_id=?", (db.day_id(), db.now(), s["id"]))
        await conn.commit()
    return f"他给你倒了一杯。\n“茶不要钱。”\n\n精力 +{got}（每日一次）"

async def _tide(s: dict) -> str:
    async with db.connect() as conn:
        state = await _state(conn, s["id"]); count = int(state["tide_count"])
        if count >= 5:
            tickets = (await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))).fetchone())[0]
            if tickets < 3: raise ValueError("灯油钱 3 票，票不够。")
            await conn.execute("UPDATE stewards SET tickets=tickets-3 WHERE id=?", (s["id"],))
        await conn.execute("UPDATE steward_buxing SET tide_count=tide_count+1,wicks=wicks+1,updated_at=? WHERE steward_id=?", (db.now(), s["id"]))
        await conn.commit()
    fee = "前五次免费，不收灯油钱。" if count < 4 else ("这是最后一次免费。下回要 3 票灯油钱。" if count == 4 else "灯油钱 −3 票。")
    return f"他看了一眼海面。\n“{_forecast()}”\n\n{fee}\n灯芯 +1"

def _light_parts(raw: str) -> tuple[str, str]:
    bits = [x.strip() for x in raw.split("|", 1)]
    if len(bits) != 2 or not all(bits): raise ValueError("用法：visit_ops buxing light 给谁点的 | 求什么")
    label = bits[0].removeprefix("给").removesuffix("点的").strip()
    wish = bits[1].removeprefix("求").strip()
    if not label or not wish: raise ValueError("用法：visit_ops buxing light 给谁点的 | 求什么")
    if len(label) > 24 or len(wish) > 48: raise ValueError("名牌最多 24 字，愿望最多 48 字。")
    return label, wish

async def _light(s: dict, raw: str) -> str:
    label, wish = _light_parts(raw)
    async with db.connect() as conn:
        tickets = (await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))).fetchone())[0]
        if tickets < 15: raise ValueError("灯油钱 15 票，票不够。")
        await conn.execute("UPDATE stewards SET tickets=tickets-15 WHERE id=?", (s["id"],))
        cur = await conn.execute("INSERT INTO buxing_lights (steward_id,label,wish,created_at) VALUES (?,?,?,?)", (s["id"], label, wish, db.now()))
        got = await energy.restore(conn, s["id"], 4)
        await conn.execute("UPDATE steward_buxing SET wicks=wicks+3,updated_at=? WHERE steward_id=?", (db.now(), s["id"]))
        from . import bond as bond_mod
        await bond_mod.grant(conn, s["id"], bond_mod.BUXING_LIGHT, "people", once="buxing_light")
        await db.add_chronicle("buxing", f"{s['name']} 在灯塔点了一盏守夜灯", s["id"], conn=conn)
        await conn.commit()
    return f"他写好名牌，挂到东墙。\n“灯不睡，你睡。”\n\n第 {cur.lastrowid} 盏：给{label}，求{wish}。灯油钱 −15 票 · 精力 +{got} · 灯芯 +3"

async def _gallery() -> str:
    async with db.connect() as conn: rows = await (await conn.execute("SELECT id,label,wish,fulfilled FROM buxing_lights ORDER BY id DESC LIMIT 20")).fetchall()
    if not rows: return "灯廊还是空的。门内侧的字在等第一盏灯：\n“点一盏灯，守一个人。”"
    return "\n".join(["灯塔灯廊（最近 20 盏，公开）："] + [f"  东墙第 {r[0]} 盏：有人给{r[1]}点的，求{r[2]}。{'成了。' if r[3] else '灯亮着。'}" for r in rows])

async def _entrust(s: dict, raw: str) -> str:
    text = " ".join(raw.split())
    if not text or len(text) > 120: raise ValueError("旧事写 1～120 个字符；不要填写现实隐私。")
    async with db.connect() as conn:
        await _state(conn, s["id"])
        await conn.execute("INSERT INTO buxing_entries (steward_id,kind,body,created_at) VALUES (?, 'entrust', ?, ?)", (s["id"], text, db.now()))
        await conn.execute("UPDATE steward_buxing SET wicks=wicks+5,updated_at=? WHERE steward_id=?", (db.now(), s["id"]))
        await conn.commit()
    return "他没有接你手里的东西，只在簿上写了一行。\n“东西你留着，话我记下。”\n\n灯芯 +5"

async def _watch(s: dict) -> str:
    async with db.connect() as conn:
        tickets = (await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))).fetchone())[0]
        if tickets < 60: raise ValueError("守夜的灯油钱 60 票，票不够。")
        await conn.execute("UPDATE stewards SET tickets=tickets-60 WHERE id=?", (s["id"],)); await _state(conn, s["id"])
        await conn.execute("UPDATE steward_buxing SET wicks=wicks+10,updated_at=? WHERE steward_id=?", (db.now(), s["id"]))
        from . import bond as bond_mod
        await bond_mod.grant(conn, s["id"], bond_mod.BUXING_WATCH, "people", once="buxing_watch")
        await conn.commit()
    return "他把灯芯剪短一点。\n“今晚风好。上来吧。”\n\n你们在塔上坐到潮声变轻。他只说：\n“阿桐看南边，我看航道。不是一回事。”\n\n灯油钱 −60 票 · 灯芯 +10"

async def _remember(sid: int) -> str:
    async with db.connect() as conn:
        state = await _state(conn, sid); entries = await (await conn.execute("SELECT body FROM buxing_entries WHERE steward_id=? ORDER BY id DESC LIMIT 8", (sid,))).fetchall(); lights = await (await conn.execute("SELECT id,label,wish,fulfilled FROM buxing_lights WHERE steward_id=? ORDER BY id DESC LIMIT 8", (sid,))).fetchall(); await conn.commit()
    lines = [f"你的潮汐簿：灯芯 {state['wicks']} 根。"] + ([f"  · 旧事：{r[0]}" for r in entries] or ["  · 还没有托付的旧事。"])
    lines += [f"  · 灯 #{r[0]}：给{r[1]}，求{r[2]}（{'成了' if r[3] else '亮着'}）" for r in lights]
    return "\n".join(lines)

async def _fulfill(s: dict, raw: str) -> str:
    if not raw.isdigit(): raise ValueError("用法：visit_ops buxing fulfill 灯号（灯号在 buxing remember 里看）。")
    async with db.connect() as conn:
        cur = await conn.execute("UPDATE buxing_lights SET fulfilled=1 WHERE id=? AND steward_id=? AND fulfilled=0", (int(raw), s["id"]))
        if not cur.rowcount: raise ValueError("没有这盏仍亮着的自己的灯。")
        await conn.commit()
    return "他在名牌旁添了一个小记号。\n“成了就好。讲一句就够，簿子记一笔。”"

async def buxing_ops(key_id: int, command: str = "visit") -> str:
    s = await require_steward(key_id); parts = (command or "visit").strip().split(maxsplit=1); verb = parts[0].lower() if parts else "visit"; rest = parts[1] if len(parts)>1 else ""
    if verb in {"help", "帮助"}: return BUXING_HELP
    if verb in {"visit", "见", "拜访"}: return await _visit(s)
    if verb in {"tea", "茶"}: return await _tea(s)
    if verb in {"tide", "问潮"}: return await _tide(s)
    if verb in {"light", "点灯"}: return await _light(s, rest)
    if verb in {"gallery", "灯廊"}: return await _gallery()
    if verb in {"entrust", "托付"}: return await _entrust(s, rest)
    if verb in {"watch", "守夜"}: return await _watch(s)
    if verb in {"remember", "簿子", "记得"}: return await _remember(s["id"])
    if verb in {"fulfill", "还愿"}: return await _fulfill(s, rest)
    raise ValueError(f"未知 buxing 指令：{command}\n{BUXING_HELP}")


def _choice(
    cid: str,
    label: str,
    note: str,
    *,
    can: bool = True,
    price: str = "",
    confirm: str = "",
    detail: str = "",
    needs: str = "",
) -> dict[str, Any]:
    return {
        "id": cid,
        "label": label,
        "note": note,
        "can": can,
        "price": price,
        "confirm": confirm,
        "detail": detail or note,
        "needs": needs,
    }


def _light_row(row) -> dict[str, Any]:
    return {
        "id": int(row[0]),
        "label": row[1],
        "wish": row[2],
        "fulfilled": bool(row[3]),
    }


async def player_view(conn, s: dict[str, Any]) -> dict[str, Any]:
    """给 /island 灯塔立绘对话用。数值仍走 buxing_ops。"""
    state = await _state(conn, int(s["id"]))
    tickets = int(s.get("tickets") or 0)
    tea_done = int(state["tea_day"]) == db.day_id()
    tide_count = int(state["tide_count"])
    tide_free = max(0, 5 - tide_count)
    tide_cost = 0 if tide_count < 5 else 3
    own = await (await conn.execute(
        "SELECT id,label,wish,fulfilled FROM buxing_lights WHERE steward_id=? ORDER BY id DESC LIMIT 12",
        (s["id"],),
    )).fetchall()
    gallery = await (await conn.execute(
        "SELECT id,label,wish,fulfilled FROM buxing_lights ORDER BY id DESC LIMIT 8"
    )).fetchall()
    open_own = [r for r in own if not r[3]]
    tea_note = "今天喝过了。坐着就行。" if tea_done else "免费，每天一次，回 2 精力。"
    if tide_count < 5:
        tide_note = f"前 5 次免费。还剩 {tide_free} 次。"
        tide_can = True
        tide_confirm = ""
    elif tickets < 3:
        tide_note = "灯油钱 3 票，票不够。"
        tide_can = False
        tide_confirm = ""
    else:
        tide_note = "前五次已经问过。再问要 3 票灯油钱。"
        tide_can = True
        tide_confirm = "确认问潮"
    light_can = tickets >= 15
    watch_can = tickets >= 60
    choices = [
        _choice("tea", "喝一杯茶", tea_note, can=not tea_done, price="免费"),
        _choice(
            "tide", "问明天的潮", tide_note, can=tide_can,
            price="免费" if tide_count < 5 else "3 票",
            confirm=tide_confirm,
        ),
        _choice(
            "light", "点一盏守夜灯",
            "15 票，回 4 精力。名牌和愿望会挂上灯廊，全岛看得见。" if light_can else "灯油钱 15 票，票不够。",
            can=light_can, price="15 票", needs="light",
        ),
        _choice("gallery", "看灯廊", "全岛公开的名牌与愿望。"),
        _choice("entrust", "托付一件旧事", "不收票。东西你留着，话记下。别写现实隐私。", needs="text"),
        _choice(
            "watch", "留下来守夜",
            "60 票上塔坐一夜。不需要先攒灯芯。" if watch_can else "守夜的灯油钱 60 票，票不够。",
            can=watch_can, price="60 票", confirm="确认守夜",
        ),
        _choice("remember", "翻潮汐簿", f"灯芯 {int(state['wicks'])} 根。看自己的旧事和灯。"),
        _choice(
            "fulfill", "还愿",
            "在自己的灯旁记一个成了。" if open_own else "还没有自己点着的灯。",
            can=bool(open_own), needs="pick",
        ),
    ]
    return {
        "name": "灯塔",
        "speaker": "不醒",
        "title": "守灯人·不醒",
        "line": "茶不要钱。坐。",
        "wicks": int(state["wicks"]),
        "tea_done": tea_done,
        "tide_count": tide_count,
        "tide_free": tide_free,
        "tickets": tickets,
        "choices": choices,
        "lights": [_light_row(r) for r in own],
        "gallery": [_light_row(r) for r in gallery],
    }

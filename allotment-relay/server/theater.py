"""小橘小剧场：单人试镜、对戏、演出、领薪、舞台好感，以及侧厅编剧社投稿。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import config, db, energy, star, survival
from .game import require_steward


THEATER_HELP = """theater_ops 子命令（整句写进 command）：
  看板 / status — 看今晚小橘专场、自己的好感和可演场次；空 command 也是看板。要专场才开
  试镜 — 耗2精力，抽取本场围绕小橘的岗位；一天只能完成一场。要专场
  对戏 — 已试镜后可选，耗3精力，成功给舞台好感并让演出更稳
  演出 — 已试镜后耗8精力，按岗位、对戏与随机结果结算待领工资
  领薪 — 把已结算的票、档信、雾智入账；忘了领也不会丢
  关系 — 单看小橘舞台好感与头粉双倍状态
  编剧社 / 稿件 — 侧厅收稿台：看规矩和自己的稿；常开，不需今晚专场
  投稿 标题 | 正文 — 把潮闻或人物故事投进编剧社。也可 投稿 潮闻 标题 | 正文 / 投稿 故事 标题 | 正文（只是建议，最终她定）
  撤回 编号 — 撤回自己还在待审的稿
  试镜/对戏/演出只在小橘当晚开 stage 小剧场专场时开放；编剧社常开。不替代 bar_ops work 的考勤。
  例子：看板 · 试镜 · 对戏 · 演出 · 领薪 · 编剧社 · 投稿 岸上旧收音机 | 第一幕……
  头粉=star_ops 应援榜第一名；头粉好感获取和每日上限翻倍，不翻倍工资。
  投稿不是 tale_ops accept / story_ops start（那是玩已有篇章）；稿费不是 领薪（那是专场工资）。不要发明 采纳 / 发稿费。
  人类 /island 总览点剧场，进院景再点编剧社 / 衣泊坊 / 剧场看台。编剧社常开能投稿；剧场看台进了是半身立绘对话，小橘站左边，只露上半身（全身的二分之一），先点对话框再出选项，点选项话写在对话框里，不另弹窗，要专场才试镜演出领薪。"""

ROLES = (
    ("announcer", "报幕员", "你替她把开场前的静默接成一句话。"),
    ("understudy", "替身演员", "她换装时，你接住第二幕的走位。"),
    ("lights", "灯光助理", "最后一盏灯由你守着，别让它先于她熄掉。"),
    ("props", "道具师", "她伸手时，那件道具必须正好落进掌心。"),
    ("stunt", "武行", "她退到侧幕的一刻，你替她挡住失控的布景。"),
)

OUTCOME_COPY = {
    "miss": "侧幕的布景慢了半拍。她仍把最后一句唱完，只是没有回头。",
    "normal": "她在台上稳稳唱完最后一段；你的那一环没有拖住整场戏。",
    "great": "她临时抬高了最后一个转音，而你恰好把整段转场接得漂亮。全场起立。",
}
OUTCOME_LABELS = {"miss": "失误", "normal": "平场", "great": "满堂彩"}
PITCH_LABELS = {"story": "故事", "tale": "潮闻"}
SCRIPT_STATUS_LABELS = {
    "pending": "待审",
    "accepted": "已采纳",
    "rejected": "已退稿",
    "withdrawn": "已撤回",
}


def _day() -> int:
    return db.day_id()


async def _require_stage() -> dict:
    state = await star.get_state()
    if state.get("venue") != "stage" or int(state.get("venue_date") or 0) != _day():
        raise ValueError("小橘今晚没有在小剧场开专场。star_ops status 看她的场子；剧场不开工。")
    return state


async def _affinity(conn: aiosqlite.Connection, steward_id: int) -> int:
    row = await (await conn.execute(
        "SELECT score FROM star_theater_affinity WHERE steward_id=?", (steward_id,)
    )).fetchone()
    return int(row[0]) if row else 0


async def _head_fan(conn: aiosqlite.Connection, steward_id: int) -> bool:
    row = await (await conn.execute(
        """SELECT steward_id FROM star_fans
           ORDER BY (cheers * 5 + tip_total) DESC, joined_at ASC LIMIT 1"""
    )).fetchone()
    return bool(row and int(row[0]) == steward_id)


def _tier(score: int) -> tuple[str, int]:
    if score >= config.THEATER_PARTNER_AFFINITY:
        return "压轴搭档", 4
    if score >= config.THEATER_FIXED_CAST_AFFINITY:
        return "固定班底", 3
    if score >= 50:
        return "后台熟人", 2
    if score >= 20:
        return "她记得你的名字", 1
    return "台下的面孔", 0


def _pay(score: int, outcome: str) -> int:
    tier = _tier(score)[1]
    return (
        {"miss": (18, 25, 32, 40, 55), "normal": (38, 50, 65, 80, 100),
         "great": (65, 82, 105, 130, 160)}[outcome][tier]
    )


async def _add_affinity(
    conn: aiosqlite.Connection, steward_id: int, amount: int, head_fan: bool
) -> int:
    if not amount:
        return 0
    gain = amount * (2 if head_fan else 1)
    score = await _affinity(conn, steward_id)
    today = await (await conn.execute(
        """SELECT rehearsal_affinity + performance_affinity FROM star_theater_runs
           WHERE steward_id=? AND day=?""",
        (steward_id, _day()),
    )).fetchone()
    gained_today = int(today[0] or 0) if today else 0
    daily_cap = (
        config.THEATER_HEAD_FAN_AFFINITY_DAILY if head_fan
        else config.THEATER_AFFINITY_DAILY
    )
    actual = min(gain, max(0, daily_cap - gained_today), 100 - score)
    if actual:
        await conn.execute(
            """INSERT INTO star_theater_affinity (steward_id, score, updated_at)
               VALUES (?,?,?) ON CONFLICT(steward_id) DO UPDATE SET
               score=excluded.score, updated_at=excluded.updated_at""",
            (steward_id, score + actual, db.now()),
        )
        from . import bond as bond_mod
        await bond_mod.affinity_gain(conn, steward_id, actual)
    return actual


async def _run(conn: aiosqlite.Connection, steward_id: int):
    return await (await conn.execute(
        "SELECT * FROM star_theater_runs WHERE steward_id=? AND day=?", (steward_id, _day())
    )).fetchone()


async def _pending_run(conn: aiosqlite.Connection, steward_id: int):
    """领薪可跨天：专场收了场，昨晚忘领的工资仍然在。"""
    return await (await conn.execute(
        """SELECT * FROM star_theater_runs WHERE steward_id=? AND outcome<>'' AND claimed=0
           ORDER BY day DESC LIMIT 1""",
        (steward_id,),
    )).fetchone()


async def _cmd_board(conn: aiosqlite.Connection, s: dict) -> str:
    state = await _require_stage()
    score = await _affinity(conn, s["id"])
    head = await _head_fan(conn, s["id"])
    run = await _run(conn, s["id"])
    tier, _ = _tier(score)
    if not run:
        phase = "还没试镜 → theater_ops 试镜"
    elif not run["outcome"]:
        phase = f"已入选{run['role_label']}" + ("，已对戏 → theater_ops 演出" if run["rehearsed"] else " → theater_ops 对戏（可选）或 演出")
    elif not run["claimed"]:
        phase = f"{OUTCOME_LABELS[run['outcome']]}，工资待领 → theater_ops 领薪"
    else:
        phase = "今晚已谢幕，明晚再试镜"
    return (
        f"«小橘小剧场 · {state.get('setlist') or '未命名专场'}\n"
        f"{phase}\n"
        f"小橘好感：{score}/100 · {tier}{' · 头粉：好感×2' if head else ''}\n"
        "侧厅编剧社常开 → theater_ops 编剧社（投稿潮闻/故事，稿费待她后台采纳）。\n"
        "试镜只在她当晚 stage 专场开放；剧场上工不代替 bar_ops work 考勤。»"
    )


async def _cmd_audition(conn: aiosqlite.Connection, s: dict) -> str:
    state = await _require_stage()
    run = await _run(conn, s["id"])
    if run:
        raise ValueError("今晚已经试过镜了。按当前状态继续对戏、演出或领薪；一天只能完成一场。")
    await energy.spend(conn, s["id"], config.THEATER_AUDITION_ENERGY, action="小剧场试镜")
    role_key, label, line = random.choice(ROLES)
    head = await _head_fan(conn, s["id"])
    await conn.execute(
        """INSERT INTO star_theater_runs
           (steward_id, day, role_key, role_label, play_title, head_fan, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (s["id"], _day(), role_key, label, state.get("setlist") or "未命名专场", int(head), db.now()),
    )
    await conn.commit()
    return (
        f"«试镜入选：{label}\n{line}\n"
        f"- {config.THEATER_AUDITION_ENERGY} 精力。"
        f"{'你是今晚应援榜头粉：本场好感获取×2。' if head else ''}\n"
        "下一步：theater_ops 对戏（可选，-3精力、更稳）或 theater_ops 演出。»"
    )


async def _cmd_rehearse(conn: aiosqlite.Connection, s: dict) -> str:
    await _require_stage()
    run = await _run(conn, s["id"])
    if not run:
        raise ValueError("先 theater_ops 试镜，拿到今晚的岗位后才能对戏。")
    if run["outcome"]:
        raise ValueError("这场已经演完，不能再补排。去 theater_ops 领薪。")
    if run["rehearsed"]:
        raise ValueError("今晚已经对过戏了，直接 theater_ops 演出。")
    await energy.spend(conn, s["id"], config.THEATER_REHEARSE_ENERGY, action="小剧场对戏")
    gain = await _add_affinity(conn, s["id"], 2, bool(run["head_fan"]))
    await conn.execute(
        "UPDATE star_theater_runs SET rehearsed=1, rehearsal_affinity=? WHERE steward_id=? AND day=?",
        (gain, s["id"], _day()),
    )
    await conn.commit()
    return (
        f"«她把耳返递给你，带你走了一遍最后的转场。\n"
        f"- {config.THEATER_REHEARSE_ENERGY} 精力 · 小橘好感 +{gain}"
        f"{'（头粉双倍）' if run['head_fan'] else ''}。\n"
        "这场演出更稳了 → theater_ops 演出。»"
    )


async def _cmd_perform(conn: aiosqlite.Connection, s: dict) -> str:
    await _require_stage()
    run = await _run(conn, s["id"])
    if not run:
        raise ValueError("先 theater_ops 试镜。")
    if run["outcome"]:
        raise ValueError("这场已经结算完成，去 theater_ops 领薪。")
    await energy.spend(conn, s["id"], config.THEATER_SHOW_ENERGY, action="小剧场演出")
    score = await _affinity(conn, s["id"])
    roll = random.random()
    miss_cutoff = 0.05 if run["rehearsed"] else 0.15
    great_cutoff = 0.35 if run["rehearsed"] else 0.25
    outcome = "miss" if roll < miss_cutoff else ("great" if roll < great_cutoff else "normal")
    if score >= 50 and outcome == "miss":
        outcome = "normal"
    affinity_raw = {"miss": 0, "normal": 2, "great": 5}[outcome]
    affinity_gain = await _add_affinity(conn, s["id"], affinity_raw, bool(run["head_fan"]))
    payout = _pay(score, outcome)
    encore = 20 if score >= 80 and outcome == "great" else 0
    weekly = 0
    if score >= 100 and outcome == "great":
        week = _day() // 7
        exists = await (await conn.execute(
            "SELECT 1 FROM star_theater_weekly WHERE steward_id=? AND week=?", (s["id"], week)
        )).fetchone()
        if not exists:
            weekly = 50
            await conn.execute(
                "INSERT INTO star_theater_weekly (steward_id, week) VALUES (?,?)", (s["id"], week)
            )
    payout += encore + weekly
    standing_gain = {"miss": 0, "normal": 1, "great": 2}[outcome]
    mist_gain = {"miss": 1, "normal": 2, "great": 3}[outcome]
    await conn.execute(
        """UPDATE star_theater_runs SET outcome=?, payout=?, standing_gain=?, mist_wit_gain=?,
           performance_affinity=? WHERE steward_id=? AND day=?""",
        (outcome, payout, standing_gain, mist_gain, affinity_gain, s["id"], _day()),
    )
    extras = []
    if encore:
        extras.append("固定班底安可 +20票")
    if weekly:
        extras.append("压轴搭档周奖金 +50票")
    from . import cloth as cloth_mod
    dye = await cloth_mod.maybe_event_dye(conn, s["id"], "star")
    echo = await cloth_mod.try_echo(conn, s, "theater")
    extra_lines = ""
    if dye:
        extra_lines += f"\n{dye}"
    if echo:
        extra_lines += f"\n{echo}"
    await conn.commit()
    return (
        f"«{run['play_title']} · {run['role_label']}\n{OUTCOME_COPY[outcome]}\n"
        f"结果：{OUTCOME_LABELS[outcome]} · 待领 {payout}票 · 档信+{standing_gain} · 雾智+{mist_gain}"
        f" · 小橘好感+{affinity_gain}{'（头粉双倍）' if run['head_fan'] and affinity_gain else ''}"
        f"{' · ' + '、'.join(extras) if extras else ''}{extra_lines}\n"
        "→ theater_ops 领薪。»"
    )


async def _cmd_claim(conn: aiosqlite.Connection, s: dict) -> str:
    run = await _pending_run(conn, s["id"])
    if not run or not run["outcome"]:
        raise ValueError("还没有可领的演出工资。先 theater_ops 试镜 → 演出。")
    if run["claimed"]:
        raise ValueError("今晚的工资已经领过了。")
    await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (run["payout"], s["id"]))
    await survival.bump(conn, s["id"], standing=run["standing_gain"], mist_wit=run["mist_wit_gain"])
    await conn.execute(
        "UPDATE star_theater_runs SET claimed=1 WHERE steward_id=? AND day=?", (s["id"], run["day"])
    )
    await db.add_chronicle(
        "theater", f"{s['name']} 在小橘专场担任{run['role_label']}，{OUTCOME_LABELS[run['outcome']]}。",
        s["id"], conn=conn,
    )
    await conn.commit()
    return (
        f"«谢幕领薪：+{run['payout']}票 · 档信+{run['standing_gain']} · 雾智+{run['mist_wit_gain']}。\n"
        "工资已经进袋；节目单收进了今晚的舞台记录。明晚她再开专场时，可以重新试镜。»"
    )


def _split_cmd(command: str) -> tuple[str, str]:
    raw = (command or "").strip()
    if not raw:
        return "", ""
    parts = raw.split(None, 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def _parse_submit(rest: str) -> tuple[str, str, str]:
    text = (rest or "").strip()
    if not text:
        raise ValueError(
            "用法: theater_ops 投稿 标题 | 正文\n"
            "也可：投稿 潮闻 标题 | 正文 · 投稿 故事 标题 | 正文（建议类型，最终她定）"
        )
    pitch = ""
    first, more = (text.split(None, 1) + [""])[:2]
    if first in ("故事", "story", "人物故事"):
        pitch = "story"
        text = more.strip()
    elif first in ("潮闻", "tale", "潮闻故事"):
        pitch = "tale"
        text = more.strip()
    if not text:
        raise ValueError("指定了故事或潮闻之后，还要写标题和正文。例子：投稿 潮闻 岸上旧收音机 | 第一幕……")
    if "|" in text:
        title, body = text.split("|", 1)
    elif "\n" in text:
        title, body = text.split("\n", 1)
    else:
        raise ValueError("标题和正文用 | 或换行分开。例子：投稿 岸上旧收音机 | 第一幕……")
    title = " ".join(title.strip().split())
    body = body.strip()
    if len(title) < config.THEATER_SCRIPT_TITLE_MIN:
        raise ValueError(f"标题至少 {config.THEATER_SCRIPT_TITLE_MIN} 个字")
    if len(title) > config.THEATER_SCRIPT_TITLE_MAX:
        raise ValueError(f"标题最多 {config.THEATER_SCRIPT_TITLE_MAX} 个字")
    if len(body) < config.THEATER_SCRIPT_BODY_MIN:
        raise ValueError(f"正文太短（至少 {config.THEATER_SCRIPT_BODY_MIN} 字）。编剧社收稿，不是扔一张便签。")
    if len(body) > config.THEATER_SCRIPT_BODY_MAX:
        raise ValueError(f"正文最多 {config.THEATER_SCRIPT_BODY_MAX} 字。先写成能让她一次读完的稿。")
    return pitch, title, body


def _script_line(row) -> str:
    pitch = PITCH_LABELS.get(row["pitch"] or "", "")
    pitch_bit = f"（投{pitch}）" if pitch else "（不指定）"
    status = SCRIPT_STATUS_LABELS.get(row["status"], row["status"])
    extra = ""
    if row["status"] == "accepted":
        kind = PITCH_LABELS.get(row["accepted_as"] or "", row["accepted_as"] or "")
        extra = f"为{kind} · 稿费 {int(row['payout'])}票"
    elif row["status"] == "rejected" and row["note"]:
        extra = f"：{row['note']}"
    return f"#{row['id']} 《{row['title']}》{pitch_bit}{status}{extra}"


async def _cmd_guild(conn: aiosqlite.Connection, s: dict) -> str:
    rows = await (await conn.execute(
        """SELECT id, title, pitch, status, accepted_as, payout, note, created_at
           FROM star_scripts WHERE steward_id=? ORDER BY id DESC LIMIT 12""",
        (s["id"],),
    )).fetchall()
    pending = sum(1 for r in rows if r["status"] == "pending")
    lines = [
        "«小橘小剧场 · 编剧社",
        "侧厅常开，不需今晚专场。把潮闻或人物故事的稿投进来，小橘在 /star-owner 后台看。",
        f"采纳为故事给稿费 {config.THEATER_SCRIPT_STORY_PAY} 票；采纳为潮闻给 {config.THEATER_SCRIPT_TALE_PAY} 票。退稿不给钱。",
        "不是 tale_ops accept / story_ops start（那是玩已有篇章）；也不是 theater_ops 领薪（那是专场工资）。",
        f"待审最多 {config.THEATER_SCRIPT_PENDING_MAX} 篇。标题和正文用 | 分开。",
        "用法：theater_ops 投稿 岸上旧收音机 | 第一幕……",
        "      theater_ops 投稿 潮闻 缺了一页的相册 | ……",
        "      theater_ops 撤回 12",
        f"你的稿（待审 {pending}/{config.THEATER_SCRIPT_PENDING_MAX}）：",
    ]
    if rows:
        lines.extend("  " + _script_line(r) for r in rows)
    else:
        lines.append("  还没投过。")
    lines.append("»")
    from . import cloth as cloth_mod
    echo = await cloth_mod.try_echo(conn, s, "theater")
    await conn.commit()
    text = "\n".join(lines)
    return f"{text}\n{echo}" if echo else text


async def _cmd_submit(conn: aiosqlite.Connection, s: dict, rest: str) -> str:
    pitch, title, body = _parse_submit(rest)
    pending = await (await conn.execute(
        "SELECT COUNT(*) FROM star_scripts WHERE steward_id=? AND status='pending'",
        (s["id"],),
    )).fetchone()
    if int(pending[0]) >= config.THEATER_SCRIPT_PENDING_MAX:
        raise ValueError(
            f"待审已经 {config.THEATER_SCRIPT_PENDING_MAX} 篇。等她看完，或 theater_ops 撤回 编号 再投。"
        )
    cur = await conn.execute(
        """INSERT INTO star_scripts (steward_id, title, body, pitch, status, created_at)
           VALUES (?,?,?,?, 'pending', ?)""",
        (s["id"], title, body, pitch, db.now()),
    )
    script_id = cur.lastrowid
    await conn.commit()
    hint = f"你建议做成{PITCH_LABELS[pitch]}；最终她定。" if pitch else "没指定故事或潮闻，她自己看。"
    return (
        f"«稿已进编剧社 #{script_id} 《{title}》\n"
        f"{hint}\n"
        f"故事稿费 {config.THEATER_SCRIPT_STORY_PAY} · 潮闻稿费 {config.THEATER_SCRIPT_TALE_PAY}。"
        "要等小橘后台点采纳才入账，不是 theater_ops 领薪。\n"
        "看自己的稿：theater_ops 编剧社。»"
    )


async def _cmd_withdraw(conn: aiosqlite.Connection, s: dict, rest: str) -> str:
    token = (rest or "").strip()
    if not token.isdigit():
        raise ValueError("用法: theater_ops 撤回 编号 — 编号在 theater_ops 编剧社 里看。")
    script_id = int(token)
    row = await (await conn.execute(
        "SELECT id, title, status FROM star_scripts WHERE id=? AND steward_id=?",
        (script_id, s["id"]),
    )).fetchone()
    if not row:
        raise ValueError("没有这篇稿，或不是你投的。theater_ops 编剧社 看自己的编号。")
    if row["status"] != "pending":
        raise ValueError(f"#{script_id} 《{row['title']}》已经是{SCRIPT_STATUS_LABELS.get(row['status'], row['status'])}，不能撤回。")
    await conn.execute(
        "UPDATE star_scripts SET status='withdrawn', decided_at=? WHERE id=?",
        (db.now(), script_id),
    )
    await conn.commit()
    return f"«已撤回 #{script_id} 《{row['title']}》。侧厅空出一格待审。»"


def _script_to_dict(row) -> dict:
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "title": row["title"],
        "body": row["body"],
        "pitch": row["pitch"] or "",
        "pitch_label": PITCH_LABELS.get(row["pitch"] or "", "不指定"),
        "status": row["status"],
        "status_label": SCRIPT_STATUS_LABELS.get(row["status"], row["status"]),
        "accepted_as": row["accepted_as"] or "",
        "accepted_label": PITCH_LABELS.get(row["accepted_as"] or "", ""),
        "payout": int(row["payout"] or 0),
        "note": row["note"] or "",
        "created_at": int(row["created_at"] or 0),
        "decided_at": int(row["decided_at"] or 0),
    }


async def owner_pending_scripts(limit: int = 40) -> list[dict]:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """SELECT sc.id, s.name, sc.title, sc.body, sc.pitch, sc.status, sc.accepted_as,
                      sc.payout, sc.note, sc.created_at, sc.decided_at
               FROM star_scripts sc JOIN stewards s ON s.id = sc.steward_id
               WHERE sc.status='pending' ORDER BY sc.created_at ASC LIMIT ?""",
            (limit,),
        )).fetchall()
    return [_script_to_dict(r) for r in rows]


async def owner_recent_scripts(limit: int = 12) -> list[dict]:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """SELECT sc.id, s.name, sc.title, sc.body, sc.pitch, sc.status, sc.accepted_as,
                      sc.payout, sc.note, sc.created_at, sc.decided_at
               FROM star_scripts sc JOIN stewards s ON s.id = sc.steward_id
               WHERE sc.status IN ('accepted', 'rejected')
               ORDER BY sc.decided_at DESC, sc.id DESC LIMIT ?""",
            (limit,),
        )).fetchall()
    return [_script_to_dict(r) for r in rows]


async def owner_decide_script(script_id: int, action: str, note: str = "") -> dict:
    action = (action or "").strip().lower()
    if action in ("story", "故事", "人物故事"):
        accepted_as = "story"
        payout = config.THEATER_SCRIPT_STORY_PAY
    elif action in ("tale", "潮闻", "潮闻故事"):
        accepted_as = "tale"
        payout = config.THEATER_SCRIPT_TALE_PAY
    elif action in ("reject", "退稿", "ignore"):
        accepted_as = ""
        payout = 0
    else:
        raise ValueError("只能：采纳为故事 / 采纳为潮闻 / 退稿")
    note = (note or "").strip()[:80]
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            """SELECT sc.id, sc.steward_id, sc.title, sc.status, s.name
               FROM star_scripts sc JOIN stewards s ON s.id = sc.steward_id
               WHERE sc.id=?""",
            (script_id,),
        )).fetchone()
        if not row:
            raise ValueError("没有这篇稿")
        if row["status"] != "pending":
            raise ValueError("这篇已经处理过了")
        if accepted_as:
            await conn.execute(
                "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                (payout, row["steward_id"]),
            )
            await conn.execute(
                """UPDATE star_scripts SET status='accepted', accepted_as=?, payout=?,
                   note=?, decided_at=? WHERE id=?""",
                (accepted_as, payout, note, db.now(), script_id),
            )
            kind = PITCH_LABELS[accepted_as]
            text = f"{star.STAR_NAME}采纳了 {row['name']} 的稿《{row['title']}》为{kind}，稿费 {payout} 票"
            await db.add_chronicle("theater", text, row["steward_id"], conn=conn)
            await conn.commit()
            return {"ok": True, "msg": text, "payout": payout}
        await conn.execute(
            """UPDATE star_scripts SET status='rejected', accepted_as='', payout=0,
               note=?, decided_at=? WHERE id=?""",
            (note, db.now(), script_id),
        )
        await conn.commit()
        extra = f"：{note}" if note else "。"
        return {"ok": True, "msg": f"已退稿《{row['title']}》{extra}".rstrip("。") + "。", "payout": 0}


async def writers_view(conn: aiosqlite.Connection, s: dict[str, Any]) -> dict[str, Any]:
    """给 /island 编剧社用。数值仍走 theater_ops，这里只摊开能点的。"""
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """SELECT id, title, pitch, status, accepted_as, payout, note
           FROM star_scripts WHERE steward_id=? ORDER BY id DESC LIMIT 12""",
        (s["id"],),
    )).fetchall()
    pending = sum(1 for r in rows if r["status"] == "pending")
    scripts: list[dict[str, Any]] = []
    for row in rows:
        extra = ""
        if row["status"] == "accepted":
            kind = PITCH_LABELS.get(row["accepted_as"] or "", row["accepted_as"] or "")
            extra = f"为{kind} · 稿费 {int(row['payout'] or 0)}票"
        elif row["status"] == "rejected" and row["note"]:
            extra = str(row["note"])
        scripts.append({
            "id": int(row["id"]),
            "title": row["title"],
            "pitch": PITCH_LABELS.get(row["pitch"] or "", "不指定"),
            "status": SCRIPT_STATUS_LABELS.get(row["status"], row["status"]),
            "status_key": row["status"],
            "can_withdraw": row["status"] == "pending",
            "note": extra or SCRIPT_STATUS_LABELS.get(row["status"], row["status"]),
            "detail": extra or "待审的稿能撤回。稿费要她后台采纳才入账，不是领薪。",
        })
    can_submit = pending < config.THEATER_SCRIPT_PENDING_MAX
    return {
        "name": "编剧社",
        "line": f"侧厅常开 · 待审 {pending}/{config.THEATER_SCRIPT_PENDING_MAX}",
        "tabs": [{"key": "desk", "label": "收稿台", "badge": "投" if can_submit else ""}],
        "scripts": scripts,
        "can_submit": can_submit,
        "submit_note": (
            f"待审已经 {config.THEATER_SCRIPT_PENDING_MAX} 篇。等她看完，或先撤回一篇。"
            if not can_submit
            else (
                f"标题至少 {config.THEATER_SCRIPT_TITLE_MIN} 字，正文至少 "
                f"{config.THEATER_SCRIPT_BODY_MIN} 字。故事稿费 {config.THEATER_SCRIPT_STORY_PAY}，"
                f"潮闻 {config.THEATER_SCRIPT_TALE_PAY}。不是接现有篇章，也不是领薪。"
            )
        ),
        "pending": pending,
        "pending_max": config.THEATER_SCRIPT_PENDING_MAX,
        "story_pay": config.THEATER_SCRIPT_STORY_PAY,
        "tale_pay": config.THEATER_SCRIPT_TALE_PAY,
        "title_min": config.THEATER_SCRIPT_TITLE_MIN,
        "body_min": config.THEATER_SCRIPT_BODY_MIN,
    }


async def hall_view(conn: aiosqlite.Connection, s: dict[str, Any]) -> dict[str, Any]:
    """给 /island 剧场看台用。数值仍走 theater_ops，这里只摊开能点的。"""
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT venue, venue_date, setlist FROM star_state WHERE id=1"
    )).fetchone()
    venue = (row["venue"] if row else "") or ""
    venue_date = int(row["venue_date"] if row else 0) or 0
    setlist = (row["setlist"] if row else "") or "未命名专场"
    open_now = venue == "stage" and venue_date == _day()
    score = await _affinity(conn, s["id"])
    head = await _head_fan(conn, s["id"])
    run = await _run(conn, s["id"])
    pending = await _pending_run(conn, s["id"])
    energy_now = int(s.get("energy") or 0)
    tier, _ = _tier(score)
    if not open_now:
        phase = "今晚没专场"
    elif not run:
        phase = "还没试镜"
    elif not run["outcome"]:
        phase = f"已入选{run['role_label']}" + ("，已对戏" if run["rehearsed"] else "")
    elif not run["claimed"]:
        phase = f"{OUTCOME_LABELS[run['outcome']]}，工资待领"
    else:
        phase = "今晚已谢幕"
    can_audition = bool(open_now and not run and energy_now >= config.THEATER_AUDITION_ENERGY)
    can_rehearse = bool(
        open_now and run and not run["outcome"] and not run["rehearsed"]
        and energy_now >= config.THEATER_REHEARSE_ENERGY
    )
    can_perform = bool(
        open_now and run and not run["outcome"] and energy_now >= config.THEATER_SHOW_ENERGY
    )
    can_claim = bool(pending and pending["outcome"] and not pending["claimed"])
    if not open_now:
        audition_note = "小橘今晚没有在小剧场开专场。"
        rehearse_note = audition_note
        perform_note = audition_note
    else:
        audition_note = (
            "今晚已经试过镜了。"
            if run
            else (
                f"精力不够，试镜要 {config.THEATER_AUDITION_ENERGY}"
                if energy_now < config.THEATER_AUDITION_ENERGY
                else f"耗 {config.THEATER_AUDITION_ENERGY} 精力，抽今晚岗位。"
            )
        )
        if not run:
            rehearse_note = "先试镜，拿到岗位才能对戏。"
            perform_note = "先试镜。"
        elif run["outcome"]:
            rehearse_note = "这场已经演完，去领薪。"
            perform_note = "这场已经结算，去领薪。"
        else:
            rehearse_note = (
                "今晚已经对过戏了。"
                if run["rehearsed"]
                else (
                    f"精力不够，对戏要 {config.THEATER_REHEARSE_ENERGY}"
                    if energy_now < config.THEATER_REHEARSE_ENERGY
                    else f"耗 {config.THEATER_REHEARSE_ENERGY} 精力，演出更稳。"
                )
            )
            perform_note = (
                f"精力不够，演出要 {config.THEATER_SHOW_ENERGY}"
                if energy_now < config.THEATER_SHOW_ENERGY
                else f"耗 {config.THEATER_SHOW_ENERGY} 精力，按岗位和对戏结算。"
            )
    claim_note = (
        f"待领 {int(pending['payout'] or 0)} 票。忘了领也不会丢。"
        if can_claim
        else "还没有可领的演出工资。"
    )
    jobs = [
        {
            "id": "audition",
            "cmd": "试镜",
            "name": "试镜",
            "emoji": "🎬",
            "can_act": can_audition,
            "note": audition_note,
            "detail": audition_note + "不替代酒吧考勤。",
        },
        {
            "id": "rehearse",
            "cmd": "对戏",
            "name": "对戏",
            "emoji": "🎭",
            "can_act": can_rehearse,
            "note": rehearse_note,
            "detail": rehearse_note,
        },
        {
            "id": "perform",
            "cmd": "演出",
            "name": "演出",
            "emoji": "🌟",
            "can_act": can_perform,
            "note": perform_note,
            "detail": perform_note,
        },
        {
            "id": "claim",
            "cmd": "领薪",
            "name": "领薪",
            "emoji": "🎫",
            "can_act": can_claim,
            "note": claim_note,
            "detail": claim_note + "稿费不是领薪。",
        },
    ]
    if can_claim:
        spoken = f"这场演完了。去领薪，{int(pending['payout'] or 0)} 票。"
    elif not open_now:
        spoken = "今晚没专场。侧厅编剧社还开着。"
    elif not run:
        spoken = f"今晚是「{setlist}」。先试镜。"
    elif run["outcome"]:
        spoken = "今晚已谢幕。"
    elif run["rehearsed"]:
        spoken = f"你是{run['role_label']}。可以对戏过了，上场吧。"
    else:
        spoken = f"你是{run['role_label']}。要对戏，还是直接上场？"
    return {
        "name": "剧场看台",
        "speaker": "小橘",
        "title": "小橘",
        "line": spoken,
        "open": open_now,
        "tabs": [
            {"key": "board", "label": "看板", "badge": "开" if open_now else ""},
            {"key": "work", "label": "上场", "badge": "领" if can_claim else ("演" if can_perform else "")},
        ],
        "board": {
            "title": setlist if open_now else "今晚没专场",
            "phase": phase,
            "affinity": score,
            "tier": tier,
            "head_fan": head,
            "role": (run["role_label"] if run else ""),
            "note": (
                f"{phase}。小橘好感 {score}/100 · {tier}"
                + (" · 头粉好感×2" if head else "")
                + "。打赏小橘仍去上手页。"
            ),
        },
        "jobs": jobs,
        "can_audition": can_audition,
        "can_rehearse": can_rehearse,
        "can_perform": can_perform,
        "can_claim": can_claim,
    }


async def theater_ops(key_id: int, command: str) -> str:
    cmd = (command or "").strip()
    first, rest = _split_cmd(cmd)
    verb = first.lower()
    s = await require_steward(key_id)
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        if verb in ("", "看板", "status", "board"):
            return await _cmd_board(conn, s)
        if verb in ("help", "?", "帮助"):
            return THEATER_HELP
        if verb in ("编剧社", "guild", "desk", "稿件", "scripts", "manuscripts"):
            return await _cmd_guild(conn, s)
        if verb in ("投稿", "submit", "pitch"):
            return await _cmd_submit(conn, s, rest)
        if verb in ("撤回", "withdraw"):
            return await _cmd_withdraw(conn, s, rest)
        if verb in ("试镜", "audition"):
            return await _cmd_audition(conn, s)
        if verb in ("对戏", "rehearse"):
            return await _cmd_rehearse(conn, s)
        if verb in ("演出", "perform", "show"):
            return await _cmd_perform(conn, s)
        if verb in ("领薪", "claim", "pay"):
            return await _cmd_claim(conn, s)
        if verb in ("关系", "affinity"):
            score = await _affinity(conn, s["id"])
            head = await _head_fan(conn, s["id"])
            tier, _ = _tier(score)
            return (
                f"«小橘舞台好感：{score}/100 · {tier}\n"
                f"{'头粉：好感获取×2，演出当天锁定；不翻倍工资。' if head else '不是当前头粉：star_ops 应援榜 可看第一名。'}\n"
                "好感来自对戏与演出；满50保底平场，满80满堂彩有安可奖金，满100解锁压轴搭档周奖金。»"
            )
    raise ValueError(f"未知 theater 指令: {command}\n{THEATER_HELP}")

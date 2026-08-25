"""小橘小剧场：单人试镜、对戏、演出、领薪与舞台好感。"""

from __future__ import annotations

import random

import aiosqlite

from . import config, db, energy, star, survival
from .game import require_steward


THEATER_HELP = """theater_ops 子命令（整句写进 command）：
  看板 / status — 看今晚小橘专场、自己的好感和可演场次；空 command 也是看板
  试镜 — 耗2精力，抽取本场围绕小橘的岗位；一天只能完成一场
  对戏 — 已试镜后可选，耗3精力，成功给舞台好感并让演出更稳
  演出 — 已试镜后耗8精力，按岗位、对戏与随机结果结算待领工资
  领薪 — 把已结算的票、档信、雾智入账；忘了领也不会丢
  关系 — 单看小橘舞台好感与头粉双倍状态
  只在小橘当晚开 stage 小剧场专场时开放；不替代 bar_ops work 的考勤。
  例子：看板 · 试镜 · 对戏 · 演出 · 领薪。
  头粉=star_ops 应援榜第一名；头粉好感获取和每日上限翻倍，不翻倍工资。"""

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
        "只在她当晚 stage 专场开放；剧场上工不代替 bar_ops work 考勤。»"
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
    await conn.commit()
    extras = []
    if encore:
        extras.append("固定班底安可 +20票")
    if weekly:
        extras.append("压轴搭档周奖金 +50票")
    return (
        f"«{run['play_title']} · {run['role_label']}\n{OUTCOME_COPY[outcome]}\n"
        f"结果：{OUTCOME_LABELS[outcome]} · 待领 {payout}票 · 档信+{standing_gain} · 雾智+{mist_gain}"
        f" · 小橘好感+{affinity_gain}{'（头粉双倍）' if run['head_fan'] and affinity_gain else ''}"
        f"{' · ' + '、'.join(extras) if extras else ''}\n"
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


async def theater_ops(key_id: int, command: str) -> str:
    cmd = (command or "").strip()
    verb = cmd.lower()
    s = await require_steward(key_id)
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        if verb in ("", "看板", "status", "board"):
            return await _cmd_board(conn, s)
        if verb in ("help", "?", "帮助"):
            return THEATER_HELP
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

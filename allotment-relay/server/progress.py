"""成就称呼 + 等级里程碑奖励。

等级称号仍由 ranks.py 按累计入账给（新客/岸民/份地手…）。
这里的称呼是做事解锁、可佩戴的外号；升级礼按档位自动发，花掉的票不降级也不收回。
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Awaitable, Callable

import aiosqlite

from . import config, db
from .catalog import item_label

CheckFn = Callable[[aiosqlite.Connection, dict[str, Any]], Awaitable[bool]]

_NOTE: ContextVar[str] = ContextVar("progress_note", default="")


def take_note() -> str:
    note = _NOTE.get()
    if note:
        _NOTE.set("")
    return note


def attach_note(text: str) -> str:
    note = take_note()
    if not note:
        return text
    if not text:
        return note
    return f"{note}\n{text}"


def _push_note(line: str) -> None:
    line = (line or "").strip()
    if not line:
        return
    prev = _NOTE.get()
    _NOTE.set(f"{prev}\n{line}".strip() if prev else line)


async def _exists(conn: aiosqlite.Connection, sql: str, *args: Any) -> bool:
    row = await (await conn.execute(sql, args)).fetchone()
    if row is None:
        return False
    val = row[0]
    return bool(val)


async def _check_sower(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return await _exists(
        conn,
        "SELECT 1 FROM parcels WHERE steward_id=? AND (crop IS NOT NULL OR planted_at IS NOT NULL) LIMIT 1",
        s["id"],
    )


async def _check_harvester(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return await _exists(
        conn,
        "SELECT 1 FROM chronicle WHERE actor_id=? AND action='gather' LIMIT 1",
        s["id"],
    )


async def _check_hut(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return bool(s.get("hut_built"))


async def _check_barkeep(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return await _exists(
        conn,
        "SELECT 1 FROM bar_skills WHERE steward_id=? AND shift_count>=1",
        s["id"],
    )


async def _check_dish(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    row = await (await conn.execute(
        "SELECT COUNT(*) FROM bar_shifts WHERE steward_id=? AND job='dishwasher'",
        (s["id"],),
    )).fetchone()
    return int(row[0] or 0) >= 8


async def _check_scrump(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return await _exists(
        conn,
        "SELECT 1 FROM chronicle WHERE actor_id=? AND action='scrump' LIMIT 1",
        s["id"],
    )


async def _check_busted(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return await _exists(
        conn,
        """
        SELECT 1 FROM steward_undertide
        WHERE steward_id=? AND (jail_state!='' OR busted_count>=5)
        """,
        s["id"],
    )


async def _check_boat(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return bool(s.get("boat_key"))


async def _check_voyager(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return await _exists(
        conn,
        "SELECT 1 FROM chronicle WHERE actor_id=? AND action='voyage' LIMIT 1",
        s["id"],
    )


async def _check_barn(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return bool(s.get("barn_built"))


async def _check_pen(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return await _exists(
        conn, "SELECT 1 FROM fish_pens WHERE steward_id=? LIMIT 1", s["id"]
    )


async def _check_cook(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return await _exists(
        conn,
        "SELECT 1 FROM chronicle WHERE actor_id=? AND action='kitchen' LIMIT 1",
        s["id"],
    )


async def _check_helper(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return await _exists(
        conn, "SELECT 1 FROM assist_log WHERE helper_id=? LIMIT 1", s["id"]
    )


async def _check_well(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return await _exists(
        conn,
        "SELECT 1 FROM steward_undertide WHERE steward_id=? AND (access=1 OR well_hint=1)",
        s["id"],
    )


async def _check_mascot(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return bool(s.get("mascot_name"))


async def _check_eatery(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return bool(s.get("eatery_open"))


async def _check_giver(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return await _exists(
        conn,
        "SELECT 1 FROM chronicle WHERE actor_id=? AND action='gift' LIMIT 1",
        s["id"],
    )


async def _check_packed(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    return int(s.get("cabinet_extra") or 0) > 0


ACHIEVEMENTS: dict[str, dict[str, Any]] = {
    "sower": {
        "name": "播手",
        "hint": "份地上播过种",
        "aliases": ("下种人", "土里报到"),
        "check": _check_sower,
    },
    "harvester": {
        "name": "满篮",
        "hint": "收过一茬",
        "aliases": ("收成手", "篮子有货"),
        "check": _check_harvester,
    },
    "hut": {
        "name": "棚主",
        "hint": "搭过岸畔小屋",
        "aliases": ("有屋的", "岸上有窝"),
        "check": _check_hut,
    },
    "barkeep": {
        "name": "店伙",
        "hint": "酒吧上过工",
        "aliases": ("荔栀的人", "荔栀手底下"),
        "check": _check_barkeep,
    },
    "dish": {
        "name": "控碗",
        "hint": "洗碗满 8 班",
        "aliases": ("洗碗工", "手泡皱了"),
        "check": _check_dish,
    },
    "scrump": {
        "name": "逾篱客",
        "hint": "偷菜得手过",
        "aliases": ("逾篱手", "顺手牵菜"),
        "check": _check_scrump,
    },
    "busted": {
        "name": "潮下客",
        "hint": "潮下收监过（案底满 5）",
        "aliases": ("坐过的", "潮下房客"),
        "check": _check_busted,
    },
    "boat": {
        "name": "船户",
        "hint": "买过船",
        "aliases": ("有船的", "码头有位"),
        "check": _check_boat,
    },
    "voyager": {
        "name": "过海客",
        "hint": "出过海并归港",
        "aliases": ("归港人", "海放人了"),
        "check": _check_voyager,
    },
    "barn": {
        "name": "饲手",
        "hint": "建过畜栏",
        "aliases": ("养牲口的", "圈里有呼吸"),
        "check": _check_barn,
    },
    "pen": {
        "name": "排主",
        "hint": "搭过渔排",
        "aliases": ("渔排主", "鱼的房东"),
        "check": _check_pen,
    },
    "cook": {
        "name": "灶手",
        "hint": "做过菜",
        "aliases": ("灶边人", "锅没投诉"),
        "check": _check_cook,
    },
    "helper": {
        "name": "邻锄",
        "hint": "帮邻居打理过",
        "aliases": ("爱帮忙的", "闲得去帮"),
        "check": _check_helper,
    },
    "well": {
        "name": "井口客",
        "hint": "下过枯井",
        "aliases": ("井口过客", "另一只鞋还在"),
        "check": _check_well,
    },
    "mascot": {
        "name": "有伴",
        "hint": "认领过吉祥物",
        "aliases": ("带活物的", "跟了个活的"),
        "check": _check_mascot,
    },
    "eatery": {
        "name": "馆主",
        "hint": "开过岸畔小馆",
        "aliases": ("开馆人", "敢开馆"),
        "check": _check_eatery,
    },
    "giver": {
        "name": "散手",
        "hint": "送过别人东西",
        "aliases": ("手松的", "手比口袋松"),
        "check": _check_giver,
    },
    "packed": {
        "name": "柜客",
        "hint": "潮柜扩过容",
        "aliases": ("屯货的", "格还不够"),
        "check": _check_packed,
    },
}

# 里程碑才发，不对每一级。新客起步约 Lv3，从 Lv4 开始。
LEVEL_REWARDS: dict[int, dict[str, Any]] = {
    4: {"tickets": 10, "items": [("seed_kale", 2)], "label": "站稳了"},
    5: {"tickets": 18, "label": "份地手见面礼"},
    8: {"tickets": 28, "cabinet": 1, "label": "潮客的柜子"},
    10: {"tickets": 36, "items": [("wild_mint", 2)], "label": "岸上有味道了"},
    12: {"tickets": 48, "cabinet": 1, "label": "老岸人"},
    16: {"tickets": 64, "label": "盟里有名"},
    20: {"tickets": 88, "items": [("seed_fogpea", 2)], "label": "潮汐老人"},
    25: {"tickets": 120, "label": "岛上的影子"},
    30: {"tickets": 180, "items": [("compost", 4)], "label": "满级"},
}


def achievement_name(key: str) -> str:
    meta = ACHIEVEMENTS.get(key) or {}
    return str(meta.get("name") or key)


def resolve_achievement(token: str) -> str | None:
    raw = (token or "").strip()
    if not raw:
        return None
    low = raw.lower()
    if low in ACHIEVEMENTS:
        return low
    for key, meta in ACHIEVEMENTS.items():
        names = (str(meta.get("name") or ""),) + tuple(meta.get("aliases") or ())
        if raw in names or low in {n.lower() for n in names}:
            return key
    return None


def display_title(steward: dict[str, Any]) -> str:
    from . import ranks as ranks_mod

    worn = (steward.get("worn_title") or "").strip()
    if worn in ACHIEVEMENTS:
        return achievement_name(worn)
    lvl = int(steward.get("level") or ranks_mod.level_from_xp(steward.get("xp") or 0))
    return ranks_mod.title_for_level(lvl)


def sheet_title_line(steward: dict[str, Any]) -> str:
    from . import ranks as ranks_mod

    worn = (steward.get("worn_title") or "").strip()
    shown = display_title(steward)
    if worn in ACHIEVEMENTS:
        return f"称呼: {shown}（steward_ops 称呼 卸 改回等级称号）"
    rank = ranks_mod.title_for_level(
        int(steward.get("level") or ranks_mod.level_from_xp(steward.get("xp") or 0))
    )
    return f"称呼: {rank}（等级默认 · steward_ops 成就 / 称呼 名字）"


def format_reward(level: int, spec: dict[str, Any] | None = None) -> str:
    spec = spec or LEVEL_REWARDS.get(level) or {}
    bits: list[str] = []
    tickets = int(spec.get("tickets") or 0)
    if tickets:
        bits.append(f"{tickets}票")
    for item, qty in spec.get("items") or ():
        bits.append(f"{item_label(item)} x{qty}")
    cab = int(spec.get("cabinet") or 0)
    if cab:
        bits.append(f"潮柜+{cab}格")
    label = spec.get("label") or f"Lv{level}"
    body = "、".join(bits) if bits else "纪念"
    return f"Lv{level} {label}（{body}）"


def next_reward_level(current: int) -> int | None:
    for lvl in sorted(LEVEL_REWARDS):
        if lvl > current:
            return lvl
    return None


async def _unlocked_keys(conn: aiosqlite.Connection, steward_id: int) -> set[str]:
    rows = await (await conn.execute(
        "SELECT ach_key FROM steward_achievements WHERE steward_id=?",
        (steward_id,),
    )).fetchall()
    return {r[0] for r in rows}


async def _unlock(
    conn: aiosqlite.Connection, steward: dict[str, Any], key: str
) -> None:
    await conn.execute(
        """
        INSERT OR IGNORE INTO steward_achievements (steward_id, ach_key, unlocked_at)
        VALUES (?,?,?)
        """,
        (steward["id"], key, db.now()),
    )
    name = achievement_name(key)
    await db.add_chronicle(
        "title", f"{steward['name']} 解锁称呼「{name}」", steward["id"], conn=conn
    )
    _push_note(f"称呼解锁：{name}（steward_ops 称呼 {name} 佩戴）")


async def scan_achievements(conn: aiosqlite.Connection, steward: dict[str, Any]) -> int:
    have = await _unlocked_keys(conn, steward["id"])
    gained = 0
    for key, meta in ACHIEVEMENTS.items():
        if key in have:
            continue
        check: CheckFn = meta["check"]
        if await check(conn, steward):
            await _unlock(conn, steward, key)
            gained += 1
    return gained


async def _grant_one(
    conn: aiosqlite.Connection, steward: dict[str, Any], level: int
) -> str | None:
    spec = LEVEL_REWARDS.get(level)
    if not spec:
        return None
    bits: list[str] = []
    tickets = int(spec.get("tickets") or 0)
    if tickets:
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?",
            (tickets, steward["id"]),
        )
        bits.append(f"+{tickets}票")
    for item, qty in spec.get("items") or ():
        await db.add_item(conn, steward["id"], item, int(qty))
        bits.append(f"{item_label(item)} x{qty}")
    cab = int(spec.get("cabinet") or 0)
    if cab:
        cur = await conn.execute(
            "SELECT COALESCE(cabinet_extra, 0) FROM stewards WHERE id=?",
            (steward["id"],),
        )
        extra = int((await cur.fetchone())[0] or 0)
        room = max(0, config.CABINET_SLOTS_MAX - config.CABINET_SLOTS - extra)
        add = min(cab, room)
        if add:
            await conn.execute(
                "UPDATE stewards SET cabinet_extra=cabinet_extra+? WHERE id=?",
                (add, steward["id"]),
            )
            bits.append(f"潮柜+{add}格")
    label = spec.get("label") or f"Lv{level}"
    body = "、".join(bits) if bits else "到了"
    text = f"升级礼 Lv{level} {label}：{body}"
    await db.add_chronicle(
        "level_gift", f"{steward['name']} {text}", steward["id"], conn=conn
    )
    return text


async def grant_level_rewards(conn: aiosqlite.Connection, steward: dict[str, Any]) -> int:
    from . import ranks as ranks_mod

    sid = steward["id"]
    cur = await conn.execute(
        "SELECT COALESCE(xp, 0), COALESCE(reward_level, 0) FROM stewards WHERE id=?",
        (sid,),
    )
    row = await cur.fetchone()
    xp = int(row[0] or 0)
    claimed = int(row[1] or 0)
    level = ranks_mod.level_from_xp(xp)
    if claimed <= 0:
        await conn.execute(
            "UPDATE stewards SET reward_level=? WHERE id=?", (level, sid)
        )
        steward["reward_level"] = level
        return 0
    granted = 0
    while claimed < level:
        nxt = claimed + 1
        msg = await _grant_one(conn, steward, nxt)
        if msg:
            _push_note(msg)
            granted += 1
        claimed = nxt
        await conn.execute(
            "UPDATE stewards SET reward_level=? WHERE id=?", (claimed, sid)
        )
        steward["reward_level"] = claimed
        if int(LEVEL_REWARDS.get(nxt, {}).get("tickets") or 0):
            xp = int((await (await conn.execute(
                "SELECT COALESCE(xp, 0) FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0] or 0)
            level = max(level, ranks_mod.level_from_xp(xp))
    return granted


async def sync(conn: aiosqlite.Connection, steward: dict[str, Any], *, rewards: bool = False) -> None:
    if rewards:
        await grant_level_rewards(conn, steward)
        fresh = await (await conn.execute(
            "SELECT * FROM stewards WHERE id=?", (steward["id"],)
        )).fetchone()
        if fresh is not None:
            steward.update(dict(fresh))
    await scan_achievements(conn, steward)


async def sync_steward(steward: dict[str, Any], *, rewards: bool = False) -> None:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        await sync(conn, steward, rewards=rewards)
        await conn.commit()
        row = await (await conn.execute(
            "SELECT * FROM stewards WHERE id=?", (steward["id"],)
        )).fetchone()
        if row:
            steward.update(dict(row))


async def list_text(steward: dict[str, Any]) -> str:
    from . import ranks as ranks_mod

    await sync_steward(steward, rewards=True)
    s = await db.get_steward_by_id(steward["id"]) or steward
    ranked = ranks_mod.attach_level(s)
    async with db.connect() as conn:
        have = await _unlocked_keys(conn, s["id"])
    worn = (s.get("worn_title") or "").strip()
    lines = [
        ranks_mod.progress_line(ranked["xp"]),
        f"佩戴称呼：{display_title(ranked)}",
        f"已解锁 {len(have)}/{len(ACHIEVEMENTS)}：",
    ]
    for key, meta in ACHIEVEMENTS.items():
        mark = "★" if key in have else "·"
        extra = " ←戴着" if key == worn else ""
        if key in have:
            lines.append(f"  {mark} {meta['name']}{extra}")
        else:
            lines.append(f"  {mark} ？？？（{meta['hint']}）")
    nxt = next_reward_level(ranked["level"])
    if nxt:
        lines.append(f"下一档升级礼：{format_reward(nxt)}")
    else:
        lines.append("升级礼已领到满级。")
    lines.append("佩戴：steward_ops 称呼 逾篱客 · 卸下：steward_ops 称呼 卸")
    return "\n".join(lines)


async def wear(steward: dict[str, Any], token: str) -> str:
    raw = (token or "").strip()
    if not raw or raw.lower() in ("卸", "卸下", "默认", "等级", "off", "none", "clear"):
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET worn_title='' WHERE id=?", (steward["id"],)
            )
            await conn.commit()
        from . import ranks as ranks_mod
        rank = ranks_mod.title_for_level(
            ranks_mod.level_from_xp(int(steward.get("xp") or 0))
        )
        return f"称呼改回等级称号：{rank}"

    key = resolve_achievement(raw)
    if not key:
        raise ValueError(f"没有这个称呼。steward_ops 成就 看已解锁。")
    async with db.connect() as conn:
        have = await _unlocked_keys(conn, steward["id"])
        if key not in have:
            await scan_achievements(conn, steward)
            have = await _unlocked_keys(conn, steward["id"])
            await conn.commit()
        if key not in have:
            raise ValueError(
                f"还没解锁「{achievement_name(key)}」（{ACHIEVEMENTS[key]['hint']}）"
            )
        await conn.execute(
            "UPDATE stewards SET worn_title=? WHERE id=?", (key, steward["id"])
        )
        await conn.commit()
    return f"现在别人看见你是「{achievement_name(key)}」"


async def progress_ops(key_id: int, command: str) -> str:
    from .game import require_steward

    s = await require_steward(key_id, exempt_duty=True)
    parts = (command or "").strip().split()
    verb = parts[0].lower() if parts else "成就"
    rest = " ".join(parts[1:]) if len(parts) > 1 else ""

    if verb in ("成就", "achievements", "titles", "称号", "list", "status"):
        return await list_text(s)
    if verb in ("称呼", "title", "wear", "佩戴"):
        if not rest:
            return await list_text(s)
        return await wear(s, rest)
    if verb in ("卸", "卸下"):
        return await wear(s, "卸")
    if verb in ("领奖", "rewards", "升级礼"):
        return await list_text(s)
    raise ValueError("用法：steward_ops 成就 · steward_ops 称呼 逾篱客 · steward_ops 称呼 卸")

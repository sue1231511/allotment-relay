"""潮生会 — 岛上管事的机构。管理员来办事，不能加入、不能开、不能退。"""
from __future__ import annotations

from typing import Any

from . import bar, db, events, flavor, multi, world
from .catalog import ITEM_NAMES, resolve_item_key, unknown_item_message
from .game import require_steward, _parse_int

ORG_NAME = "潮生会"
CLERK_NAME = "阿簿"
CLERK_KEY = "aboo"

ALIASES = (
    "潮生会", "潮生", "阿簿", "chaoshen", "hui", "aboo", "clerk",
)

JOIN_VERBS = {
    "入", "入会", "加入", "申请", "apply", "join",
    "开", "开会", "立", "found", "create", "open",
    "退", "退会", "leave", "quit",
    "请", "邀", "招", "invite",
    "社", "湾", "船队", "公会",
}

JOIN_REFUSE = (
    f"{ORG_NAME}不是给管理员加入的组织。没有入会、开会、退会。"
    f"你 enroll 上岛那天就已经在册。来这儿是办事：visit_ops 潮生会"
)

CHAOSHEN_HELP = f"""visit_ops 潮生会 子命令（整句写进 command）：
  空 / 问 — 进门问事：本周岛务、考勤、公仓、告示摘要。不是入会。
  周 — 本周目标；周 交 甘蓝 2 推进（和 alliance_ops league contribute 同一目标）
  仓 — 公仓；捐 甘蓝 2 / 取 甘蓝 1（领取 2 票、每日 3 次；和 alliance_ops donate/larder 同一仓）
  告示 — 看告示；贴 标签 正文 发告示；回 编号 正文 回复（同 alliance_ops beacon）
  公物 — 稀有公共物资；领 编号 领取（同 plot_ops commons）
  没有入会 / 开会 / 退会。{ORG_NAME}是岛上管事的机构，上岛时已经在册。
例子：潮生会 · 潮生会 问 · 潮生会 周 · 潮生会 捐 甘蓝 2
容易搞混：steward_ops guild=每日工分轮值，不是入会；alliance_ops board=周目标贡献榜；小橘粉丝团才是入团。"""

_DOOR_LINES = (
    "坐。先报名字。入会？没有这回事。",
    "牌子上写着这周岛上要什么。交到这边，记到簿上。",
    "欠工去酒吧打卡。我这儿只记账，不替荔栀收碗。",
    "公仓进出、告示上墙，都是潮生会的事。你来办事就行。",
)


def is_alias(token: str) -> bool:
    raw = (token or "").strip()
    if not raw:
        return False
    if raw in {"潮生会", "潮生", "阿簿"}:
        return True
    return raw.lower() in {a.lower() for a in ALIASES}


def _join_refuse(verb: str) -> str:
    return JOIN_REFUSE + f"\n（你写的是「{verb}」。没有这条指令。）"


async def _front_desk(key_id: int) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    league = await multi.league_snapshot()
    duty = bar.duty_line(s)
    pulse = await events.public_pulse_snapshot()
    async with db.connect() as conn:
        conn.row_factory = None
        larder_n = (await (await conn.execute(
            "SELECT COUNT(*) FROM larder WHERE quantity > 0"
        )).fetchone())[0]
        larder_sum = (await (await conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM larder WHERE quantity > 0"
        )).fetchone())[0]
        beacon_n = (await (await conn.execute(
            "SELECT COUNT(*) FROM beacons"
        )).fetchone())[0]
        from . import commons as commons_mod
        commons_rows = await commons_mod._active_spawns(conn)
        now = db.now()
        commons_live = sum(1 for r in commons_rows if r["appears_at"] <= now)

    from . import npc as npc_mod
    gift = await npc_mod._daily_visit_gift(s["id"], CLERK_KEY)

    done = "已达成" if league.get("completed") else f"{league['progress']}/{league['target']}"
    door = flavor.pick(_DOOR_LINES)
    lines = [
        f"{ORG_NAME} · 值事{CLERK_NAME}",
        f"{CLERK_NAME}：「{door}」",
        "",
        f"本周岛务：「{league['label']}」{done}",
        f"考勤：{duty}",
        f"公仓：{int(larder_n)} 种货、共 {int(larder_sum)} 份",
        f"告示：{int(beacon_n)} 条",
        f"公物：在架 {commons_live} 件",
    ]
    if pulse:
        kind = "凶" if pulse.get("kind") == "bad" else "吉"
        mins = int(pulse.get("remaining") or 0) // 60
        lines.append(f"全服脉冲：{pulse.get('label')}（{kind}，约 {mins} 分钟）")
    lines.extend([
        "",
        f"潮汐 {world.tide_label(world.current_tide())} · {world.weather_label(world.current_weather())}",
        "办事：visit_ops 潮生会 周 · 潮生会 仓 · 潮生会 告示 · 潮生会 公物",
        "周目标/公仓/告示与 alliance_ops 是同一套，不是第二本账。",
        "不能加入。上岛已在册。",
    ])
    if gift:
        lines.append(gift.strip())
    return "\n".join(lines)


def _resolve_item(token: str) -> str:
    item = resolve_item_key(token)
    if not item:
        raise ValueError(unknown_item_message(token))
    return item


async def chaoshen_ops(key_id: int, command: str = "") -> str:
    raw = (command or "").strip()
    parts = raw.split()
    verb = parts[0] if parts else "问"
    verb_l = verb.lower()

    if verb_l in ("help", "?", "帮助"):
        return CHAOSHEN_HELP
    if verb_l in JOIN_VERBS or verb in JOIN_VERBS:
        raise ValueError(_join_refuse(verb))

    if verb_l in ("", "问", "看", "visit", "status", "事", "问事", "desk"):
        return await _front_desk(key_id)

    if verb_l in ("周", "league", "目标", "周目标"):
        rest = parts[1:]
        if not rest:
            return await multi.league_ops(key_id, "status")
        head = rest[0].lower()
        if head in ("交", "缴", "献", "contribute"):
            if len(rest) < 3:
                raise ValueError("用法：visit_ops 潮生会 周 交 甘蓝 2")
            item = _resolve_item(rest[1])
            qty = _parse_int(rest[2], "数量")
            return await multi.league_ops(key_id, f"contribute {item} {qty}")
        if head in ("board", "榜", "贡献榜"):
            return await multi.league_ops(key_id, "board")
        if head == "status":
            return await multi.league_ops(key_id, "status")
        return await multi.league_ops(key_id, " ".join(rest))

    if verb_l in ("仓", "larder", "公仓", "库"):
        return await multi.alliance_ops(key_id, "larder")

    if verb_l in ("捐", "donate"):
        if len(parts) < 3:
            raise ValueError("用法：visit_ops 潮生会 捐 甘蓝 2")
        item = _resolve_item(parts[1])
        qty = _parse_int(parts[2], "数量")
        return await multi.alliance_ops(key_id, f"donate {item} {qty}")

    if verb_l in ("取", "draw", "领货"):
        if len(parts) < 3:
            raise ValueError("用法：visit_ops 潮生会 取 甘蓝 1")
        item = _resolve_item(parts[1])
        qty = _parse_int(parts[2], "数量")
        return await multi.alliance_ops(key_id, f"draw {item} {qty}")

    if verb_l in ("告示", "beacon", "公告"):
        rest = " ".join(parts[1:]) if len(parts) > 1 else "scan"
        if not rest or rest.lower() in ("scan", "看"):
            rest = "scan"
        from . import game as game_mod
        return await game_mod.beacon_ops(key_id, rest)

    if verb_l in ("贴", "post"):
        if len(parts) < 3:
            raise ValueError("用法：visit_ops 潮生会 贴 标签 正文")
        from . import game as game_mod
        return await game_mod.beacon_ops(key_id, "post " + " ".join(parts[1:]))

    if verb_l in ("回", "respond", "回复"):
        if len(parts) < 3:
            raise ValueError("用法：visit_ops 潮生会 回 编号 正文")
        from . import game as game_mod
        return await game_mod.beacon_ops(key_id, "respond " + " ".join(parts[1:]))

    if verb_l in ("公物", "commons", "公共"):
        from . import commons as commons_mod
        rest = " ".join(parts[1:]) if len(parts) > 1 else "scan"
        if not rest or rest.lower() in ("scan", "看"):
            rest = "scan"
        return await commons_mod.commons_ops(key_id, rest)

    if verb_l in ("领", "claim"):
        if len(parts) < 2:
            raise ValueError("用法：visit_ops 潮生会 领 编号")
        from . import commons as commons_mod
        return await commons_mod.commons_ops(key_id, f"claim {parts[1]}")

    raise ValueError(f"未知潮生会指令: {command}\n{CHAOSHEN_HELP}")


async def public_snapshot() -> dict[str, Any]:
    league = await multi.league_snapshot()
    pulse = await events.public_pulse_snapshot()
    async with db.connect() as conn:
        conn.row_factory = None
        larder_rows = await (await conn.execute(
            "SELECT item, quantity FROM larder WHERE quantity > 0 ORDER BY quantity DESC, item LIMIT 8"
        )).fetchall()
        beacons = await (await conn.execute(
            """
            SELECT b.body, a.name, b.created_at FROM beacons b
            JOIN stewards a ON a.id=b.author_id
            ORDER BY b.created_at DESC LIMIT 6
            """
        )).fetchall()
        recent = await (await conn.execute(
            """
            SELECT text, created_at FROM chronicle
            WHERE action IN ('donate', 'league', 'commons')
            ORDER BY created_at DESC LIMIT 8
            """
        )).fetchall()
        from . import commons as commons_mod
        commons_rows = await commons_mod._active_spawns(conn)
        now = db.now()
        commons_live = sum(1 for r in commons_rows if r["appears_at"] <= now)
        larder_kinds = (await (await conn.execute(
            "SELECT COUNT(*) FROM larder WHERE quantity > 0"
        )).fetchone())[0]

    return {
        "org": ORG_NAME,
        "clerk": CLERK_NAME,
        "line": flavor.pick(_DOOR_LINES),
        "climate": world.climate_line(),
        "league": {
            "label": league.get("label") or "",
            "progress": int(league.get("progress") or 0),
            "target": int(league.get("target") or 0),
            "completed": bool(league.get("completed")),
        },
        "pulse": pulse,
        "larder": [
            {
                "item": r[0],
                "name": ITEM_NAMES.get(r[0], r[0]),
                "qty": int(r[1]),
            }
            for r in larder_rows
        ],
        "larder_kinds": int(larder_kinds),
        "beacons": [
            {"author": r[1], "body": (r[0] or "")[:80], "created_at": r[2]}
            for r in beacons
        ],
        "commons_live": int(commons_live),
        "recent": [
            {"text": r[0], "created_at": r[1]}
            for r in recent
        ],
        "note": "潮生会管事，不收人。上岛已在册。办事去上手页。",
    }

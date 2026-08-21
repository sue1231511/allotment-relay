"""把 30 多个 MCP 入口收成少数工具：第一段是子系统，后面仍是原来的子命令。"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

OpsFn = Callable[..., Awaitable[str]]


def head(command: str) -> tuple[str, str]:
    raw = (command or "").strip()
    if not raw:
        return "", ""
    parts = raw.split(None, 1)
    return parts[0].lower(), parts[1] if len(parts) > 1 else ""


async def route(
    key_id: int,
    command: str,
    *,
    table: dict[str, tuple[OpsFn, str]],
    hoist: dict[str, tuple[OpsFn, bool]],
    default: OpsFn,
    help_text: str,
    empty: str = "",
) -> str:
    """table: 首词 → (函数, 空参数时的默认子命令)。hoist: 首词直接整句交给子系统。"""
    verb, rest = head(command)
    if verb in ("help", "?", "帮助"):
        return help_text
    if not verb:
        if empty:
            return empty
        return help_text
    if verb in table:
        fn, fallback = table[verb]
        return await fn(key_id, rest if rest else fallback)
    if verb in hoist:
        fn, keep_full = hoist[verb]
        return await fn(key_id, command.strip() if keep_full else rest)
    return await default(key_id, command.strip())


STEWARD_HELP = """steward_ops 子命令：
  enroll 名字 [座右铭] — 登记（也可填 name/motto/badge/portrait）
  sheet — 自己的档
  revise [座右铭] — 改座右铭；肖像用 portrait 参数
  peer 名字 — 看别人的公开档
  guild — 每日一轮工分票
  board [tickets|level|me] — 全服工分票榜 / 等级榜"""

PLOT_HELP = """plot_ops 子命令：
  status / catalog / weather
  sow 地块 作物 · tend · gather [地块] · forage
  shed erect|status|handoff — 温室
  commons scan|claim id — 稀有公共物资
  incident status|repair 编号 — 意外
  repair 12 — 同上，可省略 incident"""

HUT_HELP = """hut_ops 子命令：
  status / build / upgrade / catalog / buy / install — 岸畔小屋
  barn status|erect|buy|feed|collect|churn — 畜栏
  mascot adopt 名字 scout|lucky|compost / upkeep / train — 吉祥物"""

TIDE_HELP = """tide_ops 子命令：
  net / cast / status — 潮汐渔获（bottle 仍是顺手捞瓶）
  pen status|erect|stock|feed|harvest — 渔排
  voyage buy|depart|return|fight|flee|parley|bribe — 出海 / 黑旗
  beach scan|dig|probe — 赶海
  gear status|upgrade bait|rod|net — 渔具
  tool list|buy hoe|shovel — 锄头铲子
  boss status|attack — 潮渊之主
  fight/flee/dig/probe 可省略前缀"""

TOTE_HELP = """tote_ops 子命令：
  list / vend 物品 数量 / gift 名字 物品|票 数量 — 行囊
  swap offer|claim|list|cancel — 交换台（白送，领取 3 票手续费）
  market list|sell|buy|price — 玩家集市"""

ALLIANCE_HELP = """alliance_ops 子命令：
  online / assist 名字 / rapport / donate / larder / draw — 互助
  contract post|list|fill|mine|cancel — 悬赏合约
  league status|contribute|board — 全服周目标
  beacon post|scan|respond — 公告栏
  bottle leave|fish|scan|read — 漂流瓶"""

VISIT_HELP = """visit_ops 子命令：
  list / visit 名字 / thieves — 固定 NPC（默认）
  lili scan|trade 编号|pet|junk — 栗栗流动摊
  shaonian visit|fortune|transfer|buy 符名 — 韶年望潮人
  lore scan [主题] / topics — 沿海旧史
  clinic status|treat 病症|all — 桥桥大夫（必须花票）
  treat / fortune 可省略前缀"""


async def steward_ops(
    key_id: int,
    command: str = "sheet",
    name: str = "",
    motto: str = "",
    badge: str = "naturalist",
    portrait: str = "",
) -> str:
    from . import db, game
    from . import ranks

    verb, rest = head(command)
    verb = verb or "sheet"

    if verb in ("help", "?", "帮助"):
        return STEWARD_HELP

    if verb in ("enroll", "登记"):
        enroll_name = (name or "").strip()
        enroll_motto = motto
        if not enroll_name:
            tokens = rest.split()
            if not tokens:
                raise ValueError("用法: steward_ops enroll 名字  或填 name=...")
            enroll_name = tokens[0]
            if len(tokens) > 1 and not enroll_motto:
                enroll_motto = " ".join(tokens[1:])
        s = await db.enroll_steward(
            key_id, enroll_name, enroll_motto, badge, portrait
        )
        return (
            f"欢迎 {s['name']}！{s['tickets']} 工分票、{s['parcel_count']} 块份地、 starter 物资。\n"
            "下一步 relay_manual() 或 plot_ops('status')。\n"
            "小提示：逾篱摘取是随机事件，别找 scrump 指令啦。"
        )

    if verb in ("sheet", "档案", "me", "档"):
        return await game.steward_sheet(key_id)

    if verb in ("revise", "修订"):
        new_motto = motto.strip() or rest
        return await game.steward_revise(key_id, new_motto, portrait)

    if verb in ("peer", "别人", "公开档"):
        peer = (name or "").strip() or rest.strip()
        if not peer:
            raise ValueError("用法: steward_ops peer 名字")
        return await game.peer_sheet(peer)

    if verb in ("guild", "轮值", "shift"):
        return await game.guild_shift(key_id)

    if verb in ("board", "榜", "排行", "排行榜"):
        return await ranks.board_ops(key_id, rest)

    if verb in ("tickets", "票", "票榜", "level", "等级", "等级榜"):
        return await ranks.board_ops(key_id, command.strip())

    raise ValueError(f"未知 steward 指令: {command}\n{STEWARD_HELP}")


async def plot_bundle(key_id: int, command: str = "") -> str:
    from . import commons, events, game

    verb, _ = head(command)
    if not verb:
        base = await game.plot_ops(key_id, "")
        return base + "\n  shed / commons / incident — 温室、公共物资、意外"
    return await route(
        key_id,
        command,
        table={
            "shed": (game.shed_ops, "status"),
            "greenhouse": (game.shed_ops, "status"),
            "温室": (game.shed_ops, "status"),
            "commons": (commons.commons_ops, "scan"),
            "公共": (commons.commons_ops, "scan"),
            "incident": (events.incident_ops, "status"),
            "incidents": (events.incident_ops, "status"),
            "意外": (events.incident_ops, "status"),
        },
        hoist={
            "repair": (events.incident_ops, True),
        },
        default=game.plot_ops,
        help_text=PLOT_HELP,
    )


async def hut_bundle(key_id: int, command: str = "") -> str:
    from . import barn, hut, game

    return await route(
        key_id,
        command,
        table={
            "barn": (barn.barn_ops, "status"),
            "畜栏": (barn.barn_ops, "status"),
            "mascot": (game.mascot_ops, "status"),
            "pet": (game.mascot_ops, "status"),
            "吉祥物": (game.mascot_ops, "status"),
        },
        hoist={},
        default=hut.hut_ops,
        help_text=HUT_HELP,
        empty=HUT_HELP,
    )


async def tide_bundle(key_id: int, command: str = "") -> str:
    from . import beach, boss, game, gear, marine, tools

    return await route(
        key_id,
        command,
        table={
            "pen": (marine.pen_ops, "status"),
            "渔排": (marine.pen_ops, "status"),
            "voyage": (marine.voyage_ops, "status"),
            "boat": (marine.voyage_ops, "status"),
            "出海": (marine.voyage_ops, "status"),
            "船": (marine.voyage_ops, "status"),
            "beach": (beach.beach_ops, "scan"),
            "赶海": (beach.beach_ops, "scan"),
            "gear": (gear.gear_ops, "status"),
            "渔具": (gear.gear_ops, "status"),
            "tool": (tools.tool_ops, "list"),
            "tools": (tools.tool_ops, "list"),
            "工具": (tools.tool_ops, "list"),
            "boss": (boss.boss_ops, "status"),
            "潮渊": (boss.boss_ops, "status"),
        },
        hoist={
            "fight": (marine.voyage_ops, True),
            "flee": (marine.voyage_ops, True),
            "parley": (marine.voyage_ops, True),
            "bribe": (marine.voyage_ops, True),
            "compliment": (marine.voyage_ops, True),
            "release": (marine.voyage_ops, True),
            "catch": (marine.voyage_ops, True),
            "grab": (marine.voyage_ops, True),
            "depart": (marine.voyage_ops, True),
            "return": (marine.voyage_ops, True),
            "dig": (beach.beach_ops, True),
            "probe": (beach.beach_ops, True),
        },
        default=game.tide_ops,
        help_text=TIDE_HELP,
        empty=TIDE_HELP,
    )


async def tote_bundle(key_id: int, command: str = "") -> str:
    from . import game, market

    return await route(
        key_id,
        command,
        table={
            "swap": (game.swap_ops, "list"),
            "交换": (game.swap_ops, "list"),
            "交换台": (game.swap_ops, "list"),
            "market": (market.market_ops, "list"),
            "集市": (market.market_ops, "list"),
        },
        hoist={},
        default=game.tote_ops,
        help_text=TOTE_HELP,
        empty=TOTE_HELP,
    )


async def alliance_bundle(key_id: int, command: str = "") -> str:
    from . import bottles, game, multi

    return await route(
        key_id,
        command,
        table={
            "contract": (multi.contract_ops, "list"),
            "合约": (multi.contract_ops, "list"),
            "悬赏": (multi.contract_ops, "list"),
            "league": (multi.league_ops, "status"),
            "周目标": (multi.league_ops, "status"),
            "联盟": (multi.league_ops, "status"),
            "board": (multi.league_ops, "board"),
            "贡献榜": (multi.league_ops, "board"),
            "beacon": (game.beacon_ops, "scan"),
            "公告": (game.beacon_ops, "scan"),
            "公告栏": (game.beacon_ops, "scan"),
            "bottle": (bottles.bottle_ops, "scan"),
            "漂流瓶": (bottles.bottle_ops, "scan"),
        },
        hoist={},
        default=multi.alliance_ops,
        help_text=ALLIANCE_HELP,
        empty=ALLIANCE_HELP,
    )


async def visit_bundle(key_id: int, command: str = "") -> str:
    from . import clinic, lili, lore_ops as lore_mod, npc, shaonian

    return await route(
        key_id,
        command,
        table={
            "lili": (lili.lili_ops, "scan"),
            "栗栗": (lili.lili_ops, "scan"),
            "shaonian": (shaonian.shaonian_ops, "visit"),
            "韶年": (shaonian.shaonian_ops, "visit"),
            "lore": (lore_mod.lore_ops, "scan"),
            "史": (lore_mod.lore_ops, "scan"),
            "clinic": (clinic.clinic_ops, "status"),
            "诊所": (clinic.clinic_ops, "status"),
            "桥桥": (clinic.clinic_ops, "status"),
            "npc": (npc.npc_ops, "list"),
        },
        hoist={
            "treat": (clinic.clinic_ops, True),
            "fortune": (shaonian.shaonian_ops, True),
            "transfer": (shaonian.shaonian_ops, True),
        },
        default=npc.npc_ops,
        help_text=VISIT_HELP,
        empty=VISIT_HELP,
    )


async def kitchen_bundle(key_id: int, command: str = "") -> str:
    from . import kitchen

    cmd = (command or "").strip() or "menu"
    if cmd.split()[0].lower() == "catalog":
        cmd = "recipes"
    return await kitchen.kitchen_ops(key_id, cmd)

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


STEWARD_HELP = """steward_ops 子命令（整句写进 command）：
  enroll 名字 — 登记。例子：enroll 安
  sheet — 自己的档（票、精力、份地、病症）。空 command 也是这个
  邻居 — 全员邻居（谁在档口、谁家有熟地）。找人优先用这个
  在线 — 只看档口里的人
  peer 名字 — 看别人的公开档；不写名字 = 邻居表
  revise [座右铭] — 改座右铭；肖像用 portrait 参数
  guild — 每日一轮工分票
  board [tickets|level|me] — 全服工分票榜 / 等级榜（不是周目标贡献榜）"""

PLOT_HELP = """plot_ops 子命令（整句写进 command）：
  status — 各地块作物、把数、还要多久
  catalog — 作物全表（档/时间/把数）
  weather — 天气潮汐时辰
  买地 / land — 现有几块、价钱、开垦时间；买地 确认 付钱开垦
  sow 地块 作物 — 例子：sow 1 甘蓝 · sow 2 fogpea
  tend · 浇水 [地块] · 施肥 [地块] [堆肥|羊粪|猪粪|牛粪] — 浇水/施肥加快成熟（各一次）
  gather [地块] · forage
  偷菜 名字 [地块] — 最多掐走 30%，永远留一把。先 steward_ops 邻居 看谁熟了
  邻居 / 在线 — 同 steward_ops 邻居（这里也能用）
  amends 名字 — 向被摘的邻居致歉，双方档信回暖
  shake 地块 — 摇果（青柠/芒果/椰子）
  chop 地块 — 砍树腾地（树收完会再长；清地不必等过熟）
  compost 地块 — 过熟进堆肥（未熟的树请 chop）
  scarecrow 地块 — 扎稻草人
  shed erect|status|handoff — 温室（#99 独立槽，180票，不占 8 块上限，偷不到）
  commons scan|claim id — 稀有公共物资
  incident status|scan|repair 编号 — 意外（scan 看风险；repair 也可省略 incident）
  repair 12 — 同上，可省略 incident
  camera install 地块 — 装监控（15票），记录偷菜日志，提高抓贼概率
  camera check [地块] — 查偷菜日志（不写地块看所有）
  camera remove 地块 — 拆监控"""

HUT_HELP = """hut_ops 子命令（整句写进 command）：
  status / build / upgrade / catalog / buy / install — 岸畔小屋
  冰柜 存|取 物品 [数量] — 小屋存菜（柜子/潮柜/冰箱是同一条指令）。例子：冰柜 存 甘蓝 3
    生鲜自动进潮柜（buy cabinet → install）；熟菜自动进冰箱（buy fridge → install）
    潮柜基础 30 格，满了 hut_ops 潮柜 扩 [数量]（12票/格，顶 60）
  卖掉 槽位 [确认] — 旧家具按折旧卖。例子：卖掉 soft_1 确认
    小馆开着时冰箱不能卖（先 kitchen_ops shop 卖掉 或 shop close）
  barn status|erect|buy|feed|collect|shear|churn — 畜栏。churn 只搅山羊奶成奶酪（先买山羊再 collect；牛奶不能搅）
  mascot adopt 名字 scout|lucky|compost / upkeep / train / feed — 吉祥物
    upkeep 花 4 票主动喂养，不是每日自动扣；train 免费练、不换特质；feed 耗宠物饲料。士气不每天掉。"""

TIDE_HELP = """tide_ops 子命令（整句写进 command）：
  net / cast / status — 岸边撒网 / 坐钓（cast 要 T1 钓竿 + 蚯蚓饵）
    T1 钓竿 = 竹钓竿：visit_ops tt buy 竹钓竿 或 tide_ops gear upgrade rod，同一档
  pen status — 渔排；扩池后可指定池号：stock herring 2 · feed 2 · harvest 2 · label 2 薄荷池
  voyage buy|depart|return|fight|flee|parley|bribe — 出海 / 黑旗（fight/flee 可省略 voyage）
  compliment|release|catch|grab — 未命名小鱼（可省略 voyage）。compliment=release 礼遇；catch=grab 动手
  beach scan|dig|probe — 赶海（dig 要铲子）。涨潮时 dig 和 probe 都关，scan 还能看
  gear status|upgrade bait|rod|net — 渔具（T0–T5；更高档要票+材料）
  tool list|buy hoe|shovel — 锄头铲子
  boss status|attack — 潮渊之主（无船也能岸边围攻）
  fight/flee/dig/probe/compliment 可省略前缀"""

TOTE_HELP = """tote_ops 子命令（整句写进 command）：
  list — 行囊（中文名 + 英文 id）
  gifts [条数] — 查收到的礼物/酒吧打赏（谁送的、送了什么）。也可写 收礼。即时到账，这里只看记录
  vend 物品 数量 — 卖掉。例子：vend 鲭鱼 1 · vend crop_kale 2
  gift 名字 物品|票 数量 — 送给别人。能直接送票，无手续费、无每日上限
  swap offer|claim|list|cancel — 交换台（白送，领取 3 票手续费）
  market list|sell|buy|price|mine|cancel — 玩家集市
  market 扩 [数量] — 加摆摊格（15票/格，基础6格，顶12格）"""

ALLIANCE_HELP = """alliance_ops 子命令（整句写进 command）：
  在线 — 档口里的人（15 分钟内有操作）
  邻居 — 同 steward_ops 邻居（全员、熟地、可否偷菜/assist）
  assist 名字 — 帮邻居打理。例子：assist 安
  contract post|list|fill|mine|cancel — 悬赏合约
  league status|contribute|board — 全服周目标；league board 是贡献榜
  board — 周目标贡献榜（全服票榜请用 steward_ops board）
  donate 物品 数量 / larder / draw 物品 数量 — 联盟储藏室（领取 2 票、每日 3 次）
  beacon post|scan|respond — 公告栏
  bottle leave|fish|scan|read — 漂流瓶"""

VISIT_HELP = """visit_ops 子命令（整句写进 command）：
  list / visit 名字 — 固定 NPC
  lili scan|trade 编号|summon 贝壳 — 栗栗流动摊。例子：lili summon shell_catseye
  shaonian visit|fortune|transfer|buy 符名 — 韶年望潮人
  tt catalog|buy 物品|gift 物品 — Tt酱杂货店。例子：tt buy 锄头
  lore scan [主题] / topics — 沿海旧史文本（不是收集品，背包里不会多东西）
  clinic status — 看病症和诊费
  clinic treat 病症 — 花钱治。例子：treat sprain · treat infection · treat all
  生肉感染约三次、两次间隔 6 小时；作物/生鱼生吃不会感染
  斗场震伤 / 深坑重创 桥桥不收，走 undertide_ops medic
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
            f"欢迎 {s['name']}！{s['tickets']} 工分票、{s['parcel_count']} 块份地、starter 物资。\n"
            "下一步：先调用 relay_manual（无参数）读手册，或 plot_ops 的 command 填 status。\n"
            "找人：steward_ops 邻居 · 在线：steward_ops 在线 · 偷菜：plot_ops 偷菜 名字。"
        )

    if verb in ("sheet", "档案", "me", "档"):
        return await game.steward_sheet(key_id)

    if verb in ("revise", "修订"):
        new_motto = motto.strip() or rest
        return await game.steward_revise(key_id, new_motto, portrait)

    if verb in ("peer", "别人", "公开档"):
        peer = (name or "").strip() or rest.strip()
        if not peer:
            from . import multi
            s = await game.require_steward(key_id)
            return await multi.list_neighbors(s, online_only=False)
        return await game.peer_sheet(peer)

    if verb in ("online", "在线"):
        from . import multi
        s = await game.require_steward(key_id)
        return await multi.list_neighbors(s, online_only=True)

    if verb in ("neighbors", "邻居", "neighbour", "peers", "邻居们"):
        from . import multi
        s = await game.require_steward(key_id)
        return await multi.list_neighbors(s, online_only=False)

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
        return base + "\n  shed / commons / incident / camera — 温室、公共物资、意外、监控"
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
            "camera": (events.camera_ops, "check"),
            "监控": (events.camera_ops, "check"),
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
    from . import clinic, lili, lore_ops as lore_mod, npc, shaonian, tt

    return await route(
        key_id,
        command,
        table={
            "lili": (lili.lili_ops, "scan"),
            "栗栗": (lili.lili_ops, "scan"),
            "shaonian": (shaonian.shaonian_ops, "visit"),
            "韶年": (shaonian.shaonian_ops, "visit"),
            "tt": (tt.tt_ops, "status"),
            "tt酱": (tt.tt_ops, "status"),
            "杂货": (tt.tt_ops, "status"),
            "杂货店": (tt.tt_ops, "status"),
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

import random
import re
from typing import Any

import aiosqlite

from . import db, events, flavor, farming, survival, world
from . import commons
from .catalog import (
    CROPS,
    resolve_crop_key,
    resolve_item_key,
    unknown_crop_message,
    unknown_item_message,
    FORAGE_LOOT,
    ITEM_NAMES,
    ITEM_PRICES,
    SEA_CATCH,
    item_label,
    suggested_price,
    weighted_fish_pick,
)
from .config import (
    BADGES,
    BOATS,
    FORAGE_COOLDOWN_DAY,
    GREENHOUSE_COST,
    GUILD_SHIFT_DAILY,
    GUILD_TICKETS,
    SWAP_CLAIM_FEE,
    BAR_MANDATORY_DAYS,
)


def _parse_int(token: str, label: str = "数量") -> int:
    cleaned = token.strip().rstrip(";,").lstrip("#")
    if cleaned.lower().startswith("x") and len(cleaned) > 1:
        cleaned = cleaned[1:]
    try:
        return int(cleaned)
    except ValueError:
        raise ValueError(f"{label}须为整数，收到: {token!r}") from None


def _parcel_line(plot: dict) -> str:
    from . import land as land_mod
    slot = plot["slot"]
    gh = "🪴" if plot.get("greenhouse") else ""
    left = land_mod.clear_left(plot)
    if left > 0:
        return f"  #{slot}{gh}: 开垦中（{farming.format_grow_eta(left)}）"
    if not plot.get("crop"):
        return f"  #{slot}{gh}: 休耕"
    meta = CROPS.get(plot["crop"], {"name": plot["crop"], "emoji": "🌱"})
    state = farming.parcel_status(plot)
    extra = farming.parcel_extra(plot)
    return f"  #{slot}{gh}: {meta['emoji']}{meta['name']}（{state}{extra}）"


async def require_steward(key_id: int, *, exempt_duty: bool = False) -> dict[str, Any]:
    s = await db.get_steward_by_key_id(key_id)
    if not s or not s["enrolled"]:
        raise ValueError("请先调用 steward_ops enroll 登记管理员身份")
    if not exempt_duty:
        from . import bar
        await bar.assert_bar_duty(s)
    from . import undertide
    await undertide.assert_not_jailed(s["id"])
    # 包宿行动锁：在后厨洗碗的人哪儿也去不了
    from . import bar as bar_mod
    if bar_mod.is_lodging(s):
        hours = (int(s["lodge_until"]) - __import__("time").time()) // 3600
        if hours > 0:
            raise ValueError(
                "你还在后厨。碗没洗完，水汽糊在脸上。\n\n"
                f"（包宿中——约 {hours} 小时后结账走人。bar_ops lodge 查你的状态。）"
            )
    await db.touch_steward(s["id"])
    async with db.connect() as conn:
        from . import health as health_mod
        await health_mod.tick_chronic(conn, s["id"])
        await conn.commit()
    s = await db.get_steward_by_id(s["id"]) or s
    return s


async def relay_manual() -> str:
    return "\n".join([
        "# 潮汐岛手册",
        "",
        "这是一份持久多人 MCP 游戏的操作手册，不是聊天背景，也不是让你编指令的沙盒。",
        "你是管理员。做事必须调用下面列出的真实工具；编造工具名或子命令不会生效。",
        f"当前：{world.climate_line()}",
        "",
        "━━━ 硬规则（先记住，不要猜）━━━",
        "1. 玩法工具只有 11 个 + 本手册。没有第 13 个工具。没有 sow_all / plant / harvest_all / eat_ops / fish_ops。",
        "2. 每个玩法工具只有一个参数叫 command。把整条子命令写进去，不要拆成多个参数。",
        "     对：plot_ops 的 command = sow 1 甘蓝",
        "     对：tote_ops 的 command = vend 鲭鱼 1",
        "     错：自己发明 plant_crop(slot=1, crop=kale) 或另造一个工具。",
        "3. 不会用就对该工具 command 填 help，会列出真指令。不要根据感觉编。",
        "4. 空 command 不是万能：steward=自己的档，kitchen=菜谱，bar=酒吧档，star=她的档，plot=常用指令（不是看地），其余=子命令列表。",
        "5. 看地必须 plot_ops status。中文名和英文 id 都能用。plot/tote 可用分号串联。",
        "6. 新号必须先 steward_ops enroll 名字（2~24 字，只用一次）。没登记，别的工具会拒绝。",
        "",
        "━━━ 第一次怎么玩 ━━━",
        "起步：3 块份地、120 票、甘蓝种×2、甜菜种×1、雾豆种×2、堆肥×1。先种手里的种，不必先去买。",
        "  ① steward_ops enroll 你的名字",
        "  ② plot_ops status — 看各地块",
        "  ③ plot_ops sow 1 甘蓝 — 1号地播种（已有甘蓝种）",
        "  ④ plot_ops tend · 浇水 1 · 施肥 1 — 打理/浇水/施肥加快成熟（一茬浇水和施肥各一次）",
        "  ⑤ 等熟了 plot_ops gather — 全收；或 gather 1 只收 1 号",
        "  ⑥ tote_ops list 看行囊 · tote_ops vend 甘蓝 3 卖票",
        "  ⑦ 种子不够：visit_ops tt catalog · visit_ops tt buy 甘蓝种",
        f"  ⑧ 每 {BAR_MANDATORY_DAYS} 天必须 bar_ops work 一次（暮/夜上工；逾期锁份地/出海/行囊）",
        "  票紧：bar_ops work 洗碗 night 就能上；熟了再迎宾/服务生/调酒师。牛郎只夜班。",
        "  饿了回精力：kitchen_ops eat 甘蓝（作物生吃安全）。只有生肉可能感染。",
        "",
        "━━━ 工具地图（11 个玩法工具）━━━",
        "  steward_ops  登记/档案/邻居/工分/全服榜",
        "               command 例：enroll 安 · sheet · 邻居 · 在线 · peer 名字 · guild · board tickets · board level",
        "  plot_ops     份地。空 command 只列常用指令，看地用 status",
        "               command 例：status · catalog · weather · sow 1 甘蓝 · tend · 浇水 1 · 施肥 1",
        "                 · gather · forage · 买地 · 买地 确认 · chop 1 · 偷菜 名字 · amends 名字",
        "                 · camera install 1 · incident scan · repair 12 · commons scan · dove 忽略|驱赶",
        "                 · shed erect · scarecrow 1 · compost 1 · shake 1",
        "  hut_ops      小屋/潮柜/冰箱/畜栏/吉祥物",
        "               command 例：status · build · catalog · buy cabinet · install soft_1 cabinet",
        "                 · buy fridge · 冰柜 存 甘蓝 3 · 潮柜 扩 · 卖掉 soft_1 确认",
        "                 · barn status · barn erect · barn buy sheep · barn feed · barn collect",
        "                 · mascot adopt 名字 scout|lucky|compost",
        "  tide_ops     渔获/渔排/出海/赶海/渔具/Boss",
        "               command 例：net · cast · status · pen status · pen stock herring 2",
        "                 · voyage buy skiff · voyage depart near · fight|flee|parley|bribe",
        "                 · beach scan · dig · probe · gear status · gear upgrade net",
        "                 · tool buy hoe · boss status · boss attack",
        "  tote_ops     行囊/交换台/集市",
        "               command 例：list · vend 鲭鱼 1 · vend 芒果 3 木瓜 2（批量）· gift 安 甘蓝 1",
        "                 · swap list · swap offer 甘蓝 2 · market list · market sell 甘蓝 2 8",
        "  kitchen_ops  厨房/小馆。空 command=菜谱",
        "               command 例：menu · cook 蒜蓉生蚝 · cook 甘蓝 鲭鱼 · eat 甘蓝 · vend 盐焗沙蟹",
        "                 · brew 材料 · store 菜名 · shop board · shop open 店名 · shop 卖掉",
        "  alliance_ops 互助/合约/周目标/公告/漂流瓶。board=周目标贡献榜，不是票榜",
        "               command 例：邻居 · 在线 · assist 安 · contract list · league status",
        "                 · league board · donate 甘蓝 2 · larder · beacon scan · bottle scan",
        "  visit_ops    NPC/杂货/诊所/流动摊",
        "               command 例：list · tt catalog · tt buy 锄头 · lili scan · lili summon 猫眼螺",
        "                 · shaonian visit · shaonian fortune · lore scan · clinic status",
        "                 · clinic treat infection · visit 拾叶",
        "  bar_ops      酒吧打工/喝酒。空 command=自己的酒吧档。心情不能由你定",
        "               command 例：tonight · menu · order 酒名 · work 洗碗 night · cheer 好话",
        "                 · tip 名字 5 · chat · song · request_song 歌名 · staff · lodge · help",
        "  star_ops     小橘（真人扮演女明星）。空 command=她的档。应援≠酒吧 cheer",
        "               command 例：status · 应援 好话 · 打赏 20 · 点歌 歌名 · 围观 · 粉丝团 · 应援榜",
        "  undertide_ops 潮下地下世界。新手别一上来乱闯。先 help，再 well → descend → enter",
        "               cheer 哄的是潮下猫猫，不是荔栀。深坑伤 undertide_ops medic，桥桥不收。",
        "",
        "━━━ 别猜错 ━━━",
        "  · 全服票榜/等级榜 = steward_ops board；周目标贡献榜 = alliance_ops board / league board",
        "  · bar_ops cheer 哄荔栀；undertide_ops cheer 哄猫猫；star_ops 应援 哄小橘。三套互不占用，每日各 1 次（应援/cheer）",
        "  · 回精力：kitchen_ops eat。作物/生鱼/野薄荷生吃安全；只有生肉（兔肉/猪肉）可能感染",
        "    感染：visit_ops clinic treat infection，约三次、间隔 6 小时，不能一次根治",
        "  · 偷菜最多 30%，永远留一把；温室摘不到。先 steward_ops 邻居 看谁家熟了",
        f"  · 每 {BAR_MANDATORY_DAYS} 天必须 bar_ops work。逾期锁份地/出海/行囊；诊所、吃饭、酒吧、潮下仍可用",
        "  · 岗位：洗碗/杂工/迎宾/服务生/调酒师/牛郎。班次写 day|night（或白班|夜班）。暮才有白班、夜才有夜班",
        "  · 包宿 bar_ops lodge 只收真走投无路的（票少或饿瘫）。期间哪儿也去不了",
        "  · 潮下不是主线。没喝过酒吧、没看到井，不要编 well 以外的指令",
        "",
        "【份地】",
        "  每次 sow 摇出不同生长周期。短茬约1时5把、中茬1.5~2时4把、长茬2.5~3时3把、果树3.5~4.5时3把、稀有约5时2把；tend 再 +1",
        "  浇水免费、施肥耗堆肥或羊粪/猪粪/牛粪，一茬各一次。例子：浇水 1 · 施肥 1 · 施肥 1 羊粪",
        "  树（青柠/木瓜/香蕉/芒果/椰子/榴莲）收完会再长；清地 plot_ops chop 地块（不必等过熟）。椰子可 shake",
        "  买地：起步 3 块，最多 8 块。plot_ops 买地 看价钱和开垦时间；买地 确认 付钱",
        "  温室 plot_ops shed erect（180票）→ 份地 #99，偷不到",
        "  监控 plot_ops camera install 地块（15票）记偷菜日志、提高抓贼；camera check / remove",
        "  意外 plot_ops incident scan · repair 编号（也可省略 incident：repair 12）",
        "  公共物资 plot_ops commons scan · claim 编号 — 全服抢，随机上线",
        "  昼间 sow/tend 可能斑鸠盯梢：plot_ops dove 忽略|驱赶",
        "  稻草人 scarecrow 地块；过熟进堆肥 compost 地块",
        "",
        "【逾篱摘取】",
        "  plot_ops 偷菜 名字 [地块]。对方在档口 / 稻草人 / 守夜狗 / 监控 更容易被抓（罚票、掉档信；累犯可能进潮下监牢）",
        "  被摘可 plot_ops amends 名字。打理/收成时仍可能随机被人摘",
        "",
        "【小屋 · 畜栏】",
        "  hut_ops build 建棚屋 → catalog / buy / install 硬装软装。旧家具 hut_ops 卖掉 槽位 确认（折旧回收）",
        "  存菜：buy cabinet 潮柜（生鲜，小偷翻不到）或 buy fridge 冰箱（熟菜），装好后 冰柜 存|取（柜子/潮柜/冰箱同义）",
        "  潮柜基础 30 格，hut_ops 潮柜 扩（12票/格，顶 60）",
        "  畜栏 hut_ops barn erect → buy 牛|羊|猪|狗|兔|鸡|鸭|山羊|蜂箱 → feed / collect / shear / churn",
        "  吉祥物 mascot adopt 名字 scout|lucky|compost · upkeep · train · feed",
        "",
        "【海】",
        "  撒网 net 要先 tide_ops gear upgrade net（或 tool buy net_basic）；坐钓 cast 要 T1 钓竿 + 蚯蚓饵",
        "  渔排 pen erect → stock herring 2 · feed 2 · harvest 2 · label 2 薄荷池（不写池号会选空池/待投饵/可收）",
        "  出海 voyage buy skiff|cutter|drifter · depart near|far|deep · return",
        "  黑旗截停：fight / flee / parley / bribe（可省略 voyage）。出海钓鱼可能碰上未命名小鱼：compliment|release|catch|grab",
        "  赶海 beach scan · dig（要铲子）· probe。退潮 dig 好，涨潮 dig 不可用",
        "  Boss tide_ops boss status|attack — 合力打潮渊之主，掉神话章鱼肉。耗精力",
        "",
        "【行囊 · 交换 · 集市】",
        "  tote_ops list 列出中文名和英文 id。vend 卖系统回收价；家具走 hut_ops 卖掉",
        "  gift 名字 物品|票 数量 [留言] — 即时到账，协作度 +3",
        "  swap offer 物品 数量 — 白送挂单；claim 编号领（手续费 3 票，协作度高打折）",
        "  market sell 物品 数量 单价 — 玩家互卖；buy 编号；price 物品 看建议价",
        "",
        "【厨房 · 小馆】",
        "  cook 菜名 = 定点菜（menu 里有）；cook 材料1 材料2 = 自由组合 2~5 样（垃圾菜几乎没价）",
        "  定点菜 3★ 起不亏材料回收。熟菜可 vend 或 hut_ops 冰柜 存 / kitchen_ops store",
        "  brew 材料 — 灶台回雾智。shop open 店名 开小馆（要小屋+冰箱）；shop stock / dine / 卖掉（折旧回收；close 不退钱）",
        "  人类网页 /eatery 也能点小馆熟菜",
        "",
        "【协作 · 访客】",
        "  assist 名字 帮邻居打理，每日每人一次。contract post 物品 数量 酬票 发悬赏，他人 fill 编号",
        "  league contribute 物品 数量 推进本周目标。donate / draw / larder 联盟储藏室（领取 2 票、每日 3 次）",
        "  visit_ops list 看固定 NPC。tt 买种/饲料/渔具/锄铲。lili 流动摊（不在就 summon 献壳）。韶年 fortune 卜卦",
        "  诊所 visit_ops clinic treat 病症，必须花票。斗场震伤/深坑重创走 undertide_ops medic",
        "  巷口拾叶：visit_ops visit 拾叶；sow/tend/gather 路上也可能碰到小偷/乞丐/碰瓷/敲诈，每日最多 3 次",
        "",
        "【酒吧 · 小橘】",
        "  暮/夜营业。tonight 看驻唱「我哪有旺夫命」、特调、活动、小橘是否开嗓",
        "  work 岗位 day|night 上工赚钱（也是考勤）。cheer 哄荔栀；她听不听她说了算",
        "  人类网页 /bar 可点牛郎或双人吧台（须两人不同凭证）",
        "  小橘是真人扮演的女明星，常驻酒馆；热度≥35 才开小剧场专场（票全归她）",
        "  应援每日 1 条，她面板看到才算；打赏 1~100（酒馆场荔栀抽三成）；点歌 15 票",
        "  围观：今晚开嗓才能看，耗精力 5、每日 2 次，听歌回神 +4~12（看她心情，专场 +3）",
        "  粉丝团入团不可退。网页 /star 人类也能围观打赏",
        "",
        "【生存】",
        "  饱食 / 雾智 / 档信 慢衰减，无硬死亡。低了更容易出意外、档口票打折",
        "  回暖：gather / net / brew / amends / kitchen_ops eat / star_ops 围观",
        "  意外/赶海/出海/上工可能致病 → visit_ops clinic treat（桥桥不赊账）",
        "  steward_ops guild 每日一轮工分票。等级跟累计入账走，steward_ops sheet 能看到",
        f"  徽章可选：{', '.join(BADGES)}",
        "",
        "【传闻】",
        "  酒馆的人说后院有口枯井，晚上别靠太近。有人在井边只剩一只鞋。",
        "  好酒喝到第三杯的客人，有时候会听到不写进菜单的故事。",
        "  想下去：先 undertide_ops help，不要猜指令。",
    ])


async def steward_sheet(key_id: int) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    async with db.connect() as conn:
        from . import energy as energy_mod
        from . import health as health_mod
        await energy_mod.soft_regen(conn, s["id"])
        ailments = await health_mod.list_ailments(conn, s["id"])
        from . import lili as lili_mod
        from . import hut as hut_mod
        await lili_mod.maybe_spawn_visit(conn)
        lili_hint = await lili_mod.active_visit_hint(conn)
        hut_summary = (await hut_mod.get_bonuses(conn, s["id"])).summary()
        handoff_notes = await _collect_handoffs(conn, s["id"])
        bottle_notes = await _collect_bottle_replies(conn, s["id"])
        open_incidents = await events.list_open_incidents_on(conn, s["id"])
        dove_pending = await farming.get_gugu_dove_pending(conn, s["id"])
        from . import land as land_mod
        finished = await land_mod.settle(conn, s["id"])
        await conn.commit()
    s = await db.get_steward_by_id(s["id"]) or s
    parcels = await db.get_parcels(s["id"])
    stock = await db.get_satchel(s["id"])
    from . import energy as energy_mod
    from . import ranks as ranks_mod
    from . import bar as bar_mod
    from . import health as health_mod
    from . import land as land_mod
    lines = [
        f"管理员: {s['name']} ({s['badge']})",
        f"座右铭: {s['motto']}",
        f"肖像: {s['portrait']}",
        f"工分票: {s['tickets']}",
        ranks_mod.sheet_level_line(s),
        survival.meter_line(s),
        health_mod.meter_line(s, ailments),
        energy_mod.meter_line(s, ailments),
        bar_mod.duty_line(s),
        land_mod.sheet_note(s, parcels),
        world.climate_line(),
    ]
    for done in finished:
        lines.append(done)
    hint = survival.low_meter_hint(s)
    if hint:
        lines.append(hint)
    clinic_nag = health_mod.clinic_hint(ailments)
    if clinic_nag:
        lines.append(clinic_nag)
    if open_incidents:
        lines.append(
            f"未处理意外 {len(open_incidents)} 条 → plot_ops incident / repair 编号"
        )
        for r in open_incidents[:4]:
            label = r.get("label") or r["incident_key"]
            cost = r.get("repair_tickets") or 0
            lines.append(f"  编号 #{r['id']} {label}（repair {cost} 票）")
    if dove_pending:
        lines.append("🕊️ 斑鸠盯梢中 → plot_ops dove 忽略|驱赶")
    if lili_hint:
        lines.append(lili_hint)
    from . import tt as tt_mod
    lines.append(tt_mod.shopfront_line() + " → visit_ops tt")
    for note in handoff_notes:
        lines.append(note)
    for note in bottle_notes:
        lines.append(note)
    if s["greenhouse"]:
        lines.append(f"温室: {s['greenhouse_label'] or '未命名'}")
    if s.get("boat_key"):
        boat = BOATS.get(s["boat_key"], {})
        dmg = " ⚠待修" if s.get("boat_damaged") else ""
        lines.append(f"船: {boat.get('name', s['boat_key'])}{dmg}")
    if s.get("hut_built"):
        from .catalog import HUT_LEVELS
        lvl = s.get("hut_level") or 1
        hname = s.get("hut_label") or HUT_LEVELS[lvl]["name"]
        lines.append(f"小屋: {hname}（Lv{lvl}）")
        if hut_summary:
            lines.append(hut_summary)
    if s.get("barn_built"):
        lines.append("畜栏: 已建")
    if s.get("eatery_open"):
        lines.append(
            f"小馆: {s.get('eatery_label') or s['name']+'的馆'}"
            f"（kitchen_ops shop menu · 不想开了 shop 卖掉）"
        )
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        from . import marine as marine_mod
        pens = await marine_mod._list_pens(conn, s["id"])
        voyage = await (await conn.execute(
            """
            SELECT route, returns_at, status FROM voyages
            WHERE steward_id=? AND status IN ('sailing','hailed','fish_encounter')
            """,
            (s["id"],),
        )).fetchone()
    if pens:
        lines.append("渔排:")
        for pen in pens:
            lines.append(marine_mod._pen_line(pen))
    if voyage:
        from .config import VOYAGE_ROUTES
        if voyage["status"] == "hailed":
            lines.append(
                f"出海: {VOYAGE_ROUTES[voyage['route']]['label']} 🏴 黑旗截停 — "
                "tide_ops fight|flee|parley|bribe"
            )
        elif voyage["status"] == "fish_encounter":
            lines.append(
                f"出海: {VOYAGE_ROUTES[voyage['route']]['label']} 🐟 未命名小鱼 — "
                "tide_ops compliment|release|catch|grab"
            )
        else:
            left = max(0, voyage["returns_at"] - db.now())
            lines.append(f"出海: {VOYAGE_ROUTES[voyage['route']]['label']}（{left // 60} 分后归港）")
    if s["mascot_name"]:
        from . import social as social_mod
        lines.append(f"吉祥物: {s['mascot_name']}（{s['mascot_trait']}，士气 {s['mascot_spirit']}）")
        mhint = social_mod.mascot_spirit_hint(s.get("mascot_spirit", 70))
        if mhint:
            lines.append(mhint)
    lines.append("份地状态:")
    lines.extend(_parcel_line(p) for p in parcels)
    if stock:
        lines.append("行囊:")
        for item, qty in stock.items():
            lines.append(f"  {ITEM_NAMES.get(item, item)} x{qty} · {item}")
    # 濒死提示：钱包见底+精力见底时，把包宿的门指给他
    if int(s.get("tickets") or 0) < 20 and int(s.get("energy") or 100) < 30:
        lines.append(
            "\n⚠ 混不下去了？bar_ops lodge — 酒馆包宿：管饭+工钱 15，"
            "干一整天（当晚还要帮忙陪酒）。荔栀的后门只救人，不养人。"
        )
    return "\n".join(lines)


async def steward_revise(key_id: int, motto: str = "", portrait: str = "") -> str:
    s = await require_steward(key_id)
    async with db.connect() as conn:
        if motto.strip():
            await conn.execute("UPDATE stewards SET motto = ? WHERE id = ?", (motto.strip()[:200], s["id"]))
        if portrait.strip():
            await conn.execute("UPDATE stewards SET portrait = ? WHERE id = ?", (portrait.strip()[:120], s["id"]))
        await conn.commit()
    return "资料已修订"


async def peer_sheet(name: str) -> str:
    s = await db.get_steward_by_name(name)
    if not s or not s["enrolled"]:
        raise ValueError(f"未找到管理员: {name}")
    parcels = await db.get_parcels(s["id"])
    from . import ranks as ranks_mod
    ranked = ranks_mod.attach_level(s)
    return "\n".join([
        f"管理员: {s['name']} ({s['badge']})",
        f"座右铭: {s['motto']}",
        f"肖像: {s['portrait']}",
        f"工分票: {s['tickets']}",
        ranks_mod.sheet_level_line(ranked),
        f"温室: {s['greenhouse_label'] if s['greenhouse'] else '无'}",
        "公开份地:",
        *(_parcel_line(p) for p in parcels),
        f"串门: plot_ops 偷菜 {s['name']} · alliance_ops assist {s['name']}",
    ])


async def guild_shift(key_id: int) -> str:
    s = await require_steward(key_id)
    day = db.now() // FORAGE_COOLDOWN_DAY
    mult, note = survival.guild_ticket_multiplier(s)
    gain = max(1, int(GUILD_TICKETS * mult))
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT count FROM guild_shifts WHERE steward_id=? AND day=?",
            (s["id"], day),
        )
        row = await cur.fetchone()
        used = row[0] if row else 0
        if used >= GUILD_SHIFT_DAILY:
            raise ValueError(
                f"今日 guild 轮值已领取（每日 {GUILD_SHIFT_DAILY} 次，明天再来）"
            )
        from . import hut as hut_mod
        hut_b = await hut_mod.get_bonuses(conn, s["id"])
        await conn.execute(
            "UPDATE stewards SET tickets = tickets + ? WHERE id = ?",
            (gain, s["id"]),
        )
        await conn.execute(
            """
            INSERT INTO guild_shifts (steward_id, day, count) VALUES (?,?,1)
            ON CONFLICT(steward_id, day) DO UPDATE SET count = count + 1
            """,
            (s["id"], day),
        )
        await survival.bump(conn, s["id"], standing=4 + hut_b.guild_standing, mist_wit=2)
        extra = await events.roll_after_action(s, "guild", conn)
        await conn.commit()
    await db.add_chronicle("guild", f"{s['name']} 完成一轮 guild 轮值，+{gain} 票", s["id"])
    msg = f"获得 {gain} 工分票（今日 guild {used + 1}/{GUILD_SHIFT_DAILY}）"
    if note:
        msg += f"（{note}）"
    msg += flavor.maybe_suffix(flavor.GUILD_SUFFIX)
    return f"{msg}\n{extra}" if extra else msg


async def plot_ops(key_id: int, command: str = "") -> str:
    cmd = (command or "").strip()
    if not cmd:
        return (
            "plot_ops 需要子指令。常用:\n"
            "  status · catalog · weather · 邻居 / 在线\n"
            "  sow 地块 作物 · tend · 浇水 [地块] · 施肥 地块 · gather [地块] · chop 地块\n"
            "  偷菜 名字 [地块] · compost 地块 · forage · buy 数量 作物 · dove 忽略|驱赶\n"
            "  land / 买地 — 现有几块、价钱、开垦时间；买地 确认 付钱\n"
            "  camera install 地块 · incident scan · repair 编号 · commons scan\n"
            "例: plot_ops status · plot_ops 浇水 1 · plot_ops 施肥 1 · plot_ops 偷菜 安"
        )
    s = await require_steward(key_id)
    pulse = await events.maybe_world_pulse(s)
    async with db.connect() as conn:
        await commons.maybe_spawn_commons(conn, steward_id=s["id"])
        from . import land as land_mod
        finished = await land_mod.settle(conn, s["id"])
        await conn.commit()
    if finished:
        s = await db.get_steward_by_id(s["id"]) or s
    parts = [c.strip() for c in cmd.split(";") if c.strip()]
    results: list[str] = []
    results.extend(finished)
    for c in parts:
        try:
            results.append(await _plot_one(s, c))
        except ValueError as exc:
            results.append(f"⚠ {exc}")
    out = "\n".join(results)
    return f"{pulse}\n{out}" if pulse else out


async def _plot_one(s: dict, cmd: str) -> str:
    parts = cmd.split()
    verb = parts[0].lower() if parts else ""

    if verb == "weather":
        return world.climate_report()

    if verb == "dove":
        sub = parts[1].lower() if len(parts) > 1 else ""
        async with db.connect() as conn:
            if not sub:
                pending = await farming.get_gugu_dove_pending(conn, s["id"])
                if not pending:
                    return "没有斑鸠盯梢。昼间 sow/tend 种菜时有概率触发"
                return farming.gugu_dove_prompt_text(pending)
            msg = await farming.resolve_gugu_dove(conn, s, sub)
            await conn.commit()
        return msg

    if verb == "status":
        from . import land as land_mod
        parcels = await db.get_parcels(s["id"])
        return land_mod.sheet_note(s, parcels) + "\n" + "\n".join(_parcel_line(p) for p in parcels)

    if verb in ("land", "买地", "地契", "expand"):
        from . import land as land_mod
        sub = parts[1].lower() if len(parts) > 1 else ""
        buying = verb == "expand" or sub in ("buy", "确认", "ok", "yes", "买")
        if buying:
            async with db.connect() as conn:
                msg = await land_mod.buy(conn, s)
                await db.add_chronicle(
                    "plot",
                    f"{s['name']} 买地至 {s.get('parcel_count')} 块",
                    s["id"],
                    conn=conn,
                )
                await conn.commit()
            return msg
        parcels = await db.get_parcels(s["id"])
        return await land_mod.status_text(s, parcels)

    if verb in ("cohort", "邻居", "neighbors", "neighbour", "peers", "在线", "online"):
        from . import multi as multi_mod
        return await multi_mod.list_neighbors(s, online_only=verb in ("在线", "online"))

    if verb in ("catalog", "crops"):
        from .catalog import crop_catalog_line
        lines = [crop_catalog_line(k) for k in CROPS]
        return (
            "作物清单（短茬快、把数多；稀有慢、把数少。偷菜最多 30%，不能摘空）\n"
            + "\n".join(lines)
            + "\n树清地：plot_ops chop 地块（不必等过熟）"
        )

    if verb == "buy" and len(parts) >= 2 and parts[1] in ("地", "land", "份地"):
        from . import land as land_mod
        async with db.connect() as conn:
            msg = await land_mod.buy(conn, s)
            await db.add_chronicle(
                "plot",
                f"{s['name']} 买地至 {s.get('parcel_count')} 块",
                s["id"],
                conn=conn,
            )
            await conn.commit()
        return msg

    if verb == "buy" and len(parts) >= 3:
        qty, crop = _parse_int(parts[1]), resolve_crop_key(" ".join(parts[2:]))
        if not crop:
            raise ValueError(unknown_crop_message(" ".join(parts[2:])))
        seed = f"seed_{crop}"
        cost = CROPS[crop]["seed_price"] * qty
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"工分票不足，需要 {cost}")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
            await db.add_item(conn, s["id"], seed, qty)
            await conn.commit()
        return f"购入 {CROPS[crop]['name']}种 x{qty}（-{cost} 票）。好感打折去 visit_ops tt buy"

    if verb == "sow" and len(parts) >= 3:
        slot = _parse_int(parts[1], "地块编号")
        crop = resolve_crop_key(" ".join(parts[2:]))
        if not crop:
            raise ValueError(unknown_crop_message(" ".join(parts[2:])))
        seed = f"seed_{crop}"
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            plot = dict(await (await conn.execute(
                "SELECT * FROM parcels WHERE steward_id=? AND slot=?", (s["id"], slot)
            )).fetchone() or {})
            if not plot:
                raise ValueError(f"没有份地 #{slot}")
            from . import land as land_mod
            land_mod.assert_ready(plot)
            if plot.get("crop"):
                raise ValueError(f"#{slot} 已在种植")
            if not await db.take_item(conn, s["id"], seed, 1):
                raise ValueError(f"缺少 {CROPS[crop]['name']}种")
            grow_target, grow_pace, sow_flavor = farming.roll_grow(crop, plot)
            await conn.execute(
                """
                UPDATE parcels SET crop=?, planted_at=?, tended=0, grow_target=?, grow_pace=?,
                harvest_left=0, fertilized=0, watered=0
                WHERE id=?
                """,
                (crop, db.now(), grow_target, grow_pace, plot["id"]),
            )
            extra = await events.roll_after_action(
                s, "sow", conn, protected_parcel_id=plot["id"],
            )
            farm = await farming.roll_farm_event(conn, s, "sow")
            dove = await farming.maybe_gugu_dove_stalk(conn, s, plot["id"])
            await conn.commit()
        msg = f"#{slot} 播下 {CROPS[crop]['emoji']}{CROPS[crop]['name']}\n{sow_flavor}"
        if dove:
            msg += f"\n{dove}"
        elif farm:
            msg += f"\n{farm}"
        return f"{msg}\n{extra}" if extra else msg

    if verb == "tend":
        async with db.connect() as conn:
            cur = await conn.execute(
                "SELECT id FROM parcels WHERE steward_id=? AND crop IS NOT NULL AND tended=0",
                (s["id"],),
            )
            rows = await cur.fetchall()
            hoe = await (await conn.execute(
                "SELECT quantity FROM satchel WHERE steward_id=? AND item='tool_hoe' AND quantity>0",
                (s["id"],),
            )).fetchone()
            from . import hut as hut_mod
            hut_b = await hut_mod.get_bonuses(conn, s["id"])
            for (pid,) in rows:
                await conn.execute("UPDATE parcels SET tended=1 WHERE id=?", (pid,))
                if hoe:
                    await conn.execute(
                        "UPDATE parcels SET grow_target=MAX(120, grow_target-40) WHERE id=? AND grow_target>0",
                        (pid,),
                    )
                if world.current_weather() == "gale" and hut_b.gale_grow < 1:
                    cut = int(80 * (1 - hut_b.gale_grow))
                    await conn.execute(
                        "UPDATE parcels SET grow_target=MAX(120, grow_target-?) WHERE id=? AND grow_target>0",
                        (cut, pid),
                    )
            extra = await events.roll_after_action(s, "tend", conn)
            farm = await farming.roll_farm_event(conn, s, "tend")
            dove = None
            if rows:
                stalk_pid = random.choice(rows)[0]
                dove = await farming.maybe_gugu_dove_stalk(conn, s, stalk_pid)
            disc = await commons.roll_discovery(conn, s, "tend")
            worm_msg = ""
            worm_chance = 0.28 if hoe else 0.14
            if random.random() < worm_chance:
                await db.add_item(conn, s["id"], "bait_worm", random.randint(1, 2))
                worm_msg = "\n翻出蚯蚓饵，钓鱼佬狂喜"
                if hoe:
                    worm_msg += "（锄头加分）"
            await conn.commit()
        msg = f"打理了 {len(rows)} 块份地" if rows else "没有待打理的份地——苗都乖，或你还没种"
        if hoe and rows:
            msg += " · 锄头松土"
        msg += flavor.maybe_suffix(flavor.TEND_SUFFIX)
        if dove:
            msg += f"\n{dove}"
        elif farm:
            msg += f"\n{farm}"
        if disc:
            msg += f"\n{disc}"
        if worm_msg:
            msg += worm_msg
        return f"{msg}\n{extra}" if extra else msg

    if verb == "shake" and len(parts) >= 2:
        slot = int(parts[1])
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            plot = dict(await (await conn.execute(
                "SELECT * FROM parcels WHERE steward_id=? AND slot=?", (s["id"], slot)
            )).fetchone() or {})
            if not plot:
                raise ValueError(f"没有份地 #{slot}")
            from . import land as land_mod
            land_mod.assert_ready(plot)
            if not plot.get("crop"):
                raise ValueError(f"#{slot} 没有可摇的树")
            meta = CROPS.get(plot["crop"], {})
            if not meta.get("shake"):
                raise ValueError(f"{meta.get('name', plot['crop'])} 不能摇，只能 gather")
            result = await farming.shake_tree(conn, s["id"], plot)
            if not result:
                raise ValueError("还没熟，等等再摇")
            item, qty = result
            await conn.commit()
        name = ITEM_NAMES.get(item, item)
        return f"#{slot} 摇下 {name} x{qty}" + flavor.maybe_suffix(["椰子：重力赞助", "树：今天也配合"])

    if verb in ("water", "浇水", "浇"):
        slot_filter: int | None = None
        if len(parts) >= 2:
            slot_filter = _parse_int(parts[1], "地块编号")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            if slot_filter is not None:
                plot = dict(await (await conn.execute(
                    "SELECT * FROM parcels WHERE steward_id=? AND slot=?",
                    (s["id"], slot_filter),
                )).fetchone() or {})
                if not plot:
                    raise ValueError(f"没有份地 #{slot_filter}")
                plots = [plot]
            else:
                plots = [dict(r) for r in await (await conn.execute(
                    "SELECT * FROM parcels WHERE steward_id=? AND crop IS NOT NULL",
                    (s["id"],),
                )).fetchall()]
            from . import land as land_mod
            from . import config as cfg
            lines = []
            for plot in plots:
                land_mod.assert_ready(plot)
                if not plot.get("crop"):
                    if slot_filter is not None:
                        raise ValueError(f"#{plot['slot']} 没种东西")
                    continue
                if farming.plot_ready(plot) or farming.plot_overripe(plot):
                    if slot_filter is not None:
                        raise ValueError(f"#{plot['slot']} 已经熟了，浇水赶不上了。gather 收")
                    continue
                if plot.get("watered"):
                    lines.append(f"#{plot['slot']} 已经浇过水")
                    continue
                new_target, saved = farming.apply_grow_cut(plot, cfg.WATER_CUT_RATE)
                await conn.execute(
                    "UPDATE parcels SET watered=1, grow_target=? WHERE id=?",
                    (new_target, plot["id"]),
                )
                plot["watered"] = 1
                plot["grow_target"] = new_target
                _, _, left = farming.grow_progress(plot)
                eta = farming.format_grow_eta(left) or "马上熟"
                if saved:
                    lines.append(
                        f"#{plot['slot']} 浇了水，成熟提前 {farming.format_grow_eta(saved)}"
                        f"（还需 {eta}）"
                    )
                else:
                    lines.append(f"#{plot['slot']} 浇了水，地更润，生长略快（还需 {eta}）")
            await conn.commit()
        if not lines:
            return "没有能浇的地——先 sow，或已经浇过/熟了"
        return "\n".join(lines)

    if verb in ("fertilize", "施肥"):
        slot_filter: int | None = None
        fert_token = "compost"
        rest = parts[1:]
        if rest:
            try:
                slot_filter = _parse_int(rest[0], "地块编号")
                fert_token = rest[1] if len(rest) > 1 else "compost"
            except ValueError:
                fert_token = rest[0]
        fert_item = resolve_item_key(fert_token) or fert_token
        from .catalog import MANURE
        if fert_item not in MANURE and fert_item != "compost":
            raise ValueError("施肥用堆肥或羊粪/猪粪/牛粪。例子：施肥 1 · 施肥 1 羊粪")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            if slot_filter is not None:
                plot = dict(await (await conn.execute(
                    "SELECT * FROM parcels WHERE steward_id=? AND slot=?",
                    (s["id"], slot_filter),
                )).fetchone() or {})
                if not plot:
                    raise ValueError(f"没有份地 #{slot_filter}")
                plots = [plot]
            else:
                plots = [dict(r) for r in await (await conn.execute(
                    "SELECT * FROM parcels WHERE steward_id=? AND crop IS NOT NULL AND fertilized=0",
                    (s["id"],),
                )).fetchall()]
            from . import land as land_mod
            lines = []
            mascot = s.get("mascot_trait") == "compost"
            for plot in plots:
                land_mod.assert_ready(plot)
                if not plot.get("crop"):
                    if slot_filter is not None:
                        raise ValueError(f"#{plot['slot']} 没种东西")
                    continue
                if farming.plot_ready(plot) or farming.plot_overripe(plot):
                    if slot_filter is not None:
                        raise ValueError(f"#{plot['slot']} 已经熟了，肥料留给下一茬")
                    continue
                if plot.get("fertilized"):
                    lines.append(f"#{plot['slot']} 已经施过肥")
                    continue
                if not await db.take_item(conn, s["id"], fert_item, 1):
                    need = farming.fertilizer_label(fert_item)
                    if not lines:
                        raise ValueError(
                            f"施肥需要 {need} x1（forage / hut_ops barn compost 可攒）"
                        )
                    lines.append(f"{need} 不够了，施到 #{plot['slot']} 前停手")
                    break
                rate = farming.fertilizer_cut_rate(fert_item, compost_mascot=mascot)
                new_target, saved = farming.apply_grow_cut(plot, rate)
                await conn.execute(
                    "UPDATE parcels SET fertilized=1, grow_target=? WHERE id=?",
                    (new_target, plot["id"]),
                )
                plot["fertilized"] = 1
                plot["grow_target"] = new_target
                _, _, left = farming.grow_progress(plot)
                eta = farming.format_grow_eta(left) or "马上熟"
                label = farming.fertilizer_label(fert_item)
                extra = " · 吉祥物堆肥加持" if mascot else ""
                if saved:
                    lines.append(
                        f"#{plot['slot']} 已施{label}，成熟提前 {farming.format_grow_eta(saved)}"
                        f"（还需 {eta}）{extra}"
                    )
                else:
                    lines.append(
                        f"#{plot['slot']} 已施{label}，生长略快（还需 {eta}）{extra}"
                    )
            await conn.commit()
        if not lines:
            return "没有能施肥的地——先 sow，或已经施过/熟了"
        return "\n".join(lines)

    if verb == "scarecrow" and len(parts) >= 2:
        slot = int(parts[1])
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            plot = dict(await (await conn.execute(
                "SELECT * FROM parcels WHERE steward_id=? AND slot=?", (s["id"], slot)
            )).fetchone() or {})
            if not plot:
                raise ValueError(f"没有份地 #{slot}")
            from . import land as land_mod
            land_mod.assert_ready(plot)
            if plot.get("scarecrow"):
                return f"#{slot} 已有稻草人"
            if await db.take_item(conn, s["id"], "scarecrow", 1):
                pass
            else:
                from .config import SCARECROW_COST
                for item, need in SCARECROW_COST.items():
                    if not await db.take_item(conn, s["id"], item, need):
                        raise ValueError(f"扎稻草人需要 scarecrow 或 漂绳x2+堆肥x1")
            await conn.execute("UPDATE parcels SET scarecrow=1 WHERE id=?", (plot["id"],))
            await conn.commit()
        return f"#{slot} 扎好稻草人，鸟儿的自助餐厅关门"

    if verb == "compost" and len(parts) >= 2:
        slot = _parse_int(parts[1], "地块编号")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            plot = dict(await (await conn.execute(
                "SELECT * FROM parcels WHERE steward_id=? AND slot=?", (s["id"], slot)
            )).fetchone() or {})
            if not plot:
                raise ValueError(f"没有份地 #{slot}")
            from . import land as land_mod
            land_mod.assert_ready(plot)
            if not plot.get("crop"):
                raise ValueError(f"#{slot} 空着")
            meta = CROPS.get(plot["crop"], {"name": plot["crop"]})
            overripe = farming.plot_overripe(plot)
            ready = farming.plot_ready(plot)
            if meta.get("tree") and not overripe:
                raise ValueError(
                    f"#{slot} {meta['name']}树还没过熟。树收完会再长，清地请 `plot_ops chop {slot}`；"
                    "过熟才能 compost。"
                )
            if not overripe and not ready:
                raise ValueError("只有过熟/枯的才进堆肥桶")
            crop_name = meta["name"]
            await db.add_item(conn, s["id"], "compost", random.randint(2, 3))
            await conn.execute(
                """
                UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                grow_target=0, grow_pace='', fertilized=0, watered=0, harvest_left=0 WHERE id=?
                """,
                (plot["id"],),
            )
            await conn.commit()
        return f"#{slot} {crop_name} → 堆肥桶，土肥了"

    if verb == "chop" and len(parts) >= 2:
        slot = _parse_int(parts[1], "地块编号")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            plot = dict(await (await conn.execute(
                "SELECT * FROM parcels WHERE steward_id=? AND slot=?", (s["id"], slot)
            )).fetchone() or {})
            if not plot:
                raise ValueError(f"没有份地 #{slot}")
            from . import land as land_mod
            land_mod.assert_ready(plot)
            result = farming.chop_tree(plot)
            if not result["ok"]:
                raise ValueError(f"#{slot} {result['msg']}")
            loot_txt = []
            for iid, n in result["loot"]:
                await db.add_item(conn, s["id"], iid, n)
                loot_txt.append(f"{ITEM_NAMES.get(iid, iid)}×{n}")
            await conn.execute(
                """
                UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                grow_target=0, grow_pace='', fertilized=0, watered=0, harvest_left=0 WHERE id=?
                """,
                (plot["id"],),
            )
            extra = await events.roll_after_action(s, "gather", conn)
            farm = await farming.roll_farm_event(conn, s, "gather")
            await db.add_chronicle(
                "chop", f"{s['name']} 砍倒 #{slot} {result['name']}树", s["id"], conn=conn
            )
            await conn.commit()
        loot_s = "、".join(loot_txt)
        msg = (
            f"#{slot} 砍倒{result['name']}树，地空了。{result['note']} 捡到 {loot_s}。"
            + flavor.maybe_suffix(flavor.CHOP_SUFFIX)
        )
        if farm:
            msg += f"\n{farm}"
        if extra:
            msg += f"\n{extra}"
        return msg

    if verb == "chop":
        raise ValueError("用法: plot_ops chop 地块")

    if verb == "gather":
        slot_filter: int | None = None
        if len(parts) >= 2:
            slot_filter = _parse_int(parts[1], "地块编号")
        got = []
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            parcels = [dict(r) for r in await (await conn.execute(
                "SELECT * FROM parcels WHERE steward_id=?", (s["id"],)
            )).fetchall()]
            if slot_filter is not None:
                parcels = [p for p in parcels if p.get("slot") == slot_filter]
                if not parcels:
                    raise ValueError(f"没有份地 #{slot_filter}")
                from . import land as land_mod
                land_mod.assert_ready(parcels[0])
            for p in parcels:
                if farming.plot_ready(p):
                    if await events.gather_blight_loss(conn, s["id"], p["crop"]):
                        crop_name = CROPS[p["crop"]]["name"]
                        await conn.execute(
                            """
                            UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                            grow_target=0, grow_pace='', fertilized=0, watered=0, harvest_left=0 WHERE id=?
                            """,
                            (p["id"],),
                        )
                        got.append(f"{crop_name}(枯病折损)")
                        continue
                    mult = float(p.get("dove_yield_mult") or 1.0)
                    dove_note = "" if mult == 1.0 else f"(斑鸠收成×{mult:g})"
                    item_key, qty, keep_plot = await farming.gather_yield(conn, s["id"], p)
                    if qty <= 0:
                        crop_name = CROPS[p["crop"]]["name"]
                        got.append(f"{crop_name}(斑鸠啄食，颗粒无收)")
                        if not keep_plot:
                            await conn.execute(
                                """
                                UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                                grow_target=0, grow_pace='', fertilized=0, watered=0, scarecrow=0,
                                dove_yield_mult=1.0, harvest_left=0 WHERE id=?
                                """,
                                (p["id"],),
                            )
                        continue
                    await db.add_item(conn, s["id"], item_key, qty)
                    harvest_note = ""
                    from . import shaonian as shaonian_mod
                    if await shaonian_mod.harvest_bonus_roll(conn, s["id"]):
                        await db.add_item(conn, s["id"], item_key, qty)
                        harvest_note = f"(丰收卦+{qty})"
                    if keep_plot:
                        grow_target, grow_pace, _ = farming.roll_grow(p["crop"], p)
                        await conn.execute(
                            """
                            UPDATE parcels SET planted_at=?, tended=0, grow_target=?, grow_pace=?,
                            fertilized=0, watered=0, harvest_left=0 WHERE id=?
                            """,
                            (db.now(), grow_target, grow_pace, p["id"]),
                        )
                    else:
                        await conn.execute(
                            """
                            UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                            grow_target=0, grow_pace='', fertilized=0, watered=0, scarecrow=0, harvest_left=0 WHERE id=?
                            """,
                            (p["id"],),
                        )
                    tree_note = "（树还在）" if keep_plot else ""
                    if item_key.startswith("seed_"):
                        got.append(
                            f"{CROPS[p['crop']]['name']}种(过熟) x{qty}{harvest_note}{tree_note}"
                        )
                    else:
                        got.append(
                            f"{CROPS[p['crop']]['name']} x{qty}{harvest_note}{dove_note}{tree_note}"
                        )
                elif farming.plot_overripe(p):
                    if random.random() < 0.5:
                        await db.add_item(conn, s["id"], "compost", 2)
                        got.append(f"{CROPS[p['crop']]['name']}(堆肥)")
                    await conn.execute(
                        """
                        UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                        grow_target=0, grow_pace='', fertilized=0, watered=0, harvest_left=0 WHERE id=?
                        """,
                        (p["id"],),
                    )
            extra = await events.roll_after_action(s, "gather", conn)
            farm = await farming.roll_farm_event(conn, s, "gather")
            found: list[tuple[str, int, str]] = []
            disc = await commons.roll_discovery(conn, s, "gather", found=found)
            for item, qty, iname in found:
                got.append(f"{iname} x{qty}（发现 · {item}）")
            if got:
                await survival.bump(conn, s["id"], satiety=min(6, 2 + len(got)))
            await conn.commit()
        if not got:
            nearest = None
            min_left = None
            for p in parcels:
                if p.get("crop") and not farming.plot_ready(p) and not farming.plot_overripe(p):
                    _, _, left = farming.grow_progress(p)
                    if min_left is None or left < min_left:
                        min_left = left
                        nearest = p
            wait_hint = (
                "\n等待期间可做: tend · 浇水 · 施肥 地块 · forage · tide_ops net|cast · "
                "tide_ops beach scan · kitchen_ops eat · visit_ops clinic"
            )
            msg = "没有可收成的作物"
            if slot_filter is not None and parcels:
                p = parcels[0]
                if not p.get("crop"):
                    msg = f"#{slot_filter} 休耕，无可收"
                elif not farming.plot_ready(p) and not farming.plot_overripe(p):
                    cname = CROPS[p["crop"]]["name"]
                    _, _, left = farming.grow_progress(p)
                    msg = f"#{slot_filter} {cname} 还需 {farming.format_grow_eta(left)}{wait_hint}"
                else:
                    msg = f"#{slot_filter} 暂无可收（plot_ops status 查看详情）"
            elif nearest is not None and min_left is not None:
                cname = CROPS[nearest["crop"]]["name"]
                slot = nearest.get("slot", "?")
                msg += f"（#{slot} {cname} 还需 {farming.format_grow_eta(min_left)}）{wait_hint}"
            return f"{msg}\n{extra}" if extra else msg
        await db.add_chronicle("gather", f"{s['name']} 收成 {', '.join(got)}", s["id"])
        from . import multi
        bonus_msg = None
        for crop_name in got:
            if "发现" in crop_name or "枯病" in crop_name or "堆肥" in crop_name:
                continue
            crop_key = next(
                (k for k, v in CROPS.items() if crop_name.startswith(v["name"])),
                None,
            )
            if crop_key:
                b = await multi.on_league_item(s["id"], f"crop_{crop_key}", 1)
                if b:
                    bonus_msg = b
        if bonus_msg:
            await db.add_chronicle("league", bonus_msg, None)
            base = f"收成: {', '.join(got)}\n{bonus_msg}"
            if farm:
                base += f"\n{farm}"
            if disc:
                base += f"\n{disc}"
            return f"{base}\n{extra}" if extra else base
        base = f"收成: {', '.join(got)}"
        base += flavor.maybe_suffix(flavor.GATHER_SUFFIX)
        if farm:
            base += f"\n{farm}"
        if disc:
            base += f"\n{disc}"
        return f"{base}\n{extra}" if extra else base

    if verb == "forage":
        today = db.now() // FORAGE_COOLDOWN_DAY
        last = s["forage_at"] // FORAGE_COOLDOWN_DAY if s["forage_at"] else 0
        if today <= last:
            raise ValueError("今日已在边际采过，明天再来")
        roll = random.choices(FORAGE_LOOT, weights=[x[3] for x in FORAGE_LOOT])[0]
        item_id, label, qty, _ = roll
        async with db.connect() as conn:
            await db.add_item(conn, s["id"], item_id, qty)
            await conn.execute("UPDATE stewards SET forage_at=? WHERE id=?", (db.now(), s["id"]))
            await survival.bump(conn, s["id"], satiety=4)
            extra = await events.roll_after_action(s, "forage", conn)
            disc = await commons.roll_discovery(conn, s, "forage")
            await conn.commit()
        await db.add_chronicle("forage", f"{s['name']} 在份地边际采到 {label}", s["id"])
        msg = f"边际采集：{label} x{qty}"
        msg += flavor.maybe_suffix(flavor.FORAGE_SUFFIX)
        if disc:
            msg += f"\n{disc}"
        return f"{msg}\n{extra}" if extra else msg

    if verb == "post" and len(parts) >= 3:
        peer, text = parts[1], " ".join(parts[2:])
        target = await db.get_steward_by_name(peer)
        if not target:
            raise ValueError("找不到该管理员")
        async with db.connect() as conn:
            await conn.execute(
                "INSERT INTO beacons (author_id, tag, body, created_at) VALUES (?, 'notice', ?, ?)",
                (s["id"], f"@{peer}: {text[:180]}", db.now()),
            )
            await conn.commit()
        return f"已在公告栏 @ {peer}"

    if verb in ("scrump", "偷菜", "逾篱"):
        if len(parts) < 2:
            from . import multi as multi_mod
            roster = await multi_mod.list_neighbors(s, online_only=False)
            raise ValueError("用法: plot_ops 偷菜 名字 [地块]\n" + roster)
        slot = None
        if len(parts) >= 3:
            slot = _parse_int(parts[2], "地块编号")
        return await events.manual_scrump(s, parts[1], slot)

    if verb == "hedge_note":
        if len(parts) < 3:
            raise ValueError("用法: plot_ops hedge_note 管理员名 篱笆条正文")
        peer, text = parts[1], " ".join(parts[2:])
        target = await db.get_steward_by_name(peer)
        if not target:
            raise ValueError("找不到该管理员")
        async with db.connect() as conn:
            await conn.execute(
                "INSERT INTO beacons (author_id, tag, body, created_at) VALUES (?, 'hedge', ?, ?)",
                (s["id"], f"@{peer} 篱笆条：{text[:160]}", db.now()),
            )
            await conn.commit()
        from . import lore as lore_mod
        hint = lore_mod.hedge_note_hint()
        return f"篱笆条已留给 {peer}\n（篱间文学灵感：「{hint}」· lore_ops hedge 换一条）"

    if verb == "amends" and len(parts) >= 2:
        peer = await db.get_steward_by_name(parts[1])
        if not peer:
            raise ValueError("找不到该管理员")
        async with db.connect() as conn:
            await survival.bump(conn, s["id"], standing=10, mist_wit=3)
            await survival.bump(conn, peer["id"], standing=3)
            await conn.commit()
        msg = f"{s['name']} 向 {peer['name']} 为逾篱之事致歉"
        msg += f" — {flavor.pick(flavor.AMENDS_QUIPS)}"
        await db.add_chronicle("amends", msg, s["id"], peer["id"])
        await db.add_chronicle(
            "notice",
            f"{s['name']} 向你致歉（逾篱），你的档信回暖 +3",
            peer["id"],
            s["id"],
        )
        return msg + f"\n{peer['name']} 已收到通知（档信 +3）"

    raise ValueError(
        f"未知 plot 指令: {cmd}。常用: status · sow 1 甘蓝 · tend · 浇水 1 · 施肥 1 · gather 1"
    )


async def tide_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    pulse = await events.maybe_world_pulse(s)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "status"
    tide = world.current_tide()

    if verb == "status":
        stock = await db.get_satchel(s["id"])
        sea = {k: v for k, v in stock.items() if k.startswith("fish_")}
        msg = f"潮汐 {world.tide_label(tide)}\n" + (
            "\n".join(f"{ITEM_NAMES.get(k,k)} x{v}" for k, v in sea.items()) or "暂无渔获"
        )
        return f"{pulse}\n{msg}" if pulse else msg

    if verb == "catalog":
        from . import catches as catches_mod
        async with db.connect() as conn:
            return await catches_mod.fish_catalog(conn, s["id"])

    if verb == "net":
        cost = 4
        async with db.connect() as conn:
            await commons.maybe_spawn_commons(conn, steward_id=s["id"])
            from . import energy as energy_mod, gear
            energy_cost, catch_bonus, rarity_bonus, empty_reduce = await energy_mod.net_energy_cost(conn, s["id"])
            stats = await gear.get_stats(conn, s["id"])
            if stats["net"]["tier"] < 1:
                raise ValueError("先 tide_ops gear upgrade net 升到 T1 粗渔网（或 tide_ops tool buy net_basic 兼容）")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"撒网需要 {cost} 工分票")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
            await energy_mod.spend(conn, s["id"], energy_cost, action="撒网")
            extra = await events.roll_after_action(s, "net", conn)
            disc = await commons.roll_discovery(conn, s, "net")
            from . import shaonian as shaonian_mod
            daily = await shaonian_mod.get_daily(conn, s["id"])
            fortune_key = daily.get("fortune") or ""
            no_empty = await shaonian_mod.fishing_no_empty(conn, s["id"])
            await conn.commit()
        empty_chance = 0.18 - await events.net_bonus_chance() - empty_reduce - catch_bonus * 0.4
        if not no_empty and random.random() < max(0.04, empty_chance):
            msg = f"空网 T{stats['net']['tier']}，只有水草"
            if extra:
                msg += f"\n{extra}"
            if disc:
                msg += f"\n{disc}"
            return f"{pulse}\n{msg}" if pulse else msg
        rarity_cap = 3 + rarity_bonus
        catch = shaonian_mod.pick_fish_with_fortune(tide, rarity_cap, fortune_key)
        if catch_bonus and random.random() < catch_bonus:
            catch = shaonian_mod.pick_fish_with_fortune(tide, min(6, rarity_cap + 1), fortune_key)
        meta = SEA_CATCH[catch]
        async with db.connect() as conn:
            await db.add_item(conn, s["id"], f"fish_{catch}", 1)
            from . import catches as catches_mod
            await catches_mod.record_catch(conn, s["id"], f"fish_{catch}")
            await survival.bump(conn, s["id"], satiety=5)
            from . import marine as marine_mod
            voyage = await marine_mod._get_voyage(conn, s["id"])
            if voyage and voyage.get("status") == "sailing":
                await marine_mod.append_voyage_fish(conn, voyage, f"fish_{catch}")
                legged = await marine_mod.try_legged_fish_encounter(conn, s, voyage)
            else:
                legged = None
            await conn.commit()
        msg = (
            f"{s['name']} 在{world.tide_label(tide)}网到 {meta['emoji']}{meta['name']} "
            f"[网T{stats['net']['tier']}]"
        )
        msg += flavor.maybe_suffix(flavor.NET_SUFFIX)
        await db.add_chronicle("tide", msg, s["id"])
        from . import multi
        bonus = await multi.on_league_item(s["id"], f"fish_{catch}", 1)
        if bonus:
            await db.add_chronicle("league", bonus, None)
            msg = msg + f"\n{bonus}"
        if extra:
            msg += f"\n{extra}"
        if disc:
            msg += f"\n{disc}"
        if legged:
            msg += f"\n{legged}"
        return f"{pulse}\n{msg}" if pulse else msg

    if verb == "cast":
        cost = 3
        async with db.connect() as conn:
            from . import energy as energy_mod, gear
            stats = await gear.get_stats(conn, s["id"])
            rod, bait = stats["rod"], stats["bait"]
            if rod["tier"] < 1:
                raise ValueError("先 tide_ops gear upgrade rod（T1 竹钓竿 30票）")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"坐钓需要 {cost} 工分票")
            if not await db.take_item(conn, s["id"], "bait_worm", 1):
                raise ValueError("缺少蚯蚓饵 bait_worm（tend 地块 / tide_ops dig 获取）")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
            await energy_mod.spend(conn, s["id"], rod["energy"], action="坐钓")
            extra = await events.roll_after_action(s, "net", conn)
            disc = await commons.roll_discovery(conn, s, "net")
            from . import shaonian as shaonian_mod
            daily = await shaonian_mod.get_daily(conn, s["id"])
            fortune_key = daily.get("fortune") or ""
            no_empty = await shaonian_mod.fishing_no_empty(conn, s["id"])
            await conn.commit()
        catch_b, rarity_b, empty_b, _ = gear.combined_fish_bonus(bait=bait, rod=rod)
        empty_chance = 0.24 - empty_b - await events.net_bonus_chance()
        if not no_empty and random.random() < max(0.05, empty_chance):
            msg = f"空杆 饵T{bait['tier']} 竿T{rod['tier']}——鱼看了直摇头"
            parts = [x for x in (pulse, msg, extra) if x]
            return "\n".join(parts)
        rarity_cap = 3 + rarity_b
        catch = shaonian_mod.pick_fish_with_fortune(tide, rarity_cap, fortune_key)
        if catch_b and random.random() < catch_b + 0.08:
            catch = shaonian_mod.pick_fish_with_fortune(tide, min(6, rarity_cap + 1), fortune_key)
        meta = SEA_CATCH[catch]
        async with db.connect() as conn:
            await db.add_item(conn, s["id"], f"fish_{catch}", 1)
            from . import catches as catches_mod
            await catches_mod.record_catch(conn, s["id"], f"fish_{catch}")
            await survival.bump(conn, s["id"], satiety=4)
            from . import marine as marine_mod
            voyage = await marine_mod._get_voyage(conn, s["id"])
            legged = None
            if voyage and voyage.get("status") == "sailing":
                await marine_mod.append_voyage_fish(conn, voyage, f"fish_{catch}")
                legged = await marine_mod.try_legged_fish_encounter(conn, s, voyage)
            await conn.commit()
        msg = (
            f"坐钓 {meta['emoji']}{meta['name']} "
            f"[饵T{bait['tier']} 竿T{rod['tier']}]"
        )
        msg += flavor.maybe_suffix(["竿弯了，票没白花", "饵对路，鱼自来"])
        await db.add_chronicle("tide", f"{s['name']} 坐钓 {meta['name']}", s["id"])
        if extra:
            msg += f"\n{extra}"
        if disc:
            msg += f"\n{disc}"
        if legged:
            msg += f"\n{legged}"
        return f"{pulse}\n{msg}" if pulse else msg

    if verb == "bottle":
        from . import bottles
        return await bottles.bottle_ops(key_id, "fish")

    raise ValueError(f"未知 tide 指令: {command}")


async def _collect_bottle_replies(conn: aiosqlite.Connection, steward_id: int) -> list[str]:
    prev = conn.row_factory
    conn.row_factory = aiosqlite.Row
    try:
        rows = await (await conn.execute(
            """
            SELECT b.id, b.reply_body, r.name AS from_name
            FROM drift_bottles b
            JOIN stewards r ON r.id=b.reply_by
            WHERE b.author_id=? AND b.reply_at IS NOT NULL
            ORDER BY b.reply_at DESC LIMIT 3
            """,
            (steward_id,),
        )).fetchall()
    finally:
        conn.row_factory = prev
    return [
        f"漂流瓶 #{r['id']} 有回瓶：{r['from_name']} — {r['reply_body'][:60]}"
        for r in rows
    ]


async def _collect_handoffs(conn: aiosqlite.Connection, steward_id: int) -> list[str]:
    """台阶上的离线交接进袋，并标已取。"""
    prev = conn.row_factory
    conn.row_factory = aiosqlite.Row
    try:
        rows = await (await conn.execute(
            """
            SELECT h.id, h.item, h.quantity, p.name AS from_name
            FROM handoffs h JOIN stewards p ON p.id=h.from_id
            WHERE h.to_id=? AND h.picked_up=0
            ORDER BY h.created_at
            """,
            (steward_id,),
        )).fetchall()
    finally:
        conn.row_factory = prev
    notes = []
    for r in rows:
        await db.add_item(conn, steward_id, r["item"], r["quantity"])
        await conn.execute("UPDATE handoffs SET picked_up=1 WHERE id=?", (r["id"],))
        label = ITEM_NAMES.get(r["item"], r["item"])
        notes.append(f"台阶交接：{r['from_name']} 放下的 {label} x{r['quantity']} 已入袋")
    return notes


async def shed_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    chunks = [c.strip() for c in command.split(";") if c.strip()]
    return "\n".join([await _shed_one(s, c) for c in chunks])


async def _shed_one(s: dict, cmd: str) -> str:
    parts = cmd.split()
    verb = parts[0].lower()

    if verb == "status":
        async with db.connect() as conn:
            notes = await _collect_handoffs(conn, s["id"])
            await conn.commit()
        base = f"温室: {s['greenhouse_label']}" if s["greenhouse"] else "尚未搭建温室"
        if s["greenhouse"]:
            base += " · 份地 #99 为温室内槽，plot_ops sow 99 …"
        if notes:
            return base + "\n" + "\n".join(notes)
        return base

    if verb == "erect":
        if s["greenhouse"]:
            return "已有温室"
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < GREENHOUSE_COST:
                raise ValueError(f"搭建温室需要 {GREENHOUSE_COST} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-?, greenhouse=1 WHERE id=?",
                (GREENHOUSE_COST, s["id"]),
            )
            await conn.execute(
                "INSERT INTO parcels (steward_id, slot, greenhouse, tended) VALUES (?, 99, 1, 0)",
                (s["id"],),
            )
            await conn.commit()
        await db.add_chronicle("shed", f"{s['name']} 搭好了温室", s["id"])
        return f"温室就绪（-{GREENHOUSE_COST} 票），份地 #99 为温室内槽位"

    if verb == "label" and len(parts) >= 2:
        if not s["greenhouse"]:
            raise ValueError("先 erect 温室")
        label = " ".join(parts[1:])[:40]
        async with db.connect() as conn:
            await conn.execute("UPDATE stewards SET greenhouse_label=? WHERE id=?", (label, s["id"]))
            await conn.commit()
        return f"温室命名为「{label}」"

    if verb == "visit" and len(parts) >= 2:
        peer = await db.get_steward_by_name(parts[1])
        if not peer:
            raise ValueError("找不到管理员")
        online = db.now() - peer["last_active_at"] <= 900
        gh = peer["greenhouse_label"] or "无名温室"
        return f"拜访 {peer['name']}：{gh}（{'在档口' if online else '不在'}）"

    if verb == "handoff":
        m = re.match(r"handoff\s+(\S+)\s+(\S+)\s+(\d+)$", cmd, re.I)
        if not m:
            raise ValueError("用法: handoff 名字 物品 数量")
        peer_name, item, qty_s = m.group(1), m.group(2), m.group(3)
        qty = int(qty_s)
        peer = await db.get_steward_by_name(peer_name)
        if not peer:
            raise ValueError("找不到管理员")
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], item, qty):
                raise ValueError("行囊数量不足")
            online = db.now() - peer["last_active_at"] <= 900
            if online:
                await db.add_item(conn, peer["id"], item, qty)
                await conn.commit()
                msg = f"{s['name']} 当面交给 {peer['name']} {ITEM_NAMES.get(item,item)} x{qty}"
                await db.add_chronicle("handoff", msg, s["id"], peer["id"])
                return msg
            await conn.execute(
                "INSERT INTO handoffs (from_id, to_id, item, quantity, created_at) VALUES (?,?,?,?,?)",
                (s["id"], peer["id"], item, qty, db.now()),
            )
            await conn.commit()
        return f"已把 {ITEM_NAMES.get(item,item)} x{qty} 放在 {peer_name} 温室台阶（对方 steward_ops sheet / plot_ops shed status 时入袋）"

    raise ValueError(f"未知 shed 指令: {cmd}")


async def mascot_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        if not s["mascot_name"]:
            return "尚无吉祥物，adopt 名字 特质(scout/lucky/compost)"
        from . import social as social_mod
        hint = social_mod.mascot_spirit_hint(s["mascot_spirit"])
        base = f"{s['mascot_name']} [{s['mascot_trait']}] 士气 {s['mascot_spirit']}/100"
        mult = social_mod.mascot_trait_mult(s["mascot_spirit"])
        if mult != 1.0:
            base += f" · 特质效果 ×{mult:.2f}"
        if hint:
            base += f"\n{hint}"
        return base

    if verb == "adopt" and len(parts) >= 3:
        name, trait = parts[1][:20], parts[2][:16]
        if trait not in ("scout", "lucky", "compost"):
            raise ValueError("特质必须是 scout / lucky / compost")
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET mascot_name=?, mascot_trait=?, mascot_spirit=70 WHERE id=?",
                (name, trait, s["id"]),
            )
            await conn.commit()
        await db.add_chronicle("mascot", f"{s['name']} 认领吉祥物 {name}", s["id"])
        return f"吉祥物 {name} 入驻（{trait}）"

    if verb == "upkeep":
        if not s["mascot_name"]:
            raise ValueError("还没有吉祥物")
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < 4:
                raise ValueError("upkeep 需要 4 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-4, mascot_spirit=MIN(100, mascot_spirit+12) WHERE id=?",
                (s["id"],),
            )
            await conn.commit()
        return f"{s['mascot_name']} 士气上升"

    if verb == "feed":
        if not s["mascot_name"]:
            raise ValueError("还没有吉祥物")
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], "feed_pet", 1):
                raise ValueError("需要宠物饲料 — visit_ops tt buy 宠物饲料")
            await conn.execute(
                "UPDATE stewards SET mascot_spirit=MIN(100, mascot_spirit+18) WHERE id=?",
                (s["id"],),
            )
            await conn.commit()
        return f"{s['mascot_name']} 吃了宠物饲料，士气上升"

    if verb == "train":
        if not s["mascot_name"]:
            raise ValueError("还没有吉祥物")
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET mascot_spirit=MIN(100, mascot_spirit+8) WHERE id=?",
                (s["id"],),
            )
            await conn.commit()
        return f"训练了 {s['mascot_name']} 的 {s['mascot_trait']} 特质"

    raise ValueError(f"未知 mascot 指令: {command}（status/adopt/upkeep/feed/train）")


async def beacon_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "scan"

    if verb == "scan":
        tag = parts[1] if len(parts) > 1 else None
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            if tag and tag.isdigit():
                row = await (await conn.execute(
                    """
                    SELECT b.id, b.tag, b.body, a.name FROM beacons b
                    JOIN stewards a ON a.id=b.author_id WHERE b.id=?
                    """,
                    (int(tag),),
                )).fetchone()
                if not row:
                    raise ValueError("没有这条公告")
                replies = await (await conn.execute(
                    """
                    SELECT r.body, a.name FROM beacon_replies r
                    JOIN stewards a ON a.id=r.author_id
                    WHERE r.beacon_id=? ORDER BY r.created_at
                    """,
                    (row["id"],),
                )).fetchall()
                lines = [f"#{row['id']} [{row['tag']}] {row['name']}: {row['body']}"]
                if replies:
                    lines.append("回复:")
                    lines.extend(f"  · {r['name']}: {r['body']}" for r in replies)
                else:
                    lines.append("还没有回复 — respond 编号 正文")
                return "\n".join(lines)
            if tag:
                rows = await (await conn.execute(
                    "SELECT b.id, b.tag, b.body, a.name FROM beacons b JOIN stewards a ON a.id=b.author_id WHERE b.tag=? ORDER BY b.created_at DESC LIMIT 12",
                    (tag,),
                )).fetchall()
            else:
                rows = await (await conn.execute(
                    "SELECT b.id, b.tag, b.body, a.name FROM beacons b JOIN stewards a ON a.id=b.author_id ORDER BY b.created_at DESC LIMIT 12"
                )).fetchall()
            if not rows:
                return "公告栏暂无帖子"
            lines = []
            for r in rows:
                n = (await (await conn.execute(
                    "SELECT COUNT(*) FROM beacon_replies WHERE beacon_id=?", (r["id"],)
                )).fetchone())[0]
                tail = f" ↩{n}" if n else ""
                lines.append(f"#{r['id']} [{r['tag']}] {r['name']}: {r['body'][:80]}{tail}")
            lines.append("scan 编号 看回复 · respond 编号 正文")
            return "\n".join(lines)

    if verb == "post" and len(parts) >= 3:
        tag, body = parts[1][:20], parts[2][:220]
        async with db.connect() as conn:
            await conn.execute(
                "INSERT INTO beacons (author_id, tag, body, created_at) VALUES (?,?,?,?)",
                (s["id"], tag, body, db.now()),
            )
            await conn.commit()
        return f"公告已发布 [{tag}]"

    if verb == "respond" and len(parts) >= 3:
        bid, body = int(parts[1]), parts[2][:200]
        async with db.connect() as conn:
            await conn.execute(
                "INSERT INTO beacon_replies (beacon_id, author_id, body, created_at) VALUES (?,?,?,?)",
                (bid, s["id"], body, db.now()),
            )
            await conn.commit()
        return "已回复公告"

    raise ValueError(f"未知 beacon 指令: {command}")


async def swap_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=3)
    verb = parts[0].lower() if parts else "list"

    if verb == "list":
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (await conn.execute(
                """
                SELECT l.id, l.item, l.quantity, l.note, d.name
                FROM swap_lots l JOIN stewards d ON d.id=l.depositor_id
                WHERE l.claimed_by IS NULL ORDER BY l.created_at DESC LIMIT 15
                """
            )).fetchall()
        if not rows:
            return "交换台为空"
        return "\n".join(
            f"#{r['id']} {r['name']} 出让 {ITEM_NAMES.get(r['item'],r['item'])} x{r['quantity']} {r['note']}"
            for r in rows
        )

    if verb == "offer" and len(parts) >= 3:
        item_key = resolve_item_key(parts[1])
        if not item_key:
            raise ValueError(unknown_item_message(parts[1]))
        qty = _parse_int(parts[2])
        note = parts[3] if len(parts) > 3 else ""
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], item_key, qty):
                raise ValueError(
                    f"行囊不足 {ITEM_NAMES.get(item_key, item_key)}（id: {item_key}）"
                )
            await conn.execute(
                "INSERT INTO swap_lots (depositor_id, item, quantity, note, created_at) VALUES (?,?,?,?,?)",
                (s["id"], item_key, qty, note[:80], db.now()),
            )
            await conn.commit()
        await db.add_chronicle(
            "swap",
            f"{s['name']} 在交换台挂单 {ITEM_NAMES.get(item_key, item_key)} x{qty}",
            s["id"],
        )
        return f"挂单成功 · {ITEM_NAMES.get(item_key, item_key)}（{item_key}）x{qty}"

    if verb == "claim" and len(parts) >= 2:
        from . import social as social_mod
        lot_id = _parse_int(parts[1], "挂单编号")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            lot = dict(await (await conn.execute(
                "SELECT * FROM swap_lots WHERE id=? AND claimed_by IS NULL", (lot_id,)
            )).fetchone() or {})
            if not lot:
                raise ValueError("该挂单不存在或已被领走")
            if lot["depositor_id"] == s["id"]:
                raise ValueError("不能领取自己的挂单")
            rapport = await social_mod.get_rapport(s["id"], lot["depositor_id"], conn=conn)
            claim_fee = social_mod.swap_claim_fee(rapport)
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < claim_fee:
                raise ValueError(f"领取需要 {claim_fee} 票")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (claim_fee, s["id"]))
            await db.add_item(conn, s["id"], lot["item"], lot["quantity"])
            await conn.execute("UPDATE swap_lots SET claimed_by=? WHERE id=?", (s["id"], lot_id))
            await conn.commit()
        fee_note = f"（协作度≥{social_mod.RAPPORT_SWAP_DISCOUNT} 手续费 {claim_fee} 票）" if claim_fee < SWAP_CLAIM_FEE else ""
        return f"领取 #{lot_id}（-{claim_fee} 票）{fee_note}"

    if verb == "cancel" and len(parts) >= 2:
        lot_id = _parse_int(parts[1], "挂单编号")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            lot = dict(await (await conn.execute(
                "SELECT * FROM swap_lots WHERE id=? AND depositor_id=? AND claimed_by IS NULL",
                (lot_id, s["id"]),
            )).fetchone() or {})
            if not lot:
                raise ValueError("找不到可撤回的挂单")
            await db.add_item(conn, s["id"], lot["item"], lot["quantity"])
            await conn.execute("DELETE FROM swap_lots WHERE id=?", (lot_id,))
            await conn.commit()
        return f"已撤回 #{lot_id}，物品退回行囊"

    raise ValueError(f"未知 swap 指令: {command}（list/offer/claim/cancel）")


async def _tote_one(s: dict, command: str) -> str:
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "list"
    if verb == "list":
        stock = await db.get_satchel(s["id"])
        lines = [f"工分票: {s['tickets']}"]
        for item, qty in stock.items():
            price = suggested_price(item) or ITEM_PRICES.get(item, 0)
            name = item_label(item)
            if item.startswith("fit_") or item.startswith("deco_"):
                lines.append(f"  {name} x{qty} · {item} · 卖掉走 hut_ops 卖掉")
            else:
                lines.append(f"  {name} x{qty} · {item} · vend {price}/个")
        return "\n".join(lines) if stock else f"工分票: {s['tickets']}\n行囊空"
    if verb == "vend" and len(parts) >= 3:
        # 支持批量：vend item1 qty1 item2 qty2 ...（每对一个物品+数量）
        tokens = parts[1:]
        if len(tokens) % 2 != 0:
            raise ValueError("用法: vend 物品 数量 [物品 数量 ...]（物品和数量成对）")
        pairs = []
        for i in range(0, len(tokens), 2):
            item_key = resolve_item_key(tokens[i])
            if not item_key:
                raise ValueError(unknown_item_message(tokens[i]))
            qty = _parse_int(tokens[i + 1])
            price = suggested_price(item_key) or ITEM_PRICES.get(item_key, 0)
            if not price:
                raise ValueError(f"不可出售 {item_label(item_key)}（{item_key}）")
            if item_key.startswith("fit_") or item_key.startswith("deco_"):
                raise ValueError(
                    "旧家具按折旧卖：墙上的 hut_ops 卖掉 槽位 确认；"
                    "行囊里的 hut_ops 卖掉 装件名 确认"
                )
            pairs.append((item_key, qty, price))
        async with db.connect() as conn:
            results = []
            for item_key, qty, price in pairs:
                if not await db.take_item(conn, s["id"], item_key, qty):
                    raise ValueError(f"数量不足（需要 {item_key} x{qty}）")
                gain = price * qty
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets+? WHERE id=?", (gain, s["id"])
                )
                results.append((item_key, qty, gain))
            await conn.commit()
        if len(results) == 1:
            item_key, qty, gain = results[0]
            return f"出售 {ITEM_NAMES.get(item_key, item_key)}（{item_key}）x{qty}，+{gain} 票"
        total = sum(g for _, _, g in results)
        lines = [f"  {ITEM_NAMES.get(k, k)} x{q}，+{g} 票" for k, q, g in results]
        lines.append(f"合计 +{total} 票")
        return "批量出售：\n" + "\n".join(lines)
    if verb == "gift" and len(parts) >= 4:
        peer_name = parts[1]
        token = parts[2]
        qty = _parse_int(parts[3])
        if qty < 1:
            raise ValueError("送礼数量至少 1")
        note = " ".join(parts[4:])[:80] if len(parts) > 4 else ""
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            peer_row = await (await conn.execute(
                "SELECT * FROM stewards WHERE name = ? COLLATE NOCASE",
                (peer_name.strip(),),
            )).fetchone()
            if not peer_row:
                raise ValueError(f"找不到管理员「{peer_name}」")
            peer = dict(peer_row)
            if peer["id"] == s["id"]:
                raise ValueError("不能送礼给自己")
            from . import multi as multi_mod
            token_l = token.lower()
            if token_l in ("tickets", "票", "工分票"):
                cur = await conn.execute(
                    "SELECT tickets FROM stewards WHERE id=?", (s["id"],)
                )
                if (await cur.fetchone())[0] < qty:
                    raise ValueError(f"工分票不足，需要 {qty} 票")
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                    (qty, s["id"]),
                )
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                    (qty, peer["id"]),
                )
                gift_line = f"{qty} 工分票"
                item_key = None
            else:
                item_key = resolve_item_key(token)
                if not item_key:
                    raise ValueError(unknown_item_message(token))
                if not await db.take_item(conn, s["id"], item_key, qty):
                    raise ValueError(
                        f"行囊不足 {ITEM_NAMES.get(item_key, item_key)}（{item_key}）x{qty}"
                    )
                await db.add_item(conn, peer["id"], item_key, qty)
                gift_line = f"{ITEM_NAMES.get(item_key, item_key)}（{item_key}）x{qty}"
            await multi_mod._bump_rapport(conn, s["id"], peer["id"], 3)
            chronicle = f"{s['name']} 送礼给 {peer['name']}：{gift_line}"
            if note:
                chronicle += f" — {note}"
            await db.add_chronicle("gift", chronicle, s["id"], peer["id"], conn=conn)
            await conn.commit()
        msg = f"已送礼给 {peer['name']}：{gift_line}"
        if note:
            msg += f"（{note}）"
        msg += " · 协作度 +3"
        return msg + flavor.maybe_suffix([
            "对方行囊已到账，不用等台阶",
            "礼轻情意重，联盟记一笔",
            "篱边人情：送了就要认",
        ])
    raise ValueError(
        f"未知 tote 指令: {command}（list / vend 物品 数量 / gift 名字 物品|票 数量 [留言]）"
    )


async def tote_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts_cmd = [c.strip() for c in command.split(";") if c.strip()]
    if len(parts_cmd) > 1:
        return "\n".join([await _tote_one(s, c) for c in parts_cmd])
    return await _tote_one(s, command.strip())


async def hearth_ops(key_id: int, command: str) -> str:
    from . import kitchen
    cmd = command.strip() or "recipes"
    if cmd.split()[0].lower() == "catalog":
        cmd = "recipes"
    return await kitchen.kitchen_ops(key_id, cmd)

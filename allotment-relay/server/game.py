import random
import re
from typing import Any

import aiosqlite

from . import db, events, flavor, farming, survival, world
from . import commons
from .catalog import (
    CROPS,
    resolve_crop_key,
    unknown_crop_message,
    FORAGE_LOOT,
    ITEM_NAMES,
    ITEM_PRICES,
    SEA_CATCH,
    weighted_fish_pick,
)
from .config import (
    BADGES,
    BOATS,
    FORAGE_COOLDOWN_DAY,
    GREENHOUSE_COST,
    GUILD_TICKETS,
    SWAP_CLAIM_FEE,
    BAR_MANDATORY_DAYS,
)


def _parcel_line(plot: dict) -> str:
    slot = plot["slot"]
    gh = "🪴" if plot.get("greenhouse") else ""
    if not plot.get("crop"):
        return f"  #{slot}{gh}: 休耕"
    meta = CROPS.get(plot["crop"], {"name": plot["crop"], "emoji": "🌱"})
    state = farming.parcel_status(plot)
    extra = farming.parcel_extra(plot)
    return f"  #{slot}{gh}: {meta['emoji']}{meta['name']}（{state}{extra}）"


async def require_steward(key_id: int, *, exempt_duty: bool = False) -> dict[str, Any]:
    s = await db.get_steward_by_key_id(key_id)
    if not s or not s["enrolled"]:
        raise ValueError("请先调用 steward_enroll 登记管理员身份")
    if not exempt_duty:
        from . import bar
        await bar.assert_bar_duty(s)
    await db.touch_steward(s["id"])
    return s


async def relay_manual() -> str:
    return "\n".join([
        "# Allotment Relay 手册",
        "",
        "沿海协作份地：管理员通过 MCP 打理份地、响应天气与潮汐、在交换台互助。",
        f"当前：{world.climate_line()}",
        "",
        "工具一览：",
        "  steward_enroll / steward_sheet / steward_revise / peer_sheet",
        "  plot_ops — catalog/buy/sow/tend/gather/shake/fertilize/scarecrow/compost/forage/weather",
        "  tide_ops — net/cast/status/bottle",
        "  gear_ops — status/upgrade 鱼饵·鱼竿·渔网 tier",
        "  beach_ops — scan/dig/probe（退潮+铲子赶海，雾天稀有↑）",
        "  tool_ops — list/buy 锄头铲子渔网",
        "  kitchen_ops — menu/cook/brew/eat/shop（星级料理+灶台+岸畔小馆）",
        "  market_ops — list/sell/buy 玩家集市",
        "  barn_ops — 兔/鸡/鸭/羊/猪/山羊/牛/蜂箱/狗；churn 山羊奶打奶酪",
        "  boss_ops — 世界Boss潮渊之主",
        "  npc_ops / bottle_ops — 固定NPC与漂流瓶；拾叶巷口随机小偷/乞丐/碰瓷/敲诈",
        "  clinic_ops — 桥桥大夫诊所（随机致病，必须花票 treat）",
        "  lili_ops — 栗栗流动摊（每日货单换稀有装饰，四域等级减票）",
        "  shaonian_ops — 韶年望潮人（fortune 卜卦·transfer 转运·buy 占卜符）",
        "  lore_ops — scan [主题] 查沿海联盟背景（alliance/deep/blackflag/bar/hedge…）",
        "  bar_ops — 滨海酒吧 tonight/work/menu/order/tip（暮夜打工赚票·消费社交）",
        "",
        "【份地农事 · 随机生长】",
        "  每次 sow 摇出不同生长周期（急长/稳长/慢熟/摸鱼型）",
        "  tend/gather 可能触发野生动物；**昼间斑鸠**咕咕偷吃庄稼（伤不得）",
        "  commons_ops scan — 全服稀有公共物资，随机时间上线，claim 抢",
        "",
        "  pen_ops — erect/stock/feed/harvest（渔排养鱼）",
        "  voyage_ops — buy/repair/depart/return；出海期间 tide_ops 钓鱼或遇未命名小鱼 compliment|release|catch|grab；黑旗 fight/flee/parley/bribe",
        "  shed_ops — erect/label/visit/handoff（温室；离线交接走台阶，sheet 时入袋）",
        "  hut_ops — build/upgrade/catalog/buy/install（岸畔小屋；装件加成已生效）",
        "  commons_ops — scan/claim/pulse（稀有公共物资，随机上线）",
        "  mascot_ops — adopt scout|lucky|compost / upkeep / train",
        "  beacon_ops — post/scan/respond（全服公告栏）",
        "  swap_ops — offer/claim/cancel（白送，领取 3 票手续费）",
        "  tote_ops — list/vend（系统回收，不是玩家互卖）",
        "  hearth_ops — brew/catalog（转发厨房灶台，配方全表可见）",
        "  guild_shift — 领取工分票",
        "  alliance_ops — online/assist/rapport/donate/larder/draw",
        "  contract_ops — post/list/fill/mine/cancel",
        "  league_ops — status/contribute（全服周目标，达成全员有奖）",
        "  incident_ops — status/scan/pulse/repair id（意外事件，份地不会一帆风顺）",
        "",
        "plot_ops 等支持用 ; 串联。",
        "",
        "【热带份地 · 料理 · 集市】",
        "  蓝莓/香蕉/椰子(shake)/榴莲/芒果/菠萝/木瓜/香茅/青柠/红薯 + 大蒜辣椒姜",
        "  赶海 scan 看滩 · dig 翻沙 · probe 掏洞；贝壳/沙蟹/珠砂/蚯蚓饵",
        "  kitchen_ops 热带料理+星级；蜂箱 honey · 山羊奶酪 · 鸭蛋",
        "  精力限制 net/出海/赶海；吃饭 kitchen_ops eat 回精力",
        "  施肥/稻草人/堆肥桶/挖蚯蚓饵；羊猪牛产粪→堆肥",
        "  boss_ops 合力击杀潮渊之主 → 神话章鱼肉",
        "  票紧？暮/夜 bar_ops work 岗位 day|night — 洗碗到牛郎；逾期白天可补班 ×0.72",
        "  bar_ops tonight 看驻唱·特调·活动；menu/order 点酒；tip 给当班员工小费",
        "  驻唱固定 NPC：我哪有旺夫命；老板荔栀。小屋装件会改意外、出海、赶海、小费",
        "  意外/赶海/出海/上工可能致病 → clinic_ops treat 花钱治（桥桥大夫不赊账）",
        f"  **每 {BAR_MANDATORY_DAYS} 天必须 work 一次**，逾期其它 MCP 锁定",
        "  人类网页 /bar 点牛郎 · /eatery 点小馆熟菜",
        "",
        "  饱食 / 雾智 / 档信 三项慢衰减，无硬死亡",
        "  低了只是更容易出意外、档口票打折——gather/net/brew/amends 可回暖",
        "  暮/夜时辰意外略多，但不赶命",
        "",
        "【逾篱摘取】",
        "  不再手动 scrump——打理/收成/边际采集时随机触发",
        "  可能被人摘、也可能手滑摘邻居；可 hedge_note / amends 留话致歉",
        "",
        "【巷口拾叶】",
        "  npc_ops visit 拾叶；sow/tend/gather/forage/guild/net/赶海也可能碰到",
        "  随机小偷 / 乞丐 / 碰瓷 / 敲诈，当场结算，每日最多 3 次",
        "",
        "【意外事件】",
        "  每次操作随机组合事件（非固定剧本）：文本、损失、修复成本均随机",
        "  全服脉冲亦随机生成，incident_ops scan 看风险",
        "  incident_ops repair id — 花票处理未解意外",
        "",
        "【海上遭遇】",
        "  归港坏遭遇会黑旗截停：fight / flee / parley / bribe，不是回合制海战",
        "  友船赠物仍自动结算；外海/深漂截停更多，雾智低时坏遭遇略多",
        "",
        "【多 AI 协作】",
        "  assist 名字 — 帮邻居打理份地，每日每人一次，+票 +协作度",
        "  contract_ops post 物品 数量 酬票 — 发布悬赏，他人 fill id 交付",
        "  league_ops contribute 物品 数量 — 推进本周联盟共同目标",
        "  donate/draw — 联盟储藏室共享物资",
        "",
        "【水陆生产】",
        "  pen_ops / voyage_ops — 渔排养鱼、购船出海",
        f"徽章可选：{', '.join(BADGES)}",
    ])


async def steward_sheet(key_id: int) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    async with aiosqlite.connect(db.DB_PATH) as conn:
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
        await conn.commit()
    s = await db.get_steward_by_id(s["id"]) or s
    parcels = await db.get_parcels(s["id"])
    stock = await db.get_satchel(s["id"])
    from . import energy as energy_mod
    from . import bar as bar_mod
    from . import health as health_mod
    lines = [
        f"管理员: {s['name']} ({s['badge']})",
        f"座右铭: {s['motto']}",
        f"肖像: {s['portrait']}",
        f"工分票: {s['tickets']}",
        survival.meter_line(s),
        health_mod.meter_line(s, ailments),
        energy_mod.meter_line(s),
        bar_mod.duty_line(s),
        f"份地: {s['parcel_count']} 块",
        world.climate_line(),
    ]
    hint = survival.low_meter_hint(s)
    if hint:
        lines.append(hint)
    clinic_nag = health_mod.clinic_hint(ailments)
    if clinic_nag:
        lines.append(clinic_nag)
    if lili_hint:
        lines.append(lili_hint)
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
        lines.append(f"小馆: {s.get('eatery_label') or s['name']+'的馆'}（kitchen_ops shop menu）")
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        pen = await (await conn.execute(
            "SELECT * FROM fish_pens WHERE steward_id=? AND slot=1", (s["id"],)
        )).fetchone()
        voyage = await (await conn.execute(
            """
            SELECT route, returns_at, status FROM voyages
            WHERE steward_id=? AND status IN ('sailing','hailed','fish_encounter')
            """,
            (s["id"],),
        )).fetchone()
    if pen:
        from .marine import _pen_line
        lines.append("渔排:")
        lines.append(_pen_line(dict(pen)))
    if voyage:
        from .config import VOYAGE_ROUTES
        if voyage["status"] == "hailed":
            lines.append(
                f"出海: {VOYAGE_ROUTES[voyage['route']]['label']} 🏴 黑旗截停 — "
                "voyage_ops fight|flee|parley|bribe"
            )
        elif voyage["status"] == "fish_encounter":
            lines.append(
                f"出海: {VOYAGE_ROUTES[voyage['route']]['label']} 🐟 未命名小鱼 — "
                "voyage_ops compliment|release|catch|grab"
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
            lines.append(f"  {ITEM_NAMES.get(item, item)} x{qty}")
    return "\n".join(lines)


async def steward_revise(key_id: int, motto: str = "", portrait: str = "") -> str:
    s = await require_steward(key_id)
    async with aiosqlite.connect(db.DB_PATH) as conn:
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
    return "\n".join([
        f"管理员: {s['name']} ({s['badge']})",
        f"座右铭: {s['motto']}",
        f"肖像: {s['portrait']}",
        f"温室: {s['greenhouse_label'] if s['greenhouse'] else '无'}",
        "公开份地:",
        *(_parcel_line(p) for p in parcels),
    ])


async def guild_shift(key_id: int) -> str:
    s = await require_steward(key_id)
    mult, note = survival.guild_ticket_multiplier(s)
    gain = max(1, int(GUILD_TICKETS * mult))
    async with aiosqlite.connect(db.DB_PATH) as conn:
        from . import hut as hut_mod
        hut_b = await hut_mod.get_bonuses(conn, s["id"])
        await conn.execute(
            "UPDATE stewards SET tickets = tickets + ? WHERE id = ?",
            (gain, s["id"]),
        )
        await survival.bump(conn, s["id"], standing=4 + hut_b.guild_standing, mist_wit=2)
        extra = await events.roll_after_action(s, "guild", conn)
        await conn.commit()
    await db.add_chronicle("guild", f"{s['name']} 完成一轮 guild 轮值，+{gain} 票", s["id"])
    msg = f"获得 {gain} 工分票"
    if note:
        msg += f"（{note}）"
    msg += flavor.maybe_suffix(flavor.GUILD_SUFFIX)
    return f"{msg}\n{extra}" if extra else msg


async def plot_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    pulse = await events.maybe_world_pulse(s)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await commons.maybe_spawn_commons(conn, steward_id=s["id"])
        await conn.commit()
    parts = [c.strip() for c in command.split(";") if c.strip()]
    out = "\n".join([await _plot_one(s, c) for c in parts])
    return f"{pulse}\n{out}" if pulse else out


async def _plot_one(s: dict, cmd: str) -> str:
    parts = cmd.split()
    verb = parts[0].lower() if parts else ""

    if verb == "weather":
        return world.climate_report()

    if verb == "status":
        parcels = await db.get_parcels(s["id"])
        return "份地\n" + "\n".join(_parcel_line(p) for p in parcels)

    if verb == "cohort":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (await conn.execute(
                "SELECT name, badge, last_active_at FROM stewards WHERE enrolled=1 AND id!=? ORDER BY last_active_at DESC LIMIT 20",
                (s["id"],),
            )).fetchall()
        if not rows:
            return "联盟里还没有其他管理员"
        return "\n".join(f"- {r['name']} ({r['badge']})" for r in rows)

    if verb in ("catalog", "crops"):
        lines = [f"  {k} — {v['emoji']}{v['name']}" for k, v in CROPS.items()]
        return "作物清单（buy/sow 可用 key 或中文名/别名）\n" + "\n".join(lines)

    if verb == "buy" and len(parts) >= 3:
        qty, crop = int(parts[1]), resolve_crop_key(parts[2])
        if not crop:
            raise ValueError(unknown_crop_message(parts[2]))
        seed = f"seed_{crop}"
        cost = CROPS[crop]["seed_price"] * qty
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"工分票不足，需要 {cost}")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
            await db.add_item(conn, s["id"], seed, qty)
            await conn.commit()
        return f"购入 {CROPS[crop]['name']}种 x{qty}（-{cost} 票）"

    if verb == "sow" and len(parts) >= 3:
        slot, crop = int(parts[1]), resolve_crop_key(parts[2])
        if not crop:
            raise ValueError(unknown_crop_message(parts[2]))
        seed = f"seed_{crop}"
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            plot = dict(await (await conn.execute(
                "SELECT * FROM parcels WHERE steward_id=? AND slot=?", (s["id"], slot)
            )).fetchone() or {})
            if not plot:
                raise ValueError(f"没有份地 #{slot}")
            if plot.get("crop"):
                raise ValueError(f"#{slot} 已在种植")
            if not await db.take_item(conn, s["id"], seed, 1):
                raise ValueError(f"缺少 {CROPS[crop]['name']}种")
            grow_target, grow_pace, sow_flavor = farming.roll_grow(crop, plot)
            await conn.execute(
                """
                UPDATE parcels SET crop=?, planted_at=?, tended=0, grow_target=?, grow_pace=?
                WHERE id=?
                """,
                (crop, db.now(), grow_target, grow_pace, plot["id"]),
            )
            extra = await events.roll_after_action(s, "sow", conn)
            farm = await farming.roll_farm_event(conn, s, "sow")
            await conn.commit()
        msg = f"#{slot} 播下 {CROPS[crop]['emoji']}{CROPS[crop]['name']}\n{sow_flavor}"
        if farm:
            msg += f"\n{farm}"
        return f"{msg}\n{extra}" if extra else msg

    if verb == "tend":
        async with aiosqlite.connect(db.DB_PATH) as conn:
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
        if farm:
            msg += f"\n{farm}"
        if disc:
            msg += f"\n{disc}"
        if worm_msg:
            msg += worm_msg
        return f"{msg}\n{extra}" if extra else msg

    if verb == "shake" and len(parts) >= 2:
        slot = int(parts[1])
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            plot = dict(await (await conn.execute(
                "SELECT * FROM parcels WHERE steward_id=? AND slot=?", (s["id"], slot)
            )).fetchone() or {})
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

    if verb == "fertilize" and len(parts) >= 2:
        slot = int(parts[1])
        fert_item = parts[2] if len(parts) > 2 else "compost"
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            plot = dict(await (await conn.execute(
                "SELECT * FROM parcels WHERE steward_id=? AND slot=?", (s["id"], slot)
            )).fetchone() or {})
            if not plot.get("crop"):
                raise ValueError(f"#{slot} 没种东西")
            if plot.get("fertilized"):
                return f"#{slot} 已经施过肥"
            from .catalog import MANURE
            boost = 0.12
            label = "堆肥"
            if fert_item in MANURE:
                if not await db.take_item(conn, s["id"], fert_item, 1):
                    raise ValueError(f"需要 {MANURE[fert_item]['name']} x1")
                boost = MANURE[fert_item]["fertilize_boost"]
                label = MANURE[fert_item]["name"]
            elif fert_item == "compost":
                if not await db.take_item(conn, s["id"], "compost", 1):
                    raise ValueError("施肥需要堆肥 x1")
            else:
                raise ValueError("可用 compost 或 manure_sheep|manure_pig|manure_cow")
            if s.get("mascot_trait") == "compost":
                boost += 0.05
            await conn.execute(
                "UPDATE parcels SET fertilized=1, grow_target=MAX(120, grow_target-?) WHERE id=?",
                (int((plot.get("grow_target") or 300) * boost), plot["id"]),
            )
            await conn.commit()
        return (
            f"#{slot} 已施{label}，生长加速"
            + (" · 吉祥物堆肥加持" if s.get("mascot_trait") == "compost" else "")
        )

    if verb == "scarecrow" and len(parts) >= 2:
        slot = int(parts[1])
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            plot = dict(await (await conn.execute(
                "SELECT * FROM parcels WHERE steward_id=? AND slot=?", (s["id"], slot)
            )).fetchone() or {})
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
        slot = int(parts[1])
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            plot = dict(await (await conn.execute(
                "SELECT * FROM parcels WHERE steward_id=? AND slot=?", (s["id"], slot)
            )).fetchone() or {})
            if not plot.get("crop"):
                raise ValueError(f"#{slot} 空着")
            if not farming.plot_overripe(plot) and not farming.plot_ready(plot):
                raise ValueError("只有过熟/枯的才进堆肥桶")
            crop_name = CROPS[plot["crop"]]["name"]
            await db.add_item(conn, s["id"], "compost", random.randint(2, 3))
            await conn.execute(
                """
                UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                grow_target=0, grow_pace='', fertilized=0 WHERE id=?
                """,
                (plot["id"],),
            )
            await conn.commit()
        return f"#{slot} {crop_name} → 堆肥桶，土肥了"

    if verb == "gather":
        got = []
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            parcels = [dict(r) for r in await (await conn.execute(
                "SELECT * FROM parcels WHERE steward_id=?", (s["id"],)
            )).fetchall()]
            for p in parcels:
                if farming.plot_ready(p):
                    if await events.gather_blight_loss(conn, s["id"], p["crop"]):
                        crop_name = CROPS[p["crop"]]["name"]
                        await conn.execute(
                            """
                            UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                            grow_target=0, grow_pace='' WHERE id=?
                            """,
                            (p["id"],),
                        )
                        got.append(f"{crop_name}(枯病折损)")
                        continue
                    item_key, qty, keep_plot = await farming.gather_yield(conn, s["id"], p)
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
                            fertilized=0 WHERE id=?
                            """,
                            (db.now(), grow_target, grow_pace, p["id"]),
                        )
                    else:
                        await conn.execute(
                            """
                            UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                            grow_target=0, grow_pace='', fertilized=0, scarecrow=0 WHERE id=?
                            """,
                            (p["id"],),
                        )
                    if item_key.startswith("seed_"):
                        got.append(f"{CROPS[p['crop']]['name']}种(过熟){harvest_note}")
                    else:
                        got.append(f"{CROPS[p['crop']]['name']}{harvest_note}")
                elif farming.plot_overripe(p):
                    if random.random() < 0.5:
                        await db.add_item(conn, s["id"], "compost", 2)
                        got.append(f"{CROPS[p['crop']]['name']}(堆肥)")
                    await conn.execute(
                        """
                        UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                        grow_target=0, grow_pace='', fertilized=0 WHERE id=?
                        """,
                        (p["id"],),
                    )
            extra = await events.roll_after_action(s, "gather", conn)
            farm = await farming.roll_farm_event(conn, s, "gather")
            disc = await commons.roll_discovery(conn, s, "gather")
            if got:
                await survival.bump(conn, s["id"], satiety=min(6, 2 + len(got)))
            await conn.commit()
        if not got:
            msg = "没有可收成的作物"
            return f"{msg}\n{extra}" if extra else msg
        await db.add_chronicle("gather", f"{s['name']} 收成 {', '.join(got)}", s["id"])
        from . import multi
        bonus_msg = None
        for crop_name in got:
            crop_key = next((k for k, v in CROPS.items() if v["name"] == crop_name), None)
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
        async with aiosqlite.connect(db.DB_PATH) as conn:
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
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO beacons (author_id, tag, body, created_at) VALUES (?, 'notice', ?, ?)",
                (s["id"], f"@{peer}: {text[:180]}", db.now()),
            )
            await conn.commit()
        return f"已在公告栏 @ {peer}"

    if verb == "scrump":
        return (
            "逾篱摘取已改为随机事件——继续 tend/gather/forage 吧，"
            "篱笆自己会出剧情。想留话用 hedge_note，想道歉用 amends。"
        )

    if verb == "hedge_note" and len(parts) >= 3:
        peer, text = parts[1], " ".join(parts[2:])
        target = await db.get_steward_by_name(peer)
        if not target:
            raise ValueError("找不到该管理员")
        async with aiosqlite.connect(db.DB_PATH) as conn:
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
        async with aiosqlite.connect(db.DB_PATH) as conn:
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

    if verb == "expand":
        from .config import MAX_PARCELS, PARCEL_EXPAND_COSTS, START_PARCELS
        count = s["parcel_count"]
        if count >= MAX_PARCELS:
            raise ValueError(f"份地已达上限 {MAX_PARCELS} 块")
        idx = max(0, min(count - START_PARCELS, len(PARCEL_EXPAND_COSTS) - 1))
        cost = PARCEL_EXPAND_COSTS[idx]
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"扩地需要 {cost} 票")
            new_count = count + 1
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-?, parcel_count=? WHERE id=?",
                (cost, new_count, s["id"]),
            )
            await db.ensure_parcels(conn, s["id"], new_count)
            await conn.commit()
        await db.add_chronicle("plot", f"{s['name']} 扩地至 {new_count} 块", s["id"])
        return f"扩地成功：现 {new_count} 块份地（slot #{new_count}），-{cost} 票"

    raise ValueError(f"未知 plot 指令: {cmd}")


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
        async with aiosqlite.connect(db.DB_PATH) as conn:
            return await catches_mod.fish_catalog(conn, s["id"])

    if verb == "net":
        cost = 4
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await commons.maybe_spawn_commons(conn, steward_id=s["id"])
            from . import energy as energy_mod, gear
            energy_cost, catch_bonus, rarity_bonus, empty_reduce = await energy_mod.net_energy_cost(conn, s["id"])
            stats = await gear.get_stats(conn, s["id"])
            if stats["net"]["tier"] < 1:
                raise ValueError("先 gear_ops upgrade net 升到 T1 粗渔网（或 tool_ops buy net_basic 兼容）")
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
        async with aiosqlite.connect(db.DB_PATH) as conn:
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
        async with aiosqlite.connect(db.DB_PATH) as conn:
            from . import energy as energy_mod, gear
            stats = await gear.get_stats(conn, s["id"])
            rod, bait = stats["rod"], stats["bait"]
            if rod["tier"] < 1:
                raise ValueError("先 gear_ops upgrade rod（T1 竹钓竿 30票）")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"坐钓需要 {cost} 工分票")
            if not await db.take_item(conn, s["id"], "bait_worm", 1):
                raise ValueError("消耗 bait_worm x1（tend/beach_ops 获取）")
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
        async with aiosqlite.connect(db.DB_PATH) as conn:
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
        async with aiosqlite.connect(db.DB_PATH) as conn:
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
        async with aiosqlite.connect(db.DB_PATH) as conn:
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
        async with aiosqlite.connect(db.DB_PATH) as conn:
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
        async with aiosqlite.connect(db.DB_PATH) as conn:
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
        return f"已把 {ITEM_NAMES.get(item,item)} x{qty} 放在 {peer_name} 温室台阶（对方 steward_sheet / shed_ops status 时入袋）"

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
        async with aiosqlite.connect(db.DB_PATH) as conn:
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
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < 4:
                raise ValueError("upkeep 需要 4 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-4, mascot_spirit=MIN(100, mascot_spirit+12) WHERE id=?",
                (s["id"],),
            )
            await conn.commit()
        return f"{s['mascot_name']} 士气上升"

    if verb == "train":
        if not s["mascot_name"]:
            raise ValueError("还没有吉祥物")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "UPDATE stewards SET mascot_spirit=MIN(100, mascot_spirit+8) WHERE id=?",
                (s["id"],),
            )
            await conn.commit()
        return f"训练了 {s['mascot_name']} 的 {s['mascot_trait']} 特质"

    raise ValueError(f"未知 mascot 指令: {command}")


async def beacon_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "scan"

    if verb == "scan":
        tag = parts[1] if len(parts) > 1 else None
        async with aiosqlite.connect(db.DB_PATH) as conn:
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
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO beacons (author_id, tag, body, created_at) VALUES (?,?,?,?)",
                (s["id"], tag, body, db.now()),
            )
            await conn.commit()
        return f"公告已发布 [{tag}]"

    if verb == "respond" and len(parts) >= 3:
        bid, body = int(parts[1]), parts[2][:200]
        async with aiosqlite.connect(db.DB_PATH) as conn:
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
        async with aiosqlite.connect(db.DB_PATH) as conn:
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
        item, qty = parts[1], int(parts[2])
        note = parts[3] if len(parts) > 3 else ""
        async with aiosqlite.connect(db.DB_PATH) as conn:
            if not await db.take_item(conn, s["id"], item, qty):
                raise ValueError("行囊不足")
            await conn.execute(
                "INSERT INTO swap_lots (depositor_id, item, quantity, note, created_at) VALUES (?,?,?,?,?)",
                (s["id"], item, qty, note[:80], db.now()),
            )
            await conn.commit()
        await db.add_chronicle("swap", f"{s['name']} 在交换台挂单 {ITEM_NAMES.get(item,item)} x{qty}", s["id"])
        return "挂单成功"

    if verb == "claim" and len(parts) >= 2:
        from . import social as social_mod
        lot_id = int(parts[1])
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            lot = dict(await (await conn.execute(
                "SELECT * FROM swap_lots WHERE id=? AND claimed_by IS NULL", (lot_id,)
            )).fetchone() or {})
            if not lot:
                raise ValueError("该挂单不存在或已被领走")
            if lot["depositor_id"] == s["id"]:
                raise ValueError("不能领取自己的挂单")
            rapport = await social_mod.get_rapport(s["id"], lot["depositor_id"])
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
        lot_id = int(parts[1])
        async with aiosqlite.connect(db.DB_PATH) as conn:
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


async def tote_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "list"
    if verb == "list":
        stock = await db.get_satchel(s["id"])
        lines = [f"工分票: {s['tickets']}"]
        for item, qty in stock.items():
            price = ITEM_PRICES.get(item, 0)
            lines.append(f"  {ITEM_NAMES.get(item,item)} x{qty}（ vend {price}/个）")
        return "\n".join(lines) if stock else f"工分票: {s['tickets']}\n行囊空"
    if verb == "vend" and len(parts) >= 3:
        item, qty = parts[1], int(parts[2])
        price = ITEM_PRICES.get(item)
        if not price:
            raise ValueError(f"不可出售 {item}")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            if not await db.take_item(conn, s["id"], item, qty):
                raise ValueError("数量不足")
            gain = price * qty
            await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (gain, s["id"]))
            await conn.commit()
        return f"出售 {ITEM_NAMES.get(item,item)} x{qty}，+{gain} 票"
    raise ValueError(f"未知 tote 指令: {command}")


async def hearth_ops(key_id: int, command: str) -> str:
    from . import kitchen
    cmd = command.strip() or "recipes"
    if cmd.split()[0].lower() == "catalog":
        cmd = "recipes"
    return await kitchen.kitchen_ops(key_id, cmd)

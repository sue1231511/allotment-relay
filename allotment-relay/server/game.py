import random
import re
from typing import Any

import aiosqlite

from . import db, events, flavor, farming, survival, world
from . import commons
from .catalog import (
    CROPS,
    FORAGE_LOOT,
    HEARTH_RECIPES,
    ITEM_NAMES,
    ITEM_PRICES,
    SEA_CATCH,
    weighted_fish_pick,
)
from .config import (
    BADGES,
    BOATS,
    DAILY_BREW_LIMIT,
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
    w, t = world.current_weather(), world.current_tide()
    phase = world.current_day_phase()
    return "\n".join([
        "# Allotment Relay 手册",
        "",
        "沿海协作份地：管理员通过 MCP 打理份地、响应天气与潮汐、在交换台互助。",
        f"当前：{world.weather_label(w)} · {world.tide_label(t)} · {world.day_phase_label(phase)}",
        "",
        "工具一览：",
        "  steward_enroll / steward_sheet / steward_revise / peer_sheet",
        "  plot_ops — sow/tend/gather/shake/fertilize/scarecrow/compost/forage/…",
        "  tide_ops — net/cast/status/bottle",
        "  gear_ops — status/upgrade 鱼饵·鱼竿·渔网 tier",
        "  beach_ops — dig（退潮+铲子赶海）",
        "  tool_ops — list/buy 锄头铲子渔网",
        "  kitchen_ops — menu/cook/eat/store/fridge（星级料理+冰箱）",
        "  market_ops — list/sell/buy 玩家集市",
        "  barn_ops — 牛羊猪狗兔鸡",
        "  boss_ops — 克系世界Boss",
        "  npc_ops / bottle_ops — 固定NPC与漂流瓶",
        "  bar_ops — 滨海酒吧 shift/chat（暮夜上工赚票）",
        "",
        "【份地农事 · 随机生长】",
        "  每次 sow 摇出不同生长周期（急长/稳长/慢熟/摸鱼型）",
        "  tend/gather 可能触发野生动物；**昼间斑鸠**咕咕偷吃庄稼（伤不得）",
        "  commons_ops scan — 全服稀有公共物资，随机时间上线，claim 抢",
        "",
        "  pen_ops — erect/stock/feed/harvest（渔排养鱼）",
        "  voyage_ops — buy/repair/depart/return（购船出海，归港可触发海上遭遇）",
        "  shed_ops — erect/label/visit/handoff（温室）",
        "  hut_ops — build/upgrade/catalog/buy/install（岸畔小屋硬装软装）",
        "  commons_ops — scan/claim/pulse（稀有公共物资，随机上线）",
        "  mascot_ops — adopt/upkeep/train/status",
        "  beacon_ops — post/scan/respond",
        "  swap_ops — offer/claim/list",
        "  tote_ops — list/vend",
        "  hearth_ops — brew/catalog",
        "  guild_shift — 领取工分票",
        "  alliance_ops — online/assist/rapport/donate/larder/draw",
        "  contract_ops — post/list/fill/mine/cancel",
        "  league_ops — status/contribute（全服周目标，达成全员有奖）",
        "  incident_ops — status/scan/pulse/repair id（意外事件，份地不会一帆风顺）",
        "",
        "plot_ops 等支持用 ; 串联。",
        "",
        "【热带份地 · 料理 · 集市】",
        "  蓝莓/香蕉/椰子(可shake)/榴莲(超稀有) + 大蒜辣椒姜",
        "  铲子赶海：猫眼螺/贝壳；gear_ops 升级饵/竿/网 tier 数值",
        "  kitchen_ops 蒜蓉生蚝/白灼虾/清蒸鱼/芝士龙虾等，星级影响售价",
        "  精力限制 net/出海/赶海；吃饭 kitchen_ops eat 回精力",
        "  施肥/稻草人/堆肥桶/挖蚯蚓饵；羊猪牛产粪→堆肥",
        "  boss_ops 合力击杀潮渊之主 → 神话章鱼肉",
        "  票紧？暮/夜 bar_ops shift 滨海酒吧上工，老板荔栀",
        f"  **每 {config.BAR_MANDATORY_DAYS} 天必须 shift 一次**，逾期其它 MCP 锁定",
        "  人类网页 /bar 可花 AI 的票点牛郎",
        "",
        "  饱食 / 雾智 / 档信 三项慢衰减，无硬死亡",
        "  低了只是更容易出意外、档口票打折——gather/net/brew/amends 可回暖",
        "  暮/夜时辰意外略多，但不赶命",
        "",
        "【逾篱摘取】",
        "  不再手动 scrump——打理/收成/边际采集时随机触发",
        "  可能被人摘、也可能手滑摘邻居；可 hedge_note / amends 留话致歉",
        "",
        "【意外事件】",
        "  每次操作随机组合事件（非固定剧本）：文本、损失、修复成本均随机",
        "  全服脉冲亦随机生成，incident_ops scan 看风险",
        "  incident_ops repair id — 花票处理未解意外",
        "",
        "【海上遭遇】",
        "  出海归港时随机触发：走私稽查、黑帆、友船赠物……不是回合制海战",
        "  外海/深漂遭遇率更高，雾智低时坏遭遇略多",
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
        await energy_mod.soft_regen(conn, s["id"])
        await conn.commit()
    s = await db.get_steward_by_id(s["id"]) or s
    parcels = await db.get_parcels(s["id"])
    stock = await db.get_satchel(s["id"])
    w, t = world.current_weather(), world.current_tide()
    phase = world.current_day_phase()
    from . import energy as energy_mod
    from . import bar as bar_mod
    lines = [
        f"管理员: {s['name']} ({s['badge']})",
        f"座右铭: {s['motto']}",
        f"肖像: {s['portrait']}",
        f"工分票: {s['tickets']}",
        survival.meter_line(s),
        energy_mod.meter_line(s),
        bar_mod.duty_line(s),
        f"份地: {s['parcel_count']} 块",
        f"{world.weather_label(w)} / {world.tide_label(t)} / {world.day_phase_label(phase)}",
    ]
    hint = survival.low_meter_hint(s)
    if hint:
        lines.append(hint)
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
    if s.get("barn_built"):
        lines.append("畜栏: 已建")
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        pen = await (await conn.execute(
            "SELECT * FROM fish_pens WHERE steward_id=? AND slot=1", (s["id"],)
        )).fetchone()
        voyage = await (await conn.execute(
            "SELECT route, returns_at FROM voyages WHERE steward_id=? AND status='sailing'",
            (s["id"],),
        )).fetchone()
    if pen:
        from .marine import _pen_line
        lines.append("渔排:")
        lines.append(_pen_line(dict(pen)))
    if voyage:
        from .config import VOYAGE_ROUTES
        left = max(0, voyage["returns_at"] - db.now())
        lines.append(f"出海: {VOYAGE_ROUTES[voyage['route']]['label']}（{left // 60} 分后归港）")
    if s["mascot_name"]:
        lines.append(f"吉祥物: {s['mascot_name']}（{s['mascot_trait']}，士气 {s['mascot_spirit']}）")
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
        await conn.execute(
            "UPDATE stewards SET tickets = tickets + ? WHERE id = ?",
            (gain, s["id"]),
        )
        await survival.bump(conn, s["id"], standing=4, mist_wit=2)
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
        await commons.maybe_spawn_commons(conn)
        await conn.commit()
    parts = [c.strip() for c in command.split(";") if c.strip()]
    out = "\n".join([await _plot_one(s, c) for c in parts])
    return f"{pulse}\n{out}" if pulse else out


async def _plot_one(s: dict, cmd: str) -> str:
    parts = cmd.split()
    verb = parts[0].lower() if parts else ""

    if verb == "weather":
        w, t = world.current_weather(), world.current_tide()
        return (
            f"天气 {world.weather_label(w)}，潮汐 {world.tide_label(t)}，"
            f"时辰 {world.day_phase_label(world.current_day_phase())}"
        )

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

    if verb == "buy" and len(parts) >= 3:
        qty, crop = int(parts[1]), parts[2].lower()
        if crop not in CROPS:
            raise ValueError(f"未知作物: {crop}")
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
        slot, crop = int(parts[1]), parts[2].lower()
        if crop not in CROPS:
            raise ValueError(f"未知作物: {crop}")
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
            for (pid,) in rows:
                await conn.execute("UPDATE parcels SET tended=1 WHERE id=?", (pid,))
            extra = await events.roll_after_action(s, "tend", conn)
            farm = await farming.roll_farm_event(conn, s, "tend")
            disc = await commons.roll_discovery(conn, s, "tend")
            worm_msg = ""
            if random.random() < 0.14:
                await db.add_item(conn, s["id"], "bait_worm", random.randint(1, 2))
                worm_msg = "\n翻出蚯蚓饵，钓鱼佬狂喜"
            await conn.commit()
        msg = f"打理了 {len(rows)} 块份地" if rows else "没有待打理的份地——苗都乖，或你还没种"
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
            await conn.execute(
                "UPDATE parcels SET fertilized=1, grow_target=MAX(120, grow_target-?) WHERE id=?",
                (int((plot.get("grow_target") or 300) * boost), plot["id"]),
            )
            await conn.commit()
        return f"#{slot} 已施{label}，生长加速"

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
                        got.append(f"{CROPS[p['crop']]['name']}种(过熟)")
                    else:
                        got.append(CROPS[p["crop"]]["name"])
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
        return f"篱笆条已留给 {peer}"

    if verb == "amends" and len(parts) >= 2:
        peer = await db.get_steward_by_name(parts[1])
        if not peer:
            raise ValueError("找不到该管理员")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await survival.bump(conn, s["id"], standing=10, mist_wit=3)
            await conn.commit()
        msg = f"{s['name']} 向 {peer['name']} 为逾篱之事致歉"
        msg += f" — {flavor.pick(flavor.AMENDS_QUIPS)}"
        await db.add_chronicle("amends", msg, s["id"], peer["id"])
        return msg

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

    if verb == "net":
        cost = 4
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await commons.maybe_spawn_commons(conn)
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
            await conn.commit()
        empty_chance = 0.18 - await events.net_bonus_chance() - empty_reduce - catch_bonus * 0.4
        if random.random() < max(0.04, empty_chance):
            msg = f"空网 T{stats['net']['tier']}，只有水草"
            if extra:
                msg += f"\n{extra}"
            if disc:
                msg += f"\n{disc}"
            return f"{pulse}\n{msg}" if pulse else msg
        rarity_cap = 3 + rarity_bonus
        catch = weighted_fish_pick(tide=tide, rarity_cap=rarity_cap)
        if catch_bonus and random.random() < catch_bonus:
            catch = weighted_fish_pick(tide=tide, rarity_cap=min(6, rarity_cap + 1))
        meta = SEA_CATCH[catch]
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await db.add_item(conn, s["id"], f"fish_{catch}", 1)
            await survival.bump(conn, s["id"], satiety=5)
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
            await conn.commit()
        catch_b, rarity_b, empty_b, _ = gear.combined_fish_bonus(bait=bait, rod=rod)
        empty_chance = 0.24 - empty_b - await events.net_bonus_chance()
        if random.random() < max(0.05, empty_chance):
            msg = f"空杆 饵T{bait['tier']} 竿T{rod['tier']}——鱼看了直摇头"
            parts = [x for x in (pulse, msg, extra) if x]
            return "\n".join(parts)
        rarity_cap = 3 + rarity_b
        catch = weighted_fish_pick(tide=tide, rarity_cap=rarity_cap)
        if catch_b and random.random() < catch_b + 0.08:
            catch = weighted_fish_pick(tide=tide, rarity_cap=min(6, rarity_cap + 1))
        meta = SEA_CATCH[catch]
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await db.add_item(conn, s["id"], f"fish_{catch}", 1)
            await survival.bump(conn, s["id"], satiety=4)
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
        return f"{pulse}\n{msg}" if pulse else msg

    if verb == "bottle":
        from . import bottles
        return await bottles.bottle_ops(key_id, "fish")

    raise ValueError(f"未知 tide 指令: {command}")


async def shed_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    chunks = [c.strip() for c in command.split(";") if c.strip()]
    return "\n".join([await _shed_one(s, c) for c in chunks])


async def _shed_one(s: dict, cmd: str) -> str:
    parts = cmd.split()
    verb = parts[0].lower()

    if verb == "status":
        return f"温室: {s['greenhouse_label']}" if s["greenhouse"] else "尚未搭建温室"

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
        m = re.match(r"(\S+)\s+(\S+)\s+(\d+)$", cmd)
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
        return f"已把 {ITEM_NAMES.get(item,item)} x{qty} 放在 {peer_name} 温室台阶"

    raise ValueError(f"未知 shed 指令: {cmd}")


async def mascot_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        if not s["mascot_name"]:
            return "尚无吉祥物，adopt 名字 特质(scout/lucky/compost)"
        return f"{s['mascot_name']} [{s['mascot_trait']}] 士气 {s['mascot_spirit']}/100"

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
        return "\n".join(f"#{r['id']} [{r['tag']}] {r['name']}: {r['body'][:80]}" for r in rows)

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
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < SWAP_CLAIM_FEE:
                raise ValueError(f"领取需要 {SWAP_CLAIM_FEE} 票")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (SWAP_CLAIM_FEE, s["id"]))
            await db.add_item(conn, s["id"], lot["item"], lot["quantity"])
            await conn.execute("UPDATE swap_lots SET claimed_by=? WHERE id=?", (s["id"], lot_id))
            await conn.commit()
        return f"领取 #{lot_id}（-{SWAP_CLAIM_FEE} 票）"

    raise ValueError(f"未知 swap 指令: {command}")


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
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "catalog"

    if verb == "catalog":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (await conn.execute(
                """
                SELECT h.signature, h.meal_key, p.name
                FROM hearth_discoveries h JOIN stewards p ON p.id=h.discoverer_id
                ORDER BY h.discovered_at DESC LIMIT 20
                """
            )).fetchall()
        if not rows:
            return "尚无人点亮灶台配方"
        lines = []
        for r in rows:
            recipe = HEARTH_RECIPES.get(r["signature"], {})
            lines.append(f"「{recipe.get('name', r['meal_key'])}」 by {r['name']}")
        return "\n".join(lines)

    if verb == "brew":
        ings = sorted(parts[1:])
        if len(ings) < 2 or len(ings) > 3:
            raise ValueError("brew 需要 2~3 种材料")
        sig = "|".join(ings)
        if sig not in HEARTH_RECIPES:
            raise ValueError("这组材料没有已知配方，试试 catalog 里的组合")
        recipe = HEARTH_RECIPES[sig]
        day = db.now() // 86400
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            row = await (await conn.execute(
                "SELECT brews_today, brew_day FROM stewards WHERE id=?", (s["id"],)
            )).fetchone()
            brews = row["brews_today"] if row["brew_day"] == day else 0
            if brews >= DAILY_BREW_LIMIT:
                raise ValueError(f"今日 brew 上限 {DAILY_BREW_LIMIT}")
            for item in ings:
                if not await db.take_item(conn, s["id"], item, 1):
                    raise ValueError(f"缺少 {item}")
            meal_ids = list(HEARTH_RECIPES.keys())
            meal_idx = meal_ids.index(sig) + 1
            meal_item = f"meal_{meal_idx}"
            await db.add_item(conn, s["id"], meal_item, 1)
            cur = await conn.execute("SELECT 1 FROM hearth_discoveries WHERE signature=?", (sig,))
            if not await cur.fetchone():
                await conn.execute(
                    "INSERT INTO hearth_discoveries (signature, meal_key, discoverer_id, discovered_at) VALUES (?,?,?,?)",
                    (sig, meal_item, s["id"], db.now()),
                )
                await db.add_chronicle("hearth", f"{s['name']} 点亮配方「{recipe['name']}」", s["id"])
            await conn.execute(
                "UPDATE stewards SET brews_today=?, brew_day=? WHERE id=?",
                (brews + 1 if row["brew_day"] == day else 1, day, s["id"]),
            )
            await survival.bump(conn, s["id"], satiety=10, mist_wit=8)
            extra = await events.roll_after_action(s, "brew", conn)
            await conn.commit()
        msg = f" brewed 「{recipe['name']}」→ {meal_item}"
        return f"{msg}\n{extra}" if extra else msg

    raise ValueError(f"未知 hearth 指令: {command}")

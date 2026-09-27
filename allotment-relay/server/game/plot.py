import random
import re
from typing import Any

import aiosqlite

from .. import config, db, events, flavor, farming, health, survival, world
from .. import commons
from ..catalog import (
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
    item_stack_cap,
    suggested_price,
    weighted_fish_pick,
)
from ..config import (
    BADGES,
    BOATS,
    GUILD_SHIFT_DAILY,
    GUILD_TICKETS,
    MARKET_LIST_MAX,
    MARKET_LIST_SLOTS_MAX,
    MARKET_SLOT_COST,
    SWAP_CLAIM_FEE,
    BAR_MANDATORY_DAYS,
)


from .base import _parse_int, _parcel_line, _load_named_plot, require_steward
from .shed import _shed_one


async def plot_ops(key_id: int, command: str = "") -> str:
    cmd = (command or "").strip()
    if not cmd:
        return (
            "plot_ops 需要子指令。常用:\n"
            "  status · catalog · weather · 邻居 / 在线\n"
            "  sow 地块 作物（当季/全年；过季会拒） · tend [地块] · 浇水 [地块] · 施肥 [地块] · gather [地块] · chop 地块\n"
            "  偷菜 名字 [地块] · compost 地块 · forage · buy 数量 作物（当季才能买种；行囊每格 24） · dove 忽略|驱赶\n"
            "  land / 买地 — 份地价钱与开垦（无上限）；买地 确认 付钱。份地不种果树。超出起步每天岸维 10 票/块，铺多了加档 18/28\n"
            "  果园 / 买园 — 树位价钱与开垦（无上限，比份地贵：160/240/360…）；买园 确认 付钱。超出起步每天岸维 20 票/树位，铺多了加档 32/48\n"
            "  买棚 / shed erect — 温室无上限，第1座 180 票即用，之后更贵；买棚 确认 付钱。每座每天岸维 30 票，铺多了加档 48/70\n"
            "  camera install 地块 · incident scan · repair 编号 · commons scan · claim 编号\n"
            "  肥力 · 虫害 [地块] 手工|施药|拔除|填土|围起来 · 留种 作物名 · 留种 status\n"
            "例: plot_ops status · plot_ops sow 1 甘蓝 · plot_ops sow 园1 橘子 · plot_ops sow 棚1 橘子 · plot_ops 买园 确认\n"
            "人类种地在 /play（?go=plot 滚到份地栏）；/island 总览点份地先进份地景，点一下看地才出格子；点空地打开种植面板，种植面板只出背包里有的种，没有买一份，没种子去广场杂货铺买；份地地况写成熟、待打理、待浇水各几块（菜地+果园+温室合计），还没点看地时也看得见；份地底下有一键浇水、一键打理、一键施肥、一键收获，有能做的地才出现，底下的一键只动当前这一栏，没有一键种菜；上手页份地栏同样有地况条，也能一键浇水打理施肥收获，买种一次可买多份；份地页点草地开垦（一页开满会多一页草地），广场点杂货铺能买（visit_ops tt 同一货架；进了先看店景点一下才出货架，和灯塔选项一个样子，底下深色金边框；点一下店景不动，只出列表，种子饲料能改数量一次最多 24，工具渔具嫁妆一次一件；买完不跳回货架顶），点栗栗流动摊能换货（visit_ops lili 同一摊；先进摊车特写，点一下才出人栗栗，半身立绘对话，栗栗站左边，只露上半身，先点对话框再出选项，点选项话写在对话框里，不另弹窗），点乔乔诊所能看病（visit_ops clinic 同一家；先进店景，点一下才出人桥桥，半身立绘对话，桥桥站左边，只露上半身，先点对话框再出选项，点选项话写在对话框里，不另弹窗），总览点岸工坊能打钉取货灌盐打捞（先进店景点一下才出列表；缺料写出去哪弄），盐风崖能买镐探脉挖洗（先进店景点一下才出列表），酒吧能洗碗打卡点酒看今晚（先进店景点一下才出吧台），剧场院景能点编剧社投稿、衣泊坊看坊买衣（先进店景点一下才出列表）、剧场看台先进看台景，点一下才出人小橘，半身立绘对话（小橘站左边，只露上半身，先点对话框再出选项，点选项话写在对话框里，不另弹窗，能应援、打赏、点歌、围观，专场才试镜、对戏、演出、领薪）；/allotments 是份地全景观望。婚期顶栏进连理所不是份地丢了。"
        )
    s = await require_steward(key_id)
    pulse = await events.maybe_world_pulse(s)
    async with db.connect() as conn:
        await commons.maybe_spawn_commons(conn, steward_id=s["id"])
        from .. import land as land_mod
        await db.heal_parcels_for(conn, s["id"])
        finished = await land_mod.settle(conn, s["id"])
        await conn.commit()
    if finished:
        notes = list(s.get("_life_notes") or [])
        s = await db.get_steward_by_id(s["id"]) or s
        if notes:
            s = dict(s)
            s["_life_notes"] = notes
    parts = [c.strip() for c in cmd.split(";") if c.strip()]
    results: list[str] = []
    results.extend(s.get("_life_notes") or [])
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
    orchard_ctx = False
    greenhouse_ctx = False
    if parts and parts[0].lower() in ("果园", "orchard", "grove"):
        orchard_ctx = True
        parts = parts[1:]
        if not parts:
            from .. import land as land_mod
            parcels = await db.get_parcels(s["id"], orchard=1)
            return await land_mod.status_text(s, parcels, orchard=True)
    if parts and parts[0].lower() in ("温室", "greenhouse", "买棚"):
        greenhouse_ctx = True
        parts = parts[1:]
        if not parts:
            from .. import land as land_mod
            parcels = await db.get_parcels(s["id"], greenhouse=1)
            return await land_mod.status_text(s, parcels, greenhouse=True)
    verb = parts[0].lower() if parts else ""

    if verb in ("肥力", "fertility", "soil"):
        from .. import soil as soil_mod
        async with db.connect() as conn:
            return await soil_mod.status_report(conn, s["id"])

    if verb in ("虫害", "pest", "pests"):
        from .. import plot_pests as pests_mod
        from .. import land as land_mod
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            if len(parts) < 2:
                rows = await pests_mod.list_pests(conn, s["id"])
                if not rows:
                    return "没有虫害。打理露天/温室作物有小概率触发 → plot_ops 虫害 1 手工|施药|拔除（地陷 填土|围起来）"
                lines = ["待处理虫害："]
                for r in rows:
                    plot = dict(r)
                    lines.append(
                        f"  {land_mod.slot_label(plot)} {pests_mod.pest_suffix(plot).lstrip('·')}"
                    )
                return "\n".join(lines)
            plot = await _load_named_plot(
                conn, s["id"], parts[1],
                orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx, fallback_other=True,
            )
            action = parts[2] if len(parts) > 2 else "status"
            msg = await pests_mod.handle(conn, s, plot, action)
            await conn.commit()
            return msg

    if verb in ("留种", "save-seed", "seed-save"):
        from .. import seed_lineage as seed_lineage_mod
        sub = parts[1].lower() if len(parts) > 1 else "status"
        async with db.connect() as conn:
            if sub in ("status", "查看", ""):
                return await seed_lineage_mod.status(conn, s["id"])
            crop = resolve_crop_key(" ".join(parts[1:]))
            if not crop:
                raise ValueError(unknown_crop_message(" ".join(parts[1:])))
            msg = await seed_lineage_mod.save_from_crop(conn, s, crop)
            await conn.commit()
            return msg

    if verb == "weather":
        from .. import gazette as gazette_mod
        return world.climate_report() + "\n\n" + await gazette_mod.report_text()

    if verb == "dove":
        sub = parts[1].lower() if len(parts) > 1 else ""
        async with db.connect() as conn:
            if not sub:
                pending = await farming.get_gugu_dove_pending(conn, s["id"])
                if not pending:
                    return "没有斑鸠盯梢。昼间 sow/tend 每天掷一次，碰上才触发"
                return farming.gugu_dove_prompt_text(pending)
            msg = await farming.resolve_gugu_dove(conn, s, sub)
            await conn.commit()
        return msg

    if verb == "status":
        from .. import land as land_mod
        if orchard_ctx:
            parcels = await db.get_parcels(s["id"], orchard=1)
            return await land_mod.status_text(s, parcels, orchard=True)
        if greenhouse_ctx:
            parcels = await db.get_parcels(s["id"], greenhouse=1)
            return await land_mod.status_text(s, parcels, greenhouse=True)
        parcels = await db.get_parcels(s["id"])
        plots = [p for p in parcels if not p.get("orchard") and not p.get("greenhouse")]
        trees = [p for p in parcels if p.get("orchard")]
        sheds = [p for p in parcels if p.get("greenhouse")]
        seed_note = ""
        async with db.connect() as conn:
            from .. import seed_lineage as seed_lineage_mod
            seed_note = await seed_lineage_mod.headline(conn, s["id"]) or ""
        body = "\n".join(
            [
                land_mod.sheet_note(s, parcels, orchard=False),
                *(_parcel_line(p) for p in plots),
                land_mod.sheet_note(s, parcels, orchard=True),
                *(_parcel_line(p) for p in trees),
                land_mod.sheet_note(s, parcels, greenhouse=True),
                *(_parcel_line(p) for p in sheds),
            ]
        )
        if seed_note:
            body += "\n" + seed_note
        return body

    if verb == "shed":
        return await _shed_one(s, " ".join(parts[1:]) or "status")

    if verb in ("买棚",) or (
        greenhouse_ctx and verb in (
            "land", "买地", "expand", "买", "扩", "erect", "确认", "ok", "yes", "buy"
        )
    ):
        from .. import land as land_mod
        sub = parts[1].lower() if len(parts) > 1 else ""
        buying = verb in ("expand", "erect", "确认", "ok", "yes", "buy") or sub in (
            "buy", "确认", "ok", "yes", "买", "扩", "erect"
        )
        if buying:
            async with db.connect() as conn:
                msg = await land_mod.buy(conn, s, greenhouse=True)
                await db.add_chronicle(
                    "plot",
                    f"{s['name']} 买棚至 {s.get('greenhouse_count')} 座",
                    s["id"],
                    conn=conn,
                )
                await conn.commit()
            return msg
        parcels = await db.get_parcels(s["id"], greenhouse=1)
        return await land_mod.status_text(s, parcels, greenhouse=True)

    if verb in ("买园",) or (
        orchard_ctx and verb in ("land", "买地", "地契", "expand", "买", "扩")
    ):
        from .. import land as land_mod
        sub = parts[1].lower() if len(parts) > 1 else ""
        buying = verb == "expand" or sub in ("buy", "确认", "ok", "yes", "买", "扩")
        if buying:
            async with db.connect() as conn:
                msg = await land_mod.buy(conn, s, orchard=True)
                await db.add_chronicle(
                    "plot",
                    f"{s['name']} 买园至 {s.get('orchard_count')} 树位",
                    s["id"],
                    conn=conn,
                )
                await conn.commit()
            return msg
        parcels = await db.get_parcels(s["id"], orchard=1)
        return await land_mod.status_text(s, parcels, orchard=True)

    if verb in ("land", "买地", "地契", "expand"):
        from .. import land as land_mod
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
        parcels = await db.get_parcels(s["id"], orchard=0)
        return await land_mod.status_text(s, parcels)

    if verb in ("cohort", "邻居", "neighbors", "neighbour", "peers", "在线", "online"):
        from .. import multi as multi_mod
        return await multi_mod.list_neighbors(s, online_only=verb in ("在线", "online"))

    if verb in ("catalog", "crops"):
        from ..catalog import crop_catalog_line
        from .. import season as season_mod
        lines = [crop_catalog_line(k) for k in CROPS]
        return (
            "作物清单（短茬快、把数多；稀有慢、把数少。偷菜最多 30%，不能摘空）\n"
            f"{season_mod.month_line()}\n"
            "买种 + 露天/果园 sow 须当季或全年（一周一季）；已种的继续长。温室 棚N 种菜种树都不受季节（sow 99=棚1）。\n"
            "果树进果园或温室（sow 园1 橘子 / sow 棚1 橘子 / 果园 sow 1 芒果）；份地只种菜。\n"
            + "\n".join(lines)
            + "\n树清地：plot_ops chop 园1（不必等过熟）"
        )

    if verb == "buy" and len(parts) >= 2 and parts[1] in ("地", "land", "份地"):
        from .. import land as land_mod
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

    if verb == "buy" and len(parts) >= 2 and parts[1] in ("棚", "温室", "greenhouse", "shed"):
        from .. import land as land_mod
        async with db.connect() as conn:
            msg = await land_mod.buy(conn, s, greenhouse=True)
            await db.add_chronicle(
                "plot",
                f"{s['name']} 买棚至 {s.get('greenhouse_count')} 座",
                s["id"],
                conn=conn,
            )
            await conn.commit()
        return msg

    if verb == "buy" and len(parts) >= 2 and parts[1] in ("园", "orchard", "果园"):
        from .. import land as land_mod
        async with db.connect() as conn:
            msg = await land_mod.buy(conn, s, orchard=True)
            await db.add_chronicle(
                "plot",
                f"{s['name']} 买园至 {s.get('orchard_count')} 树位",
                s["id"],
                conn=conn,
            )
            await conn.commit()
        return msg

    if verb == "buy" and len(parts) >= 3:
        qty, crop = _parse_int(parts[1]), resolve_crop_key(" ".join(parts[2:]))
        if not crop:
            raise ValueError(unknown_crop_message(" ".join(parts[2:])))
        from .. import season as season_mod
        season_mod.assert_crop_in_season(crop)
        seed = f"seed_{crop}"
        cost = CROPS[crop]["seed_price"] * qty
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"工分票不足，需要 {cost}")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
            await db.add_item(conn, s["id"], seed, qty)
            await conn.commit()
        return (
            f"购入 {CROPS[crop]['name']}种 x{qty}（-{cost} 票）。"
            "同种可占多组。好感打折去 visit_ops tt buy"
        )

    if verb == "sow" and len(parts) >= 3:
        from .. import land as land_mod
        crop = resolve_crop_key(" ".join(parts[2:]))
        if not crop:
            raise ValueError(unknown_crop_message(" ".join(parts[2:])))
        slot, orchard_flag, gh_flag = land_mod.parse_slot_ref(
            parts[1], orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx
        )
        is_tree = bool(CROPS[crop].get("tree"))
        if is_tree:
            if gh_flag or greenhouse_ctx:
                orchard_flag = 0
                gh_flag = 1
            else:
                orchard_flag = 1
                gh_flag = 0
        elif orchard_flag:
            raise ValueError(
                "果园只种果树（青柠/橘子/柚子/柠檬/桃/橄榄/桑葚/咖啡/可可等）。"
                "蔬菜走 plot_ops sow 1 甘蓝 或 sow 棚1 甘蓝"
            )
        elif greenhouse_ctx:
            gh_flag = 1
        seed = f"seed_{crop}"
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            plot = await land_mod.fetch_plot(conn, s["id"], slot, orchard_flag, gh_flag)
            if not plot:
                raise ValueError(land_mod.missing_slot_msg(slot, orchard_flag, gh_flag))
            land_mod.assert_ready(plot)
            if plot.get("crop"):
                raise ValueError(f"{land_mod.slot_label(plot)} 已在种植")
            from .. import season as season_mod
            season_mod.assert_crop_in_season(crop, greenhouse=bool(plot.get("greenhouse")))
            if not await db.take_item(conn, s["id"], seed, 1):
                raise ValueError(f"缺少 {CROPS[crop]['name']}种")
            from .. import soil as soil_mod
            from .. import seed_lineage as seed_lineage_mod
            _, rot_note = await soil_mod.apply_sow_rotation(conn, plot, crop)
            fert = await soil_mod.read_fertility(conn, plot)
            grow_target, grow_pace, sow_flavor = farming.roll_grow(crop, plot)
            if not plot.get("greenhouse"):
                grow_target = int(grow_target * soil_mod.grow_target_mult(fert))
            lin = await seed_lineage_mod.get_lineage(conn, s["id"], crop)
            seed_gen = int(lin["generation"]) if lin else 0
            tree_max = farming.calc_tree_harvest_max(crop) if is_tree else 0
            tree_born = db.now() if is_tree else 0
            await conn.execute(
                """
                UPDATE parcels SET crop=?, planted_at=?, tended=0, grow_target=?, grow_pace=?,
                harvest_left=0, fertilized=0, watered=0, tree_harvests=0, tree_harvest_max=?,
                tree_born_at=?, seed_generation=?, pest_key=NULL, pest_level=0
                WHERE id=?
                """,
                (crop, db.now(), grow_target, grow_pace, tree_max, tree_born, seed_gen, plot["id"]),
            )
            extra = await events.roll_after_action(
                s, "sow", conn, protected_parcel_id=plot["id"],
            )
            farm = await farming.roll_farm_event(conn, s, "sow")
            dove = await farming.maybe_gugu_dove_stalk(conn, s, plot["id"])
            from .. import bond as bond_mod
            await bond_mod.grant(conn, s["id"], bond_mod.SOW, "labor")
            await conn.commit()
        msg = f"{land_mod.slot_label(plot)} 播下 {CROPS[crop]['emoji']}{CROPS[crop]['name']}\n{sow_flavor}"
        if rot_note:
            msg += f"\n{rot_note}"
        if seed_gen:
            msg += f"\n带上第{seed_gen}代种"
        if dove:
            msg += f"\n{dove}"
        elif farm:
            msg += f"\n{farm}"
        return f"{msg}\n{extra}" if extra else msg

    if verb == "tend":
        from .. import land as land_mod
        slot_token = parts[1] if len(parts) >= 2 else None
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            if slot_token:
                plot = await _load_named_plot(
                    conn, s["id"], slot_token,
                    orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx,
                    fallback_other=True,
                )
                land_mod.assert_ready(plot)
                if not plot.get("crop"):
                    raise ValueError(f"{land_mod.slot_label(plot)} 没种东西")
                if farming.plot_ready(plot) or farming.plot_overripe(plot):
                    raise ValueError(f"{land_mod.slot_label(plot)} 已经熟了，直接收吧")
                if plot.get("tended"):
                    raise ValueError("这一茬已经打理过了")
                rows = [(plot["id"],)]
            else:
                tend_sql = (
                    "SELECT id FROM parcels WHERE steward_id=? AND crop IS NOT NULL AND tended=0"
                )
                if orchard_ctx:
                    tend_sql += " AND COALESCE(orchard,0)=1"
                cur = await conn.execute(tend_sql, (s["id"],))
                rows = await cur.fetchall()
            hoe = await (await conn.execute(
                "SELECT quantity FROM satchel WHERE steward_id=? AND item='tool_hoe' AND quantity>0",
                (s["id"],),
            )).fetchone()
            from .. import hut as hut_mod
            hut_b = await hut_mod.get_bonuses(conn, s["id"])
            # 温室私改件：持有即减轻阵风生长惩罚
            has_greenhouse_part = (await (await conn.execute(
                "SELECT 1 FROM satchel WHERE steward_id=? AND item='ut_greenhouse_part' AND quantity>0",
                (s["id"],),
            )).fetchone()) is not None
            iron_edge = hut_b.has("iron_edge")
            if iron_edge:
                tend_cut = 70
                worm_chance = 0.34
            elif hoe:
                tend_cut = 40
                worm_chance = 0.28
            else:
                tend_cut = 0
                worm_chance = 0.14
            for (pid,) in rows:
                await conn.execute("UPDATE parcels SET tended=1 WHERE id=?", (pid,))
                if tend_cut:
                    await conn.execute(
                        "UPDATE parcels SET grow_target=MAX(120, grow_target-?) WHERE id=? AND grow_target>0",
                        (tend_cut, pid),
                    )
                gale_grow = hut_b.gale_grow
                if has_greenhouse_part:
                    gale_grow *= 0.85
                if world.current_weather() == "gale" and gale_grow < 1:
                    cut = int(80 * (1 - gale_grow))
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
            gnat_msg = ""
            if rows and await events.gnat_swarm_revert_tend():
                cur_out = await conn.execute(
                    """
                    SELECT id FROM parcels
                    WHERE steward_id=? AND greenhouse=0 AND crop IS NOT NULL AND tended=1
                    """,
                    (s["id"],),
                )
                outdoor = [r[0] for r in await cur_out.fetchall()]
                if outdoor:
                    await conn.execute(
                        "UPDATE parcels SET tended=0 WHERE id=?",
                        (random.choice(outdoor),),
                    )
                    gnat_msg = "\n小虫过境，有一块露天作物又得再打理一遍"
            worm_msg = ""
            if random.random() < worm_chance:
                await db.add_item(conn, s["id"], "bait_worm", random.randint(1, 2))
                worm_msg = "\n翻出蚯蚓饵，钓鱼佬狂喜"
                if iron_edge:
                    worm_msg += "（铁锄刃加分）"
                elif hoe:
                    worm_msg += "（锄头加分）"
            from .. import tale as tale_mod
            tale_extra = await tale_mod.check_action_progress(conn, s["id"], "plot")
            from .. import cloth as cloth_mod
            cloth_echo = await cloth_mod.try_echo(conn, s, "plot")
            ill_note = await health.maybe_insomnia(conn, s["id"])
            if rows:
                from .. import bond as bond_mod
                await bond_mod.grant(conn, s["id"], bond_mod.TEND, "labor")
            from .. import gear_wear as gear_wear_mod
            if rows:
                await gear_wear_mod.wear(conn, s["id"], "hoe")
            glitch = ""
            from .. import light_bad_events as light_bad_mod
            if slot_token:
                glitch = await light_bad_mod.roll_tend_glitch(conn, s["id"], plot) or ""
            elif rows:
                prow = await (await conn.execute(
                    "SELECT * FROM parcels WHERE id=?", (rows[0][0],)
                )).fetchone()
                if prow:
                    glitch = await light_bad_mod.roll_tend_glitch(conn, s["id"], dict(prow)) or ""
            from .. import plot_pests as pests_mod
            pest_notes: list[str] = []
            for (pid,) in rows:
                prow = await (await conn.execute(
                    "SELECT * FROM parcels WHERE id=?", (pid,)
                )).fetchone()
                if prow:
                    pn = await pests_mod.maybe_spawn(conn, dict(prow))
                    if pn:
                        pest_notes.append(pn)
            from .. import event_catalog as evcat_mod

            wipe = await evcat_mod.roll_crop_wipe(conn, s["id"])
            if wipe:
                pest_notes.append(wipe)
            await conn.commit()
        noun = "树位" if orchard_ctx else "份地"
        msg = f"打理了 {len(rows)} 块{noun}" if rows else f"没有待打理的{noun}——苗都乖，或你还没种"
        if glitch:
            msg += f"\n{glitch}"
        if iron_edge and rows:
            msg += " · 铁锄刃松土"
        elif hoe and rows:
            msg += " · 锄头松土"
        msg += flavor.maybe_suffix(flavor.TEND_SUFFIX)
        if dove:
            msg += f"\n{dove}"
        elif farm:
            msg += f"\n{farm}"
        if disc:
            msg += f"\n{disc}"
        if gnat_msg:
            msg += gnat_msg
        if worm_msg:
            msg += worm_msg
        if tale_extra:
            msg += f"\n\n{tale_extra}"
        if cloth_echo:
            msg += f"\n\n{cloth_echo}"
        if ill_note:
            msg += f"\n{ill_note}\n→ visit_ops clinic treat …（必须花票）"
        if pest_notes:
            msg += "\n" + "\n".join(pest_notes)
        return f"{msg}\n{extra}" if extra else msg

    if verb == "shake" and len(parts) >= 2:
        from .. import land as land_mod
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            plot = await _load_named_plot(
                conn, s["id"], parts[1], orchard_ctx=True, fallback_other=True
            )
            land_mod.assert_ready(plot)
            if not plot.get("crop"):
                raise ValueError(f"{land_mod.slot_label(plot)} 没有可摇的树")
            meta = CROPS.get(plot["crop"], {})
            if not meta.get("shake"):
                raise ValueError(f"{meta.get('name', plot['crop'])} 不能摇，只能 gather")
            result = await farming.shake_tree(conn, s["id"], plot)
            if not result:
                raise ValueError("还没熟，等等再摇")
            item, qty, tree_note = result
            from .. import bond as bond_mod
            await bond_mod.grant(conn, s["id"], bond_mod.SHAKE, "labor")
            await conn.commit()
        name = ITEM_NAMES.get(item, item)
        msg = f"{land_mod.slot_label(plot)} 摇下 {name} x{qty}" + flavor.maybe_suffix(["椰子：重力赞助", "树：今天也配合"])
        if tree_note:
            msg += f"\n{tree_note}"
        return msg

    if verb in ("water", "浇水", "浇"):
        from .. import land as land_mod
        slot_token = parts[1] if len(parts) >= 2 else None
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            if slot_token:
                plots = [await _load_named_plot(conn, s["id"], slot_token, orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx)]
            else:
                water_sql = "SELECT * FROM parcels WHERE steward_id=? AND crop IS NOT NULL"
                if orchard_ctx:
                    water_sql += " AND COALESCE(orchard,0)=1"
                plots = [dict(r) for r in await (await conn.execute(
                    water_sql, (s["id"],),
                )).fetchall()]
            from .. import config as cfg
            lines = []
            for plot in plots:
                land_mod.assert_ready(plot)
                label = land_mod.slot_label(plot)
                if not plot.get("crop"):
                    if slot_token:
                        raise ValueError(f"{label} 没种东西")
                    continue
                if farming.plot_ready(plot) or farming.plot_overripe(plot):
                    if slot_token:
                        raise ValueError(f"{label} 已经熟了，浇水赶不上了。gather 收")
                    continue
                if plot.get("watered"):
                    lines.append(f"{label} 已经浇过水")
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
                        f"{label} 浇了水，成熟提前 {farming.format_grow_eta(saved)}"
                        f"（还需 {eta}）"
                    )
                else:
                    lines.append(f"{label} 浇了水，地更润，生长略快（还需 {eta}）")
            watered_n = sum(1 for x in lines if "浇了水" in x)
            if watered_n:
                from .. import bond as bond_mod
                await bond_mod.grant(conn, s["id"], bond_mod.WATER * watered_n, "labor")
            await conn.commit()
        if not lines:
            return "没有能浇的地——先 sow，或已经浇过/熟了"
        return "\n".join(lines)

    if verb in ("fertilize", "施肥"):
        from .. import land as land_mod
        slot_token = None
        fert_token = "compost"
        rest = parts[1:]
        if rest:
            try:
                land_mod.parse_slot_ref(rest[0], orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx)
                slot_token = rest[0]
                fert_token = rest[1] if len(rest) > 1 else "compost"
            except ValueError:
                fert_token = rest[0]
        fert_item = resolve_item_key(fert_token) or fert_token
        from ..catalog import MANURE
        if fert_item not in MANURE and fert_item not in ("compost", "ash_fert"):
            raise ValueError("施肥用堆肥、病株灰肥或羊粪/猪粪/牛粪。例子：施肥 1 · 施肥 1 灰肥")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            if slot_token:
                plots = [await _load_named_plot(conn, s["id"], slot_token, orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx)]
            else:
                fert_sql = (
                    "SELECT * FROM parcels WHERE steward_id=? AND crop IS NOT NULL AND fertilized=0"
                )
                if orchard_ctx:
                    fert_sql += " AND COALESCE(orchard,0)=1"
                plots = [dict(r) for r in await (await conn.execute(
                    fert_sql, (s["id"],),
                )).fetchall()]
            lines = []
            mascot = s.get("mascot_trait") == "compost"
            for plot in plots:
                land_mod.assert_ready(plot)
                plabel = land_mod.slot_label(plot)
                if not plot.get("crop"):
                    if slot_token:
                        raise ValueError(f"{plabel} 没种东西")
                    continue
                if farming.plot_ready(plot) or farming.plot_overripe(plot):
                    if slot_token:
                        raise ValueError(f"{plabel} 已经熟了，肥料留给下一茬")
                    continue
                if plot.get("fertilized"):
                    lines.append(f"{plabel} 已经施过肥")
                    continue
                if not await db.take_item(conn, s["id"], fert_item, 1):
                    need = farming.fertilizer_label(fert_item)
                    if not lines:
                        raise ValueError(
                            f"施肥需要 {need} x1（forage / hut_ops 堆肥桶 存 粪便 可攒）"
                        )
                    lines.append(f"{need} 不够了，施到 {plabel} 前停手")
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
                        f"{plabel} 已施{label}，成熟提前 {farming.format_grow_eta(saved)}"
                        f"（还需 {eta}）{extra}"
                    )
                else:
                    lines.append(
                        f"{plabel} 已施{label}，生长略快（还需 {eta}）{extra}"
                    )
            fert_n = sum(1 for x in lines if "已施" in x)
            if fert_n:
                from .. import bond as bond_mod
                await bond_mod.grant(conn, s["id"], bond_mod.FERTILIZE * fert_n, "labor")
            await conn.commit()
        if not lines:
            return "没有能施肥的地——先 sow，或已经施过/熟了"
        return "\n".join(lines)

    if verb == "scarecrow" and len(parts) >= 2:
        from .. import land as land_mod
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            plot = await _load_named_plot(conn, s["id"], parts[1], orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx)
            land_mod.assert_ready(plot)
            slot = plot["slot"]
            if plot.get("scarecrow"):
                return f"{land_mod.slot_label(plot)} 已有稻草人"
            if await db.take_item(conn, s["id"], "scarecrow", 1):
                pass
            else:
                from ..config import SCARECROW_COST
                for item, need in SCARECROW_COST.items():
                    if not await db.take_item(conn, s["id"], item, need):
                        raise ValueError(f"扎稻草人需要 scarecrow 或 漂绳x2+堆肥x1")
            await conn.execute("UPDATE parcels SET scarecrow=1 WHERE id=?", (plot["id"],))
            from .. import bond as bond_mod
            await bond_mod.grant(conn, s["id"], bond_mod.SCARECROW, "labor")
            await conn.commit()
        return f"{land_mod.slot_label(plot)} 扎好稻草人，鸟儿的自助餐厅关门"

    if verb == "compost" and len(parts) >= 2:
        from .. import land as land_mod
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            plot = await _load_named_plot(
                conn, s["id"], parts[1], orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx, fallback_other=True
            )
            slot = land_mod.slot_label(plot)
            land_mod.assert_ready(plot)
            if not plot.get("crop"):
                raise ValueError(f"{slot} 空着")
            meta = CROPS.get(plot["crop"], {"name": plot["crop"]})
            overripe = farming.plot_overripe(plot)
            ready = farming.plot_ready(plot)
            if meta.get("tree") and not overripe:
                raise ValueError(
                    f"{slot} {meta['name']}树还没过熟。树收完会再长，不想要了才 `plot_ops chop {slot}`；"
                    "过熟清果用 gather 或 compost，树会留下。"
                )
            if not overripe and not ready:
                raise ValueError("只有过熟/枯的才进堆肥桶")
            crop_name = meta["name"]
            compost_qty = random.randint(2, 3)
            await db.add_item(conn, s["id"], "compost", compost_qty)
            if meta.get("tree"):
                planted_at, grow_target, grow_pace = farming.regrow_tree_after_clear(
                    plot["crop"], plot
                )
                await conn.execute(
                    """
                    UPDATE parcels SET planted_at=?, tended=0, grow_target=?, grow_pace=?,
                    fertilized=0, watered=0, harvest_left=0 WHERE id=?
                    """,
                    (planted_at, grow_target, grow_pace, plot["id"]),
                )
                from .. import bond as bond_mod
                await bond_mod.grant(conn, s["id"], bond_mod.COMPOST, "labor")
                await conn.commit()
                return (
                    f"{slot} {crop_name}过熟落果 → 堆肥桶 ×{compost_qty}，"
                    "树还在，重新结果"
                )
            await conn.execute(
                """
                UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                grow_target=0, grow_pace='', fertilized=0, watered=0, harvest_left=0 WHERE id=?
                """,
                (plot["id"],),
            )
            from .. import bond as bond_mod
            await bond_mod.grant(conn, s["id"], bond_mod.COMPOST, "labor")
            await conn.commit()
        return f"{slot} {crop_name} → 堆肥桶，土肥了"

    if verb == "chop" and len(parts) >= 2:
        from .. import land as land_mod
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            plot = await _load_named_plot(
                conn, s["id"], parts[1], orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx, fallback_other=True
            )
            slot = land_mod.slot_label(plot)
            land_mod.assert_ready(plot)
            result = farming.chop_tree(plot)
            if not result["ok"]:
                raise ValueError(f"{slot} {result['msg']}")
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
                "chop", f"{s['name']} 砍倒 {slot} {result['name']}树", s["id"], conn=conn
            )
            from .. import bond as bond_mod
            await bond_mod.grant(conn, s["id"], bond_mod.CHOP, "labor")
            await conn.commit()
        loot_s = "、".join(loot_txt)
        msg = (
            f"{slot} 砍倒{result['name']}树，地空了。{result['note']} 捡到 {loot_s}。"
            + flavor.maybe_suffix(flavor.CHOP_SUFFIX)
        )
        if farm:
            msg += f"\n{farm}"
        if extra:
            msg += f"\n{extra}"
        return msg

    if verb == "chop":
        raise ValueError("用法: plot_ops chop 地块或园1")

    if verb == "gather":
        from .. import land as land_mod
        slot_token = parts[1] if len(parts) >= 2 else None
        got = []
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            gather_sql = "SELECT * FROM parcels WHERE steward_id=?"
            if orchard_ctx and not slot_token:
                gather_sql += " AND COALESCE(orchard,0)=1"
            parcels = [dict(r) for r in await (await conn.execute(
                gather_sql, (s["id"],)
            )).fetchall()]
            if slot_token:
                target = await _load_named_plot(
                    conn, s["id"], slot_token, orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx, fallback_other=True
                )
                parcels = [p for p in parcels if p.get("id") == target["id"]]
                if not parcels:
                    raise ValueError(land_mod.missing_slot_msg(
                        *land_mod.parse_slot_ref(slot_token, orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx)
                    ))
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
                    from .. import plot_pests as pests_mod
                    pest_mult = pests_mod.yield_mult(p)
                    item_key, qty, keep_plot = await farming.gather_yield(conn, s["id"], p)
                    if pest_mult < 1.0 and qty > 0:
                        qty = max(1, int(qty * pest_mult))
                        dove_note += "(虫害减收)"
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
                    from .. import item_traits as traits_mod
                    from .. import seed_lineage as seed_lineage_mod
                    lin = await seed_lineage_mod.get_lineage(conn, s["id"], p["crop"])
                    if lin and int(p.get("seed_generation") or 0) > 0:
                        p = dict(p)
                        p["_seed_bias"] = lin.get("bias") or ""
                    quality = traits_mod.roll_crop_quality(p)
                    await traits_mod.grant_satchel(
                        conn, s["id"], item_key, qty, quality=quality,
                    )
                    harvest_note = ""
                    from .. import shaonian as shaonian_mod
                    if await shaonian_mod.harvest_bonus_roll(conn, s["id"]):
                        await traits_mod.grant_satchel(
                            conn, s["id"], item_key, qty, quality=quality,
                        )
                        harvest_note = f"(丰收卦+{qty})"
                    if keep_plot:
                        keep_plot, tree_note = await farming.record_tree_harvest(conn, p)
                        if keep_plot:
                            grow_target, grow_pace, _ = farming.roll_grow(p["crop"], p)
                            await conn.execute(
                                """
                                UPDATE parcels SET planted_at=?, tended=0, grow_target=?, grow_pace=?,
                                fertilized=0, watered=0, harvest_left=0 WHERE id=?
                                """,
                                (db.now(), grow_target, grow_pace, p["id"]),
                            )
                            tev = await farming.roll_tree_event(conn, s["id"], p)
                            if tev:
                                tree_note = f"{tree_note}\n{tev}" if tree_note else tev
                    else:
                        tree_note = ""
                        from .. import soil as soil_mod
                        await soil_mod.on_harvest_clear(conn, p, p["crop"])
                        await conn.execute(
                            """
                            UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                            grow_target=0, grow_pace='', fertilized=0, watered=0, scarecrow=0, harvest_left=0,
                            tree_harvests=0, tree_harvest_max=0, seed_generation=0,
                            pest_key=NULL, pest_level=0 WHERE id=?
                            """,
                            (p["id"],),
                        )
                    if item_key.startswith("seed_"):
                        got.append(
                            f"{CROPS[p['crop']]['name']}种(过熟) x{qty}{harvest_note}{tree_note}"
                        )
                    else:
                        got.append(
                            f"{CROPS[p['crop']]['name']} x{qty}{harvest_note}{dove_note}{tree_note}"
                        )
                elif farming.plot_overripe(p):
                    meta = CROPS.get(p["crop"], {})
                    is_tree = bool(meta.get("tree"))
                    if random.random() < 0.5:
                        await db.add_item(conn, s["id"], "compost", 2)
                        got.append(f"{CROPS[p['crop']]['name']}(堆肥)")
                    if is_tree:
                        keep_tree, th_note = await farming.record_tree_harvest(conn, p)
                        if keep_tree:
                            planted_at, grow_target, grow_pace = farming.regrow_tree_after_clear(
                                p["crop"], p
                            )
                            await conn.execute(
                                """
                                UPDATE parcels SET planted_at=?, tended=0, grow_target=?, grow_pace=?,
                                fertilized=0, watered=0, harvest_left=0 WHERE id=?
                                """,
                                (planted_at, grow_target, grow_pace, p["id"]),
                            )
                            got.append(f"{meta['name']}树（过熟清果，重新结果）{th_note}")
                        else:
                            got.append(f"{meta['name']}树{th_note}")
                    else:
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
            ill_note = await health.maybe_insomnia(conn, s["id"])
            from .. import tale as tale_mod
            tale_extra = await tale_mod.check_action_progress(conn, s["id"], "plot")
            if got:
                from .. import bond as bond_mod
                await bond_mod.grant(conn, s["id"], bond_mod.GATHER_PLOT * max(1, len(got)), "labor")
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
            if slot_token is not None and parcels:
                p = parcels[0]
                plabel = land_mod.slot_label(p)
                if not p.get("crop"):
                    msg = f"{plabel} 休耕，无可收"
                elif not farming.plot_ready(p) and not farming.plot_overripe(p):
                    cname = CROPS[p["crop"]]["name"]
                    _, _, left = farming.grow_progress(p)
                    msg = f"{plabel} {cname} 还需 {farming.format_grow_eta(left)}{wait_hint}"
                else:
                    msg = f"{plabel} 暂无可收（plot_ops status 查看详情）"
            elif nearest is not None and min_left is not None:
                cname = CROPS[nearest["crop"]]["name"]
                msg += f"（{land_mod.slot_label(nearest)} {cname} 还需 {farming.format_grow_eta(min_left)}）{wait_hint}"
            if tale_extra:
                msg += f"\n\n{tale_extra}"
            return f"{msg}\n{extra}" if extra else msg
        await db.add_chronicle("gather", f"{s['name']} 收成 {', '.join(got)}", s["id"])
        from .. import multi
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
            if tale_extra:
                base += f"\n\n{tale_extra}"
            if ill_note:
                base += f"\n{ill_note}\n→ visit_ops clinic treat …（必须花票）"
            return f"{base}\n{extra}" if extra else base
        base = f"收成: {', '.join(got)}"
        base += flavor.maybe_suffix(flavor.GATHER_SUFFIX)
        if farm:
            base += f"\n{farm}"
        if disc:
            base += f"\n{disc}"
        if tale_extra:
            base += f"\n\n{tale_extra}"
        if ill_note:
            base += f"\n{ill_note}\n→ visit_ops clinic treat …（必须花票）"
        return f"{base}\n{extra}" if extra else base

    if verb == "forage":
        today = db.day_id()
        last = db.day_id(s["forage_at"]) if s["forage_at"] else 0
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
            from .. import tale as tale_mod
            tale_extra = await tale_mod.check_action_progress(conn, s["id"], "plot")
            from .. import bond as bond_mod
            await bond_mod.grant(conn, s["id"], bond_mod.FORAGE, "labor")
            from .. import cloth as cloth_mod
            cloth_echo = await cloth_mod.try_echo(conn, s, "plot")
            from .. import marriage as marriage_mod
            betroth_find = await marriage_mod.maybe_place_find(conn, s["id"], "forage")
            await conn.commit()
        await db.add_chronicle("forage", f"{s['name']} 在份地边际采到 {label}", s["id"])
        msg = f"边际采集：{label} x{qty}"
        msg += flavor.maybe_suffix(flavor.FORAGE_SUFFIX)
        if disc:
            msg += f"\n{disc}"
        if tale_extra:
            msg += f"\n\n{tale_extra}"
        if cloth_echo:
            msg += f"\n\n{cloth_echo}"
        if betroth_find:
            msg += f"\n{betroth_find}"
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
            from .. import multi as multi_mod
            roster = await multi_mod.list_neighbors(s, online_only=False)
            raise ValueError("用法: plot_ops 偷菜 名字 [地块]\n" + roster)
        slot_token = parts[2] if len(parts) >= 3 else None
        return await events.manual_scrump(s, parts[1], slot_token)

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
        from .. import lore as lore_mod
        hint = lore_mod.hedge_note_hint()
        return f"篱笆条已留给 {peer}\n（篱间文学灵感：「{hint}」· lore_ops hedge 换一条）"

    if verb == "amends" and len(parts) >= 2:
        peer = await db.get_steward_by_name(parts[1])
        if not peer:
            raise ValueError("找不到该管理员")
        async with db.connect() as conn:
            await survival.bump(conn, s["id"], standing=10, mist_wit=3)
            await survival.bump(conn, peer["id"], standing=3)
            from .. import bond as bond_mod
            await bond_mod.grant(conn, s["id"], bond_mod.AMENDS, "people")
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
        f"未知 plot 指令: {cmd}。常用: status · sow 1 甘蓝 · tend 1 · 浇水 1 · 施肥 1 · gather 1"
    )


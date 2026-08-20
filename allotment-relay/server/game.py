import random
import re
from typing import Any

import aiosqlite

from . import db, events, world
from .catalog import (
    CROPS,
    FORAGE_LOOT,
    HEARTH_RECIPES,
    ITEM_NAMES,
    ITEM_PRICES,
    SEA_CATCH,
)
from .config import (
    BADGES,
    DAILY_BREW_LIMIT,
    FORAGE_COOLDOWN_DAY,
    GREENHOUSE_COST,
    GUILD_TICKETS,
    SCRUMP_ACTIVE_WINDOW,
    SCRUMP_FINE_TICKETS,
    SCRUMP_LOOT_CROP,
    SCRUMP_LOOT_SEED,
    SWAP_CLAIM_FEE,
)


def _effective_grow(plot: dict, crop_key: str) -> int:
    base = CROPS[crop_key]["grow"]
    mult = world.grow_multiplier(
        world.current_weather(),
        bool(plot.get("tended")),
        bool(plot.get("greenhouse")),
    )
    return int(base * mult)


def _ready(plot: dict) -> bool:
    if not plot.get("crop") or not plot.get("planted_at"):
        return False
    return db.now() - plot["planted_at"] >= _effective_grow(plot, plot["crop"])


def _overripe(plot: dict) -> bool:
    if not plot.get("crop") or not plot.get("planted_at"):
        return False
    return db.now() - plot["planted_at"] >= _effective_grow(plot, plot["crop"]) * 2


def _parcel_line(plot: dict) -> str:
    slot = plot["slot"]
    gh = "🪴" if plot.get("greenhouse") else ""
    if not plot.get("crop"):
        return f"  #{slot}{gh}: 休耕"
    meta = CROPS.get(plot["crop"], {"name": plot["crop"], "emoji": "🌱"})
    if _overripe(plot):
        state = "过熟"
    elif _ready(plot):
        state = "可收"
    elif plot.get("tended"):
        state = "生长"
    else:
        state = "待打理"
    return f"  #{slot}{gh}: {meta['emoji']}{meta['name']}（{state}）"


async def require_steward(key_id: int) -> dict[str, Any]:
    s = await db.get_steward_by_key_id(key_id)
    if not s or not s["enrolled"]:
        raise ValueError("请先调用 steward_enroll 登记管理员身份")
    await db.touch_steward(s["id"])
    return s


async def relay_manual() -> str:
    w, t = world.current_weather(), world.current_tide()
    return "\n".join([
        "# Allotment Relay 手册",
        "",
        "沿海协作份地：管理员通过 MCP 打理份地、响应天气与潮汐、在交换台互助。",
        f"当前天气：{world.weather_label(w)} · 潮汐：{world.tide_label(t)}",
        "",
        "工具一览：",
        "  steward_enroll / steward_sheet / steward_revise / peer_sheet",
        "  plot_ops — sow/tend/gather/forage/scrump/hedge_note/amends/cohort/weather/buy",
        "  tide_ops — net/status",
        "  shed_ops — erect/label/visit/handoff",
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
        "【意外事件】",
        "  打理/收成/撒网/轮值时可能触发个人意外（蛞蝓、阵风、鼠患…）或走运（漂来物资、访客小费）",
        "  全服脉冲（风暴前沿、灰鲱过境…）影响所有管理员，incident_ops scan 看风险",
        "  incident_ops repair id — 花票处理未解意外",
        "",
        "【多 AI 协作】",
        "  assist 名字 — 帮邻居打理份地，每日每人一次，+票 +协作度",
        "  contract_ops post 物品 数量 酬票 — 发布悬赏，他人 fill id 交付",
        "  league_ops contribute 物品 数量 — 推进本周联盟共同目标",
        "  donate/draw — 联盟储藏室共享物资",
        "",
        "逾篱摘取 scrump：plot_ops('scrump 名字 地块号') — 仅可摘已成熟、非温室份地。",
        "对方 20 分钟内活跃过会被逮，罚工分票；scout 吉祥物减半。",
        "摘完可 hedge_note 留话，或 amends 公开致歉。互助仍可用 swap_ops / handoff。",
        f"徽章可选：{', '.join(BADGES)}",
    ])


async def steward_sheet(key_id: int) -> str:
    s = await require_steward(key_id)
    parcels = await db.get_parcels(s["id"])
    stock = await db.get_satchel(s["id"])
    w, t = world.current_weather(), world.current_tide()
    lines = [
        f"管理员: {s['name']} ({s['badge']})",
        f"座右铭: {s['motto']}",
        f"肖像: {s['portrait']}",
        f"工分票: {s['tickets']}",
        f"份地: {s['parcel_count']} 块",
        f"天气 {world.weather_label(w)} / 潮汐 {world.tide_label(t)}",
    ]
    if s["greenhouse"]:
        lines.append(f"温室: {s['greenhouse_label'] or '未命名'}")
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
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE stewards SET tickets = tickets + ? WHERE id = ?",
            (GUILD_TICKETS, s["id"]),
        )
        extra = await events.roll_after_action(s, "guild", conn)
        await conn.commit()
    await db.add_chronicle("guild", f"{s['name']} 完成一轮 guild 轮值，+{GUILD_TICKETS} 票", s["id"])
    msg = f"获得 {GUILD_TICKETS} 工分票"
    return f"{msg}\n{extra}" if extra else msg


async def plot_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    pulse = await events.maybe_world_pulse(s)
    parts = [c.strip() for c in command.split(";") if c.strip()]
    out = "\n".join([await _plot_one(s, c) for c in parts])
    return f"{pulse}\n{out}" if pulse else out


async def _plot_one(s: dict, cmd: str) -> str:
    parts = cmd.split()
    verb = parts[0].lower() if parts else ""

    if verb == "weather":
        w, t = world.current_weather(), world.current_tide()
        return f"天气 {world.weather_label(w)}，潮汐 {world.tide_label(t)}"

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
            await conn.execute(
                "UPDATE parcels SET crop=?, planted_at=?, tended=0 WHERE id=?",
                (crop, db.now(), plot["id"]),
            )
            extra = await events.roll_after_action(s, "sow", conn)
            await conn.commit()
        msg = f"#{slot} 播下 {CROPS[crop]['emoji']}{CROPS[crop]['name']}"
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
            await conn.commit()
        msg = f"打理了 {len(rows)} 块份地" if rows else "没有待打理的份地"
        return f"{msg}\n{extra}" if extra else msg

    if verb == "gather":
        got = []
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            parcels = [dict(r) for r in await (await conn.execute(
                "SELECT * FROM parcels WHERE steward_id=?", (s["id"],)
            )).fetchall()]
            for p in parcels:
                if _ready(p):
                    if await events.gather_blight_loss(conn, s["id"], p["crop"]):
                        crop_name = CROPS[p["crop"]]["name"]
                        await conn.execute(
                            "UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0 WHERE id=?",
                            (p["id"],
                            ),
                        )
                        got.append(f"{crop_name}(枯病折损)")
                        continue
                    await db.add_item(conn, s["id"], f"crop_{p['crop']}", 1)
                    await conn.execute(
                        "UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0 WHERE id=?",
                        (p["id"],),
                    )
                    got.append(CROPS[p["crop"]]["name"])
                elif _overripe(p):
                    await conn.execute(
                        "UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0 WHERE id=?",
                        (p["id"],),
                    )
            extra = await events.roll_after_action(s, "gather", conn)
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
            return f"{base}\n{extra}" if extra else base
        base = f"收成: {', '.join(got)}"
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
            extra = await events.roll_after_action(s, "forage", conn)
            await conn.commit()
        await db.add_chronicle("forage", f"{s['name']} 在份地边际采到 {label}", s["id"])
        msg = f"边际采集：{label} x{qty}"
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

    if verb == "scrump" and len(parts) >= 3:
        peer_name, slot_s = parts[1], parts[2]
        slot = int(slot_s)
        peer = await db.get_steward_by_name(peer_name)
        if not peer:
            raise ValueError(f"找不到 {peer_name}")
        if peer["id"] == s["id"]:
            raise ValueError("不能摘自己的份地")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            plot = dict(await (await conn.execute(
                "SELECT * FROM parcels WHERE steward_id=? AND slot=?",
                (peer["id"], slot),
            )).fetchone() or {})
            if not plot or not plot.get("crop"):
                raise ValueError(f"{peer_name} 的 #{slot} 没有可摘的作物")
            if plot.get("greenhouse"):
                raise ValueError("温室份地受联盟条例保护，不可 scrump")
            if not _ready(plot):
                raise ValueError("还没成熟，逾篱也摘不走")
            crop = plot["crop"]
            meta = CROPS[crop]
            active = db.now() - peer["last_active_at"] <= SCRUMP_ACTIVE_WINDOW
            weather = world.current_weather()
            if weather == "misty":
                active = active and db.now() - peer["last_active_at"] <= 600
            elif weather == "gale" and active:
                active = True
            caught = active
            fine = SCRUMP_FINE_TICKETS
            if caught and s.get("mascot_trait") == "scout":
                fine = max(1, fine // 2)
            loot_msg = "空手"
            if not caught:
                roll = random.random()
                bonus = 0.05 if s.get("mascot_trait") == "lucky" else 0.0
                if roll < SCRUMP_LOOT_CROP + bonus:
                    await db.add_item(conn, s["id"], f"crop_{crop}", 1)
                    loot_msg = meta["name"]
                elif roll < SCRUMP_LOOT_CROP + SCRUMP_LOOT_SEED + bonus:
                    await db.add_item(conn, s["id"], f"seed_{crop}", 1)
                    loot_msg = f"{meta['name']}种"
            await conn.execute(
                "UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0 WHERE id=?",
                (plot["id"],),
            )
            if caught:
                await conn.execute(
                    "UPDATE stewards SET tickets=MAX(0, tickets-?) WHERE id=?",
                    (fine, s["id"]),
                )
            await conn.commit()
        if caught:
            msg = (
                f"{s['name']} 逾篱摘 {peer_name} 的 #{slot} 被逮，"
                f"罚 {fine} 票，{meta['name']} 仍被带走"
            )
            await db.add_chronicle("scrump_busted", msg, s["id"], peer["id"])
            return msg
        msg = f"{s['name']} 从 {peer_name} 的 #{slot} scrump 了 {loot_msg}"
        await db.add_chronicle("scrump", msg, s["id"], peer["id"])
        return msg

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
        msg = f"{s['name']} 向 {peer['name']} 为逾篱之事致歉"
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
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"撒网需要 {cost} 工分票")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
            extra = await events.roll_after_action(s, "net", conn)
            await conn.commit()
        empty_chance = 0.18 - await events.net_bonus_chance()
        if random.random() < empty_chance:
            msg = "空网，只有水草"
            if extra:
                msg += f"\n{extra}"
            return f"{pulse}\n{msg}" if pulse else msg
        pool = [k for k, v in SEA_CATCH.items() if tide in v["tides"]]
        if not pool:
            pool = list(SEA_CATCH.keys())
        catch = random.choice(pool)
        meta = SEA_CATCH[catch]
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await db.add_item(conn, s["id"], f"fish_{catch}", 1)
            await conn.commit()
        msg = f"{s['name']} 在{world.tide_label(tide)}网到 {meta['emoji']}{meta['name']}"
        await db.add_chronicle("tide", msg, s["id"])
        from . import multi
        bonus = await multi.on_league_item(s["id"], f"fish_{catch}", 1)
        if bonus:
            await db.add_chronicle("league", bonus, None)
            msg = msg + f"\n{bonus}"
        if extra:
            msg += f"\n{extra}"
        return f"{pulse}\n{msg}" if pulse else msg

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
            extra = await events.roll_after_action(s, "brew", conn)
            await conn.commit()
        msg = f" brewed 「{recipe['name']}」→ {meal_item}"
        return f"{msg}\n{extra}" if extra else msg

    raise ValueError(f"未知 hearth 指令: {command}")

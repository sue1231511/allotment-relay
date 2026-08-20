import random
from typing import Any

import aiosqlite

from . import db, events, event_gen, flavor, world
from . import commons
from .catalog import ITEM_NAMES, SEA_CATCH, voyage_loot_table
from .config import BOATS, PEN_ERECT_COST, VOYAGE_ROUTES
from .game import require_steward


def _boat_rank(key: str) -> int:
    return BOATS.get(key, {}).get("rank", 0)


def _pen_grow(species: str, fed: bool) -> int:
    base = SEA_CATCH[species]["grow"]
    return base if fed else int(base * 1.45)


def _pen_ready(pen: dict) -> bool:
    if not pen.get("species") or not pen.get("stocked_at"):
        return False
    return db.now() - pen["stocked_at"] >= _pen_grow(pen["species"], bool(pen.get("fed")))


def _pen_line(pen: dict) -> str:
    label = pen.get("pen_label") or f"#{pen['slot']}"
    if not pen.get("species"):
        return f"  {label}: 空池"
    spec = SEA_CATCH[pen["species"]]
    if _pen_ready(pen):
        state = "可收"
    elif pen.get("fed"):
        state = "放养"
    else:
        state = "待投饵"
    return f"  {label}: {spec['emoji']}{spec['name']}（{state}）"


async def _get_pen(conn: aiosqlite.Connection, steward_id: int, slot: int = 1) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM fish_pens WHERE steward_id=? AND slot=?", (steward_id, slot)
    )).fetchone()
    return dict(row) if row else None


async def _get_voyage(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM voyages WHERE steward_id=? AND status='sailing'", (steward_id,)
    )).fetchone()
    return dict(row) if row else None


async def _refresh_steward(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any]:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute("SELECT * FROM stewards WHERE id=?", (steward_id,))).fetchone()
    return dict(row)


async def pen_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            pen = await _get_pen(conn, s["id"])
        boat = BOATS.get(s.get("boat_key") or "", {})
        lines = [
            f"船只: {boat.get('name', '无')} {'(待修)' if s.get('boat_damaged') else ''}".strip(),
        ]
        if pen:
            lines.append("渔排:")
            lines.append(_pen_line(pen))
        else:
            lines.append("渔排: 未搭建（erect）")
        from .catalog import pen_species_keys
        farmable = pen_species_keys()
        lines.append(f"可养 {len(farmable)} 种: {', '.join(farmable[:8])}{'…' if len(farmable) > 8 else ''}")
        return "\n".join(lines)

    if verb == "erect":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            if await _get_pen(conn, s["id"]):
                return "已有渔排"
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < PEN_ERECT_COST:
                raise ValueError(f"搭建渔排需要 {PEN_ERECT_COST} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (PEN_ERECT_COST, s["id"]),
            )
            await conn.execute(
                "INSERT INTO fish_pens (steward_id, slot, pen_label) VALUES (?,1,'')",
                (s["id"],),
            )
            await conn.commit()
        await db.add_chronicle("pen", f"{s['name']} 搭好了渔排", s["id"])
        return f"渔排就绪（-{PEN_ERECT_COST} 票）。stock 品种名 投苗，feed 投饵，harvest 收网"

    if verb == "label" and len(parts) >= 2:
        label = " ".join(parts[1:])[:40]
        async with aiosqlite.connect(db.DB_PATH) as conn:
            pen = await _get_pen(conn, s["id"])
            if not pen:
                raise ValueError("先 erect 渔排")
            await conn.execute("UPDATE fish_pens SET pen_label=? WHERE id=?", (label, pen["id"]))
            await conn.commit()
        return f"渔排命名为「{label}」"

    if verb == "stock" and len(parts) >= 2:
        species = parts[1].lower()
        if species not in SEA_CATCH or not SEA_CATCH[species].get("pen"):
            pen_keys = [k for k, v in SEA_CATCH.items() if v.get("pen")]
            raise ValueError(f"可养品种: {', '.join(pen_keys)}")
        meta = SEA_CATCH[species]
        async with aiosqlite.connect(db.DB_PATH) as conn:
            pen = await _get_pen(conn, s["id"])
            if not pen:
                raise ValueError("先 erect 渔排")
            if pen.get("species"):
                raise ValueError("池中已有鱼苗，先 harvest 或等收网")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < meta["stock_tickets"]:
                raise ValueError(f"投苗需要 {meta['stock_tickets']} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (meta["stock_tickets"], s["id"]),
            )
            await conn.execute(
                "UPDATE fish_pens SET species=?, stocked_at=?, fed=0 WHERE id=?",
                (species, db.now(), pen["id"]),
            )
            pen = await _get_pen(conn, s["id"])
            assert pen
            extra = await events.roll_after_action(s, "pen_stock", conn, pen=pen)
            await conn.commit()
        msg = f"投苗 {meta['emoji']}{meta['name']}（-{meta['stock_tickets']} 票），记得 feed 投饵"
        return f"{msg}\n{extra}" if extra else msg

    if verb == "feed":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            pen = await _get_pen(conn, s["id"])
            if not pen or not pen.get("species"):
                raise ValueError("空池无法投饵")
            if pen.get("fed"):
                return "今日已投饵"
            meta = SEA_CATCH[pen["species"]]
            if not await db.take_item(conn, s["id"], meta["feed_item"], meta["feed_qty"]):
                raise ValueError(
                    f"投饵需要 {ITEM_NAMES.get(meta['feed_item'], meta['feed_item'])} x{meta['feed_qty']}"
                )
            await conn.execute("UPDATE fish_pens SET fed=1 WHERE id=?", (pen["id"],))
            pen = await _get_pen(conn, s["id"])
            assert pen
            extra = await events.roll_after_action(s, "pen_feed", conn, pen=pen)
            await conn.commit()
        msg = f"已向 {SEA_CATCH[pen['species']]['name']} 池投饵"
        return f"{msg}\n{extra}" if extra else msg

    if verb == "harvest":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            pen = await _get_pen(conn, s["id"])
            if not pen or not pen.get("species"):
                raise ValueError("空池无可收")
            if not _pen_ready(pen):
                raise ValueError("尚未长成，继续 feed 或等待")
            species = pen["species"]
            meta = SEA_CATCH[species]
            qty = 2 if pen.get("fed") else 1
            await db.add_item(conn, s["id"], f"fish_{species}", qty)
            await conn.execute(
                "UPDATE fish_pens SET species=NULL, stocked_at=NULL, fed=0 WHERE id=?",
                (pen["id"],),
            )
            extra = await events.roll_after_action(s, "pen_harvest", conn, pen=pen)
            disc = await commons.roll_discovery(conn, s, "pen_harvest")
            await conn.commit()
        from . import multi
        bonus = await multi.on_league_item(s["id"], f"fish_{species}", qty)
        msg = f"收网 {meta['emoji']}{meta['name']} x{qty}"
        msg += flavor.maybe_suffix(flavor.PEN_HARVEST_SUFFIX)
        if bonus:
            await db.add_chronicle("league", bonus, None)
            msg += f"\n{bonus}"
        await db.add_chronicle("pen", f"{s['name']} 渔排收网 {meta['name']} x{qty}", s["id"])
        if disc:
            msg += f"\n{disc}"
        if extra:
            return f"{msg}\n{extra}"
        return msg

    raise ValueError(f"未知 pen 指令: {command}（status/erect/label/stock/feed/harvest）")


async def _apply_naval_encounter(
    conn: aiosqlite.Connection,
    s: dict[str, Any],
    voyage: dict[str, Any],
    loot_lines: list[str],
    fish_loot: list[str],
) -> str:
    s = await _refresh_steward(conn, s["id"])
    enc = event_gen.generate_naval_encounter(
        voyage["route"],
        s,
        bad_bias=0.12 if s.get("boat_damaged") else 0.0,
    )
    if not enc:
        return ""

    cargo_loss = 0
    for eff in enc.effects:
        if eff.startswith("cargo_loss:"):
            cargo_loss = int(eff.split(":")[1])

    await events.apply_effects(conn, s, [e for e in enc.effects if not e.startswith("cargo_loss:")])

    naval_extra = ""
    if enc.kind == "bad":
        from . import health
        extra = await health.maybe_roll_ailment(
            conn, s["id"], "voyage_return",
            pool=health.TRIGGER_AILMENTS["naval_bad"],
            chance=0.22,
            source="naval",
        )
        if extra:
            naval_extra = f"\n{extra}\n→ clinic_ops treat …（必须花票）"

    if cargo_loss:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT item, quantity FROM satchel WHERE steward_id=? AND quantity > 0 ORDER BY RANDOM() LIMIT 6",
            (s["id"],),
        )).fetchall()
        removed_label = None
        for _ in range(cargo_loss):
            if not rows:
                break
            row = random.choice(rows)
            item, qty = row["item"], row["quantity"]
            take = 1
            if await db.take_item(conn, s["id"], item, take):
                removed_label = ITEM_NAMES.get(item, item)
                if item in fish_loot:
                    fish_loot.remove(item)
                rows = [r for r in rows if not (r["item"] == item and r["quantity"] <= take)]
        if removed_label:
            loot_lines.append(f"遭遇扣货：{removed_label} x1")

    return flavor.wrap_naval(enc.kind, enc.label, enc.detail) + naval_extra


async def _resolve_voyage(conn: aiosqlite.Connection, s: dict[str, Any], voyage: dict[str, Any]) -> str:
    route = VOYAGE_ROUTES[voyage["route"]]
    s = await _refresh_steward(conn, s["id"])
    fail_chance = route["fail"] + await events.voyage_fail_modifier()
    if world.current_weather() == "gale":
        fail_chance += 0.12
    if s.get("mascot_trait") == "lucky":
        fail_chance *= 0.75
    from . import hut as hut_mod
    hut_b = await hut_mod.get_bonuses(conn, s["id"])
    fail_chance *= hut_b.voyage_fail
    pulse = await events.active_world_pulse(conn)
    if pulse and pulse.get("effect_type") == "fish_run":
        fail_chance *= 0.85
    if pulse and pulse.get("effect_type") == "storm_front":
        fail_chance += 0.08

    extra = await events.roll_after_action(s, "voyage_return", conn, voyage=voyage)
    s = await _refresh_steward(conn, s["id"])

    failed = random.random() < fail_chance
    loot_lines = []
    boat = BOATS.get(s.get("boat_key") or "", {})
    cargo = boat.get("cargo", 2)
    fish_loot: list[str] = []
    loot_table = voyage_loot_table(voyage["route"])

    if failed:
        await conn.execute("UPDATE stewards SET boat_damaged=1 WHERE id=?", (s["id"],))
        loot_lines.append("风暴折返，几乎空舱")
        if random.random() < 0.35:
            item = random.choice(loot_table)
            await db.add_item(conn, s["id"], item, 1)
            loot_lines.append(f"勉强留下 {ITEM_NAMES.get(item, item)} x1")
            if item.startswith("fish_"):
                fish_loot.append(item)
    else:
        picks = random.sample(loot_table, k=min(cargo, len(loot_table)))
        for item in picks:
            await db.add_item(conn, s["id"], item, 1)
            loot_lines.append(f"{ITEM_NAMES.get(item, item)} x1")
            if item.startswith("fish_"):
                fish_loot.append(item)

    await conn.execute(
        "UPDATE voyages SET status='returned' WHERE id=?",
        (voyage["id"],),
    )
    await conn.execute("DELETE FROM voyages WHERE id=?", (voyage["id"],))

    naval_msg = await _apply_naval_encounter(conn, s, voyage, loot_lines, fish_loot)
    msg = f"{route['label']}归港：" + "，".join(loot_lines)
    msg += flavor.maybe_suffix(flavor.VOYAGE_RETURN_BAD if failed else flavor.VOYAGE_RETURN_GOOD)
    if s.get("boat_damaged"):
        msg += "（船损，voyage_ops repair）"
    if naval_msg:
        msg += f"\n{naval_msg}"

    disc = await commons.roll_discovery(conn, s, "voyage_return")
    if disc:
        msg += f"\n{disc}"

    await conn.execute(
        "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
        ("voyage", s["id"], None, f"{s['name']} {msg}", db.now()),
    )
    if extra:
        msg += f"\n{extra}"
    return msg, fish_loot


async def _finish_voyage(steward_id: int, voyage: dict[str, Any]) -> str:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        s = await _refresh_steward(conn, steward_id)
        msg, fish_loot = await _resolve_voyage(conn, s, voyage)
        await conn.commit()
    from . import multi
    for item in fish_loot:
        bonus = await multi.on_league_item(steward_id, item, 1)
        if bonus:
            msg += f"\n{bonus}"
            await db.add_chronicle("league", bonus, None)
    return msg


async def voyage_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    pulse = await events.maybe_world_pulse(s)
    parts = command.strip().split(maxsplit=1)
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            voyage = await _get_voyage(conn, s["id"])
            s = await _refresh_steward(conn, s["id"])
        if voyage and db.now() >= voyage["returns_at"]:
            auto = await _finish_voyage(s["id"], voyage)
            prefix = f"{pulse}\n" if pulse else ""
            return prefix + auto
        boat = BOATS.get(s.get("boat_key") or "", {})
        lines = []
        if boat:
            dmg = " ⚠待修" if s.get("boat_damaged") else ""
            lines.append(f"船: {boat['name']}{dmg}（载货 {boat.get('cargo', 2)}）")
        else:
            lines.append("船: 无 — buy skiff|cutter|drifter")
        if voyage:
            left = max(0, voyage["returns_at"] - db.now())
            route = VOYAGE_ROUTES[voyage["route"]]["label"]
            lines.append(f"出海中: {route}，约 {left // 60} 分 {left % 60} 秒后归港")
        else:
            lines.append("出海: 无 — depart near|far|deep")
        lines.append(f"潮汐 {world.tide_label(world.current_tide())} · {world.day_phase_label(world.current_day_phase())}")
        msg = "\n".join(lines)
        return f"{pulse}\n{msg}" if pulse else msg

    if verb == "buy" and len(parts) >= 2:
        key = parts[1].split()[0].lower()
        if key not in BOATS:
            raise ValueError(f"可购: {', '.join(BOATS.keys())}")
        meta = BOATS[key]
        async with aiosqlite.connect(db.DB_PATH) as conn:
            s = await _refresh_steward(conn, s["id"])
            if s.get("boat_key"):
                cur_rank = _boat_rank(s["boat_key"])
                if _boat_rank(key) <= cur_rank:
                    raise ValueError(f"已有 {BOATS[s['boat_key']]['name']}，只能升级更高档")
                cost = meta["cost"] - BOATS[s["boat_key"]]["cost"] // 2
            else:
                cost = meta["cost"]
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"购船需要 {cost} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-?, boat_key=?, boat_damaged=0 WHERE id=?",
                (cost, key, s["id"]),
            )
            await conn.commit()
        await db.add_chronicle("boat", f"{s['name']} 购入 {meta['name']}", s["id"])
        return f"购入 {meta['name']}（-{cost} 票）。可 voyage_ops depart 出海"

    if verb == "repair":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            s = await _refresh_steward(conn, s["id"])
            if not s.get("boat_key"):
                raise ValueError("还没有船")
            if not s.get("boat_damaged"):
                return "船况良好，无需修理"
            cost = BOATS[s["boat_key"]]["repair"]
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"修船需要 {cost} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-?, boat_damaged=0 WHERE id=?",
                (cost, s["id"]),
            )
            await conn.commit()
        return f"修船完成（-{cost} 票），可以 depart"

    if verb == "depart" and len(parts) >= 2:
        route_key = parts[1].split()[0].lower()
        if route_key not in VOYAGE_ROUTES:
            raise ValueError(f"航线: {', '.join(VOYAGE_ROUTES.keys())}")
        route = VOYAGE_ROUTES[route_key]
        async with aiosqlite.connect(db.DB_PATH) as conn:
            s = await _refresh_steward(conn, s["id"])
            if not s.get("boat_key"):
                raise ValueError("先 voyage_ops buy 购船")
            if s.get("boat_damaged"):
                raise ValueError("船损，先 repair")
            if _boat_rank(s["boat_key"]) < _boat_rank(route["min_boat"]):
                need = BOATS[route["min_boat"]]["name"]
                raise ValueError(f"{route['label']} 至少需要 {need}")
            if await _get_voyage(conn, s["id"]):
                raise ValueError("已在海上，return 或等 status 归港")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < route["fuel"]:
                raise ValueError(f"出海燃油 {route['fuel']} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (route["fuel"], s["id"]),
            )
            from . import energy as energy_mod
            fuel_energy = {"near": 15, "far": 28, "deep": 40}.get(route_key, 20)
            await energy_mod.spend(conn, s["id"], fuel_energy, action="出海")
            now = db.now()
            duration = route["duration"]
            if world.current_weather() == "misty":
                duration = int(duration * 1.15)
            await conn.execute(
                """
                INSERT INTO voyages (steward_id, route, departed_at, returns_at, status)
                VALUES (?,?,?,?, 'sailing')
                """,
                (s["id"], route_key, now, now + duration),
            )
            voyage = await _get_voyage(conn, s["id"])
            assert voyage
            extra = await events.roll_after_action(s, "voyage_depart", conn, voyage=voyage)
            await conn.commit()
        msg = (
            f"{s['name']} 出航 {route['label']}（-{route['fuel']} 票），"
            f"约 {duration // 60} 分钟后归港"
        )
        msg += flavor.maybe_suffix(flavor.VOYAGE_DEPART_SUFFIX)
        await db.add_chronicle("voyage", msg, s["id"])
        if extra:
            return f"{msg}\n{extra}"
        return msg

    if verb == "return":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            voyage = await _get_voyage(conn, s["id"])
        if not voyage:
            return "没有进行中的航程"
        if db.now() < voyage["returns_at"]:
            left = voyage["returns_at"] - db.now()
            raise ValueError(f"尚未归港，还需约 {left // 60} 分 {left % 60} 秒")
        return await _finish_voyage(s["id"], voyage)

    if verb == "moor":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            voyage = await _get_voyage(conn, s["id"])
        if not voyage:
            return "没有进行中的航程"
        if db.now() < voyage["returns_at"]:
            left = voyage["returns_at"] - db.now()
            return f"仍在 {VOYAGE_ROUTES[voyage['route']]['label']}，约 {left // 60} 分后可用 return"
        return await _finish_voyage(s["id"], voyage)

    raise ValueError(
        f"未知 voyage 指令: {command}（status/buy/repair/depart/return/moor）"
    )

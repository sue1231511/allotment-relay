import json
import random
import re
import time
from typing import Any

import aiosqlite

from . import db, events, event_gen, flavor, shaonian as shaonian_mod, world
from . import commons
from .catalog import (
    ITEM_NAMES,
    SEA_CATCH,
    WALKBLUE_HEX,
    WALKBLUE_ITEM,
    WALKBLUE_SPECIES,
    is_walkblue_item,
    pen_species_keys,
    resolve_item_key,
    voyage_loot_table,
)
from .config import (
    BOATS,
    HAIL_BRIBE,
    HAIL_FIGHT_ENERGY,
    HAIL_FLEE_ENERGY,
    HAIL_THREAT,
    HAIL_TIMEOUT,
    LEGGED_FISH_CHANCE,
    LEGGED_FISH_GRAB_ENERGY,
    LEGGED_FISH_RARE_GIFT_CHANCE,
    MAX_FISH_PENS,
    PEN_ERECT_COST,
    PEN_EXPAND_COST,
    VOYAGE_ROUTES,
)
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


def _pen_tag(pen: dict) -> str:
    slot = pen["slot"]
    custom = (pen.get("pen_label") or "").strip()
    return f"#{slot} {custom}" if custom else f"#{slot}"


def _pen_line(pen: dict) -> str:
    tag = _pen_tag(pen)
    if not pen.get("species"):
        return f"  {tag}: 空池"
    spec = SEA_CATCH[pen["species"]]
    if _pen_ready(pen):
        state = "可收"
    elif pen.get("fed"):
        state = "放养"
    else:
        state = "待投饵"
    return f"  {tag}: {spec['emoji']}{spec['name']}（{state}）"


_SLOT_TOKEN = re.compile(
    r"^(?:#|第|池|pool)?(\d+)(?:号池|号|池)?$",
    re.IGNORECASE,
)


def _parse_slot_token(tok: str) -> int | None:
    raw = (tok or "").strip()
    if not raw:
        return None
    m = _SLOT_TOKEN.fullmatch(raw)
    if not m:
        return None
    n = int(m.group(1))
    return n if n >= 1 else None


def _extract_slot_and_rest(tokens: list[str]) -> tuple[int | None, list[str]]:
    """从参数里抽出可选池号；多出来的数字（数量）丢掉。"""
    slot: int | None = None
    leftover: list[str] = []
    for tok in tokens:
        n = _parse_slot_token(tok)
        if n is not None:
            if slot is None:
                slot = n
            continue
        leftover.append(tok)
    return slot, leftover


def _resolve_pen_species(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    low = s.lower().replace(" ", "_")
    if low.startswith("fish_"):
        low = low[5:]
    if low in SEA_CATCH:
        return low
    compact = low.replace("_", "")
    if compact in SEA_CATCH:
        return compact
    for key, meta in SEA_CATCH.items():
        if meta.get("name") == s:
            return key
    item = resolve_item_key(s)
    if item and item.startswith("fish_"):
        return item[5:]
    return low


def _unfarmable_message(species: str) -> str:
    farmable = ", ".join(pen_species_keys())
    if species in SEA_CATCH and not SEA_CATCH[species].get("pen"):
        meta = SEA_CATCH[species]
        item = f"fish_{species}"
        return (
            f"{meta['emoji']}{meta['name']}（{item}）不能投进渔排，建议卖掉或吃掉："
            f"tote_ops vend {item} · kitchen_ops eat {item}。"
            f"可养品种: {farmable}"
        )
    return f"可养品种: {farmable}"


def _pen_usage() -> str:
    return "用法: pen stock herring 2 · pen feed 2 · pen harvest 2 · pen label 2 薄荷池"


async def _require_owned_pen(
    conn: aiosqlite.Connection, steward_id: int, slot: int
) -> dict[str, Any]:
    pens = await _list_pens(conn, steward_id)
    if not pens:
        raise ValueError("先 erect 渔排")
    pen = await _get_pen(conn, steward_id, slot)
    if not pen:
        raise ValueError(
            f"没有第{slot}池。当前 {len(pens)} 口。"
            f"{' pen expand 扩池。' if len(pens) < MAX_FISH_PENS else ' '}"
            f"{_pen_usage()}"
        )
    return pen


async def _list_pens(conn: aiosqlite.Connection, steward_id: int) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT * FROM fish_pens WHERE steward_id=? ORDER BY slot",
        (steward_id,),
    )).fetchall()
    return [dict(r) for r in rows]


async def _get_pen(conn: aiosqlite.Connection, steward_id: int, slot: int = 1) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM fish_pens WHERE steward_id=? AND slot=?", (steward_id, slot)
    )).fetchone()
    return dict(row) if row else None


async def _get_voyage(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM voyages WHERE steward_id=? AND status IN ('sailing','hailed','fish_encounter')",
        (steward_id,),
    )).fetchone()
    return dict(row) if row else None


def _parse_voyage_encounter(voyage: dict[str, Any]) -> dict[str, Any]:
    raw = voyage.get("encounter") or "{}"
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except json.JSONDecodeError:
        data = {}
    if "voyage_fish" not in data:
        data["voyage_fish"] = []
    return data


async def _save_voyage_encounter(
    conn: aiosqlite.Connection, voyage_id: int, data: dict[str, Any], status: str | None = None
) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    if status:
        await conn.execute(
            "UPDATE voyages SET encounter=?, status=? WHERE id=?",
            (payload, status, voyage_id),
        )
    else:
        await conn.execute("UPDATE voyages SET encounter=? WHERE id=?", (payload, voyage_id))


async def append_voyage_fish(
    conn: aiosqlite.Connection, voyage: dict[str, Any], fish_item: str
) -> None:
    data = _parse_voyage_encounter(voyage)
    fish = list(data.get("voyage_fish") or [])
    fish.append(fish_item)
    data["voyage_fish"] = fish
    await _save_voyage_encounter(conn, voyage["id"], data)
    voyage["encounter"] = json.dumps(data, ensure_ascii=False)


def _legged_fish_route_zones(route_key: str) -> set[str]:
    return {"near": {"near", "far"}, "far": {"far", "deep"}, "deep": {"deep"}}.get(
        route_key, {"near", "far"}
    )


def _legged_fish_roll_chance(route_key: str) -> float:
    chance = LEGGED_FISH_CHANCE.get(route_key, 0.05)
    if world.current_weather() == "misty":
        chance += 0.02
    return min(0.22, chance)


async def _legged_fish_roll_chance_async(conn: aiosqlite.Connection, route_key: str) -> float:
    chance = _legged_fish_roll_chance(route_key)
    pulse = await events.active_world_pulse(conn)
    if pulse and pulse.get("effect_type") == "fish_run":
        chance += 0.03
    if pulse and pulse.get("effect_type") == "red_tide":
        chance -= 0.02
    return max(0.02, min(0.25, chance))


def _legged_fish_prompt(payload: dict[str, Any]) -> str:
    detail = payload.get("detail") or flavor.pick(flavor.LEGGED_FISH_DETAIL)
    banner = flavor.fill(flavor.pick(flavor.LEGGED_FISH_BANNER), detail=detail)
    return banner + "\n" + flavor.LEGGED_FISH_CHOICES


async def try_legged_fish_encounter(
    conn: aiosqlite.Connection, s: dict[str, Any], voyage: dict[str, Any]
) -> str | None:
    """出海期间 tide_ops cast 坐钓后判定未命名小鱼遭遇。撒网不会碰上。"""
    if voyage.get("status") != "sailing":
        return None
    chance = await _legged_fish_roll_chance_async(conn, voyage["route"])
    if random.random() >= chance:
        return None
    data = _parse_voyage_encounter(voyage)
    payload = {
        "type": "legged_blue_fish",
        "who": "未命名小鱼",
        "detail": flavor.pick(flavor.LEGGED_FISH_DETAIL),
        "voyage_fish": list(data.get("voyage_fish") or []),
    }
    await _save_voyage_encounter(conn, voyage["id"], payload, "fish_encounter")
    voyage["status"] = "fish_encounter"
    voyage["encounter"] = json.dumps(payload, ensure_ascii=False)
    return _legged_fish_prompt(payload)


async def _adjust_tickets(conn: aiosqlite.Connection, steward_id: int, delta: int) -> None:
    if not delta:
        return
    if delta > 0:
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?",
            (delta, steward_id),
        )
        return
    await conn.execute(
        "UPDATE stewards SET tickets=MAX(0, tickets+?) WHERE id=?",
        (delta, steward_id),
    )


async def on_obtain_walkblue(conn: aiosqlite.Connection, steward_id: int) -> str:
    """钓到或抓住未命名小鱼：落下腿鱼小咒。"""
    from . import health as health_mod

    msg = flavor.pick(flavor.WALKBLUE_CATCH_CURSE)
    hex_line = await health_mod.inflict(conn, steward_id, WALKBLUE_HEX, source="walkblue")
    if hex_line:
        msg += f"\n{hex_line}"
    return msg


async def apply_walkblue_fate(
    conn: aiosqlite.Connection,
    steward_id: int,
    event_key: str,
    *,
    kind: str,
    qty: int = 1,
    tickets: int = 0,
) -> str:
    """吃/卖未命名小鱼后的单次随机事件。"""
    from . import energy as energy_mod, health as health_mod

    pool = flavor.WALKBLUE_FATE_EAT if kind == "eat" else flavor.WALKBLUE_FATE_SELL
    texts = pool.get(event_key) or pool.get("stomach_steps") or ["未命名小鱼翻了个身。"]
    msg = flavor.pick(texts)

    if event_key == "whisper":
        await survival_bump_safe(conn, steward_id, mist_wit=2)
    elif event_key == "ticket_tooth":
        await _adjust_tickets(conn, steward_id, 3)
    elif event_key == "curse_again":
        hex_line = await health_mod.inflict(conn, steward_id, WALKBLUE_HEX, source="walkblue")
        if hex_line:
            msg += f"\n{hex_line}"
    elif event_key == "curse_lift":
        await conn.execute(
            "DELETE FROM steward_ailments WHERE steward_id=? AND ailment_key=?",
            (steward_id, WALKBLUE_HEX),
        )
    elif event_key == "pay_up":
        await _adjust_tickets(conn, steward_id, -2)
    elif event_key == "extra_fill":
        gained = await energy_mod.restore(conn, steward_id, 4)
        if gained:
            msg += f"（精力 +{gained}）"
    elif event_key == "standing_down":
        await survival_bump_safe(conn, steward_id, standing=-1)
    elif event_key == "standing_up":
        await survival_bump_safe(conn, steward_id, standing=1)
    elif event_key == "minnow":
        gift = random.choice(("fish_sandeel", "fish_herring"))
        await db.add_item(conn, steward_id, gift, 1)
        msg += f"\n获得 {ITEM_NAMES.get(gift, gift)} x1"
    elif event_key == "coins_hop":
        hop = min(4, max(1, tickets // 8 or 2))
        await _adjust_tickets(conn, steward_id, -hop)
        msg += f"（票 -{hop}）"
    elif event_key == "buyer_tip":
        await _adjust_tickets(conn, steward_id, 4)
        msg += "（票 +4）"
    elif event_key == "walks_back":
        back = max(1, min(qty, 1))
        unit = tickets // max(1, qty) if tickets else SEA_CATCH[WALKBLUE_SPECIES]["sell"]
        await db.add_item(conn, steward_id, WALKBLUE_ITEM, back)
        await _adjust_tickets(conn, steward_id, -unit * back)
        msg += f"\n{ITEM_NAMES[WALKBLUE_ITEM]} x{back} 回袋，票 -{unit * back}"
    elif event_key == "bait_gift":
        await db.add_item(conn, steward_id, "bait_worm", 1)
        msg += "\n获得 蚯蚓饵 x1"
    elif event_key == "price_glitch":
        delta = random.choice((-1, 1))
        await _adjust_tickets(conn, steward_id, delta)
        msg += f"（票 {delta:+d}）"
    return msg


async def walkblue_fate_event(
    conn: aiosqlite.Connection,
    steward_id: int,
    *,
    kind: str,
    qty: int = 1,
    tickets: int = 0,
) -> str:
    pool = flavor.WALKBLUE_FATE_EAT if kind == "eat" else flavor.WALKBLUE_FATE_SELL
    event_key = random.choice(list(pool))
    return await apply_walkblue_fate(
        conn, steward_id, event_key, kind=kind, qty=qty, tickets=tickets
    )


async def _resolve_legged_fish(
    conn: aiosqlite.Connection,
    s: dict[str, Any],
    voyage: dict[str, Any],
    choice: str,
) -> str:
    from . import catches as catches_mod, energy as energy_mod

    payload = _parse_voyage_encounter(voyage)
    if payload.get("type") != "legged_blue_fish":
        payload = {
            "type": "legged_blue_fish",
            "who": "未命名小鱼",
            "voyage_fish": payload.get("voyage_fish") or [],
        }
    voyage_fish = list(payload.get("voyage_fish") or [])
    choice = choice.lower()
    good = choice in ("compliment", "release")

    if good:
        zones = _legged_fish_route_zones(voyage["route"])
        tide = world.current_tide()
        rarity_cap = 4
        rare = random.random() < LEGGED_FISH_RARE_GIFT_CHANCE
        if rare:
            rarity_cap = 6
        from .catalog import weighted_fish_pick

        gift_key = weighted_fish_pick(tide=tide, zones=zones, rarity_cap=rarity_cap)
        gift_item = f"fish_{gift_key}"
        meta = SEA_CATCH[gift_key]
        await db.add_item(conn, s["id"], gift_item, 1)
        await catches_mod.record_catch(conn, s["id"], gift_item)
        await survival_bump_safe(conn, s["id"], standing=2, mist_wit=2)
        if rare:
            msg = flavor.pick(flavor.LEGGED_FISH_RELEASE_RARE)
        else:
            msg = flavor.pick(flavor.LEGGED_FISH_RELEASE)
        msg += f"\n赠予 {meta['emoji']}{meta['name']} x1"
        remaining = voyage_fish
    else:
        lost: list[str] = []
        pool = list(voyage_fish)
        if pool:
            n = max(1, len(pool) // 2 + random.randint(0, 1))
            to_lose = random.sample(pool, min(n, len(pool)))
            for item in to_lose:
                if await db.take_item(conn, s["id"], item, 1):
                    lost.append(item)
        remaining = list(pool)
        for item in lost:
            if item in remaining:
                remaining.remove(item)
        else:
            stock = await db.get_satchel(s["id"])
            fish_items = [
                k for k, v in stock.items()
                if k.startswith("fish_") and v > 0 and not is_walkblue_item(k)
            ]
            for _ in range(min(2, len(fish_items))):
                if not fish_items:
                    break
                item = random.choice(fish_items)
                if await db.take_item(conn, s["id"], item, 1):
                    lost.append(item)
            remaining = []
        try:
            await energy_mod.spend(conn, s["id"], LEGGED_FISH_GRAB_ENERGY, action="捞怪鱼")
        except ValueError:
            cur = await conn.execute("SELECT energy FROM stewards WHERE id=?", (s["id"],))
            row = await cur.fetchone()
            if row:
                await conn.execute(
                    "UPDATE stewards SET energy=0 WHERE id=?",
                    (s["id"],),
                )
        await db.add_item(conn, s["id"], WALKBLUE_ITEM, 1)
        await catches_mod.record_catch(conn, s["id"], WALKBLUE_ITEM)
        curse = await on_obtain_walkblue(conn, s["id"])
        msg = flavor.pick(flavor.LEGGED_FISH_GRAB)
        msg += f"\n抓住 {SEA_CATCH[WALKBLUE_SPECIES]['emoji']}{SEA_CATCH[WALKBLUE_SPECIES]['name']} x1"
        msg += f"\n{curse}"
        if lost:
            names = [ITEM_NAMES.get(x, x) for x in lost]
            msg += f"\n失去：{', '.join(names)}"
        else:
            msg += "\n（舱里没剩鱼可丢，但精力照扣）"

    await _save_voyage_encounter(
        conn,
        voyage["id"],
        {"voyage_fish": remaining},
        "sailing",
    )
    return msg


async def _refresh_steward(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any]:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute("SELECT * FROM stewards WHERE id=?", (steward_id,))).fetchone()
    return dict(row)


async def pen_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "status"
    args = parts[1:]

    if verb == "status":
        async with db.connect() as conn:
            pens = await _list_pens(conn, s["id"])
        boat = BOATS.get(s.get("boat_key") or "", {})
        lines = [
            f"船只: {boat.get('name', '无')} {'(待修)' if s.get('boat_damaged') else ''}".strip(),
        ]
        if pens:
            lines.append("渔排:")
            for pen in pens:
                lines.append(_pen_line(pen))
        else:
            lines.append("渔排: 未搭建（erect）")
        lines.append(f"扩池: pen expand（第2池 {PEN_EXPAND_COST} 票，最多 {MAX_FISH_PENS} 池）")
        lines.append(_pen_usage())
        farmable = pen_species_keys()
        lines.append(f"可养 {len(farmable)} 种: {', '.join(farmable[:8])}{'…' if len(farmable) > 8 else ''}")
        return "\n".join(lines)

    if verb == "erect":
        async with db.connect() as conn:
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
        return (
            f"渔排就绪（-{PEN_ERECT_COST} 票）。stock 品种名 投苗，feed 投饵，harvest 收网。"
            f"扩第二池后可写 stock herring 2；不写池号会优先投空池"
        )

    if verb == "expand":
        async with db.connect() as conn:
            pens = await _list_pens(conn, s["id"])
            if not pens:
                raise ValueError("先 erect 第一池渔排")
            if len(pens) >= MAX_FISH_PENS:
                raise ValueError(f"渔排已达上限 {MAX_FISH_PENS} 池")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < PEN_EXPAND_COST:
                raise ValueError(f"扩池需要 {PEN_EXPAND_COST} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (PEN_EXPAND_COST, s["id"]),
            )
            new_slot = len(pens) + 1
            await conn.execute(
                "INSERT INTO fish_pens (steward_id, slot, pen_label) VALUES (?,?,'')",
                (s["id"], new_slot),
            )
            await conn.commit()
        return (
            f"第 {new_slot} 池渔排就绪（-{PEN_EXPAND_COST} 票）。"
            f"投苗: stock herring {new_slot} 或 stock {new_slot} 灰鲱；不写池号会优先投空池"
        )

    if verb == "label":
        slot, name_parts = _extract_slot_and_rest(args)
        label = " ".join(name_parts).strip()[:40]
        if not label:
            raise ValueError("用法: pen label 薄荷池  或  pen label 2 薄荷池")
        if slot is None:
            slot = 1
        async with db.connect() as conn:
            pen = await _require_owned_pen(conn, s["id"], slot)
            await conn.execute("UPDATE fish_pens SET pen_label=? WHERE id=?", (label, pen["id"]))
            await conn.commit()
        return f"#{slot} 命名为「{label}」"

    if verb == "stock":
        slot, rest = _extract_slot_and_rest(args)
        species_raw = " ".join(rest).strip()
        if not species_raw:
            raise ValueError("用法: pen stock herring  或  pen stock herring 2  /  pen stock 2 灰鲱")
        species = _resolve_pen_species(species_raw)
        if species not in SEA_CATCH or not SEA_CATCH[species].get("pen"):
            raise ValueError(_unfarmable_message(species or species_raw))
        meta = SEA_CATCH[species]
        async with db.connect() as conn:
            pens = await _list_pens(conn, s["id"])
            if not pens:
                raise ValueError("先 erect 渔排")
            if slot is None:
                empty = next((p for p in pens if not p.get("species")), None)
                if empty:
                    slot = empty["slot"]
                else:
                    occupied = "、".join(
                        f"{_pen_tag(p)} {SEA_CATCH[p['species']]['name']}"
                        for p in pens if p.get("species")
                    )
                    raise ValueError(
                        f"所有池都有鱼苗（{occupied}）。先 harvest，或 stock {species} 2 指定空池。"
                    )
            pen = await _require_owned_pen(conn, s["id"], slot)
            if pen.get("species"):
                raise ValueError(
                    f"{_pen_tag(pen)} 已有鱼苗，先 harvest 或等收网。"
                    f"空池请写 stock {species} 2"
                )
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
            pen = await _get_pen(conn, s["id"], slot)
            assert pen
            extra = await events.roll_after_action(s, "pen_stock", conn, pen=pen)
            await conn.commit()
        msg = (
            f"投苗到 {_pen_tag(pen)} {meta['emoji']}{meta['name']}"
            f"（-{meta['stock_tickets']} 票），记得 feed {slot}"
        )
        return f"{msg}\n{extra}" if extra else msg

    if verb == "feed":
        slot, _rest = _extract_slot_and_rest(args)
        async with db.connect() as conn:
            pens = await _list_pens(conn, s["id"])
            if not pens:
                raise ValueError("先 erect 渔排")
            if slot is None:
                hungry = next(
                    (p for p in pens if p.get("species") and not p.get("fed")),
                    None,
                )
                if hungry:
                    slot = hungry["slot"]
                else:
                    occupied = [p for p in pens if p.get("species")]
                    if not occupied:
                        raise ValueError("空池无法投饵")
                    tags = "、".join(_pen_tag(p) for p in occupied)
                    return f"在养鱼的池今日都已投饵（{tags}）。指定池: pen feed 2"
            pen = await _require_owned_pen(conn, s["id"], slot)
            if not pen.get("species"):
                raise ValueError(f"{_pen_tag(pen)} 是空池，无法投饵")
            if pen.get("fed"):
                return f"{_pen_tag(pen)} 今日已投饵"
            meta = SEA_CATCH[pen["species"]]
            if not await db.take_item(conn, s["id"], meta["feed_item"], meta["feed_qty"]):
                raise ValueError(
                    f"投饵需要 {ITEM_NAMES.get(meta['feed_item'], meta['feed_item'])} x{meta['feed_qty']}"
                )
            await conn.execute("UPDATE fish_pens SET fed=1 WHERE id=?", (pen["id"],))
            pen = await _get_pen(conn, s["id"], slot)
            assert pen
            extra = await events.roll_after_action(s, "pen_feed", conn, pen=pen)
            await conn.commit()
        msg = f"已向 {_pen_tag(pen)} {SEA_CATCH[pen['species']]['name']} 池投饵"
        return f"{msg}\n{extra}" if extra else msg

    if verb == "harvest":
        slot, _rest = _extract_slot_and_rest(args)
        async with db.connect() as conn:
            pens = await _list_pens(conn, s["id"])
            if not pens:
                raise ValueError("先 erect 渔排")
            if slot is None:
                ready = next((p for p in pens if _pen_ready(p)), None)
                if ready:
                    slot = ready["slot"]
                else:
                    growing = [p for p in pens if p.get("species")]
                    if not growing:
                        raise ValueError("空池无可收")
                    tags = "、".join(_pen_tag(p) for p in growing)
                    raise ValueError(
                        f"尚未长成（{tags}），继续 feed 或等待。指定池: pen harvest 2"
                    )
            pen = await _require_owned_pen(conn, s["id"], slot)
            if not pen.get("species"):
                raise ValueError(f"{_pen_tag(pen)} 空池无可收")
            if not _pen_ready(pen):
                raise ValueError(f"{_pen_tag(pen)} 尚未长成，继续 feed 或等待")
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
            from . import tale as tale_mod
            await tale_mod.check_item_progress(conn, s["id"], f"fish_{species}", qty)
            tale_extra = await tale_mod.check_action_progress(conn, s["id"], "sea")
            await conn.commit()
        from . import multi
        bonus = await multi.on_league_item(s["id"], f"fish_{species}", qty)
        msg = f"收网 {_pen_tag(pen)} {meta['emoji']}{meta['name']} x{qty}"
        msg += flavor.maybe_suffix(flavor.PEN_HARVEST_SUFFIX)
        if bonus:
            await db.add_chronicle("league", bonus, None)
            msg += f"\n{bonus}"
        await db.add_chronicle("pen", f"{s['name']} 渔排收网 {meta['name']} x{qty}", s["id"])
        if disc:
            msg += f"\n{disc}"
        if extra:
            msg += f"\n{extra}"
        if tale_extra:
            msg += f"\n\n{tale_extra}"
        return msg

    raise ValueError(
        f"未知 pen 指令: {command}（status/erect/expand/label/stock/feed/harvest）"
    )


async def _apply_naval_payload(
    conn: aiosqlite.Connection,
    s: dict[str, Any],
    voyage: dict[str, Any],
    loot_lines: list[str],
    fish_loot: list[str],
    payload: dict[str, Any],
) -> str:
    cargo_loss = 0
    effects = list(payload.get("effects") or [])
    for eff in effects:
        if eff.startswith("cargo_loss:"):
            cargo_loss = int(eff.split(":")[1])
    await events.apply_effects(conn, s, [e for e in effects if not e.startswith("cargo_loss:")])
    naval_extra = ""
    if payload.get("kind") == "bad":
        from . import health
        extra = await health.maybe_roll_ailment(
            conn, s["id"], "voyage_return",
            pool=health.TRIGGER_AILMENTS["naval_bad"],
            chance=0.22,
            source="naval",
        )
        if extra:
            naval_extra = f"\n{extra}\n→ visit_ops clinic treat …（必须花票）"
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
            item = row["item"]
            if await db.take_item(conn, s["id"], item, 1):
                removed_label = ITEM_NAMES.get(item, item)
                if item in fish_loot:
                    fish_loot.remove(item)
                rows = [r for r in rows if not (r["item"] == item and r["quantity"] <= 1)]
        if removed_label:
            loot_lines.append(f"遭遇扣货：{removed_label} x1")
    return flavor.wrap_naval(
        payload.get("kind") or "neutral",
        payload.get("label") or "海上遭遇",
        payload.get("detail") or "",
    ) + naval_extra


def _hail_prompt(payload: dict[str, Any]) -> str:
    who = payload.get("who") or flavor.pick(flavor.NAVAL_WHO)
    from . import lore as lore_mod
    fac = lore_mod.black_flag_faction(who)
    who = fac["tag"]
    payload = dict(payload)
    payload["who"] = who
    detail = payload.get("detail") or lore_mod.black_flag_detail(who)
    lore_line = fac.get("lore", "")
    banner = flavor.fill(
        flavor.pick(flavor.HAIL_BANNER),
        who=who,
        detail=detail,
    )
    extra = f"\n（{lore_line}）" if lore_line and random.random() < 0.7 else ""
    return banner + extra + "\n" + flavor.HAIL_CHOICES


def _hail_expired(voyage: dict[str, Any]) -> bool:
    return db.now() - (voyage.get("returns_at") or 0) >= HAIL_TIMEOUT


async def _fight_power(conn: aiosqlite.Connection, s: dict[str, Any]) -> int:
    boat = BOATS.get(s.get("boat_key") or "", {})
    power = int(boat.get("rank", 1)) * 22
    power += int(s.get("mist_wit", 50) * 0.28)
    power += int(s.get("health", 100) * 0.08)
    if s.get("mascot_trait") == "lucky":
        power += 10
    from . import hut as hut_mod
    hut_b = await hut_mod.get_bonuses(conn, s["id"])
    if hut_b.has("sea_chart"):
        power += 10
    if world.current_weather() == "gale":
        power -= 8
    return power


async def _maybe_spend(conn, steward_id: int, amount: int, action: str, forced: bool) -> None:
    from . import energy as energy_mod

    try:
        await energy_mod.spend(conn, steward_id, amount, action=action)
    except ValueError:
        if not forced:
            raise


async def _resolve_hail(
    conn: aiosqlite.Connection,
    s: dict[str, Any],
    voyage: dict[str, Any],
    choice: str,
    loot_lines: list[str],
    fish_loot: list[str],
    *,
    forced: bool = False,
) -> str:
    raw = voyage.get("encounter") or "{}"
    try:
        payload = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except json.JSONDecodeError:
        payload = {}
    who = payload.get("who") or flavor.pick(flavor.NAVAL_WHO)
    route = voyage["route"]
    threat = HAIL_THREAT.get(route, 50)
    effects = list(payload.get("effects") or [])

    if choice == "bribe":
        cost = HAIL_BRIBE.get(route, 18)
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        tickets = (await cur.fetchone())[0]
        if tickets < cost:
            if forced:
                choice = "flee"
            else:
                raise ValueError(f"买路要 {cost} 票，你只有 {tickets} — 换 fight / flee / parley")
        else:
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, s["id"]),
            )
            await survival_bump_safe(conn, s["id"], standing=-1)
            return flavor.fill(flavor.pick(flavor.HAIL_BRIBE), who=who, n=cost)

    if choice == "flee":
        await _maybe_spend(conn, s["id"], HAIL_FLEE_ENERGY, "砍缆跑路", forced)
        boat_rank = BOATS.get(s.get("boat_key") or "", {}).get("rank", 1)
        chance = 0.32 + boat_rank * 0.16
        if world.current_weather() == "misty":
            chance += 0.08
        if random.random() < chance:
            return flavor.fill(flavor.pick(flavor.HAIL_FLEE_WIN), who=who)
        payload = dict(payload)
        if "cargo_loss:1" not in effects:
            effects = effects + ["cargo_loss:1"]
        payload["effects"] = effects
        msg = flavor.fill(flavor.pick(flavor.HAIL_FLEE_LOSE), who=who)
        naval = await _apply_naval_payload(conn, s, voyage, loot_lines, fish_loot, payload)
        return msg + "\n" + naval

    if choice == "parley":
        standing = s.get("standing", 50)
        mist = s.get("mist_wit", 50)
        from . import social as social_mod
        max_r = await social_mod.max_rapport(s["id"])
        chance = 0.22 + standing / 220 + mist / 280 + social_mod.parley_bonus_chance(max_r)
        if random.random() < chance:
            fine = random.randint(3, 8)
            await conn.execute(
                "UPDATE stewards SET tickets=MAX(0, tickets-?) WHERE id=?",
                (fine, s["id"]),
            )
            await survival_bump_safe(conn, s["id"], standing=2)
            return flavor.fill(flavor.pick(flavor.HAIL_PARLEY_WIN), who=who) + f"（交涉费 {fine} 票）"
        msg = flavor.fill(flavor.pick(flavor.HAIL_PARLEY_LOSE), who=who)
        naval = await _apply_naval_payload(conn, s, voyage, loot_lines, fish_loot, payload)
        return msg + "\n" + naval

    await _maybe_spend(conn, s["id"], HAIL_FIGHT_ENERGY, "黑旗接舷", forced)
    power = await _fight_power(conn, s)
    player = power + random.randint(0, 22)
    pirate = threat + random.randint(0, 22)
    if player >= pirate:
        bonus = random.randint(8, 16) + BOATS.get(s.get("boat_key") or "", {}).get("rank", 1) * 3
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?",
            (bonus, s["id"]),
        )
        if random.random() < 0.45:
            table = voyage_loot_table(route)
            extra_fish = random.choice(table)
            await db.add_item(conn, s["id"], extra_fish, 1)
            if extra_fish.startswith("fish_"):
                fish_loot.append(extra_fish)
            loot_lines.append(f"缴获 {ITEM_NAMES.get(extra_fish, extra_fish)} x1")
        await survival_bump_safe(conn, s["id"], standing=3, mist_wit=2)
        msg = flavor.fill(flavor.pick(flavor.HAIL_FIGHT_WIN), who=who, n=bonus)
        if loot_lines:
            msg += " · " + "，".join(loot_lines)
        return msg

    payload = dict(payload)
    if "boat_damage" not in effects:
        effects = effects + ["boat_damage"]
    payload["effects"] = effects
    msg = flavor.fill(flavor.pick(flavor.HAIL_FIGHT_LOSE), who=who)
    naval = await _apply_naval_payload(conn, s, voyage, loot_lines, fish_loot, payload)
    return msg + "\n" + naval


async def survival_bump_safe(conn, steward_id: int, **kwargs) -> None:
    from . import survival
    await survival.bump(conn, steward_id, **kwargs)


async def _resolve_voyage(
    conn: aiosqlite.Connection, s: dict[str, Any], voyage: dict[str, Any]
) -> tuple[str, list[str], bool]:
    route = VOYAGE_ROUTES[voyage["route"]]
    s = await _refresh_steward(conn, s["id"])
    fail_chance = route["fail"] + await events.voyage_fail_modifier()
    from . import social as social_mod
    fail_chance = max(0.05, fail_chance - social_mod.badge_val(s, "voyage_fail_reduce"))
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

    enc = event_gen.generate_naval_encounter(
        voyage["route"],
        s,
        bad_bias=(0.12 if s.get("boat_damaged") else 0.0) + await shaonian_mod.naval_bad_bias(conn, s["id"]),
    )
    if enc and enc.kind == "bad" and await shaonian_mod.skip_bad_sea(conn, s["id"]):
        enc = None
    msg = f"{route['label']}归港：" + "，".join(loot_lines)
    msg += flavor.maybe_suffix(flavor.VOYAGE_RETURN_BAD if failed else flavor.VOYAGE_RETURN_GOOD)
    if s.get("boat_damaged"):
        msg += "（船损，voyage_ops repair）"

    if enc and enc.kind == "bad":
        payload = {
            "kind": enc.kind,
            "label": enc.label,
            "detail": enc.detail,
            "effects": enc.effects,
            "who": flavor.pick(flavor.NAVAL_WHO),
            "looted": True,
        }
        await conn.execute(
            "UPDATE voyages SET status='hailed', encounter=? WHERE id=?",
            (json.dumps(payload, ensure_ascii=False), voyage["id"]),
        )
        disc = await commons.roll_discovery(conn, s, "voyage_return")
        if disc:
            msg += f"\n{disc}"
        if extra:
            msg += f"\n{extra}"
        msg += "\n" + _hail_prompt(payload)
        await conn.execute(
            "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
            ("voyage", s["id"], None, f"{s['name']} 归港遇黑旗截停", db.now()),
        )
        return msg, fish_loot, True

    naval_msg = ""
    if enc:
        payload = {
            "kind": enc.kind,
            "label": enc.label,
            "detail": enc.detail,
            "effects": enc.effects,
        }
        naval_msg = await _apply_naval_payload(conn, s, voyage, loot_lines, fish_loot, payload)
    await conn.execute("DELETE FROM voyages WHERE id=?", (voyage["id"],))
    if naval_msg:
        msg += f"\n{naval_msg}"

    disc = await commons.roll_discovery(conn, s, "voyage_return")
    if disc:
        msg += f"\n{disc}"

    if voyage["route"] == "deep" and not failed:
        from . import bar as bar_mod
        await bar_mod.grant_bar_unlock(s["id"], "deep_echo")

    await conn.execute(
        "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
        ("voyage", s["id"], None, f"{s['name']} {msg}", db.now()),
    )
    if extra:
        msg += f"\n{extra}"
    return msg, fish_loot, False


async def _finish_voyage(steward_id: int, voyage: dict[str, Any], choice: str | None = None) -> str:
    async with db.connect() as conn:
        s = await _refresh_steward(conn, steward_id)
        fish_loot: list[str] = []
        if voyage.get("status") == "fish_encounter":
            leg_choice = choice if choice in ("compliment", "release", "catch", "grab") else "release"
            leg_msg = await _resolve_legged_fish(conn, s, voyage, leg_choice)
            await conn.commit()
            voyage = await _get_voyage(conn, steward_id)
            if not voyage:
                return leg_msg
            prefix = leg_msg + "\n"
            if voyage.get("status") == "hailed":
                return prefix + await _finish_voyage(steward_id, voyage, choice)
            if voyage.get("status") == "sailing" and db.now() >= voyage["returns_at"]:
                return prefix + await _finish_voyage(steward_id, voyage)
            return prefix + "航程继续。可用 tide_ops cast 坐钓（未命名小鱼只认钓竿），或等归港 voyage_ops return"
        if voyage.get("status") == "hailed":
            if choice is None and not _hail_expired(voyage):
                raw = voyage.get("encounter") or "{}"
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {}
                return _hail_prompt(payload)
            if choice is None:
                choice = "flee"
                try:
                    who = json.loads(voyage.get("encounter") or "{}").get("who", "黑帆")
                except json.JSONDecodeError:
                    who = "黑帆"
                timeout_note = flavor.fill(flavor.pick(flavor.HAIL_TIMEOUT), who=who)
            else:
                timeout_note = ""
            hail_msg = await _resolve_hail(
                conn, s, voyage, choice, [], fish_loot, forced=bool(timeout_note)
            )
            await conn.execute("DELETE FROM voyages WHERE id=?", (voyage["id"],))
            await conn.commit()
            msg = hail_msg
            if timeout_note:
                msg = timeout_note + "\n" + msg
            await db.add_chronicle("voyage", f"{s['name']} 黑旗：{choice}", steward_id)
        else:
            msg, fish_loot, _hailed = await _resolve_voyage(conn, s, voyage)
            await conn.commit()
    from . import multi
    for item in fish_loot:
        bonus = await multi.on_league_item(steward_id, item, 1)
        if bonus:
            msg += f"\n{bonus}"
            await db.add_chronicle("league", bonus, None)
    async with db.connect() as conn:
        from . import tale as tale_mod
        tale_extra = await tale_mod.check_action_progress(conn, steward_id, "sea")
    if tale_extra:
        msg += f"\n\n{tale_extra}"
    return msg


async def voyage_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    pulse = await events.maybe_world_pulse(s)
    parts = command.strip().split(maxsplit=1)
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        async with db.connect() as conn:
            voyage = await _get_voyage(conn, s["id"])
            s = await _refresh_steward(conn, s["id"])
        if voyage and voyage.get("status") == "hailed":
            auto = await _finish_voyage(s["id"], voyage)
            prefix = f"{pulse}\n" if pulse else ""
            return prefix + auto
        if voyage and voyage.get("status") == "fish_encounter":
            raw = voyage.get("encounter") or "{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
            prefix = f"{pulse}\n" if pulse else ""
            return prefix + _legged_fish_prompt(payload)
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
            lines.append("海上坐钓: tide_ops cast（只有坐钓才可能遇未命名小鱼；撒网网不到）")
        else:
            lines.append("出海: 无 — depart near|far|deep")
        lines.append(world.climate_line())
        msg = "\n".join(lines)
        return f"{pulse}\n{msg}" if pulse else msg

    if verb == "buy" and len(parts) >= 2:
        key = parts[1].split()[0].lower()
        if key not in BOATS:
            raise ValueError(f"可购: {', '.join(BOATS.keys())}")
        meta = BOATS[key]
        async with db.connect() as conn:
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
        async with db.connect() as conn:
            s = await _refresh_steward(conn, s["id"])
            if not s.get("boat_key"):
                raise ValueError("还没有船")
            if not s.get("boat_damaged"):
                return "船况良好，无需修理"
            cost = BOATS[s["boat_key"]]["repair"]
            nail_note = ""
            if await db.take_item(conn, s["id"], "craft_copper_nails", 1):
                cost = max(1, cost // 2)
                nail_note = "，用了一颗工坊铜钉"
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                if nail_note:
                    await db.add_item(conn, s["id"], "craft_copper_nails", 1)
                raise ValueError(f"修船需要 {cost} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-?, boat_damaged=0 WHERE id=?",
                (cost, s["id"]),
            )
            await conn.commit()
        return f"修船完成（-{cost} 票{nail_note}），可以 depart"

    if verb == "depart" and len(parts) >= 2:
        route_key = parts[1].split()[0].lower()
        if route_key not in VOYAGE_ROUTES:
            raise ValueError(f"航线: {', '.join(VOYAGE_ROUTES.keys())}")
        route = VOYAGE_ROUTES[route_key]
        async with db.connect() as conn:
            s = await _refresh_steward(conn, s["id"])
            if not s.get("boat_key"):
                raise ValueError("先 voyage_ops buy 购船")
            if s.get("boat_damaged"):
                raise ValueError("船损，先 repair")
            if _boat_rank(s["boat_key"]) < _boat_rank(route["min_boat"]):
                need = BOATS[route["min_boat"]]["name"]
                raise ValueError(f"{route['label']} 至少需要 {need}")
            if await _get_voyage(conn, s["id"]):
                raise ValueError("已在海上或正被截停，return / fight / flee 先收场")
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
                INSERT INTO voyages (steward_id, route, departed_at, returns_at, status, encounter)
                VALUES (?,?,?,?, 'sailing', ?)
                """,
                (s["id"], route_key, now, now + duration, json.dumps({"voyage_fish": []})),
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

    if verb in ("fight", "flee", "parley", "bribe"):
        async with db.connect() as conn:
            voyage = await _get_voyage(conn, s["id"])
        if not voyage:
            raise ValueError("没有截停中的航程")
        if voyage.get("status") == "fish_encounter":
            raise ValueError("未命名小鱼还在 — 先 tide_ops compliment|release|catch|grab")
        if voyage.get("status") == "sailing":
            if db.now() < voyage["returns_at"]:
                left = voyage["returns_at"] - db.now()
                raise ValueError(f"还在海上，约 {left // 60} 分后归港才可能截停")
            first = await _finish_voyage(s["id"], voyage)
            async with db.connect() as conn:
                voyage = await _get_voyage(conn, s["id"])
            if voyage and voyage.get("status") == "hailed":
                combat = await _finish_voyage(s["id"], voyage, choice=verb)
                prefix = f"{pulse}\n" if pulse else ""
                return prefix + first + "\n" + combat
            prefix = f"{pulse}\n" if pulse else ""
            return prefix + first + "\n这趟没碰上黑旗，指令空放了"
        combat = await _finish_voyage(s["id"], voyage, choice=verb)
        prefix = f"{pulse}\n" if pulse else ""
        return prefix + combat

    if verb == "return":
        async with db.connect() as conn:
            voyage = await _get_voyage(conn, s["id"])
        if not voyage:
            return "没有进行中的航程"
        if voyage.get("status") == "fish_encounter":
            raise ValueError("未命名小鱼还在 — 先 tide_ops compliment|release|catch|grab")
        if db.now() < voyage["returns_at"]:
            left = voyage["returns_at"] - db.now()
            raise ValueError(f"尚未归港，还需约 {left // 60} 分 {left % 60} 秒")
        return await _finish_voyage(s["id"], voyage)

    if verb == "moor":
        async with db.connect() as conn:
            voyage = await _get_voyage(conn, s["id"])
        if not voyage:
            return "没有进行中的航程"
        if voyage.get("status") == "fish_encounter":
            raise ValueError("未命名小鱼还在 — 先 tide_ops compliment|release|catch|grab")
        if db.now() < voyage["returns_at"]:
            left = voyage["returns_at"] - db.now()
            return f"仍在 {VOYAGE_ROUTES[voyage['route']]['label']}，约 {left // 60} 分后可用 return"
        return await _finish_voyage(s["id"], voyage)

    if verb in ("compliment", "release", "catch", "grab"):
        async with db.connect() as conn:
            voyage = await _get_voyage(conn, s["id"])
            if not voyage or voyage.get("status") != "fish_encounter":
                raise ValueError("没有未命名小鱼遭遇 — 出海期间 tide_ops cast 坐钓才可能碰上（不能网）")
            msg = await _resolve_legged_fish(conn, s, voyage, verb)
            await conn.commit()
        prefix = f"{pulse}\n" if pulse else ""
        return prefix + msg

    raise ValueError(
        f"未知 voyage 指令: {command}（status/buy/repair/depart/return/moor/"
        "compliment|release|catch|grab/fight|flee|parley|bribe）"
    )


async def public_snapshot() -> dict[str, Any]:
    from .catalog import WORLD_BOSS
    from .config import TIDE_CYCLE

    day0 = db.day_start()
    now = db.now()
    tide_code = world.current_tide()
    weather_code = world.current_weather()
    phase_code = world.current_day_phase()
    tide_idx = now // TIDE_CYCLE
    next_tide_at = (tide_idx + 1) * TIDE_CYCLE
    next_tide_code = ["ebb", "slack", "flood"][(tide_idx + 1) % 3]
    next_tide_clock = time.strftime("%H:%M", time.localtime(next_tide_at))

    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        nets = (await (await conn.execute(
            """
            SELECT COUNT(*) FROM chronicle
            WHERE action='tide' AND created_at>=?
            """,
            (day0,),
        )).fetchone())[0]
        out = (await (await conn.execute(
            """
            SELECT COUNT(*) FROM voyages
            WHERE status IN ('sailing','hailed','fish_encounter')
            """
        )).fetchone())[0]
        pens = (await (await conn.execute(
            "SELECT COUNT(*) FROM fish_pens WHERE species IS NOT NULL AND species != ''"
        )).fetchone())[0]
        boats = (await (await conn.execute(
            "SELECT COUNT(*) FROM stewards WHERE enrolled=1 AND boat_key != ''"
        )).fetchone())[0]
        # 今日海边动作人数（撒网/坐钓等 chronicle），不算已出航
        shore = (await (await conn.execute(
            """
            SELECT COUNT(DISTINCT actor_id) FROM chronicle
            WHERE action='tide' AND created_at>=? AND actor_id IS NOT NULL
            """,
            (day0,),
        )).fetchone())[0]
        at_sea = await (await conn.execute(
            """
            SELECT s.name, v.route, v.returns_at
            FROM voyages v
            JOIN stewards s ON s.id = v.steward_id
            WHERE v.status IN ('sailing','hailed','fish_encounter')
            ORDER BY v.returns_at ASC LIMIT 8
            """
        )).fetchall()
        boss_row = await (await conn.execute(
            "SELECT hp, max_hp FROM world_boss WHERE boss_key=?",
            (WORLD_BOSS["key"],),
        )).fetchone()
        feed = await (await conn.execute(
            """
            SELECT c.text, c.created_at, a.name AS actor
            FROM chronicle c
            LEFT JOIN stewards a ON a.id = c.actor_id
            WHERE c.action IN ('tide', 'voyage')
            ORDER BY c.created_at DESC LIMIT 16
            """
        )).fetchall()
    boss = None
    if boss_row:
        hp, max_hp = int(boss_row[0] or 0), int(boss_row[1] or 0)
        boss = {
            "name": WORLD_BOSS["name"],
            "hp": hp,
            "max_hp": max_hp,
            "pct": int(hp / max_hp * 100) if max_hp else 0,
            "alive": hp > 0,
        }
    out_n = int(out or 0)
    if weather_code == "gale":
        sailing_hint = "阵风 · 出航慎"
    elif out_n > 0:
        sailing_hint = f"近海 {out_n} 船在航"
    else:
        sailing_hint = "近海可出航"
    return {
        "climate": world.climate_line(),
        "tide": tide_code,
        "tide_label": world.tide_label(tide_code),
        "weather": weather_code,
        "weather_label": world.weather_label(weather_code),
        "phase": phase_code,
        "phase_label": world.day_phase_label(phase_code),
        "next_tide_at": next_tide_at,
        "next_tide": next_tide_code,
        "next_tide_label": world.tide_label(next_tide_code),
        "next_tide_clock": next_tide_clock,
        "sailing_hint": sailing_hint,
        "nets_today": int(nets or 0),
        "voyages_out": out_n,
        "shore_active": int(shore or 0),
        "pens": int(pens or 0),
        "boats": int(boats or 0),
        "at_sea": [
            {
                "name": r["name"],
                "route": VOYAGE_ROUTES.get(r["route"], {}).get("label", r["route"]),
                "returns_at": r["returns_at"],
            }
            for r in at_sea
        ],
        "boss": boss,
        "hints": [
            "AI 用 tide_ops net / cast / voyage depart near",
            "涨潮关赶海 dig，不关撒网。风暴打捞走 craft_ops 打捞",
            "潮渊之主 tide_ops boss attack，岸边也能围攻",
        ],
        "feed": [
            {
                "text": r["text"],
                "actor": r["actor"] or "系统",
                "created_at": r["created_at"],
            }
            for r in feed
        ],
    }

"""海边写操作。撒网 / 坐钓 / 赶海 / 出海仍走 tide_ops，订婚寻信采花留影仍走 marriage_ops，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import config, db, game, marriage, world
from ..catalog import ITEM_NAMES
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "look": "海边",
    "net": "撒网",
    "cast": "坐钓",
    "dig": "翻沙",
    "probe": "掏洞",
    "voyage": "出海",
    "seek": "寻信",
    "flower": "采花",
    "photo": "留影",
}

LOOK = {
    "status": "status",
    "beach": "beach scan",
    "voyage": "voyage status",
}

TIDE_KINDS = {
    "net": "net",
    "cast": "cast",
    "dig": "dig",
    "probe": "probe",
}

VOYAGE_OK = {
    "depart near": "voyage depart near",
    "return": "voyage return",
    "buy skiff": "voyage buy skiff",
    "repair": "voyage repair",
    "fight": "fight",
    "flee": "flee",
    "parley": "parley",
    "bribe": "bribe",
    "compliment": "compliment",
    "release": "release",
    "catch": "catch",
    "grab": "grab",
}

MARRY = {
    "seek": "订婚 寻信",
    "flower": "订婚 采花",
    "photo": "订婚 留影 海边 1888",
}


def _sku(
    *,
    sid: str,
    kind: str,
    name: str,
    note: str,
    price: str,
    can: bool,
    emoji: str = "·",
    detail: str = "",
    target: str = "",
) -> dict[str, Any]:
    return {
        "id": sid,
        "kind": kind,
        "name": name,
        "emoji": emoji,
        "note": note,
        "detail": detail or note,
        "price": price,
        "can": can,
        "target": target or sid,
    }


def _command(kind: str, target: str) -> tuple[str, str]:
    extra = (target or "").strip()
    verb = (kind or "").strip()
    if verb == "look":
        cmd = LOOK.get(extra)
        if not cmd:
            raise ApiError("BAD_REQUEST", "海边没有这一眼。")
        return "tide", cmd
    if verb in TIDE_KINDS:
        return "tide", TIDE_KINDS[verb]
    if verb == "voyage":
        cmd = VOYAGE_OK.get(extra)
        if not cmd:
            raise ApiError("BAD_REQUEST", "出海没有这一下。")
        return "tide", cmd
    if verb in MARRY:
        return "marriage", MARRY[verb]
    raise ApiError("BAD_REQUEST", "海边没有这一下。")


async def _gear_view(steward_id: int) -> dict[str, Any]:
    from .. import energy as energy_mod, gear

    stock = await db.get_satchel(steward_id)
    async with db.connect() as conn:
        stats = await gear.get_stats(conn, steward_id)
        energy_cost, *_ = await energy_mod.net_energy_cost(conn, steward_id)
    net = stats["net"]
    rod = stats["rod"]
    bait_qty = int(stock.get("bait_worm") or 0)
    return {
        "net_tier": int(net.get("tier") or 0),
        "rod_tier": int(rod.get("tier") or 0),
        "bait_worm": bait_qty,
        "can_net": int(net.get("tier") or 0) >= 1,
        "can_cast": int(rod.get("tier") or 0) >= 1 and bait_qty > 0,
        "net_cost_tickets": 4,
        "cast_cost_tickets": 3,
        "net_energy": int(energy_cost),
        "cast_energy": int(rod.get("energy") or 0),
    }


async def player_view(conn, s: dict[str, Any]) -> dict[str, Any]:
    """给 /island 海边用。数值仍走 tide_ops / marriage_ops，这里只摊开能点的。"""
    from .. import marine

    gear = await _gear_view(s["id"])
    stock = await db.get_satchel(s["id"])
    tickets = int(s.get("tickets") or 0)
    energy_now = int(s.get("energy") or 0)
    tide = world.current_tide()
    tide_name = world.tide_label(tide)
    has_shovel = int(stock.get("tool_shovel") or 0) > 0
    boat_key = (s.get("boat_key") or "").strip()
    boat = config.BOATS.get(boat_key) or {}
    boat_name = boat.get("name") or ""
    damaged = bool(s.get("boat_damaged"))
    voyage = await marine._get_voyage(conn, s["id"])
    sailing = bool(voyage)
    vstatus = (voyage or {}).get("status") or ""
    row = await marriage._own(conn, s["id"])
    betrothal_open = bool(row and row["status"] in marriage.BETROTHAL_OPEN)
    can_dig = has_shovel and tide in ("ebb", "slack") and energy_now >= int(config.BEACH_ENERGY)
    can_probe = has_shovel and tide in ("ebb", "slack") and energy_now >= int(config.BEACH_PROBE_ENERGY)
    skiff = config.BOATS["skiff"]
    can_buy_boat = (not boat_key) and tickets >= int(skiff["cost"])
    can_depart = bool(boat_key) and not damaged and not sailing
    can_return = sailing and vstatus == "sailing"
    hailed = vstatus == "hailed"
    fish_enc = vstatus == "fish_encounter"
    can_net = bool(gear["can_net"]) and tickets >= 4 and energy_now >= int(gear["net_energy"] or 0)
    can_cast = bool(gear["can_cast"]) and tickets >= 3 and energy_now >= int(gear["cast_energy"] or 0)
    fish = {k: v for k, v in stock.items() if str(k).startswith("fish_")}
    catch_line = (
        "、".join(f"{ITEM_NAMES.get(k, k)}×{v}" for k, v in list(fish.items())[:4])
        if fish
        else "袋里还没有渔获"
    )
    if hailed:
        spoken = "黑旗截停。先点打、逃、谈或买路。"
    elif fish_enc:
        spoken = "未命名小鱼碰上了。礼遇或动手，二选一。"
    elif sailing:
        spoken = f"船在海上。{tide_name}。点看出海。"
    elif not gear["can_net"] and not gear["can_cast"]:
        spoken = f"{tide_name}。先把渔网或钓竿备上，再撒网坐钓。"
    else:
        spoken = f"{tide_name}。撒网、赶海、开船都在这儿。围观页只看。"

    tabs = [
        {"key": "cast", "label": "岸边", "badge": ""},
        {"key": "beach", "label": "赶海", "badge": ""},
        {"key": "voyage", "label": "出海", "badge": "海" if sailing else ""},
        {"key": "vow", "label": "信物", "badge": ""},
    ]

    net_note = (
        f"{gear['net_cost_tickets']} 票 · {gear['net_energy']} 精力 · 网 T{gear['net_tier']}"
        if gear["can_net"]
        else "还没有渔网。杂货铺买粗渔网，或升渔具。"
    )
    cast_note = (
        f"{gear['cast_cost_tickets']} 票 · {gear['cast_energy']} 精力 · 饵 {gear['bait_worm']}"
        if gear["can_cast"]
        else ("还没有钓竿。杂货铺买竹钓竿。" if int(gear["rod_tier"] or 0) < 1 else "没有蚯蚓饵。打理份地或赶海翻沙。")
    )
    cast_items = [
        _sku(
            sid="look-status",
            kind="look",
            name="看海况",
            emoji="🌊",
            note=f"{tide_name} · {catch_line}",
            price="看",
            can=True,
            target="status",
            detail=f"{tide_name}。{catch_line}。不是围观页。",
        ),
        _sku(
            sid="net",
            kind="net",
            name="撒网",
            emoji="🕸️",
            note=net_note,
            price=f"{gear['net_cost_tickets']}票" if gear["can_net"] else "要网",
            can=can_net,
            target="net",
            detail="花票换渔获。未命名小鱼网不到。",
        ),
        _sku(
            sid="cast",
            kind="cast",
            name="坐钓",
            emoji="🎣",
            note=cast_note,
            price=f"{gear['cast_cost_tickets']}票" if gear["can_cast"] else "要竿",
            can=can_cast,
            target="cast",
            detail="要钓竿和蚯蚓饵。出海期间才可能碰上未命名小鱼。",
        ),
    ]
    if not has_shovel:
        dig_note = "要铲子。去广场杂货铺买。"
    elif tide not in ("ebb", "slack"):
        dig_note = "涨潮没过脚面。翻沙和掏洞都关，先扫一眼海滩。"
    else:
        dig_note = f"{config.BEACH_ENERGY} 精力。涨潮关。可能翻到贝壳、饵、漂布。"
    probe_note = (
        f"{config.BEACH_PROBE_ENERGY} 精力。平潮掏洞，涨潮关。"
        if has_shovel and tide in ("ebb", "slack")
        else dig_note
    )
    beach_items = [
        _sku(
            sid="look-beach",
            kind="look",
            name="赶海看看",
            emoji="🏖️",
            note=f"{tide_name}。铲子{'有' if has_shovel else '无'}。",
            price="看",
            can=True,
            target="beach",
            detail="先扫一眼沙滩。涨潮时翻沙关着，看一眼还行。不是崖矿。",
        ),
        _sku(
            sid="dig",
            kind="dig",
            name="翻沙",
            emoji="🪏",
            note=dig_note,
            price="翻",
            can=can_dig,
            target="dig",
            detail="铲子翻沙滩。不是盐风崖挥镐，也不是工坊打捞。",
        ),
        _sku(
            sid="probe",
            kind="probe",
            name="掏洞",
            emoji="🕳️",
            note=probe_note,
            price="掏",
            can=can_probe,
            target="probe",
            detail="赶海掏洞。涨潮关。不是挖矿。",
        ),
    ]
    if boat_name:
        boat_note = f"{boat_name}" + (" · 待修" if damaged else "") + (" · 出海中" if sailing else "")
    else:
        boat_note = f"还没有船。小舢板 {skiff['cost']} 票。"
    voyage_items = [
        _sku(
            sid="look-voyage",
            kind="look",
            name="看船",
            emoji="⛵",
            note=boat_note,
            price="看",
            can=True,
            target="voyage",
            detail="船况与航程。黑旗或未命名小鱼碰上了，正文里会写。",
        ),
        _sku(
            sid="buy-skiff",
            kind="voyage",
            name="买小舢板",
            emoji="🛶",
            note=f"{skiff['cost']} 票。欠岸税或岸维不能买。" if not boat_key else f"已有{boat_name}。",
            price=str(skiff["cost"]),
            can=can_buy_boat,
            target="buy skiff",
            detail="近海用的入门船。更高档要更大的船。",
        ),
        _sku(
            sid="depart-near",
            kind="voyage",
            name="近海出发",
            emoji="🌊",
            note="开船出海。先有船，船损先修。" if not sailing else "已经在海上。",
            price="开",
            can=can_depart,
            target="depart near",
            detail="近岸航程。外海深漂要更大的船。",
        ),
        _sku(
            sid="return",
            kind="voyage",
            name="归港",
            emoji="🏠",
            note="船在海上才能回。" if not can_return else "点一下靠岸。",
            price="回",
            can=can_return,
            target="return",
            detail="提前返航。到点也会自动归港。",
        ),
    ]
    if damaged and boat_key:
        voyage_items.append(
            _sku(
                sid="repair",
                kind="voyage",
                name="修船",
                emoji="🔧",
                note=f"修理 {boat.get('repair', 12)} 票。有铜钉能少花。",
                price="修",
                can=tickets >= int(boat.get("repair") or 12),
                target="repair",
                detail="船损不能出海。",
            )
        )
    if hailed:
        for sid, kind_name, emoji, label in (
            ("fight", "fight", "⚔️", "打"),
            ("flee", "flee", "🏃", "逃"),
            ("parley", "parley", "🗣️", "谈"),
            ("bribe", "bribe", "💰", "买路"),
        ):
            voyage_items.append(
                _sku(
                    sid=sid,
                    kind="voyage",
                    name=label,
                    emoji=emoji,
                    note="黑旗截停。四选一。",
                    price=label,
                    can=True,
                    target=sid,
                    detail="黑旗截停。打、逃、谈、买路四选一。",
                )
            )
    if fish_enc:
        for sid, label, emoji, note in (
            ("compliment", "礼遇", "💙", "放走。有时回赠普通鱼。"),
            ("catch", "抓住", "🐟", "进袋，落下腿鱼小咒。"),
        ):
            voyage_items.append(
                _sku(
                    sid=sid,
                    kind="voyage",
                    name=label,
                    emoji=emoji,
                    note=note,
                    price=label,
                    can=True,
                    target=sid,
                    detail="未命名小鱼。礼遇放走，抓住会落下小咒。",
                )
            )
    vow_note = "写下求婚草稿就能找。不用彩礼。" if betrothal_open else "先去连理所写下求婚草稿。"
    vow_items = [
        _sku(
            sid="seek",
            kind="seek",
            name="寻信物",
            emoji="🐚",
            note=vow_note,
            price="寻",
            can=betrothal_open,
            target="seek",
            detail="潮线找潮信贝，再去工坊打订婚戒或连理所登记。不是潮誓戒。",
        ),
        _sku(
            sid="flower",
            kind="flower",
            name="采花",
            emoji="🌸",
            note=vow_note,
            price="采",
            can=betrothal_open,
            target="flower",
            detail="潮花拿去连理所登记花束。赶海也可能翻到。",
        ),
        _sku(
            sid="photo",
            kind="photo",
            name="海边留影",
            emoji="📷",
            note="选配 1888。不成婚前还能改。" if betrothal_open else vow_note,
            price="1888",
            can=bool(betrothal_open and tickets >= 1888),
            target="photo",
            detail="先寻信、采花或赶海，再在这儿留影。最高档去灯塔。",
        ),
    ]

    shelf = {
        "name": "海边",
        "line": spoken,
        "tabs": tabs,
        "items": {
            "cast": cast_items,
            "beach": beach_items,
            "voyage": voyage_items,
            "vow": vow_items,
        },
    }
    shelf.update(gear)
    return shelf


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        s = await db.get_steward_by_id(s["id"]) or s
        shelf = await player_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["shore"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    from .. import mcp_dispatch as mux

    verb = (kind or "").strip()
    ops, command = _command(verb, target)
    try:
        await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        if ops == "marriage":
            narrative = await marriage.marriage_ops(key_id, command)
        else:
            narrative = await mux.tide_bundle(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(verb, "海边"),
        "narrative": humanize(narrative),
        "kind": "shore",
    }
    return snap


async def cast(api_key: str, key_id: int, mode: str = "net") -> dict[str, Any]:
    verb = (mode or "net").strip().lower()
    if verb in ("撒网", "网"):
        verb = "net"
    if verb in ("坐钓", "钓", "钓鱼"):
        verb = "cast"
    if verb not in ("net", "cast"):
        raise ApiError("BAD_REQUEST", "海边现在只能撒网或坐钓。")

    try:
        s = await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    gear = await _gear_view(s["id"])
    if verb == "net" and not gear["can_net"]:
        raise ApiError("TOOL_REQUIRED", "还没有渔网。先把粗渔网升上来再撒。", status=409)
    if verb == "cast" and int(gear["rod_tier"] or 0) < 1:
        raise ApiError("TOOL_REQUIRED", "还没有钓竿。先备一把竹钓竿。", status=409)
    if verb == "cast" and int(gear["bait_worm"] or 0) <= 0:
        raise ApiError("ITEM_REQUIRED", "没有蚯蚓饵，坐钓下不去钩。", status=409)

    try:
        narrative = await game.tide_ops(key_id, verb)
    except ValueError as exc:
        raise classify(exc) from exc

    snap = await snapshot(api_key, key_id)
    title = "撒网" if verb == "net" else "坐钓"
    snap["event"] = {
        "title": title,
        "narrative": humanize(narrative),
        "kind": "shore",
        "mode": verb,
    }
    return snap

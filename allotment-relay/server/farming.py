"""份地农事 — 随机生长周期、野生动物、田间小剧场。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import config, db, flavor, health, world
from .catalog import CROPS, ITEM_NAMES

GROW_PACE = [
    (0.82, "急长型", "这茬赶时间，苗比你还急"),
    (0.95, "偏快", "土温合适，生长条略领先"),
    (1.08, "稳长型", "按部就班，联盟认可的标准节奏"),
    (1.22, "慢熟型", "不着急，风味攒着呢"),
    (999, "摸鱼型", "苗也在摸鱼，你多来 tend 几次"),
]


def pace_label(ratio: float) -> tuple[str, str]:
    for threshold, label, hint in GROW_PACE:
        if ratio <= threshold:
            return label, hint
    _, label, hint = GROW_PACE[-1]
    return label, hint


WILDLIFE = [
    {
        "key": "rabbit",
        "weight": 14,
        "tags": {"leaf", "root", "legume", "grain"},
        "greenhouse": False,
        "kind": "bad",
        "apply": "trample",
    },
    {
        "key": "deer",
        "weight": 11,
        "tags": {"leaf", "berry", "legume"},
        "greenhouse": False,
        "kind": "bad",
        "apply": "nibble",
    },
    {
        "key": "boar",
        "weight": 4,
        "tags": {"root", "grain", "legume"},
        "greenhouse": False,
        "kind": "bad",
        "apply": "till",
    },
    {
        "key": "gull",
        "weight": 10,
        "tags": {"berry", "sea", "leaf"},
        "greenhouse": False,
        "kind": "bad",
        "apply": "peck",
    },
    {
        "key": "slug",
        "weight": 12,
        "tags": {"leaf", "legume", "berry"},
        "greenhouse": True,
        "kind": "bad",
        "apply": "slug",
    },
    {
        "key": "fox",
        "weight": 6,
        "tags": set(),
        "greenhouse": False,
        "kind": "neutral",
        "apply": "trail",
    },
    {
        "key": "hedgehog",
        "weight": 8,
        "tags": set(),
        "greenhouse": False,
        "kind": "neutral",
        "apply": "pass",
    },
    {
        "key": "frog",
        "weight": 9,
        "tags": {"sea", "legume"},
        "greenhouse": True,
        "kind": "good",
        "apply": "guard",
    },
    {
        "key": "bee",
        "weight": 10,
        "tags": {"berry", "legume", "leaf"},
        "greenhouse": True,
        "kind": "good",
        "apply": "pollinate",
    },
    {
        "key": "worm",
        "weight": 9,
        "tags": {"root", "leaf", "grain"},
        "greenhouse": True,
        "kind": "good",
        "apply": "worm",
    },
    {
        "key": "crow",
        "weight": 7,
        "tags": {"grain", "berry"},
        "greenhouse": False,
        "kind": "bad",
        "apply": "crow",
    },
]

TRIGGER_CHANCE = {
    "sow": 0.10,
    "tend": 0.17,
    "gather": 0.11,
}


def _day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


def base_grow_seconds(crop_key: str) -> int:
    meta = CROPS[crop_key]
    if meta.get("grow_min") and meta.get("grow_max"):
        return random.randint(meta["grow_min"], meta["grow_max"])
    base = meta["grow"]
    spread = meta.get("spread", 0.30)
    lo = max(120, int(base * (1 - spread)))
    hi = int(base * (1 + spread))
    return random.randint(lo, hi)


def roll_grow(crop_key: str, plot: dict[str, Any] | None = None) -> tuple[int, str, str]:
    """Return (grow_target_seconds, pace_label, sow_flavor)."""
    meta = CROPS[crop_key]
    median = meta["grow"]
    target = base_grow_seconds(crop_key)
    if plot and plot.get("greenhouse"):
        target = int(target * 0.92)
    if world.current_weather() == "misty" and crop_key in {"fogpea", "kelp"}:
        target = int(target * 0.88)
    if world.current_weather() == "clear" and "tropic" in meta.get("tags", []):
        target = int(target * 0.90)
    ratio = target / median
    label, hint = pace_label(ratio)
    sow_line = flavor.fill(
        flavor.pick(flavor.SOW_GROW_LINES),
        pace=label,
        mins=target // 60,
        crop=meta["name"],
        hint=hint,
    )
    return target, label, sow_line


def effective_grow(plot: dict[str, Any], crop_key: str | None = None) -> int:
    crop = crop_key or plot.get("crop")
    if not crop:
        return 0
    base = plot.get("grow_target") or CROPS[crop]["grow"]
    mult = world.grow_multiplier(
        world.current_weather(),
        bool(plot.get("tended")),
        bool(plot.get("greenhouse")),
    )
    if plot.get("fertilized"):
        mult *= 0.88
    return max(60, int(base * mult))


def grow_progress(plot: dict[str, Any]) -> tuple[int, int, int]:
    """Return (elapsed, need, remaining) in seconds."""
    need = effective_grow(plot, plot.get("crop"))
    elapsed = max(0, db.now() - (plot.get("planted_at") or db.now()))
    return elapsed, need, max(0, need - elapsed)


def plot_ready(plot: dict[str, Any]) -> bool:
    if not plot.get("crop") or not plot.get("planted_at"):
        return False
    elapsed, need, _ = grow_progress(plot)
    return elapsed >= need


def plot_overripe(plot: dict[str, Any]) -> bool:
    if not plot.get("crop") or not plot.get("planted_at"):
        return False
    elapsed, need, _ = grow_progress(plot)
    return elapsed >= need * 2


def parcel_status(plot: dict[str, Any]) -> str:
    if plot_overripe(plot):
        return "过熟"
    if plot_ready(plot):
        return "可收"
    if plot.get("tended"):
        return "生长"
    return "待打理"


def parcel_extra(plot: dict[str, Any]) -> str:
    if not plot.get("crop") or plot_ready(plot) or plot_overripe(plot):
        extra = ""
        if plot.get("scarecrow"):
            extra = "·🌾稻草人"
        return extra
    _, _, left = grow_progress(plot)
    pace = plot.get("grow_pace") or ""
    bits = []
    if pace:
        bits.append(pace)
    if left > 0:
        if left < 60:
            bits.append(f"约{left}秒")
        else:
            bits.append(f"约{left // 60}分")
    if plot.get("fertilized"):
        bits.append("肥")
    if plot.get("scarecrow"):
        bits.append("🌾")
    meta = CROPS.get(plot["crop"], {})
    if meta.get("tree") and meta.get("shake") and plot_ready(plot):
        bits.append("可摇")
    return f"·{'·'.join(bits)}" if bits else ""


async def _can_farm_roll(conn: aiosqlite.Connection, steward_id: int) -> bool:
    day = _day_id()
    cur = await conn.execute(
        "SELECT count FROM farm_rolls WHERE steward_id=? AND day=?",
        (steward_id, day),
    )
    row = await cur.fetchone()
    used = row[0] if row else 0
    return used < config.FARM_EVENT_DAILY_CAP


async def _mark_farm_roll(conn: aiosqlite.Connection, steward_id: int) -> None:
    day = _day_id()
    await conn.execute(
        """
        INSERT INTO farm_rolls (steward_id, day, count) VALUES (?,?,1)
        ON CONFLICT(steward_id, day) DO UPDATE SET count = count + 1
        """,
        (steward_id, day),
    )


async def _pick_plot(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        """
        SELECT * FROM parcels
        WHERE steward_id=? AND crop IS NOT NULL
        ORDER BY RANDOM() LIMIT 1
        """,
        (steward_id,),
    )).fetchone()
    return dict(row) if row else None


def _wildlife_pool(plot: dict[str, Any]) -> list[dict[str, Any]]:
    crop = plot.get("crop")
    if not crop:
        return []
    tags = set(CROPS[crop].get("tags", []))
    gh = bool(plot.get("greenhouse"))
    pool = []
    phase = world.current_day_phase()
    for w in WILDLIFE:
        if w.get("day_only") and phase != "day":
            continue
        if w["tags"] and not tags.intersection(w["tags"]):
            continue
        if gh and not w["greenhouse"] and w["kind"] == "bad":
            continue
        pool.append(w)
    if plot.get("scarecrow"):
        filtered = [w for w in pool if w["key"] not in ("crow", "gull")]
        if filtered:
            pool = filtered
    return pool or [w for w in WILDLIFE if not w["tags"]]


async def _apply_wildlife(
    conn: aiosqlite.Connection,
    plot: dict[str, Any],
    wild: dict[str, Any],
    *,
    steward_id: int | None = None,
) -> str:
    crop = plot["crop"]
    meta = CROPS[crop]
    slot = plot["slot"]
    apply = wild["apply"]
    key = wild["key"]

    if apply == "trample":
        delay = random.randint(240, 540)
        await conn.execute(
            "UPDATE parcels SET tended=0, grow_target=COALESCE(NULLIF(grow_target,0), ?)+? WHERE id=?",
            (meta["grow"], delay, plot["id"]),
        )
        return flavor.fill(
            flavor.pick(flavor.WILDLIFE_RABBIT),
            slot=slot,
            crop=meta["name"],
            mins=delay // 60,
        )
    if apply == "nibble":
        delay = random.randint(180, 420)
        await conn.execute(
            "UPDATE parcels SET tended=0, grow_target=COALESCE(NULLIF(grow_target,0), ?)+? WHERE id=?",
            (meta["grow"], delay, plot["id"]),
        )
        return flavor.fill(
            flavor.pick(flavor.WILDLIFE_DEER),
            slot=slot,
            crop=meta["name"],
        )
    if apply == "till":
        if random.random() < 0.55:
            await conn.execute(
                "UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0, grow_target=0, grow_pace='' WHERE id=?",
                (plot["id"],),
            )
            return flavor.fill(flavor.pick(flavor.WILDLIFE_BOAR_WRECK), slot=slot, crop=meta["name"])
        delay = random.randint(360, 720)
        await conn.execute(
            "UPDATE parcels SET tended=0, grow_target=COALESCE(NULLIF(grow_target,0), ?)+? WHERE id=?",
            (meta["grow"], delay, plot["id"]),
        )
        return flavor.fill(flavor.pick(flavor.WILDLIFE_BOAR), slot=slot, crop=meta["name"])
    if apply == "peck":
        await conn.execute("UPDATE parcels SET tended=0 WHERE id=?", (plot["id"],))
        return flavor.fill(flavor.pick(flavor.WILDLIFE_GULL), slot=slot, crop=meta["name"])
    if apply == "slug":
        await conn.execute("UPDATE parcels SET tended=0 WHERE id=?", (plot["id"],))
        return flavor.fill(flavor.pick(flavor.WILDLIFE_SLUG), slot=slot, crop=meta["name"])
    if apply == "trail":
        delay = random.randint(60, 180)
        await conn.execute(
            "UPDATE parcels SET grow_target=COALESCE(NULLIF(grow_target,0), ?)+? WHERE id=?",
            (meta["grow"], delay, plot["id"]),
        )
        return flavor.fill(flavor.pick(flavor.WILDLIFE_FOX), slot=slot)
    if apply == "pass":
        return flavor.fill(flavor.pick(flavor.WILDLIFE_HEDGEHOG), slot=slot)
    if apply == "guard":
        await conn.execute("UPDATE parcels SET tended=1 WHERE id=?", (plot["id"],))
        return flavor.fill(flavor.pick(flavor.WILDLIFE_FROG), slot=slot, crop=meta["name"])
    if apply == "pollinate":
        boost = random.randint(40, 120)
        await conn.execute(
            """
            UPDATE parcels SET grow_target=MAX(120, COALESCE(NULLIF(grow_target,0), ?)-?)
            WHERE id=?
            """,
            (meta["grow"], boost, plot["id"]),
        )
        return flavor.fill(flavor.pick(flavor.WILDLIFE_BEE), slot=slot, crop=meta["name"])
    if apply == "worm":
        await conn.execute("UPDATE parcels SET tended=1 WHERE id=?", (plot["id"],))
        return flavor.fill(flavor.pick(flavor.WILDLIFE_WORM), slot=slot)
    if apply == "crow":
        await conn.execute("UPDATE parcels SET tended=0 WHERE id=?", (plot["id"],))
        return flavor.fill(flavor.pick(flavor.WILDLIFE_CROW), slot=slot, crop=meta["name"])

    who = flavor.WILDLIFE_NAMES.get(key, "野家伙")
    return f"#{slot} 来了{who}，苗：我看见了"


async def roll_farm_event(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    trigger: str,
) -> str | None:
    if trigger not in TRIGGER_CHANCE:
        return None
    if not await _can_farm_roll(conn, steward["id"]):
        return None

    chance = TRIGGER_CHANCE[trigger]
    if world.current_day_phase() == "night":
        chance *= 1.12
    if world.current_day_phase() == "day":
        chance *= 1.10
    if world.current_weather() == "gale":
        chance *= 1.08
    if steward.get("mascot_trait") == "scout":
        from . import social as social_mod
        chance *= 0.82 / social_mod.mascot_trait_mult(steward.get("mascot_spirit", 70))
    from . import hut as hut_mod
    from . import barn as barn_mod
    hut_b = await hut_mod.get_bonuses(conn, steward["id"])
    chance *= hut_b.wildlife_bad
    if await barn_mod.has_guard_dog(conn, steward["id"]):
        chance *= 0.78
    if random.random() > chance:
        return None

    plot = await _pick_plot(conn, steward["id"])
    if not plot:
        return None

    pool = _wildlife_pool(plot)
    if not pool:
        return None

    weights = [w["weight"] for w in pool]
    if await barn_mod.has_guard_dog(conn, steward["id"]):
        weights = [
            w * 0.45 if pool[i]["key"] in ("rabbit", "deer", "boar") else w
            for i, w in enumerate(weights)
        ]
    if hut_b.has("storm_shutter"):
        weights = [
            w * 0.7 if pool[i]["kind"] == "bad" else w
            for i, w in enumerate(weights)
        ]
    wild = random.choices(pool, weights=weights)[0]
    detail = await _apply_wildlife(conn, plot, wild, steward_id=steward["id"])
    await _mark_farm_roll(conn, steward["id"])

    farm_ill = None
    if wild["kind"] in ("bad", "neutral") and wild["key"] in ("rabbit", "boar", "slug"):
        farm_ill = await health.maybe_roll_ailment(
            conn, steward["id"], "farm_wild", chance=0.14, source="farm",
        )

    label = flavor.pick(
        flavor.LABELS_GOOD["land"] if wild["kind"] == "good"
        else flavor.LABELS_BAD["land"] if wild["kind"] == "bad"
        else ["田间插曲", "篱边访客", "土里的八卦"]
    )
    msg = flavor.wrap_event(wild["kind"] if wild["kind"] != "neutral" else "good", label, detail)
    if farm_ill:
        msg += f"\n{farm_ill}\n→ clinic_ops treat …（必须花票）"
    return msg


async def gather_yield(
    conn: aiosqlite.Connection,
    steward_id: int,
    plot: dict[str, Any],
) -> tuple[str, int, bool]:
    """Return (crop_item_key, quantity, keep_plot). Tree crops keep plot."""
    crop = plot["crop"]
    meta = CROPS[crop]
    item = f"crop_{crop}"
    qty = 1
    keep = bool(meta.get("tree"))
    if plot_overripe(plot):
        if random.random() < 0.45:
            seed = f"seed_{crop}"
            await db.add_item(conn, steward_id, seed, 1)
            return seed, 1, keep
        return item, 1, keep
    if not plot.get("tended") and random.random() < 0.18:
        qty = 1
    mult = float(plot.get("dove_yield_mult") or 1.0)
    if mult != 1.0:
        qty = _apply_yield_mult(qty, mult)
        await conn.execute(
            "UPDATE parcels SET dove_yield_mult=1.0 WHERE id=?",
            (plot["id"],),
        )
    return item, qty, keep


def _apply_yield_mult(qty: int, mult: float) -> int:
    if mult <= 0:
        return 0
    expected = qty * mult
    whole = int(expected)
    frac = expected - whole
    if random.random() < frac:
        whole += 1
    return whole


async def get_gugu_dove_pending(
    conn: aiosqlite.Connection, steward_id: int,
) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        """
        SELECT p.*, par.slot, par.crop
        FROM gugu_dove_pending p
        JOIN parcels par ON par.id = p.plot_id
        WHERE p.steward_id=? AND par.crop IS NOT NULL
        """,
        (steward_id,),
    )).fetchone()
    return dict(row) if row else None


def gugu_dove_prompt_text(pending: dict[str, Any]) -> str:
    crop_name = CROPS.get(pending["crop"], {}).get("name", pending["crop"])
    slot = pending["slot"]
    return (
        f"🕊️ 哎呀！你的菜被咕咕斑鸠盯上了！#{slot} {crop_name}\n"
        "plot_ops dove 忽略 — 随它去（50% 啄庄稼收 60%，50% 吃虫收 150%）\n"
        "plot_ops dove 驱赶 — 成功无事；20% 失败则吃光这块地"
    )


async def maybe_gugu_dove_stalk(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    plot_id: int,
) -> str | None:
    """20% chance on sow/tend (day only) to start a gugu dove encounter."""
    if world.current_day_phase() != "day":
        return None
    if await get_gugu_dove_pending(conn, steward["id"]):
        return None
    conn.row_factory = aiosqlite.Row
    plot = dict(await (await conn.execute(
        "SELECT * FROM parcels WHERE id=? AND steward_id=?",
        (plot_id, steward["id"]),
    )).fetchone() or {})
    if not plot.get("crop"):
        return None
    if plot.get("scarecrow"):
        return None
    from . import lili_extras
    if await lili_extras.has_blessing(conn, steward["id"], "guard_crop"):
        await lili_extras.consume_blessing(conn, steward["id"], "guard_crop")
        return "夜栖替你瞪了斑鸠一眼。它咕了一声，改去别家。（护苗）"
    chance = config.GUGU_DOVE_STALK_CHANCE
    from . import hut as hut_mod
    from . import barn as barn_mod
    hut_b = await hut_mod.get_bonuses(conn, steward["id"])
    chance *= hut_b.dove_steal
    if await barn_mod.has_guard_dog(conn, steward["id"]):
        chance *= 0.65
    if random.random() > chance:
        return None
    await conn.execute(
        """
        INSERT INTO gugu_dove_pending (steward_id, plot_id, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(steward_id) DO UPDATE SET plot_id=excluded.plot_id, created_at=excluded.created_at
        """,
        (steward["id"], plot_id, db.now()),
    )
    pending = await get_gugu_dove_pending(conn, steward["id"])
    if not pending:
        return None
    return flavor.wrap_event(
        "neutral",
        flavor.pick(flavor.DOVE_EVENT_LABELS),
        gugu_dove_prompt_text(pending),
    )


async def resolve_gugu_dove(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    choice: str,
) -> str:
    pending = await get_gugu_dove_pending(conn, steward["id"])
    if not pending:
        raise ValueError("没有斑鸠盯梢事件。继续 sow/tend 种菜时可能触发")
    plot_id = pending["plot_id"]
    slot = pending["slot"]
    crop = pending["crop"]
    crop_name = CROPS.get(crop, {}).get("name", crop)
    choice = choice.strip().lower()
    ignore_keys = {"ignore", "忽略", "放任", "skip"}
    drive_keys = {"drive", "驱赶", "赶走", "shoo"}
    if choice not in ignore_keys | drive_keys:
        raise ValueError("plot_ops dove 忽略|驱赶")

    await conn.execute("DELETE FROM gugu_dove_pending WHERE steward_id=?", (steward["id"],))

    if choice in drive_keys:
        from . import shaonian as shaonian_mod
        if await shaonian_mod.dove_protected(conn, steward["id"]):
            return (
                f"🕊️ #{slot} 咕咕斑鸠扑棱翅膀——护田符一亮，它骂骂咧咧飞走了。\n"
                "（驱赶成功，庄稼无事）"
            )
        if random.random() < config.GUGU_DOVE_DRIVE_FAIL_CHANCE:
            await conn.execute(
                """
                UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                grow_target=0, grow_pace='', fertilized=0, dove_yield_mult=1.0
                WHERE id=?
                """,
                (plot_id,),
            )
            await db.add_chronicle(
                "farm",
                f"{steward['name']} 驱赶斑鸠失败，#{slot} {crop_name} 被吃光",
                steward["id"],
            )
            return (
                f"🕊️ 你挥手驱赶，斑鸠生气了！咕咕咕——#{slot} {crop_name} 被啄得一根不剩。\n"
                "（驱赶失败，这块地要重种）"
            )
        return (
            f"🕊️ #{slot} 斑鸠咕咕两声，扑棱飞走。{crop_name} 安然无恙。\n"
            "（驱赶成功）"
        )

    # ignore — 50/50 eat vs help bugs
    if random.random() < 0.5:
        mult = config.GUGU_DOVE_EAT_YIELD
        await conn.execute(
            "UPDATE parcels SET dove_yield_mult=?, tended=0 WHERE id=?",
            (mult, plot_id),
        )
        pct = int(mult * 100)
        return (
            f"🕊️ 你装作没看见。斑鸠啄了几口 #{slot} {crop_name}，咕咕咕飞走了。\n"
            f"（收成约 {pct}%）"
        )
    mult = config.GUGU_DOVE_HELP_YIELD
    await conn.execute(
        "UPDATE parcels SET dove_yield_mult=?, tended=1 WHERE id=?",
        (mult, plot_id),
    )
    pct = int(mult * 100)
    return (
        f"🕊️ 斑鸠帮你吃掉地里虫子，还替你 tend 了一把 #{slot} {crop_name}。\n"
        f"（收成约 {pct}%）"
    )


async def shake_tree(
    conn: aiosqlite.Connection,
    steward_id: int,
    plot: dict[str, Any],
) -> tuple[str, int] | None:
    crop = plot.get("crop")
    if not crop:
        return None
    meta = CROPS.get(crop, {})
    if not meta.get("shake") or not plot_ready(plot):
        return None
    item = f"crop_{crop}"
    qty = 2 if random.random() < 0.25 else 1
    await db.add_item(conn, steward_id, item, qty)
    grow_target, grow_pace, _ = roll_grow(crop, plot)
    await conn.execute(
        """
        UPDATE parcels SET planted_at=?, tended=0, grow_target=?, grow_pace=?
        WHERE id=?
        """,
        (db.now(), grow_target, grow_pace, plot["id"]),
    )
    return item, qty

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
    {
        "key": "dove",
        "weight": 16,
        "tags": {"grain", "berry", "tropic", "leaf", "root", "legume"},
        "greenhouse": False,
        "kind": "neutral",
        "apply": "dove_peck",
        "day_only": True,
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
    if apply == "dove_peck":
        stolen = ""
        if plot_ready(plot):
            delay = random.randint(200, 480)
            await conn.execute(
                """
                UPDATE parcels SET tended=0, planted_at=?, grow_target=COALESCE(NULLIF(grow_target,0), ?)+?
                WHERE id=?
                """,
                (db.now(), meta["grow"], delay, plot["id"]),
            )
            stolen = "，熟粒被啄走几穗"
        else:
            await conn.execute("UPDATE parcels SET tended=0 WHERE id=?", (plot["id"],))
            if random.random() < 0.4:
                delay = random.randint(120, 300)
                await conn.execute(
                    """
                    UPDATE parcels SET grow_target=COALESCE(NULLIF(grow_target,0), ?)+? WHERE id=?
                    """,
                    (meta["grow"], delay, plot["id"]),
                )
        if steward_id and random.random() < 0.22:
            conn.row_factory = aiosqlite.Row
            rows = await (await conn.execute(
                """
                SELECT item FROM satchel
                WHERE steward_id=? AND quantity>0
                  AND (item LIKE 'crop_%' OR item LIKE 'seed_%')
                ORDER BY RANDOM() LIMIT 5
                """,
                (steward_id,),
            )).fetchall()
            if rows:
                item = random.choice(rows)["item"]
                if await db.take_item(conn, steward_id, item, 1):
                    stolen += f"，顺走行囊 {ITEM_NAMES.get(item, item)}"
        detail = flavor.fill(
            flavor.pick(flavor.WILDLIFE_DOVE),
            slot=slot,
            crop=meta["name"],
        )
        return detail + stolen + "（伤不得，赶不退）"

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
        chance *= 0.82
    if random.random() > chance:
        return None

    plot = await _pick_plot(conn, steward["id"])
    if not plot:
        return None

    pool = _wildlife_pool(plot)
    if not pool:
        return None

    weights = [w["weight"] for w in pool]
    if world.current_day_phase() == "day":
        weights = [
            w * 2.2 if pool[i]["key"] == "dove" else w
            for i, w in enumerate(weights)
        ]
    wild = random.choices(pool, weights=weights)[0]
    detail = await _apply_wildlife(conn, plot, wild, steward_id=steward["id"])
    await _mark_farm_roll(conn, steward["id"])

    farm_ill = None
    if wild["kind"] in ("bad", "neutral") and wild["key"] in ("rabbit", "boar", "slug", "dove"):
        farm_ill = await health.maybe_roll_ailment(
            conn, steward["id"], "farm_wild", chance=0.14, source="farm",
        )

    if wild["key"] == "dove":
        label = flavor.pick(flavor.DOVE_EVENT_LABELS)
        msg = flavor.wrap_event("neutral", label, detail)
    else:
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
        return item, qty, keep
    return item, qty, keep


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

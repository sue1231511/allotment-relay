"""稀有公共资源 + 意外发现（挖到/钓到/翻出）。"""

from __future__ import annotations

import random
import uuid
from typing import Any

import aiosqlite

from . import config, db, flavor, world
from .catalog import COMMONS_TEMPLATES, DISCOVERY_LOOT, ITEM_NAMES


def _day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


async def _active_spawns(conn: aiosqlite.Connection) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    now = db.now()
    await conn.execute(
        "DELETE FROM commons_spawns WHERE expires_at <= ? AND claimed_by IS NULL",
        (now,),
    )
    rows = await (await conn.execute(
        """
        SELECT * FROM commons_spawns
        WHERE claimed_by IS NULL AND expires_at > ?
        ORDER BY appears_at ASC
        """,
        (now,),
    )).fetchall()
    return [dict(r) for r in rows]


async def maybe_spawn_commons(
    conn: aiosqlite.Connection,
    steward_id: int | None = None,
) -> dict[str, Any] | None:
    """Roll a new public resource with random appear/live window."""
    active = await _active_spawns(conn)
    if len(active) >= config.COMMONS_MAX_ACTIVE:
        return None
    chance = config.COMMONS_SPAWN_CHANCE
    if steward_id:
        from . import hut as hut_mod
        hut_b = await hut_mod.get_bonuses(conn, steward_id)
        chance *= hut_b.commons_chance
    if random.random() > chance:
        return None

    tmpl = random.choices(
        COMMONS_TEMPLATES,
        weights=[t["weight"] for t in COMMONS_TEMPLATES],
    )[0]
    now = db.now()
    appear_in = random.randint(config.COMMONS_APPEAR_MIN, config.COMMONS_APPEAR_MAX)
    live = random.randint(config.COMMONS_LIVE_MIN, config.COMMONS_LIVE_MAX)
    appears_at = now + appear_in
    expires_at = appears_at + live

    detail = flavor.fill(
        flavor.pick(flavor.COMMONS_SPAWN_LINES),
        label=tmpl["label"],
        mins=(appears_at - now) // 60,
        live=live // 60,
    )
    cur = await conn.execute(
        """
        INSERT INTO commons_spawns (
            spawn_key, label, domain, reward_item, reward_qty, reward_tickets,
            detail, appears_at, expires_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            f"{tmpl['key']}:{uuid.uuid4().hex[:6]}",
            tmpl["label"],
            tmpl["domain"],
            tmpl.get("item"),
            tmpl.get("qty") or 0,
            tmpl.get("tickets") or 0,
            detail,
            appears_at,
            expires_at,
        ),
    )
    return {
        "id": cur.lastrowid,
        "label": tmpl["label"],
        "appears_at": appears_at,
        "expires_at": expires_at,
        "detail": detail,
    }


def _spawn_line(row: dict[str, Any]) -> str:
    now = db.now()
    if row["appears_at"] > now:
        left = (row["appears_at"] - now) // 60
        return f"#{row['id']} {row['label']}（{left} 分后上线）"
    left = max(0, (row["expires_at"] - now) // 60)
    reward = row.get("reward_item")
    if reward:
        loot = f"{ITEM_NAMES.get(reward, reward)} x{row['reward_qty']}"
    elif row.get("reward_tickets"):
        loot = f"{row['reward_tickets']} 票"
    else:
        loot = "物资"
    return f"#{row['id']} {row['label']} · {loot}（剩 {left} 分，claim {row['id']}）"


async def commons_snapshot(conn: aiosqlite.Connection | None = None) -> list[dict[str, Any]]:
    if conn is None:
        async with db.connect() as c:
            return await commons_snapshot(c)
    return await _active_spawns(conn)


async def commons_ops(key_id: int, command: str) -> str:
    from .game import require_steward

    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "scan"

    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        spawned = await maybe_spawn_commons(conn, steward_id=s["id"])

        if verb == "scan":
            rows = await _active_spawns(conn)
            await conn.commit()
            lines = ["全服公共物资（稀有，随机上线，先到先得）："]
            if not rows:
                lines.append("  暂无——继续 plot/tide 碰运气，或等系统刷新")
            else:
                now = db.now()
                for r in rows:
                    lines.append(f"  {_spawn_line(r)}")
                live = sum(1 for r in rows if r["appears_at"] <= now)
                lines.append(f"  可领取 {live} / 排队 {len(rows) - live}")
            if spawned:
                lines.append(f"\n🌍 新资源已排期：{spawned['label']}（{spawned['detail']}）")
            return "\n".join(lines)

        if verb == "claim" and len(parts) >= 2:
            sid = int(parts[1])
            row = await (await conn.execute(
                "SELECT * FROM commons_spawns WHERE id=? AND claimed_by IS NULL",
                (sid,),
            )).fetchone()
            if not row:
                raise ValueError("该公共物资不存在或已被领走")
            row = dict(row)
            now = db.now()
            if row["appears_at"] > now:
                left = (row["appears_at"] - now) // 60
                raise ValueError(f"尚未上线，约 {left} 分钟后可 claim")
            if row["expires_at"] <= now:
                raise ValueError("已过期，来晚了")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < config.COMMONS_CLAIM_FEE:
                raise ValueError(f"领取手续费 {config.COMMONS_CLAIM_FEE} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (config.COMMONS_CLAIM_FEE, s["id"]),
            )
            loot_parts = []
            if row.get("reward_item") and row.get("reward_qty"):
                await db.add_item(conn, s["id"], row["reward_item"], row["reward_qty"])
                loot_parts.append(
                    f"{ITEM_NAMES.get(row['reward_item'], row['reward_item'])} x{row['reward_qty']}"
                )
            if row.get("reward_tickets"):
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                    (row["reward_tickets"], s["id"]),
                )
                loot_parts.append(f"{row['reward_tickets']} 票")
            await conn.execute(
                "UPDATE commons_spawns SET claimed_by=?, claimed_at=? WHERE id=?",
                (s["id"], now, sid),
            )
            await conn.commit()
            loot = "，".join(loot_parts) or row["label"]
            msg = flavor.fill(
                flavor.pick(flavor.COMMONS_CLAIM_LINES),
                label=row["label"],
                loot=loot,
                fine=config.COMMONS_CLAIM_FEE,
            )
            await db.add_chronicle("commons", f"{s['name']} 领取 {row['label']}：{loot}", s["id"])
            return msg

        if verb == "pulse":
            rows = await _active_spawns(conn)
            await conn.commit()
            if not rows:
                return "公共物资池空——联盟还没排期新货"
            n = sum(1 for r in rows if r["appears_at"] <= db.now())
            return f"公共池 {len(rows)} 项排期，{n} 项可领 → commons_ops scan"

    raise ValueError(f"未知 commons 指令: {command}（scan / claim id / pulse）")


async def _can_discover(conn: aiosqlite.Connection, steward_id: int) -> bool:
    day = _day_id()
    cur = await conn.execute(
        "SELECT count FROM discovery_rolls WHERE steward_id=? AND day=?",
        (steward_id, day),
    )
    row = await cur.fetchone()
    return (row[0] if row else 0) < config.DISCOVERY_DAILY_CAP


async def _mark_discover(conn: aiosqlite.Connection, steward_id: int) -> None:
    day = _day_id()
    await conn.execute(
        """
        INSERT INTO discovery_rolls (steward_id, day, count) VALUES (?,?,1)
        ON CONFLICT(steward_id, day) DO UPDATE SET count = count + 1
        """,
        (steward_id, day),
    )


async def roll_discovery(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    trigger: str,
    *,
    found: list[tuple[str, int, str]] | None = None,
) -> str | None:
    pool_cfg = DISCOVERY_LOOT.get(trigger)
    if not pool_cfg or not await _can_discover(conn, steward["id"]):
        return None

    chance = config.DISCOVERY_CHANCE.get(trigger, 0.08)
    if steward.get("mascot_trait") == "lucky":
        chance *= 1.25
    if world.current_weather() == "misty":
        chance *= 1.08
    if random.random() > chance:
        return None

    items, weights, labels = [], [], []
    for item, qty, w, _ in pool_cfg:
        items.append((item, qty))
        weights.append(w)
        labels.append(_)

    item, qty = random.choices(items, weights=weights)[0]
    idx = items.index((item, qty))
    hint = labels[idx]
    await db.add_item(conn, steward["id"], item, qty)
    await _mark_discover(conn, steward["id"])

    from . import tale as tale_mod
    tale_extra = await tale_mod.check_item_progress(conn, steward["id"], item, qty)

    iname = ITEM_NAMES.get(item, item)
    if found is not None:
        found.append((item, qty, iname))
    detail = flavor.fill(
        flavor.pick(flavor.DISCOVERY_LINES),
        hint=hint,
        item=f"{iname}（{item}）x{qty}",
    )
    label = flavor.pick(flavor.DISCOVERY_LABELS)
    result = flavor.wrap_event("good", label, detail)
    if tale_extra:
        result += f"\n\n{tale_extra}"
    return result

"""韶年望潮人 — shaonian_ops：卜卦、转运、占卜符。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import config, db, survival
from .catalog import SEA_CATCH, weighted_fish_pick
from .game import require_steward
from .shaonian_catalog import (
    ALL_FORTUNE_KEYS,
    BAD_FORTUNES,
    CHARMS,
    CHRONICLE_TAGS,
    FORTUNE_COST,
    FORTUNES,
    GOOD_FORTUNES,
    TRANSFER_COST,
    TRANSFER_FAIL,
    TRANSFER_FAIL_BAD_MULT,
    TRANSFER_OK,
    TRANSFER_SUCCESS_RATE,
    VISIT_LINE,
)


def day_id() -> int:
    return db.day_id()


def _resolve_charm_key(query: str) -> str | None:
    q = query.strip()
    ql = q.lower()
    for key, meta in CHARMS.items():
        if key == ql or meta["name"] == q:
            return key
        if ql in meta.get("aliases", ()):
            return key
    return None


async def _ensure_row(conn: aiosqlite.Connection, steward_id: int, day: int) -> dict[str, Any]:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM shaonian_daily WHERE steward_id=? AND day=?",
        (steward_id, day),
    )).fetchone()
    if row:
        return dict(row)
    await conn.execute(
        """
        INSERT INTO shaonian_daily (
            steward_id, day, fortune, fortune_casts, transfer_done,
            transfer_failed, visit_done
        ) VALUES (?,?,?,?,?,?,?)
        """,
        (steward_id, day, "", 0, 0, 0, 0),
    )
    row = await (await conn.execute(
        "SELECT * FROM shaonian_daily WHERE steward_id=? AND day=?",
        (steward_id, day),
    )).fetchone()
    return dict(row)


async def get_daily(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any]:
    return await _ensure_row(conn, steward_id, day_id())


async def has_charm(conn: aiosqlite.Connection, steward_id: int, charm_key: str) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM shaonian_charms WHERE steward_id=? AND day=? AND charm_key=?",
        (steward_id, day_id(), charm_key),
    )
    return await cur.fetchone() is not None


def roll_fortune() -> str:
    return random.choice(ALL_FORTUNE_KEYS)


def fortune_label(key: str) -> str:
    if not key:
        return "未卜"
    meta = FORTUNES.get(key, {})
    return f"{meta.get('name', key)}（{meta.get('omen', '?')}）"


async def shaonian_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "catalog"
    today = day_id()

    if verb == "visit":
        async with db.connect() as conn:
            row = await _ensure_row(conn, s["id"], today)
            note = ""
            if not row["visit_done"]:
                await conn.execute(
                    "UPDATE shaonian_daily SET visit_done=1 WHERE steward_id=? AND day=?",
                    (s["id"], today),
                )
                await survival.bump(conn, s["id"], mist_wit=2)
                note = "\n雾智 +2（今日首次拜访韶年）"
                await db.add_chronicle(
                    "shaonian",
                    f"{s['name']} 拜访滩头韶年",
                    s["id"],
                    conn=conn,
                )
                await conn.commit()
            fortune = row.get("fortune") or ""
        line = VISIT_LINE
        if fortune:
            meta = FORTUNES.get(fortune, {})
            line += f"\n今日卦：{fortune_label(fortune)} — {meta.get('hint', '')}"
        return f"韶年：{line}{note}"

    if verb == "fortune":
        async with db.connect() as conn:
            row = await _ensure_row(conn, s["id"], today)
            casts = row["fortune_casts"]
            cost = 0 if casts == 0 else FORTUNE_COST
            if cost:
                cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
                tickets = (await cur.fetchone())[0]
                if tickets < cost:
                    raise ValueError(f"再算卦需要 {cost} 票（今日已免费卜过）")
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                    (cost, s["id"]),
                )
            key = roll_fortune()
            await conn.execute(
                """
                UPDATE shaonian_daily SET fortune=?, fortune_casts=fortune_casts+1,
                    transfer_done=0, transfer_failed=0
                WHERE steward_id=? AND day=?
                """,
                (key, s["id"], today),
            )
            meta = FORTUNES[key]
            cost_note = f"（-{cost} 票）" if cost else "（今日首次免费）"
            await db.add_chronicle(
                "shaonian",
                f"{s['name']} 韶年卜得{meta['name']}",
                s["id"],
                conn=conn,
            )
            await conn.commit()
        return (
            f"韶年望潮人卜卦{cost_note}\n"
            f"「{meta['name']}」{meta['omen']} — {meta['line']}\n"
            f"今日：{meta['hint']}"
        )

    if verb == "transfer":
        async with db.connect() as conn:
            row = await _ensure_row(conn, s["id"], today)
            fortune = row.get("fortune") or ""
            if not fortune:
                raise ValueError("先 visit_ops shaonian fortune 卜今日卦象")
            if fortune not in BAD_FORTUNES:
                raise ValueError(f"当前{fortune_label(fortune)}不是凶卦，无需转运")
            if row["transfer_done"]:
                raise ValueError("今日已试过转运，不可再来")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < TRANSFER_COST:
                raise ValueError(f"转运需要 {TRANSFER_COST} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (TRANSFER_COST, s["id"]),
            )
            ok = random.random() < TRANSFER_SUCCESS_RATE
            if ok:
                new_key = random.choice(GOOD_FORTUNES)
                meta = FORTUNES[new_key]
                await conn.execute(
                    """
                    UPDATE shaonian_daily SET fortune=?, transfer_done=1, transfer_failed=0
                    WHERE steward_id=? AND day=?
                    """,
                    (new_key, s["id"], today),
                )
                await db.add_chronicle(
                    "shaonian",
                    f"{s['name']} 韶年转运得{meta['name']}",
                    s["id"],
                    conn=conn,
                )
                await conn.commit()
                return (
                    f"韶年：{TRANSFER_OK}\n"
                    f"「{meta['name']}」— {meta['line']}\n"
                    f"-{TRANSFER_COST} 票"
                )
            await conn.execute(
                """
                UPDATE shaonian_daily SET transfer_done=1, transfer_failed=1
                WHERE steward_id=? AND day=?
                """,
                (s["id"], today),
            )
            await db.add_chronicle("shaonian", f"{s['name']} 韶年转运未成", s["id"], conn=conn)
            await conn.commit()
            bad_meta = FORTUNES[fortune]
            return (
                f"韶年：{TRANSFER_FAIL}\n"
                f"仍挂「{bad_meta['name']}」；今日坏事概率 +10%\n"
                f"-{TRANSFER_COST} 票"
            )

    if verb == "buy" and len(parts) >= 2:
        charm_key = _resolve_charm_key(parts[1])
        if not charm_key:
            raise ValueError(f"未知符：{parts[1]}（visit_ops shaonian catalog 看符名）")
        meta = CHARMS[charm_key]
        price = meta["price"]
        async with db.connect() as conn:
            if await has_charm(conn, s["id"], charm_key):
                raise ValueError(f"今日已买过「{meta['name']}」，每人每日每种限购 1")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < price:
                raise ValueError(f"「{meta['name']}」需要 {price} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (price, s["id"]),
            )
            await conn.execute(
                """
                INSERT INTO shaonian_charms (steward_id, day, charm_key, purchased_at)
                VALUES (?,?,?,?)
                """,
                (s["id"], today, charm_key, db.now()),
            )
            await db.add_chronicle(
                "shaonian",
                f"{s['name']} 向韶年买{meta['name']}",
                s["id"],
                conn=conn,
            )
            await conn.commit()
        buy_line = meta["line"]
        if charm_key == "calm_sea":
            buy_line = CHARMS["calm_sea"]["line"]
        return f"韶年：{buy_line}\n「{meta['name']}」当日生效 · -{price} 票 · {meta['hint']}"

    if verb == "catalog":
        async with db.connect() as conn:
            row = await _ensure_row(conn, s["id"], today)
            charms = await (await conn.execute(
                "SELECT charm_key FROM shaonian_charms WHERE steward_id=? AND day=?",
                (s["id"], today),
            )).fetchall()
        owned = {r[0] for r in charms}
        lines = [
            "韶年望潮人 · 滩头卜卦（shaonian_ops）",
            "指令: visit · fortune · transfer · buy 符名 · catalog",
            "",
            "卦象六档（fortune 随机，transfer 仅凶卦可转吉）:",
        ]
        for key, meta in FORTUNES.items():
            lines.append(f"  {meta['name']} [{meta['omen']}] — {meta['hint']}")
        lines.append("")
        lines.append(f"再算 {FORTUNE_COST} 票/次（每日首次 fortune 免费）· 转运 {TRANSFER_COST} 票（{int(TRANSFER_SUCCESS_RATE*100)}% 成功）")
        lines.append("")
        lines.append("占卜符（当日作废，每种每日限购 1）:")
        for key, meta in CHARMS.items():
            tag = "已买" if key in owned else f"{meta['price']} 票"
            lines.append(f"  {meta['name']} — {tag} · {meta['hint']}")
        if row.get("fortune"):
            fm = FORTUNES[row["fortune"]]
            lines.append("")
            lines.append(f"你今日卦：{fortune_label(row['fortune'])} — {fm['hint']}")
            if row.get("transfer_failed"):
                lines.append("转运失败：坏事概率 +10%")
        return "\n".join(lines)

    raise ValueError(
        "未知韶年指令: " + command + "\n"
        "用法: visit_ops shaonian visit · fortune · transfer · buy 符名 · catalog"
    )


# ── 玩法挂钩 ──


async def shiye_bump_bonus(conn: aiosqlite.Connection, steward_id: int) -> float:
    row = await get_daily(conn, steward_id)
    bonus = 0.0
    if row.get("fortune") == "broke":
        bonus += 0.06
    return bonus


async def shiye_kind_weights(
    conn: aiosqlite.Connection,
    steward_id: int,
    weights: dict[str, int],
) -> dict[str, int]:
    row = await get_daily(conn, steward_id)
    if row.get("fortune") == "broke":
        weights["thief"] = weights.get("thief", 0) + 15
        weights["extort"] = weights.get("extort", 0) + 6
    if row.get("transfer_failed"):
        weights["thief"] = weights.get("thief", 0) + 5
        weights["extort"] = weights.get("extort", 0) + 5
    return weights


async def event_bad_share_bonus(conn: aiosqlite.Connection, steward_id: int) -> float:
    row = await get_daily(conn, steward_id)
    if row.get("transfer_failed"):
        return TRANSFER_FAIL_BAD_MULT
    return 0.0


async def naval_bad_bias(conn: aiosqlite.Connection, steward_id: int) -> float:
    row = await get_daily(conn, steward_id)
    bias = 0.0
    if row.get("fortune") == "rough_sea":
        bias += 0.14
    return bias


async def skip_bad_sea(conn: aiosqlite.Connection, steward_id: int) -> bool:
    return await has_charm(conn, steward_id, "calm_sea")


async def fishing_no_empty(conn: aiosqlite.Connection, steward_id: int) -> bool:
    return await has_charm(conn, steward_id, "fish_charm")


async def dove_protected(conn: aiosqlite.Connection, steward_id: int) -> bool:
    return await has_charm(conn, steward_id, "field_charm")


async def beach_double(conn: aiosqlite.Connection, steward_id: int) -> bool:
    return await has_charm(conn, steward_id, "beach_charm")


async def harvest_bonus_roll(conn: aiosqlite.Connection, steward_id: int) -> bool:
    row = await get_daily(conn, steward_id)
    return row.get("fortune") == "harvest" and random.random() < 0.20


async def rapport_multiplier(conn: aiosqlite.Connection, steward_id: int) -> float:
    row = await get_daily(conn, steward_id)
    if row.get("fortune") == "peach":
        return 2.0
    return 1.0


def pick_fish_with_fortune(
    tide: str,
    rarity_cap: int,
    fortune_key: str | None,
    *,
    allow_cast_only: bool = False,
) -> str:
    if fortune_key != "fish_catch":
        return weighted_fish_pick(
            tide=tide, rarity_cap=rarity_cap, allow_cast_only=allow_cast_only
        )
    pool: list[tuple[str, int]] = []
    for key, meta in SEA_CATCH.items():
        if meta.get("cast_only") and not allow_cast_only:
            continue
        if tide and tide not in meta.get("tides", []):
            continue
        if rarity_cap and meta.get("rarity", 1) > rarity_cap:
            continue
        rarity = meta.get("rarity", 1)
        weight = max(1, 7 - rarity)
        if rarity >= 3:
            weight *= 2
        pool.append((key, weight))
    if not pool:
        return weighted_fish_pick(
            tide=tide, rarity_cap=rarity_cap, allow_cast_only=allow_cast_only
        )
    keys, weights = zip(*pool)
    return random.choices(keys, weights=weights, k=1)[0]

"""物品履历。行囊仍按名叠放；有来历的东西另记一本，不另造地点。"""
from __future__ import annotations

import json
from typing import Any

from . import db
from .catalog import (
    GOLD_FIVE_EXTRA,
    GOLD_THREE,
    ITEM_NAMES,
    QUARRY_VEINS,
    SEA_CATCH,
    item_label,
)

MAX_LINES = 12
MAX_LEN = 80
MAX_LIVING = 24

CLAIM_POETRY = {
    1: "东脉",
    2: "西脉",
    3: "南窝",
    4: "北缝",
    5: "潮台",
    6: "雾台",
    7: "夜台",
}

NOTABLE_KEYS = {
    "tide_vow_ring",
    "tide_vow_sand",
    "betroth_ring",
    "betroth_shell",
    "betroth_bloom",
    "quarry_gold_sand",
    "quarry_fog",
    "quarry_fog_lead",
    "quarry_marrow_raw",
    "quarry_marrow",
    "quarry_tide",
    "quarry_tide_stone",
    "craft_fog_sinker",
    "fit_tide_weight",
    "fit_marrow_sieve",
    "fit_copper_chime",
    "fit_boat_rib",
    "sea_glass",
}
NOTABLE_KEYS.update(GOLD_THREE)
NOTABLE_KEYS.update(GOLD_FIVE_EXTRA)
NOTABLE_KEYS.update({
    "craft_gyotaku",
    "craft_boat_model",
    "craft_shell_case",
    "craft_ore_case",
    "craft_bottle_rack",
    "craft_flower_book",
    "craft_old_photo",
    "craft_tide_stamp",
    "craft_npc_sign",
    "wreck_scrap",
    "craft_relic",
    "craft_fish_bone",
    "craft_seed_box",
    "proc_black_salt",
    "drink_fog_port",
})

NOTABLE_PREFIXES = (
    "craft_gyotaku",
    "craft_boat_model",
    "craft_relic",
    "craft_old_photo",
    "craft_tide_stamp",
    "craft_npc_sign",
    "craft_fish_bone",
    "craft_seed_box",
    "relic_",
    "wine_",
)


def calendar_phrase(ts: int | None = None) -> str:
    return f"潮汐历第 {int(db.day_id(ts))} 日"


def claim_place(slot: int, vein_key: str = "") -> str:
    poetry = CLAIM_POETRY.get(int(slot) or 0, f"坑{int(slot) or 0}")
    vein = ""
    if vein_key and vein_key in QUARRY_VEINS:
        vein = str(QUARRY_VEINS[vein_key].get("name") or "")
    if vein:
        return f"盐风崖{poetry}{vein}"
    return f"盐风崖{poetry}"


def is_notable(item: str) -> bool:
    key = str(item or "")
    if not key:
        return False
    if key in NOTABLE_KEYS:
        return True
    name = ITEM_NAMES.get(key) or ""
    if "戒" in name or key.endswith("_ring"):
        return True
    if key.startswith("fish_"):
        meta = SEA_CATCH.get(key[5:]) or {}
        return int(meta.get("rarity") or 0) >= 4
    if key.startswith("shell_shine_"):
        return True
    return False


def _clip(line: str) -> str:
    return (line or "").strip()[:MAX_LEN]


def _dump(lines: list[str]) -> str:
    clean = [_clip(x) for x in lines if _clip(x)]
    return json.dumps(clean[:MAX_LINES], ensure_ascii=False)


def _load(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [_clip(str(x)) for x in raw if _clip(str(x))]
    text = str(raw or "")
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [_clip(text)]
    if isinstance(data, list):
        return [_clip(str(x)) for x in data if _clip(str(x))]
    return [_clip(text)]


def _cell(row: Any, idx: int, key: str):
    if row is None:
        return None
    if hasattr(row, "keys"):
        return row[key]
    return row[idx]


def origin_snippet(lines: list[str], item: str) -> str:
    label = item_label(item)
    if lines:
        first = lines[0]
        if label[:2] in first or item_label(item).rstrip(" ") in first:
            return first
        return f"{label}：{first}"
    return ""


def format_block(lines: list[str], indent: str = "    ") -> str:
    return "\n".join(f"{indent}{ln}" for ln in lines if ln)


async def birth(
    conn,
    owner_id: int,
    item: str,
    lines: list[str],
    *,
    qty: int = 1,
) -> int:
    if qty <= 0 or not is_notable(item):
        return 0
    owner_id = int(owner_id)
    have = await (await conn.execute(
        "SELECT COUNT(*) FROM item_ledgers WHERE owner_id=? AND item=? AND alive=1",
        (owner_id, item),
    )).fetchone()
    living = int((have[0] if have else 0) or 0)
    n = min(int(qty), max(0, MAX_LIVING - living))
    if n <= 0:
        return 0
    now = db.now()
    blob = _dump(lines)
    for _ in range(n):
        await conn.execute(
            """
            INSERT INTO item_ledgers (item, owner_id, lines_json, born_at, updated_at, alive)
            VALUES (?,?,?,?,?,1)
            """,
            (item, owner_id, blob, now, now),
        )
    return n


async def note_gain(conn, owner_id: int, item: str, qty: int, *lines: str) -> int:
    return await birth(conn, owner_id, item, list(lines), qty=qty)


async def birth_story(
    conn,
    owner_id: int,
    item: str,
    lines: list[str],
    *,
    qty: int = 1,
) -> int:
    """种子血统等：强制记履历（不受 is_notable 限制）。"""
    if qty <= 0 or not (item or "").strip():
        return 0
    owner_id = int(owner_id)
    have = await (await conn.execute(
        "SELECT COUNT(*) FROM item_ledgers WHERE owner_id=? AND item=? AND alive=1",
        (owner_id, item),
    )).fetchone()
    living = int((have[0] if have else 0) or 0)
    n = min(int(qty), max(0, MAX_LIVING - living))
    if n <= 0:
        return 0
    now = db.now()
    blob = _dump(lines)
    for _ in range(n):
        await conn.execute(
            """
            INSERT INTO item_ledgers (item, owner_id, lines_json, born_at, updated_at, alive)
            VALUES (?,?,?,?,?,1)
            """,
            (item, owner_id, blob, now, now),
        )
    return n


async def _living_rows(conn, owner_id: int, item: str, qty: int):
    return await (await conn.execute(
        """
        SELECT id, lines_json FROM item_ledgers
        WHERE owner_id=? AND item=? AND alive=1
        ORDER BY id ASC
        LIMIT ?
        """,
        (int(owner_id), item, max(0, int(qty))),
    )).fetchall()


async def consume(
    conn,
    owner_id: int,
    item: str,
    qty: int,
    extra: str = "",
) -> list[list[str]]:
    if qty <= 0 or not is_notable(item):
        return []
    rows = await _living_rows(conn, owner_id, item, qty)
    now = db.now()
    out: list[list[str]] = []
    for row in rows:
        rid = int(_cell(row, 0, "id"))
        lines = _load(_cell(row, 1, "lines_json"))
        if extra:
            lines = (lines + [_clip(extra)])[:MAX_LINES]
            await conn.execute(
                "UPDATE item_ledgers SET lines_json=?, updated_at=?, alive=0 WHERE id=?",
                (_dump(lines), now, rid),
            )
        else:
            await conn.execute(
                "UPDATE item_ledgers SET updated_at=?, alive=0 WHERE id=?",
                (now, rid),
            )
        out.append(lines)
    return out


async def transfer(
    conn,
    from_id: int,
    to_id: int,
    item: str,
    qty: int,
    extra: str = "",
) -> int:
    if qty <= 0 or not is_notable(item) or int(from_id) == int(to_id):
        return 0
    rows = await _living_rows(conn, from_id, item, qty)
    now = db.now()
    moved = 0
    for row in rows:
        rid = int(_cell(row, 0, "id"))
        lines = _load(_cell(row, 1, "lines_json"))
        if extra:
            lines = (lines + [_clip(extra)])[:MAX_LINES]
        await conn.execute(
            "UPDATE item_ledgers SET owner_id=?, lines_json=?, updated_at=? WHERE id=?",
            (int(to_id), _dump(lines), now, rid),
        )
        moved += 1
    return moved


async def preview_map(conn, owner_id: int) -> dict[str, list[str]]:
    rows = await (await conn.execute(
        """
        SELECT item, lines_json FROM item_ledgers
        WHERE owner_id=? AND alive=1
        ORDER BY id ASC
        """,
        (int(owner_id),),
    )).fetchall()
    out: dict[str, list[str]] = {}
    for row in rows:
        item = str(_cell(row, 0, "item") or "")
        if item and item not in out:
            out[item] = _load(_cell(row, 1, "lines_json"))
    return out


async def stories_for(conn, owner_id: int, item: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT id, item, lines_json FROM item_ledgers
        WHERE owner_id=? AND alive=1
    """
    args: list[Any] = [int(owner_id)]
    if item:
        sql += " AND item=?"
        args.append(item)
    sql += " ORDER BY id ASC"
    rows = await (await conn.execute(sql, args)).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append({
            "id": int(_cell(row, 0, "id")),
            "item": str(_cell(row, 1, "item") or ""),
            "lines": _load(_cell(row, 2, "lines_json")),
        })
    return out


async def recent_lines(conn, *, since: int, limit: int = 4) -> list[str]:
    rows = await (await conn.execute(
        """
        SELECT item, lines_json FROM item_ledgers
        WHERE updated_at>=?
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(since), int(limit)),
    )).fetchall()
    out: list[str] = []
    for row in rows:
        item = str(_cell(row, 0, "item") or "")
        lines = _load(_cell(row, 1, "lines_json"))
        if not lines:
            continue
        bit = " / ".join(lines[:3])
        label = item_label(item)
        if label not in bit:
            bit = f"{label} · {bit}"
        out.append(bit[:120])
    return out


def attach_stock(stock: list[dict[str, Any]], previews: dict[str, list[str]]) -> list[dict[str, Any]]:
    out = []
    for row in stock:
        item = str(row.get("item") or "")
        lines = previews.get(item) or []
        if lines:
            out.append({**row, "story": lines, "story_text": "\n".join(lines)})
        else:
            out.append(row)
    return out

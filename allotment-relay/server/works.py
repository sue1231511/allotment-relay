"""岛级公共工程。全服一起填料，不另开公会。"""
from __future__ import annotations

import json
from typing import Any

from . import db
from .catalog import item_label, resolve_item_key

BONUS_SECONDS = 7 * 86400

PROJECTS: list[dict[str, Any]] = [
    {
        "slug": "dock_repair",
        "name": "旧码头翻修",
        "blurb": "木板泡烂了。捐岸木、铜钉或票。修完出航稳几天。",
        "need": {"craft_timber": 24, "craft_copper_nails": 12, "tickets": 400},
        "bonus": "dock",
        "place": "harbor",
        "done": "码头的新木还渗着盐。出航时船帮不那么响。",
    },
    {
        "slug": "lighthouse_lens",
        "name": "灯塔换透镜",
        "blurb": "旧镜起雾。捐岸木、铜钉或票。换完塔里的茶更烫。",
        "need": {"craft_timber": 16, "craft_copper_nails": 8, "tickets": 360},
        "bonus": "lens",
        "place": "lighthouse",
        "done": "透镜换过了。光更白，茶更烫。",
    },
    {
        "slug": "greenhouse_reopen",
        "name": "重开旧温室",
        "blurb": "骨架还在。捐岸木、铜钉或票。修好只是岛还记得这儿能种。",
        "need": {"craft_timber": 20, "craft_copper_nails": 10, "tickets": 320},
        "bonus": "shed",
        "place": "plaza",
        "done": "旧温室的玻璃擦过了。里面空着，但不再漏风。",
    },
    {
        "slug": "ting_tiles",
        "name": "听潮亭补瓦",
        "blurb": "瓦缝漏潮声。捐岸木、铜钉或票。补完木牌不那么潮。",
        "need": {"craft_timber": 12, "craft_copper_nails": 16, "tickets": 280},
        "bonus": "ting",
        "place": "ting",
        "done": "亭上新瓦还反光。钉的字干得慢一点。",
    },
    {
        "slug": "drain_works",
        "name": "岸下排水",
        "blurb": "井口返潮。捐岸木、铜钉或票。修完潮压缓几天。",
        "need": {"craft_timber": 18, "craft_copper_nails": 14, "tickets": 360},
        "bonus": "drain",
        "place": "plaza",
        "done": "排水渠通了。井口不那么咸。",
    },
]
PROJECT_BY_SLUG = {p["slug"]: p for p in PROJECTS}
MATTER = {"craft_timber", "craft_copper_nails"}


def _need(meta: dict[str, Any]) -> dict[str, int]:
    return {k: int(v) for k, v in (meta.get("need") or {}).items()}


def _have(raw: str | None) -> dict[str, int]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, int] = {}
    for key, val in data.items():
        try:
            out[str(key)] = max(0, int(val))
        except (TypeError, ValueError):
            continue
    return out


def _progress_line(meta: dict[str, Any], have: dict[str, int]) -> str:
    bits = []
    for key, need in _need(meta).items():
        got = int(have.get(key) or 0)
        label = "工分票" if key == "tickets" else item_label(key)
        bits.append(f"{label} {got}/{need}")
    return " · ".join(bits)


def _view(row: dict[str, Any]) -> dict[str, Any]:
    meta = PROJECT_BY_SLUG.get(row["slug"]) or PROJECTS[0]
    have = _have(row.get("have_json"))
    need = _need(meta)
    open_now = row.get("status") == "open"
    bonus_on = int(row.get("bonus_until") or 0) > db.now() and not open_now
    headline = (
        f"岸上工程「{meta['name']}」：{_progress_line(meta, have)}"
        if open_now
        else (
            f"「{meta['name']}」收工了。{meta['done']}"
            if bonus_on
            else f"上一期「{meta['name']}」过了。下一期还没写上墙。"
        )
    )
    return {
        "id": int(row["id"]),
        "slug": meta["slug"],
        "name": meta["name"],
        "blurb": meta["blurb"],
        "done": meta["done"],
        "bonus": meta["bonus"],
        "place": meta["place"],
        "need": need,
        "have": have,
        "open": open_now,
        "bonus_on": bonus_on,
        "headline": headline,
        "progress": _progress_line(meta, have),
    }


def _next_slug(prev: str | None) -> str:
    if not prev or prev not in PROJECT_BY_SLUG:
        return PROJECTS[db.week_id() // 4 % len(PROJECTS)]["slug"]
    idx = next((i for i, p in enumerate(PROJECTS) if p["slug"] == prev), -1)
    return PROJECTS[(idx + 1) % len(PROJECTS)]["slug"]


def _row(row) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    keys = ("id", "slug", "opened_at", "status", "have_json", "completed_at", "bonus_until")
    return {k: row[i] for i, k in enumerate(keys)}


async def ensure(conn) -> dict[str, Any]:
    row = await (await conn.execute(
        """
        SELECT * FROM island_works
        WHERE status='open'
        ORDER BY id DESC LIMIT 1
        """
    )).fetchone()
    if row:
        return _row(row)
    last = await (await conn.execute(
        "SELECT * FROM island_works ORDER BY id DESC LIMIT 1"
    )).fetchone()
    last_d = _row(last)
    if last_d and int(last_d.get("bonus_until") or 0) > db.now():
        return last_d
    slug = _next_slug(last_d["slug"] if last_d else None)
    cur = await conn.execute(
        """
        INSERT INTO island_works (slug, opened_at, status, have_json, completed_at, bonus_until)
        VALUES (?,?, 'open', '{}', 0, 0)
        """,
        (slug, db.now()),
    )
    row = await (await conn.execute(
        "SELECT * FROM island_works WHERE id=?", (cur.lastrowid,)
    )).fetchone()
    return _row(row)


async def snapshot(conn) -> dict[str, Any]:
    return _view(await ensure(conn))


async def active_bonus(conn, key: str) -> bool:
    row = await (await conn.execute(
        """
        SELECT slug, bonus_until, status FROM island_works
        WHERE status='done' AND bonus_until>?
        ORDER BY id DESC LIMIT 1
        """,
        (db.now(),),
    )).fetchone()
    if not row:
        return False
    meta = PROJECT_BY_SLUG.get(row[0]) or {}
    return meta.get("bonus") == key


def _parse_gift(raw: str) -> tuple[str, int]:
    parts = (raw or "").strip().split()
    if not parts:
        raise ValueError("用法：visit_ops 潮生会 工程 捐 岸木 10 · 工程 捐 铜钉 4 · 工程 捐 50")
    if len(parts) == 1 and parts[0].isdigit():
        return "tickets", int(parts[0])
    if parts[0] in ("票", "工分票", "tickets") and len(parts) >= 2 and parts[1].isdigit():
        return "tickets", int(parts[1])
    if parts[-1].isdigit():
        qty = int(parts[-1])
        token = " ".join(parts[:-1])
    else:
        qty = 1
        token = " ".join(parts)
    if token in ("票", "工分票", "tickets"):
        return "tickets", qty
    key = resolve_item_key(token) or token
    if key not in MATTER:
        raise ValueError("这期只要岸木、铜钉或票。不是潮汐基金，也不是公仓捐甘蓝。")
    if qty < 1:
        raise ValueError("至少捐 1。")
    return key, qty


async def donate(key_id: int, raw: str) -> str:
    from .game import require_steward
    from . import traces as traces_mod
    from . import tax as tax_mod

    s = await require_steward(key_id, exempt_duty=True)
    item, qty = _parse_gift(raw)
    async with db.connect() as conn:
        conn.row_factory = __import__("aiosqlite").Row
        row = await ensure(conn)
        view = _view(dict(row))
        if not view["open"]:
            raise ValueError(f"「{view['name']}」已经收工。{view['done']}")
        need = view["need"]
        have = dict(view["have"])
        room = max(0, int(need.get(item) or 0) - int(have.get(item) or 0))
        if room <= 0:
            label = "工分票" if item == "tickets" else item_label(item)
            raise ValueError(f"{label}这期已经够了。看看还缺什么：{view['progress']}")
        qty = min(qty, room)
        if item == "tickets":
            pocket = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (s["id"],)
            )).fetchone())[0] or 0)
            if pocket < qty:
                raise ValueError(f"口袋 {pocket}，捐不了 {qty} 票。")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?", (qty, s["id"])
            )
            await tax_mod.record_life_spend(conn, s["id"], qty, "works")
        else:
            if not await db.take_item(conn, s["id"], item, qty):
                raise ValueError(f"行囊没有足够的{item_label(item)}。")
        have[item] = int(have.get(item) or 0) + qty
        await conn.execute(
            "UPDATE island_works SET have_json=? WHERE id=?",
            (json.dumps(have, ensure_ascii=False), view["id"]),
        )
        await conn.execute(
            """
            INSERT INTO island_work_gifts (work_id, steward_id, item, qty, created_at)
            VALUES (?,?,?,?,?)
            """,
            (view["id"], s["id"], item, qty, db.now()),
        )
        done = all(int(have.get(k) or 0) >= int(n) for k, n in need.items())
        extra = ""
        if done:
            until = db.now() + BONUS_SECONDS
            await conn.execute(
                """
                UPDATE island_works
                SET status='done', completed_at=?, bonus_until=?
                WHERE id=?
                """,
                (db.now(), until, view["id"]),
            )
            await traces_mod.leave(conn, view["place"], "works", view["done"], 0)
            await db.add_chronicle(
                "works",
                f"{s['name']} 把「{view['name']}」最后一笔填上了",
                s["id"],
                conn=conn,
            )
            extra = f"\n收工。{view['done']}"
        else:
            await db.add_chronicle(
                "works",
                f"{s['name']} 向「{view['name']}」捐了{item_label(item) if item != 'tickets' else str(qty)+'票'}",
                s["id"],
                conn=conn,
            )
        await conn.commit()
    label = f"{qty} 票" if item == "tickets" else f"{item_label(item)}×{qty}"
    left = _view({**dict(row), "have_json": json.dumps(have, ensure_ascii=False), "status": "done" if done else "open"})
    return f"{s['name']} 给「{view['name']}」捐了 {label}。{left['progress']}{extra}"


async def status_text(key_id: int | None = None) -> str:
    from .game import require_steward

    if key_id is not None:
        await require_steward(key_id, exempt_duty=True)
    async with db.connect() as conn:
        view = await snapshot(conn)
        await conn.commit()
    lines = [
        f"岸上工程 · {view['name']}",
        view["blurb"],
        view["progress"],
        "不是潮汐基金（基金 捐 50 是均贫富），也不是公仓（alliance_ops donate 甘蓝）。",
        "捐：visit_ops 潮生会 工程 捐 岸木 10 · 工程 捐 铜钉 4 · 工程 捐 50",
        "人类 /island 总览点潮生会，点一下看会厅，工程栏能捐。",
    ]
    if not view["open"]:
        lines.append(view["done"])
    return "\n".join(lines)

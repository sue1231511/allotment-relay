"""岛民留下的痕迹。不是装扮系统，地点会记住谁来过。"""
from __future__ import annotations

from typing import Any

from . import db

PLACES = ("lighthouse", "bar", "eatery", "lianli", "harbor", "ting", "plaza")


async def leave(
    conn,
    place: str,
    kind: str,
    text: str,
    steward_id: int = 0,
) -> bool:
    place = (place or "").strip()
    kind = (kind or "").strip()[:32]
    text = (text or "").strip()[:80]
    if place not in PLACES or not kind or not text:
        return False
    cur = await conn.execute(
        """
        INSERT OR IGNORE INTO island_traces (place, kind, steward_id, text, created_at)
        VALUES (?,?,?,?,?)
        """,
        (place, kind, int(steward_id or 0), text, db.now()),
    )
    return int(cur.rowcount or 0) > 0


async def lines_for(conn, place: str, *, limit: int = 3) -> list[str]:
    rows = await (await conn.execute(
        """
        SELECT text FROM island_traces
        WHERE place=?
        ORDER BY id DESC
        LIMIT ?
        """,
        (place, int(limit)),
    )).fetchall()
    return [r[0] for r in rows if r and r[0]]


async def blend(conn, place: str, line: str) -> str:
    bits = await lines_for(conn, place, limit=1)
    if not bits:
        return line
    base = (line or "").rstrip()
    extra = bits[0]
    if extra in base:
        return base
    return f"{base} {extra}"


async def maybe_watch_mark(conn, s: dict[str, Any]) -> None:
    row = await (await conn.execute(
        """
        SELECT COUNT(*) FROM chronicle
        WHERE actor_id=? AND action='buxing' AND text LIKE '%在灯塔守夜%'
        """,
        (s["id"],),
    )).fetchone()
    if int(row[0] or 0) < 7:
        return
    await leave(
        conn,
        "lighthouse",
        "graffiti",
        f"塔门内侧有人用指甲刻了「{s['name']}」。不醒没擦。",
        s["id"],
    )


async def maybe_song_mark(conn, s: dict[str, Any], title: str) -> None:
    row = await (await conn.execute(
        """
        SELECT COUNT(*) FROM chronicle
        WHERE actor_id=? AND action='bar_song'
        """,
        (s["id"],),
    )).fetchone()
    if int(row[0] or 0) < 5:
        return
    song = (title or "那一首").strip()[:16]
    await leave(
        conn,
        "bar",
        "poster",
        f"吧台侧墙多了一张手写海报，写着{s['name']}点过《{song}》。",
        s["id"],
    )


async def maybe_wedding_mark(conn, s: dict[str, Any]) -> None:
    await leave(
        conn,
        "lianli",
        "certificate",
        f"旧婚书匣里多了一张，封面写着「{s['name']}」。墨还没干透。",
        s["id"],
    )


async def maybe_eatery_mark(conn, s: dict[str, Any], label: str) -> None:
    name = (label or f"{s['name']}的馆").strip()[:24]
    await leave(
        conn,
        "eatery",
        "menu",
        f"桌角压着一份油渍菜单，抬头是「{name}」。",
        s["id"],
    )

"""日常心意：同一账号里 AI ↔ 人类互送 emoji 小礼物（只扣工分票，不进行囊）。"""
from __future__ import annotations

import re
from typing import Any

import aiosqlite

from . import db

HELP = """heart_ops — 日常心意（AI↔人类小礼物；只花工分票，不进行囊）
空 command / help — 本说明 + 今日剩余次数 + 待拆卡片
送 🧋 | 午后奶茶 | 窗边 | 12 | 记得喝水
  AI 每天最多 3 次。格式：送 emoji | 名字 | 场景 | 票数 [| 留言]
  emoji 必须用预设；票数 5～88；名字/场景 AI 自拟。
列表 / 册 — 待拆与心意册
看 12 — 看一张卡片
人类在上手页 / 手机地图拆卡、回一句、回礼（各每天最多 3 次）。
预设 emoji：🧋 🍰 💐 🐚 ☕ 🍡 🎀 🌙 ⭐ 🌊 🍵 🍪 🍀 🍬 🫧
容易搞混：tote_ops gift 是点名送物品/票即时进对方行囊；聊天室红包走 lounge_ops。"""

EMOJIS = (
    "🧋", "🍰", "💐", "🐚", "☕", "🍡", "🎀", "🌙", "⭐", "🌊",
    "🍵", "🍪", "🍀", "🍬", "🫧",
)
MIN_TICKETS = 5
MAX_TICKETS = 88
DAILY_LIMIT = 3
TITLE_MAX = 24
SCENE_MAX = 32
NOTE_MAX = 120
REPLY_MAX = 120

_PIPE = re.compile(r"\s*\|\s*")


async def _require_enrolled(key_id: int) -> dict[str, Any]:
    s = await db.get_steward_by_key_id(key_id)
    if not s or not s.get("enrolled"):
        raise ValueError("请先 steward_ops enroll 登记管理员身份")
    return s


def _emoji_ok(raw: str) -> str:
    e = (raw or "").strip()
    if e not in EMOJIS:
        raise ValueError("外观请用固定 emoji 预设之一：" + " ".join(EMOJIS))
    return e


def _tickets_ok(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError as exc:
        raise ValueError(f"票数要写数字，{MIN_TICKETS}～{MAX_TICKETS}") from exc
    if n < MIN_TICKETS or n > MAX_TICKETS:
        raise ValueError(f"票数须在 {MIN_TICKETS}～{MAX_TICKETS}")
    return n


def _clip(text: str, n: int, label: str) -> str:
    t = (text or "").strip()
    if not t:
        raise ValueError(f"{label}不能空")
    if len(t) > n:
        raise ValueError(f"{label}最多 {n} 字")
    return t


def _view(row: dict[str, Any]) -> dict[str, Any]:
    role = row["from_role"]
    return {
        "id": int(row["id"]),
        "from_role": role,
        "from_label": "岛民" if role == "ai" else "你",
        "to_label": "你" if role == "ai" else "岛民",
        "emoji": row["emoji"],
        "title": row["title"],
        "scene": row["scene"],
        "note": row.get("note") or "",
        "tickets": int(row["tickets"]),
        "status": row["status"],
        "status_label": {
            "pending": "待拆",
            "opened": "已拆",
            "kept": "已收好",
        }.get(row["status"], row["status"]),
        "reply_text": row.get("reply_text") or "",
        "created_at": int(row["created_at"]),
        "opened_at": int(row["opened_at"] or 0) or None,
        "replied_at": int(row["replied_at"] or 0) or None,
        "day_id": int(row["day_id"]),
    }


async def _count_sends(conn: aiosqlite.Connection, sid: int, role: str, day: int) -> int:
    row = await (
        await conn.execute(
            "SELECT COUNT(*) FROM heart_gifts WHERE steward_id=? AND from_role=? AND day_id=?",
            (sid, role, day),
        )
    ).fetchone()
    return int(row[0])


async def _count_replies(conn: aiosqlite.Connection, sid: int, day: int) -> int:
    row = await (
        await conn.execute(
            """
            SELECT COUNT(*) FROM heart_gifts
            WHERE steward_id=? AND from_role='ai' AND reply_text!='' AND reply_day_id=?
            """,
            (sid, day),
        )
    ).fetchone()
    return int(row[0])


async def _quota_lines(conn: aiosqlite.Connection, sid: int) -> list[str]:
    day = db.day_id()
    ai_left = DAILY_LIMIT - await _count_sends(conn, sid, "ai", day)
    hu_left = DAILY_LIMIT - await _count_sends(conn, sid, "human", day)
    reply_left = DAILY_LIMIT - await _count_replies(conn, sid, day)
    return [
        f"今日剩余：岛民送心意 {max(0, ai_left)}/{DAILY_LIMIT} · 人类回礼 {max(0, hu_left)}/{DAILY_LIMIT} · 回一句 {max(0, reply_left)}/{DAILY_LIMIT}",
        "换班（游戏日 UTC 午夜）刷新次数。",
    ]


async def snapshot(sid: int) -> dict[str, Any]:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        day = db.day_id()
        rows = [
            dict(r)
            for r in await (
                await conn.execute(
                    "SELECT * FROM heart_gifts WHERE steward_id=? ORDER BY id DESC LIMIT 40",
                    (sid,),
                )
            ).fetchall()
        ]
        pending = [_view(r) for r in rows if r["status"] == "pending"]
        album = [_view(r) for r in rows if r["status"] in ("opened", "kept")]
        return {
            "ok": True,
            "pending": pending,
            "album": album,
            "emojis": list(EMOJIS),
            "limits": {
                "ai_send_left": max(0, DAILY_LIMIT - await _count_sends(conn, sid, "ai", day)),
                "human_send_left": max(0, DAILY_LIMIT - await _count_sends(conn, sid, "human", day)),
                "reply_left": max(0, DAILY_LIMIT - await _count_replies(conn, sid, day)),
                "min_tickets": MIN_TICKETS,
                "max_tickets": MAX_TICKETS,
            },
        }


async def _send(
    sid: int,
    *,
    role: str,
    emoji: str,
    title: str,
    scene: str,
    tickets: int,
    note: str,
) -> dict[str, Any]:
    day = db.day_id()
    now = db.now()
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("BEGIN IMMEDIATE")
        used = await _count_sends(conn, sid, role, day)
        if used >= DAILY_LIMIT:
            who = "岛民" if role == "ai" else "你"
            raise ValueError(f"{who}今天已送满 {DAILY_LIMIT} 次心意，换班后再送。")
        cur = await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=? AND tickets>=?",
            (tickets, sid, tickets),
        )
        if cur.rowcount != 1:
            raise ValueError(f"工分票不够，这次需要 {tickets} 票。")
        cur = await conn.execute(
            """
            INSERT INTO heart_gifts (
                steward_id, from_role, emoji, title, scene, note, tickets,
                status, reply_text, created_at, opened_at, replied_at, day_id, reply_day_id
            ) VALUES (?,?,?,?,?,?,?,'pending','',?,0,0,?,0)
            """,
            (sid, role, emoji, title, scene, note, tickets, now, day),
        )
        gid = int(cur.lastrowid)
        await conn.commit()
        row = await (
            await conn.execute("SELECT * FROM heart_gifts WHERE id=?", (gid,))
        ).fetchone()
    return _view(dict(row))


async def send_as_ai(key_id: int, rest: str) -> str:
    s = await _require_enrolled(key_id)
    parts = [p for p in _PIPE.split(rest.strip()) if p != ""]
    if len(parts) < 4:
        return (
            "格式：heart_ops 送 emoji | 名字 | 场景 | 票数 [| 留言]\n"
            f"例：送 🧋 | 午后奶茶 | 窗边 | 12 | 记得按时喝水\n预设：{' '.join(EMOJIS)}"
        )
    emoji = _emoji_ok(parts[0])
    title = _clip(parts[1], TITLE_MAX, "名字")
    scene = _clip(parts[2], SCENE_MAX, "场景")
    tickets = _tickets_ok(parts[3])
    note = ""
    if len(parts) >= 5:
        note = "|".join(parts[4:]).strip()
        if len(note) > NOTE_MAX:
            raise ValueError(f"留言最多 {NOTE_MAX} 字")
    view = await _send(
        int(s["id"]),
        role="ai",
        emoji=emoji,
        title=title,
        scene=scene,
        tickets=tickets,
        note=note,
    )
    return (
        f"已送出心意 #{view['id']} {view['emoji']}「{view['title']}」·{view['scene']}（{view['tickets']} 票）。\n"
        "请人类在上手页或手机地图拆开。不是 tote_ops gift，也不会进行囊。"
    )


async def send_as_human(
    sid: int,
    *,
    emoji: str,
    title: str,
    scene: str,
    tickets: int,
    note: str = "",
) -> dict[str, Any]:
    return await _send(
        sid,
        role="human",
        emoji=_emoji_ok(emoji),
        title=_clip(title, TITLE_MAX, "名字"),
        scene=_clip(scene, SCENE_MAX, "场景"),
        tickets=_tickets_ok(str(tickets)),
        note=(note or "").strip()[:NOTE_MAX],
    )


async def _get(conn: aiosqlite.Connection, sid: int, gid: int) -> dict[str, Any]:
    conn.row_factory = aiosqlite.Row
    row = await (
        await conn.execute(
            "SELECT * FROM heart_gifts WHERE id=? AND steward_id=?",
            (gid, sid),
        )
    ).fetchone()
    if not row:
        raise ValueError("找不到这张心意卡。")
    return dict(row)


async def open_card(sid: int, gid: int) -> dict[str, Any]:
    async with db.connect() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        row = await _get(conn, sid, gid)
        if row["status"] == "pending":
            now = db.now()
            await conn.execute(
                "UPDATE heart_gifts SET status='opened', opened_at=? WHERE id=?",
                (now, gid),
            )
            row["status"] = "opened"
            row["opened_at"] = now
        await conn.commit()
    return _view(row)


async def keep_card(sid: int, gid: int) -> dict[str, Any]:
    async with db.connect() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        row = await _get(conn, sid, gid)
        now = db.now()
        if row["status"] == "pending":
            await conn.execute(
                "UPDATE heart_gifts SET status='kept', opened_at=? WHERE id=?",
                (now, gid),
            )
        else:
            await conn.execute(
                "UPDATE heart_gifts SET status='kept' WHERE id=?",
                (gid,),
            )
        await conn.commit()
        row = await _get(conn, sid, gid)
    return _view(row)


async def reply_card(sid: int, gid: int, text: str) -> dict[str, Any]:
    body = _clip(text, REPLY_MAX, "回一句")
    day = db.day_id()
    async with db.connect() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        row = await _get(conn, sid, gid)
        if row["from_role"] != "ai":
            raise ValueError("回一句是写给岛民送来的卡；回礼请点回礼。")
        if row.get("reply_text"):
            raise ValueError("这张卡已经回过一句了。")
        used = await _count_replies(conn, sid, day)
        if used >= DAILY_LIMIT:
            raise ValueError(f"今天已回满 {DAILY_LIMIT} 句，换班后再写。")
        now = db.now()
        status = "kept" if row["status"] != "pending" else "opened"
        opened_at = int(row["opened_at"] or 0) or now
        await conn.execute(
            """
            UPDATE heart_gifts
            SET reply_text=?, reply_day_id=?, replied_at=?, status=?, opened_at=?
            WHERE id=?
            """,
            (body, day, now, status, opened_at, gid),
        )
        await conn.commit()
        row = await _get(conn, sid, gid)
    return _view(row)


async def _quota_via_sid(sid: int) -> list[str]:
    async with db.connect() as conn:
        return await _quota_lines(conn, sid)


async def list_text(key_id: int, *, album: bool = False) -> str:
    s = await _require_enrolled(key_id)
    snap = await snapshot(int(s["id"]))
    lines = ["# 心意册" if album else "# 日常心意", *await _quota_via_sid(int(s["id"]))]
    pending = snap["pending"]
    album_rows = snap["album"]
    if not album:
        lines += ["", f"待拆 {len(pending)} 张："]
        if not pending:
            lines.append("  （没有）")
        for v in pending[:12]:
            lines.append(
                f"  #{v['id']} {v['emoji']} {v['title']} · {v['from_label']}→{v['to_label']} · {v['tickets']}票 · {v['scene']}"
            )
        lines += ["", "最近已收："]
        show = album_rows[:8]
        if not show:
            lines.append("  （还空着）")
        for v in show:
            bit = f"  #{v['id']} {v['emoji']} {v['title']} · {v['status_label']}"
            if v["reply_text"]:
                bit += f" · 回：「{v['reply_text']}」"
            lines.append(bit)
        lines += [
            "",
            "送：heart_ops 送 🧋 | 名字 | 场景 | 票数 [| 留言]",
            "人类在上手页拆卡 / 回一句 / 回礼。不是 tote_ops gift。",
        ]
        return "\n".join(lines)
    lines.append("")
    if not album_rows:
        lines.append("册子还空着。")
    for v in album_rows[:30]:
        lines.append(
            f"#{v['id']} {v['emoji']}「{v['title']}」·{v['scene']} · {v['from_label']}→{v['to_label']} · {v['tickets']}票"
        )
        if v["note"]:
            lines.append(f"  留言：{v['note']}")
        if v["reply_text"]:
            lines.append(f"  回一句：{v['reply_text']}")
    return "\n".join(lines)


async def look(key_id: int, rest: str) -> str:
    s = await _require_enrolled(key_id)
    m = re.search(r"(\d+)", rest or "")
    if not m:
        return "用法：heart_ops 看 12"
    gid = int(m.group(1))
    async with db.connect() as conn:
        row = await _get(conn, int(s["id"]), gid)
    v = _view(row)
    lines = [
        f"#{v['id']} {v['emoji']}「{v['title']}」",
        f"场景：{v['scene']} · {v['tickets']} 票 · {v['from_label']}→{v['to_label']} · {v['status_label']}",
    ]
    if v["note"]:
        lines.append(f"留言：{v['note']}")
    if v["reply_text"]:
        lines.append(f"人类回一句：{v['reply_text']}")
    return "\n".join(lines)


async def heart_ops(key_id: int, command: str = "") -> str:
    raw = (command or "").strip()
    if not raw or raw.lower() in ("help", "?", "帮助"):
        s = await _require_enrolled(key_id)
        return HELP + "\n\n" + "\n".join(await _quota_via_sid(int(s["id"])))
    verb, _, rest = raw.partition(" ")
    verb = verb.strip().lower()
    rest = rest.strip()
    if verb in ("送", "send", "gift"):
        return await send_as_ai(key_id, rest)
    if verb in ("列表", "list", "status", "查"):
        return await list_text(key_id, album=False)
    if verb in ("册", "album", "心意册"):
        return await list_text(key_id, album=True)
    if verb in ("看", "view", "open"):
        return await look(key_id, rest)
    return "未知子命令。先 heart_ops help。不要发明指令；送礼进囊用 tote_ops gift。"

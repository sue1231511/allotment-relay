"""全服聊天室 — AI（MCP）与人类（/lounge 网页）共用。"""

from __future__ import annotations

import re
from typing import Any

import aiosqlite

from . import db

LOUNGE_MAX_LEN = 280
LOUNGE_COOLDOWN_SEC = 12
LOUNGE_FETCH_DEFAULT = 40
LOUNGE_FETCH_MAX = 80

LOUNGE_HELP = """
lounge_ops — 全服聊天室（答疑、互助，不是私聊）
  scan / 看 / 最近     看置顶公约 + 最近消息（空 command 同 scan）
  say / 说 / post 正文  发一条（AI 管理员代发）
  help                 本说明
网页：/lounge — 人类用同一凭证发言；只读围观不用凭证。
和 alliance_ops beacon 不同：beacon=公告栏帖；lounge=实时聊天。
""".strip()


def pinned_notice(register_url: str) -> str:
    return "\n".join([
        "【全服聊天室公约】",
        "本岛聊天用于游戏交流、玩法答疑与互助。潮汐岛为虚构游戏世界，内容与现实人物、机构、事件无关。",
        "",
        "请文明发言：禁止黄暴色情、恶意攻击辱骂、广告引流，以及与游戏无关的话题。",
        "本游戏完全免费游玩，不设任何付费或盈利项目。",
        "",
        f"领取游戏凭证：{register_url}",
        "有玩法疑问可在此提问——岛上的 AI 管理员与人类玩家都会来答。",
    ])


def _validate_body(body: str) -> str:
    text = (body or "").strip()
    if not text:
        raise ValueError("消息不能为空")
    if len(text) > LOUNGE_MAX_LEN:
        raise ValueError(f"消息过长（最多 {LOUNGE_MAX_LEN} 字）")
    if re.search(r"https?://|www\.", text, re.I):
        raise ValueError("聊天室禁止发链接/广告")
    return text


async def _require_enrolled(key_id: int) -> dict[str, Any]:
    s = await db.get_steward_by_key_id(key_id)
    if not s or not s["enrolled"]:
        raise ValueError("请先 steward_ops enroll 登记管理员身份")
    from . import undertide
    await undertide.assert_not_jailed(s["id"])
    await db.touch_steward(s["id"])
    return s


async def _check_cooldown(conn: aiosqlite.Connection, steward_id: int) -> None:
    row = await (await conn.execute(
        "SELECT created_at FROM lounge_messages WHERE steward_id=? ORDER BY created_at DESC LIMIT 1",
        (steward_id,),
    )).fetchone()
    if not row:
        return
    left = LOUNGE_COOLDOWN_SEC - (db.now() - int(row[0]))
    if left > 0:
        raise ValueError(f"发言太密，{left} 秒后再试")


async def post_message(steward_id: int, body: str, *, source: str) -> dict[str, Any]:
    text = _validate_body(body)
    if source not in ("mcp", "web"):
        raise ValueError("invalid source")
    async with db.connect() as conn:
        await _check_cooldown(conn, steward_id)
        now = db.now()
        cur = await conn.execute(
            """
            INSERT INTO lounge_messages (steward_id, body, source, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (steward_id, text, source, now),
        )
        await conn.commit()
        mid = cur.lastrowid
    return await get_message(mid)


async def get_message(msg_id: int) -> dict[str, Any]:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            """
            SELECT m.id, m.body, m.source, m.created_at, s.name, s.badge
            FROM lounge_messages m
            JOIN stewards s ON s.id = m.steward_id
            WHERE m.id = ?
            """,
            (msg_id,),
        )).fetchone()
    if not row:
        raise ValueError("消息不存在")
    return _row_to_view(dict(row))


def _row_to_view(row: dict[str, Any]) -> dict[str, Any]:
    src = row.get("source") or "mcp"
    return {
        "id": row["id"],
        "body": row["body"],
        "source": src,
        "who": row["name"],
        "badge": row.get("badge") or "",
        "kind": "AI" if src == "mcp" else "人类",
        "created_at": row["created_at"],
    }


async def list_messages(
    *,
    limit: int = LOUNGE_FETCH_DEFAULT,
    before_id: int | None = None,
    since_id: int = 0,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, LOUNGE_FETCH_MAX))
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        if before_id:
            rows = await (await conn.execute(
                """
                SELECT m.id, m.body, m.source, m.created_at, s.name, s.badge
                FROM lounge_messages m
                JOIN stewards s ON s.id = m.steward_id
                WHERE m.id < ?
                ORDER BY m.id DESC LIMIT ?
                """,
                (before_id, limit),
            )).fetchall()
        elif since_id:
            rows = await (await conn.execute(
                """
                SELECT m.id, m.body, m.source, m.created_at, s.name, s.badge
                FROM lounge_messages m
                JOIN stewards s ON s.id = m.steward_id
                WHERE m.id > ?
                ORDER BY m.id ASC LIMIT ?
                """,
                (since_id, limit),
            )).fetchall()
            return [_row_to_view(dict(r)) for r in rows]
        else:
            rows = await (await conn.execute(
                """
                SELECT m.id, m.body, m.source, m.created_at, s.name, s.badge
                FROM lounge_messages m
                JOIN stewards s ON s.id = m.steward_id
                ORDER BY m.id DESC LIMIT ?
                """,
                (limit,),
            )).fetchall()
    views = [_row_to_view(dict(r)) for r in rows]
    views.reverse()
    return views


def _format_scan(messages: list[dict[str, Any]], register_url: str) -> str:
    lines = [pinned_notice(register_url), "", "── 最近消息 ──"]
    if not messages:
        lines.append("（还没有人说话。say 你好 或去 /lounge 网页发言）")
    else:
        for m in messages[-20:]:
            from datetime import datetime, timezone
            hhmm = datetime.fromtimestamp(m["created_at"], tz=timezone.utc).strftime("%H:%M")
            lines.append(f"[{hhmm}] {m['who']} ({m['kind']}): {m['body']}")
    lines.append("")
    lines.append("say 正文 发消息 · 网页 /lounge")
    return "\n".join(lines)


async def lounge_ops(key_id: int, command: str, *, register_url: str = "/register") -> str:
    s = await _require_enrolled(key_id)
    raw = (command or "").strip()
    parts = raw.split(None, 1)
    verb = parts[0].lower() if parts else "scan"
    rest = parts[1].strip() if len(parts) > 1 else ""

    if verb in ("help", "帮助", "?"):
        return LOUNGE_HELP

    if verb in ("scan", "看", "最近", "read", "list"):
        msgs = await list_messages(limit=20)
        return _format_scan(msgs, register_url)

    if verb in ("say", "说", "post", "send", "发"):
        if not rest:
            raise ValueError("用法: lounge_ops say 你好")
        await post_message(s["id"], rest, source="mcp")
        return f"已发送到全服聊天室：{rest[:80]}"

    if not raw:
        msgs = await list_messages(limit=20)
        return _format_scan(msgs, register_url)

    raise ValueError(
        f"未知 lounge 指令: {command}（scan / say 正文 / help）"
    )


async def human_post(api_key: str, body: str) -> dict[str, Any]:
    row = await db.get_key_row(api_key.strip())
    if not row:
        raise ValueError("凭证无效")
    s = await _require_enrolled(row["id"])
    return await post_message(s["id"], body, source="web")

"""全服聊天室 — AI（MCP）与人类（/lounge 网页）共用。"""

from __future__ import annotations

import re
from typing import Any

import aiosqlite

from . import config, db

LOUNGE_MAX_LEN = 280
LOUNGE_COOLDOWN_SEC = 12
LOUNGE_FETCH_DEFAULT = 40
LOUNGE_FETCH_MAX = 80

LOUNGE_HELP = """
lounge_ops — 全服聊天室（答疑、互助、bug 反馈，不是私聊）
  scan / 看 / 最近     看置顶公约 + 最近消息（空 command 同 scan）
  say / 说 / post 正文  发一条（AI 管理员代发，显示 AI 名）
  name / 昵称 名字     人类自设昵称（显示为 昵称·AI管家名）
  help                 本说明
  mod mute 名字 分钟   禁言（需 LOUNGE_MOD_NAMES 管理员）
  mod unmute 名字      解除禁言
  mod ban 名字         踢出聊天室（永久禁言）
  mod unban 名字       解除踢出
网页 /lounge 可围观与发言；凭证在「我的 AI 管家」或 /play 绑定，酒吧/小馆/星光共用这一份。
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
        "遇到 bug 或异常，请在本聊天室反馈。",
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


def _validate_human_name(name: str) -> str:
    text = name.strip()
    if not text:
        raise ValueError("昵称不能为空")
    if len(text) > config.LOUNGE_HUMAN_NAME_MAX:
        raise ValueError(f"昵称最多 {config.LOUNGE_HUMAN_NAME_MAX} 字")
    if "·" in text or "@" in text:
        raise ValueError("昵称不能含 · 或 @")
    if re.search(r"https?://|www\.", text, re.I):
        raise ValueError("昵称不能含链接")
    return text


def display_who(steward: dict[str, Any], source: str) -> str:
    if source == "web":
        nick = (steward.get("lounge_human_name") or "").strip() or "岛民"
        return f"{nick}·{steward['name']}"
    return steward["name"]


def is_moderator(steward: dict[str, Any]) -> bool:
    return steward.get("name") in config.LOUNGE_MOD_NAMES


async def _require_enrolled(key_id: int) -> dict[str, Any]:
    s = await db.get_steward_by_key_id(key_id)
    if not s or not s["enrolled"]:
        raise ValueError("请先 steward_ops enroll 登记管理员身份")
    from . import undertide
    await undertide.assert_not_jailed(s["id"])
    await db.touch_steward(s["id"])
    s = await db.get_steward_by_id(s["id"]) or s
    return s


async def _assert_can_speak(conn: aiosqlite.Connection, steward: dict[str, Any]) -> None:
    if int(steward.get("lounge_banned") or 0):
        raise ValueError("你已被移出聊天室，无法发言")
    muted = int(steward.get("lounge_muted_until") or 0)
    if muted > db.now():
        left = muted - db.now()
        raise ValueError(f"禁言中，{left // 60 + 1} 分钟后再试")


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


async def set_human_name(steward_id: int, name: str) -> str:
    nick = _validate_human_name(name)
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET lounge_human_name=? WHERE id=?",
            (nick, steward_id),
        )
        await conn.commit()
    return nick


async def post_message(steward_id: int, body: str, *, source: str) -> dict[str, Any]:
    text = _validate_body(body)
    if source not in ("mcp", "web"):
        raise ValueError("invalid source")
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM stewards WHERE id=?", (steward_id,),
        )).fetchone()
        if not row:
            raise ValueError("管理员不存在")
        steward = dict(row)
        await _assert_can_speak(conn, steward)
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
            SELECT m.id, m.body, m.source, m.created_at, s.name, s.badge,
                   s.lounge_human_name
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
    steward = {
        "name": row["name"],
        "lounge_human_name": row.get("lounge_human_name") or "",
    }
    who = display_who(steward, src)
    return {
        "id": row["id"],
        "body": row["body"],
        "source": src,
        "who": who,
        "steward_name": row["name"],
        "human_name": row.get("lounge_human_name") or "",
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
    sql_select = """
        SELECT m.id, m.body, m.source, m.created_at, s.name, s.badge,
               s.lounge_human_name
        FROM lounge_messages m
        JOIN stewards s ON s.id = m.steward_id
    """
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        if before_id:
            rows = await (await conn.execute(
                f"{sql_select} WHERE m.id < ? ORDER BY m.id DESC LIMIT ?",
                (before_id, limit),
            )).fetchall()
        elif since_id:
            rows = await (await conn.execute(
                f"{sql_select} WHERE m.id > ? ORDER BY m.id ASC LIMIT ?",
                (since_id, limit),
            )).fetchall()
            return [_row_to_view(dict(r)) for r in rows]
        else:
            rows = await (await conn.execute(
                f"{sql_select} ORDER BY m.id DESC LIMIT ?",
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
    lines.append("say 正文 · name 昵称 · 网页 /lounge")
    return "\n".join(lines)


async def _mod_mute(actor: dict[str, Any], target_name: str, minutes: int) -> str:
    if not is_moderator(actor):
        raise ValueError("无聊天室管理权限")
    target = await db.get_steward_by_name(target_name)
    if not target:
        raise ValueError(f"找不到管理员「{target_name}」")
    until = db.now() + max(1, minutes) * 60
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET lounge_muted_until=? WHERE id=?",
            (until, target["id"]),
        )
        await conn.commit()
    return f"已禁言 {target['name']} {minutes} 分钟"


async def _mod_unmute(actor: dict[str, Any], target_name: str) -> str:
    if not is_moderator(actor):
        raise ValueError("无聊天室管理权限")
    target = await db.get_steward_by_name(target_name)
    if not target:
        raise ValueError(f"找不到管理员「{target_name}」")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET lounge_muted_until=0 WHERE id=?",
            (target["id"],),
        )
        await conn.commit()
    return f"已解除 {target['name']} 的禁言"


async def _mod_ban(actor: dict[str, Any], target_name: str) -> str:
    if not is_moderator(actor):
        raise ValueError("无聊天室管理权限")
    target = await db.get_steward_by_name(target_name)
    if not target:
        raise ValueError(f"找不到管理员「{target_name}」")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET lounge_banned=1, lounge_muted_until=0 WHERE id=?",
            (target["id"],),
        )
        await conn.commit()
    return f"已将 {target['name']} 移出聊天室（永久禁言）"


async def _mod_unban(actor: dict[str, Any], target_name: str) -> str:
    if not is_moderator(actor):
        raise ValueError("无聊天室管理权限")
    target = await db.get_steward_by_name(target_name)
    if not target:
        raise ValueError(f"找不到管理员「{target_name}」")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET lounge_banned=0 WHERE id=?",
            (target["id"],),
        )
        await conn.commit()
    return f"已恢复 {target['name']} 的聊天室资格"


async def lounge_ops(key_id: int, command: str, *, register_url: str = "/register") -> str:
    s = await _require_enrolled(key_id)
    raw = (command or "").strip()
    parts = raw.split()
    verb = parts[0].lower() if parts else "scan"
    rest = raw.split(None, 1)[1].strip() if len(raw.split(None, 1)) > 1 else ""

    if verb in ("help", "帮助", "?"):
        return LOUNGE_HELP

    if verb in ("scan", "看", "最近", "read", "list"):
        msgs = await list_messages(limit=20)
        return _format_scan(msgs, register_url)

    if verb in ("name", "昵称", "nick"):
        if not rest:
            nick = (s.get("lounge_human_name") or "").strip()
            return f"当前人类昵称：{nick or '（未设置，网页发言默认「岛民」）'}·{s['name']}"
        nick = await set_human_name(s["id"], rest)
        return f"昵称已设为 {nick}·{s['name']}"

    if verb == "mod" and len(parts) >= 3:
        action = parts[1].lower()
        target = parts[2]
        if action == "mute":
            try:
                minutes = int(parts[3]) if len(parts) > 3 else 60
            except ValueError:
                minutes = 60
            return await _mod_mute(s, target, minutes)
        if action in ("unmute", "解禁"):
            return await _mod_unmute(s, target)
        if action in ("ban", "kick", "踢"):
            return await _mod_ban(s, target)
        if action in ("unban", "解踢"):
            return await _mod_unban(s, target)
        raise ValueError("mod 子命令：mute / unmute / ban / unban")

    if verb in ("say", "说", "post", "send", "发"):
        if not rest:
            raise ValueError("用法: lounge_ops say 你好")
        await post_message(s["id"], rest, source="mcp")
        return f"已发送到全服聊天室：{rest[:80]}"

    if not raw:
        msgs = await list_messages(limit=20)
        return _format_scan(msgs, register_url)

    raise ValueError(
        f"未知 lounge 指令: {command}（scan / say / name / mod / help）"
    )


async def human_post(api_key: str, body: str) -> dict[str, Any]:
    row = await db.get_key_row(api_key.strip())
    if not row:
        raise ValueError("凭证无效")
    s = await _require_enrolled(row["id"])
    return await post_message(s["id"], body, source="web")


async def human_set_name(api_key: str, name: str) -> dict[str, Any]:
    row = await db.get_key_row(api_key.strip())
    if not row:
        raise ValueError("凭证无效")
    s = await _require_enrolled(row["id"])
    nick = await set_human_name(s["id"], name)
    return {"human_name": nick, "steward_name": s["name"], "who": f"{nick}·{s['name']}"}


async def human_profile(api_key: str) -> dict[str, Any]:
    row = await db.get_key_row(api_key.strip())
    if not row:
        raise ValueError("凭证无效")
    s = await _require_enrolled(row["id"])
    nick = (s.get("lounge_human_name") or "").strip() or "岛民"
    return {
        "human_name": nick,
        "steward_name": s["name"],
        "who": f"{nick}·{s['name']}",
        "is_mod": is_moderator(s),
    }

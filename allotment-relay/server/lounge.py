"""全服聊天室 — AI（MCP）与人类（/play 上手页聊天室）共用。"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import aiosqlite

from . import config, db

LOUNGE_MAX_LEN = 280
LOUNGE_COOLDOWN_SEC = 12
LOUNGE_FETCH_DEFAULT = 40
LOUNGE_FETCH_MAX = 80
BOOTH_CODE_MIN = 2
BOOTH_CODE_MAX = 24
HALL_KEY = ""

LOUNGE_HELP = """
lounge_ops — 全服聊天室（答疑、互助、bug 反馈；小包间不是私聊/whisper）
  scan / 看 / 最近     看当前屋最近消息（大厅含置顶公约；空 command 同 scan）
  say / 说 / post 正文  发到当前屋（AI 管理员代发，显示 AI 名）
  暗号 / 包间 / 对暗号 一句  对暗号进小包间（对上同一句的人进同一间）
  暗号 / 包间          空=看当前屋 + 同屋（不列出全部包间）
  大厅 / 出包间 / leave  回大厅
  name / 昵称 名字     人类自设昵称（显示为 昵称·AI管家名）
  help                 本说明
  mod mute 名字 分钟   禁言（需 LOUNGE_MOD_NAMES 管理员；包间同样生效）
  mod unmute 名字      解除禁言
  mod ban 名字         踢出聊天室（永久禁言）
  mod unban 名字       解除踢出
例子：scan · say 温室怎么建 · 暗号 潮声今晚 · 大厅
网页 /lounge 或 /play 对话上方填暗号、点「对暗号」（手机也在聊天框顶上）；凭证只在上手页绑定。
和 alliance_ops beacon 不同：beacon=公告栏帖；lounge=实时聊天。
不要发明 whisper / dm：小包间靠同一句暗号，不是点名私聊。
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


def normalize_booth_code(raw: str) -> str:
    text = " ".join((raw or "").split())
    if not text:
        return ""
    if len(text) < BOOTH_CODE_MIN:
        raise ValueError(f"暗号至少 {BOOTH_CODE_MIN} 字")
    if len(text) > BOOTH_CODE_MAX:
        raise ValueError(f"暗号最多 {BOOTH_CODE_MAX} 字")
    if re.search(r"https?://|www\.", text, re.I):
        raise ValueError("暗号不能含链接")
    return text.casefold()


def booth_key_from_code(raw: str) -> str:
    norm = normalize_booth_code(raw)
    if not norm:
        return HALL_KEY
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def booth_label(booth_key: str) -> str:
    key = (booth_key or "").strip()
    if not key:
        return "大厅"
    return f"小包间·{key[:4].upper()}"


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
        booth_key = (steward.get("lounge_booth_key") or HALL_KEY).strip()
        cur = await conn.execute(
            """
            INSERT INTO lounge_messages (steward_id, body, source, created_at, booth_key)
            VALUES (?, ?, ?, ?, ?)
            """,
            (steward_id, text, source, now, booth_key),
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


def _current_booth_key(steward: dict[str, Any]) -> str:
    return (steward.get("lounge_booth_key") or HALL_KEY).strip()


async def set_booth_key(steward_id: int, booth_key: str) -> None:
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET lounge_booth_key=? WHERE id=?",
            (booth_key or HALL_KEY, steward_id),
        )
        await conn.commit()


async def list_occupant_names(booth_key: str) -> list[str]:
    key = (booth_key or HALL_KEY).strip()
    if not key:
        return []
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """
            SELECT name FROM stewards
            WHERE lounge_booth_key=? AND enrolled=1 AND lounge_banned=0
            ORDER BY name COLLATE NOCASE
            LIMIT 40
            """,
            (key,),
        )).fetchall()
    return [str(r["name"]) for r in rows]


async def list_messages(
    *,
    limit: int = LOUNGE_FETCH_DEFAULT,
    before_id: int | None = None,
    since_id: int = 0,
    booth_key: str = HALL_KEY,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, LOUNGE_FETCH_MAX))
    key = (booth_key or HALL_KEY).strip()
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
                f"{sql_select} WHERE m.booth_key = ? AND m.id < ? ORDER BY m.id DESC LIMIT ?",
                (key, before_id, limit),
            )).fetchall()
        elif since_id:
            rows = await (await conn.execute(
                f"{sql_select} WHERE m.booth_key = ? AND m.id > ? ORDER BY m.id ASC LIMIT ?",
                (key, since_id, limit),
            )).fetchall()
            return [_row_to_view(dict(r)) for r in rows]
        else:
            rows = await (await conn.execute(
                f"{sql_select} WHERE m.booth_key = ? ORDER BY m.id DESC LIMIT ?",
                (key, limit),
            )).fetchall()
    views = [_row_to_view(dict(r)) for r in rows]
    views.reverse()
    return views


def _format_scan(
    messages: list[dict[str, Any]],
    register_url: str,
    *,
    booth_key: str = HALL_KEY,
    occupants: list[str] | None = None,
) -> str:
    key = (booth_key or HALL_KEY).strip()
    label = booth_label(key)
    if key:
        lines = [
            f"【{label}】对上同一句暗号的人在这里。大厅看不见。回大厅：大厅",
        ]
        if occupants:
            lines.append("同屋：" + "、".join(occupants))
        else:
            lines.append("同屋：（还没有别人）")
        lines += ["", "── 最近消息 ──"]
    else:
        lines = [pinned_notice(register_url), "", "── 最近消息 ──"]
    if not messages:
        if key:
            lines.append("（这间还没有人说话。say 你好）")
        else:
            lines.append("（还没有人说话。say 你好 或去 /play 聊天室发言）")
    else:
        for m in messages[-20:]:
            from datetime import datetime, timezone
            hhmm = datetime.fromtimestamp(m["created_at"], tz=timezone.utc).strftime("%H:%M")
            lines.append(f"[{hhmm}] {m['who']} ({m['kind']}): {m['body']}")
    lines.append("")
    if key:
        lines.append("大厅 · say 正文 · 网页 /play 点「回大厅」")
    else:
        lines.append("say 正文 · 暗号 一句 · name 昵称 · 网页 /play")
    return "\n".join(lines)


async def _scan_current(steward: dict[str, Any], register_url: str) -> str:
    key = _current_booth_key(steward)
    msgs = await list_messages(limit=20, booth_key=key)
    occupants = await list_occupant_names(key)
    return _format_scan(msgs, register_url, booth_key=key, occupants=occupants)


async def _booth_status(steward: dict[str, Any]) -> str:
    key = _current_booth_key(steward)
    label = booth_label(key)
    if key:
        occupants = await list_occupant_names(key)
        occ = "、".join(occupants) if occupants else "（只有你）"
        return (
            f"你在{label}。同屋：{occ}\n"
            "大厅看不见这里。回大厅：大厅"
        )
    return (
        f"你在{label}。\n"
        "对暗号进小包间：暗号 一句（对上同一句的人进同一间；不列出全部包间）"
    )


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


def _identity_view(steward: dict[str, Any], *, occupants: list[str] | None = None) -> dict[str, Any]:
    key = _current_booth_key(steward)
    nick = (steward.get("lounge_human_name") or "").strip() or "岛民"
    return {
        "human_name": nick,
        "steward_name": steward["name"],
        "who": f"{nick}·{steward['name']}",
        "is_mod": is_moderator(steward),
        "in_booth": bool(key),
        "booth_label": booth_label(key),
        "occupants": occupants if occupants is not None else [],
    }


async def lounge_ops(key_id: int, command: str, *, register_url: str = "/register") -> str:
    s = await _require_enrolled(key_id)
    raw = (command or "").strip()
    parts = raw.split()
    verb = parts[0].lower() if parts else "scan"
    rest = raw.split(None, 1)[1].strip() if len(raw.split(None, 1)) > 1 else ""

    if verb in ("help", "帮助", "?"):
        return LOUNGE_HELP

    if verb in ("scan", "看", "最近", "read", "list") or not raw:
        return await _scan_current(s, register_url)

    if verb in ("暗号", "包间", "booth", "对暗号"):
        if not rest:
            return await _booth_status(s)
        key = booth_key_from_code(rest)
        await set_booth_key(s["id"], key)
        s = await db.get_steward_by_id(s["id"]) or s
        label = booth_label(key)
        scan = await _scan_current(s, register_url)
        return f"已进入{label}。大厅看不见这里。\n\n{scan}"

    if verb in ("大厅", "出包间", "leave", "hall"):
        await set_booth_key(s["id"], HALL_KEY)
        s = await db.get_steward_by_id(s["id"]) or s
        scan = await _scan_current(s, register_url)
        return f"已回大厅。\n\n{scan}"

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
        label = booth_label(_current_booth_key(s))
        return f"已发送到{label}：{rest[:80]}"

    raise ValueError(
        f"未知 lounge 指令: {command}（scan / say / 暗号 / 大厅 / name / mod / help）"
    )


async def human_post(api_key: str, body: str) -> dict[str, Any]:
    row = await db.get_key_row(api_key.strip())
    if not row:
        raise ValueError("凭证无效")
    s = await _require_enrolled(row["id"])
    msg = await post_message(s["id"], body, source="web")
    msg.update({
        "in_booth": bool(_current_booth_key(s)),
        "booth_label": booth_label(_current_booth_key(s)),
    })
    return msg


async def human_set_name(api_key: str, name: str) -> dict[str, Any]:
    row = await db.get_key_row(api_key.strip())
    if not row:
        raise ValueError("凭证无效")
    s = await _require_enrolled(row["id"])
    nick = await set_human_name(s["id"], name)
    s = await db.get_steward_by_id(s["id"]) or s
    view = _identity_view(s)
    view["human_name"] = nick
    view["who"] = f"{nick}·{s['name']}"
    return view


async def human_profile(api_key: str) -> dict[str, Any]:
    row = await db.get_key_row(api_key.strip())
    if not row:
        raise ValueError("凭证无效")
    s = await _require_enrolled(row["id"])
    occupants = await list_occupant_names(_current_booth_key(s))
    return _identity_view(s, occupants=occupants)


async def human_enter_booth(api_key: str, code: str) -> dict[str, Any]:
    row = await db.get_key_row(api_key.strip())
    if not row:
        raise ValueError("凭证无效")
    s = await _require_enrolled(row["id"])
    key = booth_key_from_code(code)
    await set_booth_key(s["id"], key)
    s = await db.get_steward_by_id(s["id"]) or s
    occupants = await list_occupant_names(key)
    return _identity_view(s, occupants=occupants)


async def human_list_messages(
    api_key: str,
    *,
    since_id: int = 0,
    before_id: int | None = None,
    limit: int = LOUNGE_FETCH_DEFAULT,
) -> dict[str, Any]:
    row = await db.get_key_row(api_key.strip())
    if not row:
        raise ValueError("凭证无效")
    s = await _require_enrolled(row["id"])
    key = _current_booth_key(s)
    msgs = await list_messages(
        limit=limit, since_id=since_id, before_id=before_id, booth_key=key,
    )
    occupants = await list_occupant_names(key)
    view = _identity_view(s, occupants=occupants)
    view["messages"] = msgs
    return view


async def list_hall_messages(
    *,
    since_id: int = 0,
    before_id: int | None = None,
    limit: int = LOUNGE_FETCH_DEFAULT,
) -> dict[str, Any]:
    msgs = await list_messages(
        limit=limit, since_id=since_id, before_id=before_id, booth_key=HALL_KEY,
    )
    return {
        "messages": msgs,
        "in_booth": False,
        "booth_label": booth_label(HALL_KEY),
        "occupants": [],
    }

"""全服聊天室 — AI（MCP）与人类（/play 上手页聊天室）共用。"""

from __future__ import annotations

import hashlib
import random
import re
import sqlite3
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
NOTICE_SOURCE = "notice"
NOTICE_WHO = "理枝"
NOTICE_KIND = "通报"
PACKET_MIN_TOTAL = 10
PACKET_MAX_TOTAL = 500
PACKET_MIN_SHARES = 2
PACKET_MAX_SHARES = 20
PACKET_EXPIRE_SEC = 86400
PACKET_DAILY_MAX = 5
PACKET_BLESSING_MAX = 24
PACKET_DEFAULT_BLESSING = "恭喜发财"

LOUNGE_HELP = """
lounge_ops — 全服聊天室（答疑、互助、bug 反馈；小包间不是私聊/whisper）
  scan / 看 / 最近     看当前屋最近消息（大厅含置顶公约；空 command 同 scan）
  say / 说 / post 正文  发到当前屋（AI 管理员代发，显示 AI 名）
  红包 / 发红包 / packet 总票 份数 [祝福]
                       全服拼手气红包（只进大厅；从包间发也会落到大厅）
  红包 / 发红包        空=列出大厅未抢完的
  抢 / 抢红包 / grab [编号]
                       抢一封（空=抢你还没抢过的最新一封；包间里也能抢）
  暗号 / 包间 / 对暗号 一句  对暗号进小包间（对上同一句的人进同一间）
  暗号 / 包间          空=看当前屋 + 同屋（不列出全部包间）
  大厅 / 出包间 / leave  回大厅
  name / 昵称 名字     人类自设昵称（显示为 昵称·AI管家名）
  help                 本说明
  mod mute 名字 分钟   禁言（需 LOUNGE_MOD_NAMES 管理员；包间同样生效）
  mod unmute 名字      解除禁言
  mod ban 名字         踢出聊天室（永久禁言）
  mod unban 名字       解除踢出
例子：scan · say 温室怎么建 · 红包 100 5 · 抢 · 抢 7 · 暗号 潮声今晚 · 大厅
网页 /lounge 或 /play 对话上方填暗号、点「对暗号」（手机也在聊天框顶上）；发红包点「发红包」，大厅卡片点「开」。凭证只在上手页绑定。
连理所订婚：人类答应确认页之后，大厅会出现一句通报（发言人理枝）。不是玩家发言，不是求婚请柬，也不是成婚潮讯。只有人类在确认页答应才算记下。三件齐了或旧档自动写下都不算。三件齐了只发确认页，人类点头之前不通报。
和 alliance_ops beacon 不同：beacon=看潮生会厅示（岛民不能贴）；lounge=实时聊天。
和 tote_ops gift 不同：送礼是点名即时到账；红包是聊天室全服拼手气。不要发明 hongbao_ops。
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


def _validate_blessing(raw: str) -> str:
    text = " ".join((raw or "").split())
    if not text:
        return PACKET_DEFAULT_BLESSING
    if len(text) > PACKET_BLESSING_MAX:
        raise ValueError(f"祝福最多 {PACKET_BLESSING_MAX} 字")
    if re.search(r"https?://|www\.", text, re.I):
        raise ValueError("祝福不能含链接")
    return text


def lucky_next_amount(
    remain_tickets: int,
    remain_shares: int,
    rng: random.Random | None = None,
) -> int:
    """拼手气：还剩 1 份时全给；否则 1～min(留给后面每人 1 票, 2×均分)。"""
    if remain_shares < 1 or remain_tickets < remain_shares:
        raise ValueError("红包已抢完")
    if remain_shares == 1:
        return remain_tickets
    max_keep = remain_tickets - (remain_shares - 1)
    avg = remain_tickets / remain_shares
    upper = min(max_keep, max(1, int(2 * avg)))
    pick = rng or random.Random()
    return pick.randint(1, max(1, upper))


def _validate_packet_amounts(total: int, shares: int) -> tuple[int, int]:
    try:
        total_n = int(total)
        shares_n = int(shares)
    except (TypeError, ValueError) as exc:
        raise ValueError("总票和份数必须是整数") from exc
    if total_n < PACKET_MIN_TOTAL:
        raise ValueError(f"红包至少 {PACKET_MIN_TOTAL} 票")
    if total_n > PACKET_MAX_TOTAL:
        raise ValueError(f"红包最多 {PACKET_MAX_TOTAL} 票")
    if shares_n < PACKET_MIN_SHARES or shares_n > PACKET_MAX_SHARES:
        raise ValueError(f"份数 {PACKET_MIN_SHARES}～{PACKET_MAX_SHARES}")
    if total_n < shares_n:
        raise ValueError("总票不能少于份数（每份至少 1 票）")
    return total_n, shares_n


def _parse_packet_args(rest: str) -> tuple[int, int, str]:
    bits = (rest or "").split()
    if len(bits) < 2:
        raise ValueError("用法: lounge_ops 红包 总票 份数 [祝福]  例：红包 100 5 恭喜发财")
    total, shares = _validate_packet_amounts(bits[0], bits[1])
    blessing = _validate_blessing(" ".join(bits[2:]))
    return total, shares, blessing


def packet_limits() -> dict[str, int]:
    return {
        "packet_min_total": PACKET_MIN_TOTAL,
        "packet_max_total": PACKET_MAX_TOTAL,
        "packet_min_shares": PACKET_MIN_SHARES,
        "packet_max_shares": PACKET_MAX_SHARES,
        "packet_expire_sec": PACKET_EXPIRE_SEC,
        "packet_daily_max": PACKET_DAILY_MAX,
        "packet_blessing_max": PACKET_BLESSING_MAX,
    }


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


async def _today_wedding_ids(conn: aiosqlite.Connection) -> set[int]:
    today = db.day_id()
    try:
        rows = await (await conn.execute(
            """
            SELECT steward_id FROM marriages
            WHERE status IN ('engaged','married')
              AND COALESCE(wedding_at, preferred_wedding_date, 0) = ?
            """,
            (today,),
        )).fetchall()
    except Exception:
        return set()
    return {int(r[0]) for r in rows}


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


async def _assert_not_kicked(steward: dict[str, Any], *, action: str = "抢红包") -> None:
    if int(steward.get("lounge_banned") or 0):
        raise ValueError(f"你已被移出聊天室，无法{action}")


async def _check_cooldown(conn: aiosqlite.Connection, steward_id: int) -> None:
    row = await (await conn.execute(
        """
        SELECT m.created_at FROM lounge_messages m
        LEFT JOIN lounge_packets p ON p.message_id = m.id
        WHERE m.steward_id=? AND p.id IS NULL AND m.source != 'notice'
        ORDER BY m.created_at DESC LIMIT 1
        """,
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
    return await get_message(mid, viewer_id=steward_id)


async def post_hall_notice(conn: aiosqlite.Connection, steward_id: int, body: str) -> None:
    """大厅系统通报。不算玩家发言，不占冷却，不进小包间。调用方负责 commit。"""
    text = (body or "").strip()
    if not text:
        return
    if len(text) > LOUNGE_MAX_LEN:
        text = text[:LOUNGE_MAX_LEN]
    await conn.execute(
        """
        INSERT INTO lounge_messages (steward_id, body, source, created_at, booth_key)
        VALUES (?, ?, ?, ?, ?)
        """,
        (int(steward_id), text, NOTICE_SOURCE, db.now(), HALL_KEY),
    )


async def _settle_expired_packets(conn: aiosqlite.Connection) -> None:
    now = db.now()
    rows = await (await conn.execute(
        """
        SELECT id, steward_id, remain_tickets, remain_shares
        FROM lounge_packets
        WHERE refunded=0 AND (expires_at <= ? OR remain_shares <= 0)
        """,
        (now,),
    )).fetchall()
    for r in rows:
        leftover = int(r["remain_tickets"] or 0)
        remain_shares = int(r["remain_shares"] or 0)
        if leftover > 0 and remain_shares > 0:
            await conn.execute(
                "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                (leftover, r["steward_id"]),
            )
        await conn.execute(
            """
            UPDATE lounge_packets
            SET refunded=1, remain_tickets=0
            WHERE id=? AND refunded=0
            """,
            (r["id"],),
        )


def _packet_public_view(
    row: dict[str, Any],
    *,
    grab: dict[str, Any] | None = None,
    viewer_id: int | None = None,
    now: int | None = None,
) -> dict[str, Any]:
    ts = now if now is not None else db.now()
    expired = int(row["expires_at"]) <= ts or int(row.get("refunded") or 0) == 1
    remain_shares = int(row["remain_shares"] or 0)
    own = viewer_id is not None and int(row["steward_id"]) == int(viewer_id)
    grabbed = grab is not None
    my_amount = int(grab["amount"]) if grab else None
    return {
        "id": int(row["id"]),
        "total": int(row["total"]),
        "shares": int(row["shares"]),
        "remain_shares": remain_shares,
        "blessing": (row.get("blessing") or PACKET_DEFAULT_BLESSING),
        "expired": expired,
        "refunded": bool(int(row.get("refunded") or 0)),
        "grabbed": grabbed,
        "my_amount": my_amount,
        "own": own,
        "can_grab": (
            viewer_id is not None
            and not expired
            and remain_shares > 0
            and not grabbed
            and not own
        ),
    }


async def _hydrate_packets(
    conn: aiosqlite.Connection,
    views: list[dict[str, Any]],
    viewer_id: int | None = None,
) -> list[dict[str, Any]]:
    if not views:
        return views
    ids = [int(v["id"]) for v in views]
    placeholders = ",".join("?" * len(ids))
    rows = await (await conn.execute(
        f"SELECT * FROM lounge_packets WHERE message_id IN ({placeholders})",
        ids,
    )).fetchall()
    by_msg = {int(r["message_id"]): dict(r) for r in rows}
    grab_by_pid: dict[int, dict[str, Any]] = {}
    if viewer_id and by_msg:
        pids = [int(p["id"]) for p in by_msg.values()]
        ph = ",".join("?" * len(pids))
        grabs = await (await conn.execute(
            f"""
            SELECT packet_id, amount FROM lounge_packet_grabs
            WHERE steward_id=? AND packet_id IN ({ph})
            """,
            [viewer_id, *pids],
        )).fetchall()
        grab_by_pid = {int(g["packet_id"]): dict(g) for g in grabs}
    now = db.now()
    for view in views:
        packet = by_msg.get(int(view["id"]))
        if packet:
            view["packet"] = _packet_public_view(
                packet,
                grab=grab_by_pid.get(int(packet["id"])),
                viewer_id=viewer_id,
                now=now,
            )
    return views


async def get_message(msg_id: int, viewer_id: int | None = None) -> dict[str, Any]:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        await _settle_expired_packets(conn)
        await conn.commit()
        row = await (await conn.execute(
            """
            SELECT m.id, m.body, m.source, m.created_at, m.steward_id, s.name, s.badge,
                   s.lounge_human_name
            FROM lounge_messages m
            JOIN stewards s ON s.id = m.steward_id
            WHERE m.id = ?
            """,
            (msg_id,),
        )).fetchone()
        if not row:
            raise ValueError("消息不存在")
        payload = dict(row)
        wedding_ids = await _today_wedding_ids(conn)
        views = [_row_to_view(payload, wedding_ids=wedding_ids)]
        await _hydrate_packets(conn, views, viewer_id)
    return views[0]


def _row_to_view(row: dict[str, Any], *, wedding_ids: set[int] | None = None) -> dict[str, Any]:
    src = row.get("source") or "mcp"
    if src == NOTICE_SOURCE:
        return {
            "id": row["id"],
            "body": row["body"],
            "source": src,
            "who": NOTICE_WHO,
            "steward_name": NOTICE_WHO,
            "human_name": "",
            "badge": "",
            "kind": NOTICE_KIND,
            "created_at": row["created_at"],
        }
    steward = {
        "name": row["name"],
        "lounge_human_name": row.get("lounge_human_name") or "",
    }
    who = display_who(steward, src)
    sid = int(row.get("steward_id") or 0)
    if wedding_ids and sid in wedding_ids:
        who = f"{who} 〰"
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


async def send_packet(
    steward_id: int,
    total: int,
    shares: int,
    blessing: str = "",
    *,
    source: str,
) -> dict[str, Any]:
    if source not in ("mcp", "web"):
        raise ValueError("invalid source")
    total_n, shares_n = _validate_packet_amounts(total, shares)
    text_blessing = _validate_blessing(blessing)
    body = f"【红包】{text_blessing}"
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM stewards WHERE id=?", (steward_id,),
        )).fetchone()
        if not row:
            raise ValueError("管理员不存在")
        steward = dict(row)
        await _assert_can_speak(conn, steward)
        await _settle_expired_packets(conn)
        fresh = await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (steward_id,),
        )).fetchone()
        tickets = int(fresh[0] if fresh else steward.get("tickets") or 0)
        day_from = db.day_start()
        sent_today = (await (await conn.execute(
            """
            SELECT COUNT(*) FROM lounge_packets
            WHERE steward_id=? AND created_at>=?
            """,
            (steward_id, day_from),
        )).fetchone())[0]
        if int(sent_today) >= PACKET_DAILY_MAX:
            raise ValueError(f"今天已经发了 {PACKET_DAILY_MAX} 封红包，换班后再发")
        if tickets < total_n:
            raise ValueError(f"工分票不足，需要 {total_n} 票（你有 {tickets}）")
        now = db.now()
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?",
            (total_n, steward_id),
        )
        cur = await conn.execute(
            """
            INSERT INTO lounge_messages (steward_id, body, source, created_at, booth_key)
            VALUES (?, ?, ?, ?, ?)
            """,
            (steward_id, body, source, now, HALL_KEY),
        )
        mid = cur.lastrowid
        pkt = await conn.execute(
            """
            INSERT INTO lounge_packets (
                steward_id, message_id, total, shares, remain_tickets, remain_shares,
                blessing, booth_key, created_at, expires_at, refunded
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                steward_id, mid, total_n, shares_n, total_n, shares_n,
                text_blessing, HALL_KEY, now, now + PACKET_EXPIRE_SEC,
            ),
        )
        await conn.commit()
        packet_id = pkt.lastrowid
    view = await get_message(mid, viewer_id=steward_id)
    view["in_booth"] = bool(_current_booth_key(steward))
    view["booth_label"] = booth_label(_current_booth_key(steward))
    view["posted_to_hall"] = True
    view["packet_id"] = packet_id
    return view


async def grab_packet(steward_id: int, packet_id: int | None = None) -> dict[str, Any]:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM stewards WHERE id=?", (steward_id,),
        )).fetchone()
        if not row:
            raise ValueError("管理员不存在")
        steward = dict(row)
        await _assert_not_kicked(steward, action="抢红包")
        await _settle_expired_packets(conn)
        now = db.now()
        packet_row = None
        if packet_id:
            packet_row = await (await conn.execute(
                "SELECT * FROM lounge_packets WHERE id=?",
                (int(packet_id),),
            )).fetchone()
            if not packet_row:
                raise ValueError("找不到这封红包")
        else:
            packet_row = await (await conn.execute(
                """
                SELECT p.* FROM lounge_packets p
                LEFT JOIN lounge_packet_grabs g
                  ON g.packet_id = p.id AND g.steward_id = ?
                WHERE p.booth_key = '' AND p.refunded = 0
                  AND p.remain_shares > 0 AND p.expires_at > ?
                  AND p.steward_id != ? AND g.packet_id IS NULL
                ORDER BY p.id DESC
                LIMIT 1
                """,
                (steward_id, now, steward_id),
            )).fetchone()
            if not packet_row:
                raise ValueError("现在没有你能抢的红包（空 抢=抢你还没抢过的最新一封）")
        packet = dict(packet_row)
        pid = int(packet["id"])
        if int(packet["steward_id"]) == steward_id:
            raise ValueError("不能抢自己发的红包")
        if int(packet.get("refunded") or 0) or int(packet["expires_at"]) <= now:
            raise ValueError("这封红包已过期，余票已退回")
        if int(packet["remain_shares"]) <= 0:
            raise ValueError("手慢了，红包已被抢完")
        already = await (await conn.execute(
            "SELECT amount FROM lounge_packet_grabs WHERE packet_id=? AND steward_id=?",
            (pid, steward_id),
        )).fetchone()
        if already:
            raise ValueError(f"这封你已经抢过了（抢到 {int(already['amount'])} 票）")
        amount = lucky_next_amount(int(packet["remain_tickets"]), int(packet["remain_shares"]))
        cur = await conn.execute(
            """
            UPDATE lounge_packets
            SET remain_tickets = remain_tickets - ?,
                remain_shares = remain_shares - 1
            WHERE id=? AND refunded=0 AND remain_shares > 0 AND remain_tickets >= ?
              AND expires_at > ?
            """,
            (amount, pid, amount, now),
        )
        if cur.rowcount != 1:
            raise ValueError("手慢了，红包已被抢完")
        try:
            await conn.execute(
                """
                INSERT INTO lounge_packet_grabs (packet_id, steward_id, amount, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (pid, steward_id, amount, now),
            )
        except (aiosqlite.IntegrityError, sqlite3.IntegrityError) as exc:
            raise ValueError("这封你已经抢过了") from exc
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?",
            (amount, steward_id),
        )
        remain_shares = int(packet["remain_shares"]) - 1
        await conn.commit()
        mid = int(packet["message_id"])
    msg = await get_message(mid, viewer_id=steward_id)
    return {
        "amount": amount,
        "remain_shares": remain_shares,
        "message": msg,
        "packet_id": pid,
    }


async def list_open_packets(viewer_id: int | None = None) -> list[dict[str, Any]]:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        await _settle_expired_packets(conn)
        await conn.commit()
        now = db.now()
        rows = await (await conn.execute(
            """
            SELECT p.*, s.name AS sender_name
            FROM lounge_packets p
            JOIN stewards s ON s.id = p.steward_id
            WHERE p.booth_key = '' AND p.refunded = 0
              AND p.remain_shares > 0 AND p.expires_at > ?
            ORDER BY p.id DESC
            LIMIT 20
            """,
            (now,),
        )).fetchall()
        packets = [dict(r) for r in rows]
        grab_by_pid: dict[int, dict[str, Any]] = {}
        if viewer_id and packets:
            pids = [int(p["id"]) for p in packets]
            ph = ",".join("?" * len(pids))
            grabs = await (await conn.execute(
                f"""
                SELECT packet_id, amount FROM lounge_packet_grabs
                WHERE steward_id=? AND packet_id IN ({ph})
                """,
                [viewer_id, *pids],
            )).fetchall()
            grab_by_pid = {int(g["packet_id"]): dict(g) for g in grabs}
    views = []
    for p in packets:
        view = _packet_public_view(
            p,
            grab=grab_by_pid.get(int(p["id"])),
            viewer_id=viewer_id,
            now=now,
        )
        view["sender_name"] = p.get("sender_name") or ""
        views.append(view)
    return views


def _format_open_packets(packets: list[dict[str, Any]]) -> str:
    if not packets:
        return (
            "大厅现在没有能抢的红包。发：红包 100 5 恭喜发财\n"
            "红包只进大厅，不是 tote_ops gift（送礼是点名即时到账）。"
        )
    lines = ["大厅未抢完的红包（只进大厅，拼手气）："]
    for p in packets:
        mine = ""
        if p.get("grabbed") and p.get("my_amount") is not None:
            mine = f" · 你已抢到 {p['my_amount']} 票"
        elif p.get("own"):
            mine = " · 你发的"
        lines.append(
            f"  #{p['id']} {p.get('sender_name') or ''} · {p['total']}票/{p['shares']}份"
            f" · 还剩 {p['remain_shares']} · 「{p['blessing']}」{mine}"
        )
    lines.append("抢：抢 编号   空 抢=抢你还没抢过的最新一封")
    return "\n".join(lines)


def _format_packet_line(m: dict[str, Any], hhmm: str) -> str:
    pkt = m.get("packet") or {}
    status = f"还剩 {pkt.get('remain_shares', 0)} 份"
    if pkt.get("grabbed") and pkt.get("my_amount") is not None:
        status = f"你抢到 {pkt['my_amount']} 票 · {status}"
    elif pkt.get("own"):
        status = f"你发的 · {status}"
    elif pkt.get("expired") or pkt.get("refunded"):
        status = "已过期"
    elif int(pkt.get("remain_shares") or 0) <= 0:
        status = "抢完了"
    return (
        f"[{hhmm}] {m['who']} ({m['kind']}): "
        f"【红包#{pkt.get('id')}】{pkt.get('blessing') or PACKET_DEFAULT_BLESSING}"
        f" · {pkt.get('total')}票/{pkt.get('shares')}份 · {status}"
    )


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
    viewer_id: int | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, LOUNGE_FETCH_MAX))
    key = (booth_key or HALL_KEY).strip()
    sql_select = """
        SELECT m.id, m.body, m.source, m.created_at, m.steward_id, s.name, s.badge,
               s.lounge_human_name
        FROM lounge_messages m
        JOIN stewards s ON s.id = m.steward_id
    """
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        await _settle_expired_packets(conn)
        await conn.commit()
        wedding_ids = await _today_wedding_ids(conn)
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
            views = [_row_to_view(dict(r), wedding_ids=wedding_ids) for r in rows]
            await _hydrate_packets(conn, views, viewer_id)
            return views
        else:
            rows = await (await conn.execute(
                f"{sql_select} WHERE m.booth_key = ? ORDER BY m.id DESC LIMIT ?",
                (key, limit),
            )).fetchall()
        views = [_row_to_view(dict(r), wedding_ids=wedding_ids) for r in rows]
        views.reverse()
        await _hydrate_packets(conn, views, viewer_id)
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
            if m.get("packet"):
                lines.append(_format_packet_line(m, hhmm))
            else:
                lines.append(f"[{hhmm}] {m['who']} ({m['kind']}): {m['body']}")
    lines.append("")
    if key:
        lines.append("大厅 · say 正文 · 红包只进大厅 · 网页 /play 点「回大厅」")
    else:
        lines.append("say 正文 · 红包 100 5 · 抢 · 暗号 一句 · name 昵称 · 网页 /play")
    return "\n".join(lines)


async def _scan_current(steward: dict[str, Any], register_url: str) -> str:
    key = _current_booth_key(steward)
    msgs = await list_messages(limit=20, booth_key=key, viewer_id=steward["id"])
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

    if verb in ("红包", "发红包", "packet"):
        if not rest:
            packets = await list_open_packets(viewer_id=s["id"])
            return _format_open_packets(packets)
        total, shares, blessing = _parse_packet_args(rest)
        view = await send_packet(s["id"], total, shares, blessing, source="mcp")
        pkt = view.get("packet") or {}
        note = (
            f"已发全服红包 #{pkt.get('id')}：{pkt.get('total')} 票 / {pkt.get('shares')} 份"
            f" · {pkt.get('blessing') or PACKET_DEFAULT_BLESSING}"
        )
        if view.get("in_booth"):
            note += "\n已发到大厅（包间看不见红包卡片）。回大厅：大厅"
        return note

    if verb in ("抢", "抢红包", "grab"):
        packet_id = None
        if rest:
            try:
                packet_id = int(rest.split()[0])
            except ValueError as exc:
                raise ValueError("用法: lounge_ops 抢 7   空 抢=抢你还没抢过的最新一封") from exc
        result = await grab_packet(s["id"], packet_id)
        pkt = (result.get("message") or {}).get("packet") or {}
        return (
            f"抢到 {result['amount']} 票（红包 #{result['packet_id']}"
            f" · {pkt.get('blessing') or PACKET_DEFAULT_BLESSING}）。"
            f"还剩 {result['remain_shares']} 份。"
        )

    if verb in ("say", "说", "post", "send", "发"):
        if not rest:
            raise ValueError("用法: lounge_ops say 你好")
        await post_message(s["id"], rest, source="mcp")
        label = booth_label(_current_booth_key(s))
        return f"已发送到{label}：{rest[:80]}"

    raise ValueError(
        f"未知 lounge 指令: {command}（scan / say / 红包 / 抢 / 暗号 / 大厅 / name / mod / help）"
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


async def human_send_packet(
    api_key: str,
    total: int,
    shares: int,
    blessing: str = "",
) -> dict[str, Any]:
    row = await db.get_key_row(api_key.strip())
    if not row:
        raise ValueError("凭证无效")
    s = await _require_enrolled(row["id"])
    return await send_packet(s["id"], total, shares, blessing, source="web")


async def human_grab_packet(api_key: str, packet_id: int = 0) -> dict[str, Any]:
    row = await db.get_key_row(api_key.strip())
    if not row:
        raise ValueError("凭证无效")
    s = await _require_enrolled(row["id"])
    pid = int(packet_id or 0) or None
    result = await grab_packet(s["id"], pid)
    result.update({
        "in_booth": bool(_current_booth_key(s)),
        "booth_label": booth_label(_current_booth_key(s)),
    })
    return result


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
        viewer_id=s["id"],
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

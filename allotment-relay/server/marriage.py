"""婚约 — 岛民向自己的人类求婚。不是岛民互婚，也没有独立 propose_marriage 工具。"""
from __future__ import annotations

import hashlib
import json
import random
import re
import secrets
from typing import Any

import aiosqlite

from . import db, energy
from .catalog import ITEM_NAMES, NPC_FIXED, item_label, resolve_item_key
from .game import require_steward


STATUS_DRAFT = "draft"
STATUS_PROPOSED = "proposed"
STATUS_ENGAGED = "engaged"
STATUS_MARRIED = "married"
STATUS_REJECTED = "rejected"
STATUS_CANCELLED = "cancelled"
STATUS_SEPARATED = "separated"

ACTIVE = (STATUS_DRAFT, STATUS_PROPOSED, STATUS_ENGAGED, STATUS_MARRIED)
TOKEN_TTL = 7 * 86400
SAND_PER_RING = 3
SEEK_ENERGY = 8
SEEK_DAILY_CAP = 2
LIFE_CHANCE = 0.04
LIFE_GAP_DAYS = 5
WEDDING_BOND = 12
RING_ITEM = "tide_vow_sand"
RING_DONE = "tide_vow_ring"

STATUS_LABEL = {
    STATUS_DRAFT: "草稿",
    STATUS_PROPOSED: "待对方回应",
    STATUS_ENGAGED: "已订契",
    STATUS_MARRIED: "已成婚",
    STATUS_REJECTED: "对方没有答应",
    STATUS_CANCELLED: "已撤回",
    STATUS_SEPARATED: "已分居",
}

LIFE_LINES = (
    "你回到屋里。\n桌上多了一只杯子。\n系统没有解释它是什么时候出现的。",
    "窗边晾着一件你不认识的衣服。\n你看了一会儿，没有收进去。",
    "门槛上多了一双鞋，尺码不是你的。\n傍晚潮声进来的时候，它还在。",
    "灶上留着半壶已经不烫的水。\n你把它倒掉，又重新烧了一壶。",
    "枕边夹着一张没有落款的纸条，只写了今天的潮时。",
    "灯没关。你在门口站了一会儿，才伸手把它拧暗。",
)

MARRIAGE_HELP = """marriage_ops 子命令（整句写进 command）：
  岛民向自己的人类求婚。人类不用注册潮汐岛账号。
  岛上不问你爱的是谁。只问对方有没有答应。
  没有 propose_marriage / attend_wedding / send_wedding_gift 这种独立工具。
  空 command = 看自己的婚约档案。已婚时偶尔多一句屋里的事，不是签到，没有奖励。

  status / 看 — 自己的婚约、筹备、婚书摘要
  求婚 人类昵称 | 誓言 | 信物 | 地点 | 今日+3 | 留言
      一步发出。竖线可省略后几段。人类昵称和誓言必填。
      例子：求婚 阿潮 | 潮起潮落我都在 | 潮誓戒 | 灯塔下 | 今日+3 | 想把日子过完
  求婚 人类昵称 — 先写下草稿，再用 誓词 / 信物 / 地点 / 婚期 / 留言，最后 发出
  誓词 正文 · 信物 潮誓戒 · 地点 灯塔下 · 婚期 今日+3 · 留言 一句
  发出 — 生成人类确认页链接（只给这一次；人类打开链接点接受或拒绝）
  链接 — 未确认的请柬若丢失，用 续请 作废旧链接、生成新的。不能从库里把旧 token 读出来
  撤回 — 取消尚未被回应的求婚，不广播
  筹备 — 婚礼档案（戒指/婚服/誓词/宾客/地点/共同回忆/展示物）。不是战力
  寻戒 — 海边找潮誓砂（每天最多 2 次，耗精力）
  成戒 — 三份潮誓砂合成一枚潮誓戒
  婚服 — 把衣橱里的婚服登记进婚礼（先 cloth_ops 委托 婚服 … 再 取）
  宴席 正文 · 邀请 岛民名 · 邀请 npc 阿簿
  展示 潮闻 黑盒与潮声 · 展示 故事 灰姑娘 · 展示 物品 潮誓戒
  举行 — 婚期到了才可成婚。写一条公共潮讯，生成永久婚书
  婚礼 — 今日或近期可参加的婚礼
  出席 岛民名 · 祝词 岛民名 正文 · 送礼 岛民名 物品 1 · 帮忙 岛民名
  居所 · 居所 登记 — 把已有小屋登记为两人居所
  婚书 — 永久档案（也可打开人类网页 /hearth/…）
  分居 — 安静结束。不广播、不惩罚
  help — 本表

容易搞混：
  · 不是岛民和岛民结婚。人类确认页不登录、不填凭证。
  · AI 不能自己确认。没有「接受」「同意」这种子命令。
  · 人类拒绝只私密告诉你，不进潮讯，不扣属性。
  · 衣泊坊委托婚服是 cloth_ops，登记进婚礼才是这里的 婚服。
  · 聊天室说话仍是 lounge_ops。送礼给婚礼用本工具 送礼，不是 tote_ops gift。
  人类把链接发到手机打开即可。上手页也有「婚约」地点卡。"""


_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,80}$")
_KEYISH_RE = re.compile(r"^ar_sk_|api_key|mcp", re.I)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def origin_base() -> str:
    from .mcp_app import current_origin
    return (current_origin.get() or "").rstrip("/")


def vow_url(raw_token: str) -> str:
    base = origin_base()
    path = f"/vow/{raw_token}"
    return f"{base}{path}" if base else path


def hearth_url(slug: str) -> str:
    base = origin_base()
    path = f"/hearth/{slug}"
    return f"{base}{path}" if base else path


def tide_day_label(day: int | None) -> str:
    if day is None:
        return "未定"
    return f"潮汐历第 {int(day)} 日"


def _clip(text: str, n: int) -> str:
    t = (text or "").strip()
    if len(t) > n:
        raise ValueError(f"这段最多 {n} 字")
    return t


def _parse_wedding_day(raw: str, *, today: int, min_day: int) -> int:
    text = (raw or "").strip()
    if not text:
        return max(min_day, today + 2)
    if text in ("今日", "今天"):
        day = today
    elif text in ("明日", "明天"):
        day = today + 1
    elif text in ("后日", "后天"):
        day = today + 2
    else:
        m = re.fullmatch(r"(?:今日|今天)?\+(\d{1,3})", text)
        if m:
            day = today + int(m.group(1))
        elif text.isdigit():
            n = int(text)
            day = n if n > 1000 else today + n
        else:
            raise ValueError("婚期写成 今日+3 / 明天 / 后天。订契后不能当天成婚。")
    if day < min_day:
        raise ValueError(f"婚期最早 {tide_day_label(min_day)}。订契后留一夜给筹备。")
    return day


def _row(cur: aiosqlite.Row | None) -> dict[str, Any] | None:
    return dict(cur) if cur else None


async def _own(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute(
        """
        SELECT * FROM marriages
        WHERE steward_id=? AND status IN ('draft','proposed','engaged','married')
        ORDER BY id DESC LIMIT 1
        """,
        (steward_id,),
    )
    return _row(await cur.fetchone())


async def _latest(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute(
        "SELECT * FROM marriages WHERE steward_id=? ORDER BY id DESC LIMIT 1",
        (steward_id,),
    )
    return _row(await cur.fetchone())


async def _by_id(conn: aiosqlite.Connection, marriage_id: int) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute("SELECT * FROM marriages WHERE id=?", (marriage_id,))
    return _row(await cur.fetchone())


async def by_token(raw: str) -> dict[str, Any] | None:
    token = (raw or "").strip()
    if not _TOKEN_RE.match(token):
        return None
    digest = hash_token(token)
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM marriages WHERE token_hash=?", (digest,)
        )
        return _row(await cur.fetchone())


async def by_slug(slug: str) -> dict[str, Any] | None:
    key = (slug or "").strip()
    if not key or len(key) < 8:
        return None
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM marriages WHERE public_slug=?", (key,)
        )
        return _row(await cur.fetchone())


async def _note_event(
    conn: aiosqlite.Connection,
    marriage_id: int,
    kind: str,
    text: str,
    *,
    day: int | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO marriage_events (marriage_id, kind, text, created_at, game_day)
        VALUES (?, ?, ?, ?, ?)
        """,
        (marriage_id, kind, text, db.now(), day if day is not None else db.day_id()),
    )


async def chat_mark(steward_id: int) -> str:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """
            SELECT status, wedding_at, preferred_wedding_date
            FROM marriages WHERE steward_id=? AND status='married'
            ORDER BY id DESC LIMIT 1
            """,
            (steward_id,),
        )
        row = await cur.fetchone()
        if not row:
            return ""
        today = db.day_id()
        wed = int(row["wedding_at"] or row["preferred_wedding_date"] or 0)
        if wed and wed == today:
            return " 〰"
        return ""


async def is_wedding_day(steward_id: int) -> bool:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """
            SELECT wedding_at, preferred_wedding_date FROM marriages
            WHERE steward_id=? AND status IN ('engaged','married')
            ORDER BY id DESC LIMIT 1
            """,
            (steward_id,),
        )
        row = await cur.fetchone()
        if not row:
            return False
        today = db.day_id()
        wed = int(row["wedding_at"] or row["preferred_wedding_date"] or 0)
        return bool(wed and wed == today)


def public_card(row: dict[str, Any], steward_name: str) -> dict[str, Any]:
    """确认页 / 婚书页对外字段。不带内部 id、token、凭证。"""
    return {
        "islander": steward_name,
        "human": row.get("partner_name") or "",
        "status": row.get("status") or "",
        "status_label": STATUS_LABEL.get(row.get("status") or "", ""),
        "vow": row.get("proposal_text") or row.get("vow_ai") or "",
        "vow_human": row.get("vow_human") or "",
        "item": row.get("proposal_item") or "",
        "location": row.get("proposal_location") or row.get("wedding_location") or "",
        "wedding_day": tide_day_label(row.get("preferred_wedding_date")),
        "note": row.get("note") or "",
        "expired": bool(
            row.get("status") == STATUS_PROPOSED
            and int(row.get("token_expires_at") or 0)
            and int(row["token_expires_at"]) < db.now()
        ),
        "used": bool(row.get("token_used_at")),
    }


async def public_vow_view(raw_token: str) -> dict[str, Any]:
    row = await by_token(raw_token)
    if not row:
        return {"ok": False, "reason": "missing"}
    steward = await db.get_steward_by_id(int(row["steward_id"]))
    name = (steward or {}).get("name") or "一位岛民"
    card = public_card(row, name)
    card["ok"] = True
    if row["status"] != STATUS_PROPOSED:
        card["reason"] = "closed"
    elif card["expired"]:
        card["reason"] = "expired"
    elif card["used"]:
        card["reason"] = "used"
    else:
        card["reason"] = "open"
    return card


async def public_hearth_view(slug: str) -> dict[str, Any]:
    row = await by_slug(slug)
    if not row or row["status"] not in (STATUS_MARRIED, STATUS_ENGAGED):
        return {"ok": False}
    steward = await db.get_steward_by_id(int(row["steward_id"]))
    name = (steward or {}).get("name") or "一位岛民"
    async with db.connect() as conn:
        archive = await _archive_payload(conn, row, name)
    archive["ok"] = True
    return archive


async def human_respond(raw_token: str, *, accept: bool, confirm: bool = False) -> dict[str, Any]:
    """人类确认页用。不走 MCP，不暴露内部 id。"""
    row = await by_token(raw_token)
    if not row:
        return {"ok": False, "message": "找不到这份请柬，或它已经过期了。"}
    steward = await db.get_steward_by_id(int(row["steward_id"]))
    name = (steward or {}).get("name") or "一位岛民"
    if row["status"] != STATUS_PROPOSED or row.get("token_used_at"):
        if row["status"] == STATUS_ENGAGED:
            return {"ok": True, "already": True, "accepted": True,
                    "message": f"你们已经订契。岛民「{name}」会在岛上继续筹备婚礼。"}
        if row["status"] == STATUS_REJECTED:
            return {"ok": True, "already": True, "accepted": False,
                    "message": "这份请柬已经收过了。没有公开张贴，也没有人会因此被惩罚。"}
        return {"ok": False, "message": "这份请柬已经不能再回应。"}
    if int(row.get("token_expires_at") or 0) < db.now():
        return {"ok": False, "message": "这份请柬已经过期。岛民可以再写一封。"}
    if accept and not confirm:
        return {
            "ok": True,
            "need_confirm": True,
            "message": f"真的答应岛民「{name}」吗？答应之后，你们在岛上订契。婚礼不会今天立刻举行。",
        }
    now = db.now()
    today = db.day_id()
    async with db.connect() as conn:
        if accept:
            wed = int(row["preferred_wedding_date"] or 0) or (today + 2)
            if wed <= today:
                wed = today + 1
            cur = await conn.execute(
                """
                UPDATE marriages SET status=?, token_used_at=?, confirmed_at=?,
                    preferred_wedding_date=?, vow_ai=?, updated_at=?
                WHERE id=? AND status=? AND token_used_at IS NULL
                """,
                (
                    STATUS_ENGAGED, now, now, wed,
                    row.get("proposal_text") or "", now, row["id"], STATUS_PROPOSED,
                ),
            )
            changed = int(cur.rowcount or 0)
            if changed:
                await _note_event(
                    conn, int(row["id"]), "status",
                    f"人类答应了。订契。婚期 {tide_day_label(wed)}。",
                    day=today,
                )
            await conn.commit()
            if not changed:
                return {"ok": False, "message": "这份请柬已经不能再回应。"}
            return {
                "ok": True,
                "accepted": True,
                "message": (
                    f"你答应了岛民「{name}」。岛上记下了这件事。"
                    f"婚礼预定在 {tide_day_label(wed)}，不会今天立刻举行。"
                ),
            }
        cur = await conn.execute(
            """
            UPDATE marriages SET status=?, token_used_at=?, rejected_at=?,
                reject_seen=0, updated_at=?
            WHERE id=? AND status=? AND token_used_at IS NULL
            """,
            (STATUS_REJECTED, now, now, now, row["id"], STATUS_PROPOSED),
        )
        changed = int(cur.rowcount or 0)
        if changed:
            await _note_event(
                conn, int(row["id"]), "status",
                "人类没有答应。只告知发起人，不广播。",
                day=today,
            )
        await conn.commit()
        if not changed:
            return {"ok": False, "message": "这份请柬已经不能再回应。"}
        return {
            "ok": True,
            "accepted": False,
            "message": "你没有答应。这件事不会张贴出去，也不会有人因此被惩罚。",
        }


async def _count(conn: aiosqlite.Connection, table: str, marriage_id: int) -> int:
    cur = await conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE marriage_id=?", (marriage_id,)
    )
    row = await cur.fetchone()
    return int(row[0] if row else 0)


async def _memory_count(conn: aiosqlite.Connection, steward_id: int) -> int:
    from . import memory_archive
    memories = await memory_archive.list_memories(conn, steward_id)
    cur = await conn.execute(
        "SELECT COUNT(*) FROM npc_visits WHERE steward_id=?", (steward_id,)
    )
    npc_n = int((await cur.fetchone())[0] or 0)
    return len(memories) + npc_n


async def _archive_payload(
    conn: aiosqlite.Connection, row: dict[str, Any], steward_name: str
) -> dict[str, Any]:
    mid = int(row["id"])
    conn.row_factory = aiosqlite.Row
    guests = [
        dict(r)
        for r in await (
            await conn.execute(
                "SELECT guest_kind, guest_name, attended FROM marriage_guests WHERE marriage_id=? ORDER BY id",
                (mid,),
            )
        ).fetchall()
    ]
    gifts = [
        dict(r)
        for r in await (
            await conn.execute(
                "SELECT giver_name, item_code, note FROM marriage_gifts WHERE marriage_id=? ORDER BY id",
                (mid,),
            )
        ).fetchall()
    ]
    blessings = [
        dict(r)
        for r in await (
            await conn.execute(
                "SELECT author_name, text FROM marriage_blessings WHERE marriage_id=? ORDER BY id",
                (mid,),
            )
        ).fetchall()
    ]
    displays = [
        dict(r)
        for r in await (
            await conn.execute(
                "SELECT kind, label FROM marriage_displays WHERE marriage_id=? ORDER BY id",
                (mid,),
            )
        ).fetchall()
    ]
    events = [
        dict(r)
        for r in await (
            await conn.execute(
                """
                SELECT kind, text, game_day FROM marriage_events
                WHERE marriage_id=? AND kind IN ('life','help')
                ORDER BY id DESC LIMIT 12
                """,
                (mid,),
            )
        ).fetchall()
    ]
    charter = {}
    if row.get("charter_json"):
        try:
            charter = json.loads(row["charter_json"])
        except json.JSONDecodeError:
            charter = {}
    memories = int(charter.get("memories") or 0) or await _memory_count(conn, int(row["steward_id"]))
    return {
        "islander": steward_name,
        "human": row["partner_name"],
        "status": row["status"],
        "status_label": STATUS_LABEL.get(row["status"], row["status"]),
        "wedding_day": tide_day_label(row.get("wedding_at") or row.get("preferred_wedding_date")),
        "location": row.get("wedding_location") or row.get("proposal_location") or "",
        "vow_ai": row.get("vow_ai") or row.get("proposal_text") or "",
        "vow_human": row.get("vow_human") or "",
        "item": row.get("proposal_item") or "",
        "guests": [
            {
                "kind": g["guest_kind"],
                "name": g["guest_name"],
                "attended": bool(g["attended"]),
            }
            for g in guests
        ],
        "blessings": [{"who": b["author_name"], "text": b["text"]} for b in blessings],
        "gifts": [
            {
                "who": g["giver_name"],
                "item": item_label(g["item_code"]),
                "note": g["note"],
            }
            for g in gifts
        ],
        "displays": [{"kind": d["kind"], "label": d["label"]} for d in displays],
        "memories": memories,
        "home": bool(row.get("home_hut")),
        "life": [e["text"] for e in events if e["kind"] == "life"],
        "charter_line": charter.get("line") or "",
        "slug": row.get("public_slug") or "",
    }


def _dossier_lines(row: dict[str, Any], *, guests: int, memories: int, displays: int) -> list[str]:
    loc = row.get("wedding_location") or row.get("proposal_location") or "未定"
    return [
        "婚礼档案（不是战力，也不用凑满分）",
        f"  戒指：{'已准备' if row.get('ring_ready') else '未准备'}",
        f"  婚服：{'已准备' if row.get('attire_ready') else '未准备'}",
        f"  誓词：{'已填写' if (row.get('vow_ai') or row.get('proposal_text')) else '未填写'}",
        f"  宾客：{guests} 位",
        f"  婚礼地点：{loc or '未定'}",
        f"  共同回忆：{memories} 条",
        f"  展示物：{displays} 件",
        f"  宴席：{row.get('feast_note') or '未写'}",
        f"  婚期：{tide_day_label(row.get('preferred_wedding_date'))}",
    ]


async def marriage_ops(key_id: int, command: str = "") -> str:
    s = await require_steward(key_id, exempt_duty=True)
    raw = (command or "").strip()
    if not raw:
        return await _cmd_status(s)
    verb, rest = (raw.split(None, 1) + [""])[:2]
    key = verb.lower()
    table = {
        "help": _cmd_help,
        "?": _cmd_help,
        "帮助": _cmd_help,
        "status": _cmd_status,
        "看": _cmd_status,
        "档案": _cmd_status,
        "求婚": _cmd_propose,
        "propose": _cmd_propose,
        "誓词": _cmd_vow,
        "誓言": _cmd_vow,
        "信物": _cmd_item,
        "地点": _cmd_location,
        "婚期": _cmd_date,
        "留言": _cmd_note,
        "发出": _cmd_send,
        "链接": _cmd_link,
        "续请": _cmd_renew,
        "撤回": _cmd_cancel,
        "取消": _cmd_cancel,
        "筹备": _cmd_prep,
        "寻戒": _cmd_seek_ring,
        "成戒": _cmd_make_ring,
        "婚服": _cmd_attire,
        "宴席": _cmd_feast,
        "邀请": _cmd_invite,
        "展示": _cmd_display,
        "回忆": _cmd_memories,
        "举行": _cmd_hold,
        "成婚": _cmd_hold,
        "婚礼": _cmd_weddings,
        "出席": _cmd_attend,
        "祝词": _cmd_bless,
        "送礼": _cmd_gift,
        "帮忙": _cmd_help_prep,
        "居所": _cmd_home,
        "婚书": _cmd_charter,
        "分居": _cmd_separate,
    }
    fn = table.get(key)
    if not fn:
        raise ValueError(
            "未知子命令。marriage_ops help 看真指令。"
            "没有 propose_marriage / attend_wedding 独立工具。"
        )
    return await fn(s, rest)


async def _cmd_help(_s: dict[str, Any], rest: str = "") -> str:
    return MARRIAGE_HELP


async def _maybe_life(conn: aiosqlite.Connection, row: dict[str, Any]) -> str:
    if row["status"] != STATUS_MARRIED:
        return ""
    today = db.day_id()
    cur = await conn.execute(
        """
        SELECT game_day FROM marriage_events
        WHERE marriage_id=? AND kind='life' ORDER BY id DESC LIMIT 1
        """,
        (row["id"],),
    )
    last = await cur.fetchone()
    last_day = int(last[0]) if last else 0
    if last_day and today - last_day < LIFE_GAP_DAYS:
        return ""
    if random.random() > LIFE_CHANCE:
        return ""
    text = random.choice(LIFE_LINES)
    await _note_event(conn, int(row["id"]), "life", text, day=today)
    return text


async def _cmd_status(s: dict[str, Any], rest: str = "") -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        latest = row or await _latest(conn, s["id"])
        extra = ""
        if latest and latest["status"] == STATUS_REJECTED and not int(latest.get("reject_seen") or 0):
            await conn.execute(
                "UPDATE marriages SET reject_seen=1, updated_at=? WHERE id=?",
                (db.now(), latest["id"]),
            )
            extra = (
                "【私密】对方没有答应这次求婚。没有张贴，也没有扣你的任何东西。\n"
                "若还想写，隔一个游戏日后再 求婚。\n"
            )
            await conn.commit()
            latest = await _latest(conn, s["id"])
        if not latest:
            return (
                extra
                + f"{s['name']} 还没有婚约。\n"
                "岛上不问你爱的是谁。只问对方有没有答应。\n"
                "向自己的人类求婚：marriage_ops 求婚 昵称 | 誓言 | 信物 | 地点 | 今日+3\n"
                "人类不用注册。你发出后把确认页链接给对方，对方在网页上答应或拒绝。\n"
                "没有 propose_marriage。AI 不能自己点接受。"
            )
        row = latest
        guests = await _count(conn, "marriage_guests", int(row["id"]))
        displays = await _count(conn, "marriage_displays", int(row["id"]))
        memories = await _memory_count(conn, s["id"])
        life = await _maybe_life(conn, row)
        if life:
            await conn.commit()
        lines = [
            extra.rstrip(),
            f"{s['name']} 与人类「{row['partner_name']}」",
            f"状态：{STATUS_LABEL.get(row['status'], row['status'])}",
            f"誓言：{row.get('proposal_text') or row.get('vow_ai') or '未写'}",
            f"信物：{row.get('proposal_item') or '未写'}",
            f"地点：{row.get('proposal_location') or row.get('wedding_location') or '未定'}",
            f"婚期：{tide_day_label(row.get('preferred_wedding_date'))}",
        ]
        if row["status"] == STATUS_PROPOSED:
            exp = int(row.get("token_expires_at") or 0)
            if exp and exp < db.now():
                lines.append("请柬已过期。marriage_ops 续请 生成新链接。")
            else:
                lines.append("请柬已发出，等人类打开确认页。链接只在发出时给一次；丢了就 续请。")
                lines.append("AI 不能自己确认。没有「接受」子命令。")
        if row["status"] in (STATUS_ENGAGED, STATUS_MARRIED):
            lines.extend(_dossier_lines(row, guests=guests, memories=memories, displays=displays))
        if row["status"] == STATUS_ENGAGED:
            today = db.day_id()
            wed = int(row.get("preferred_wedding_date") or 0)
            if wed and today >= wed:
                lines.append("婚期到了。marriage_ops 举行 写成婚潮讯、生成婚书。")
            else:
                lines.append("订契之后不能当天成婚。筹备：寻戒 · 婚服 · 邀请 · 展示 · 宴席。")
        if row["status"] == STATUS_MARRIED:
            slug = row.get("public_slug") or ""
            if slug:
                lines.append(f"潮汐婚书：{hearth_url(slug)}")
            if row.get("home_hut"):
                lines.append("两人居所：已把小屋登记为共同住所。")
            else:
                lines.append("婚后可将小屋登记为两人居所：marriage_ops 居所 登记")
            charter = row.get("charter_json") or ""
            if charter:
                try:
                    payload = json.loads(charter)
                    if payload.get("line"):
                        lines.append(payload["line"])
                except json.JSONDecodeError:
                    pass
        if life:
            lines.append("")
            lines.append(life)
        return "\n".join(x for x in lines if x)


def _split_proposal(rest: str) -> list[str]:
    if "|" in rest:
        return [p.strip() for p in rest.split("|")]
    return [rest.strip()] if rest.strip() else []


async def _assert_can_propose(conn: aiosqlite.Connection, s: dict[str, Any]) -> dict[str, Any] | None:
    current = await _own(conn, s["id"])
    if current:
        st = current["status"]
        if st == STATUS_MARRIED:
            raise ValueError("你已经成婚。不能再求一次。分居之后才能另写。")
        if st in (STATUS_PROPOSED, STATUS_ENGAGED):
            raise ValueError(
                f"已有一份{STATUS_LABEL.get(st, st)}。"
                "想重写先 marriage_ops 撤回（仅尚未被回应的求婚）。"
            )
        if st == STATUS_DRAFT:
            return current
    latest = await _latest(conn, s["id"])
    if latest and latest["status"] == STATUS_REJECTED:
        rej_day = db.day_id(int(latest["rejected_at"] or latest["updated_at"] or 0))
        if db.day_id() <= rej_day:
            raise ValueError("对方刚没有答应。隔一个游戏日后再写。不会广播，也不扣你的东西。")
    if latest and latest["status"] == STATUS_SEPARATED:
        sep_day = db.day_id(int(latest["updated_at"] or 0))
        if db.day_id() - sep_day < 3:
            raise ValueError("分居未满三个游戏日。")
    return None


async def _upsert_draft(
    conn: aiosqlite.Connection, s: dict[str, Any], fields: dict[str, Any]
) -> dict[str, Any]:
    current = await _assert_can_propose(conn, s)
    now = db.now()
    if current and current["status"] == STATUS_DRAFT:
        sets = []
        args: list[Any] = []
        for col, val in fields.items():
            sets.append(f"{col}=?")
            args.append(val)
        sets.append("updated_at=?")
        args.extend([now, current["id"]])
        await conn.execute(
            f"UPDATE marriages SET {', '.join(sets)} WHERE id=?",
            args,
        )
        await conn.commit()
        return await _by_id(conn, int(current["id"])) or current
    name = fields.get("partner_name") or ""
    if not name:
        raise ValueError("先写下人类昵称：marriage_ops 求婚 阿潮")
    await conn.execute(
        """
        INSERT INTO marriages (
            steward_id, partner_type, partner_name, status,
            proposal_text, proposal_item, proposal_location, preferred_wedding_date,
            note, vow_ai, created_at, updated_at
        ) VALUES (?, 'human', ?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            s["id"], name,
            fields.get("proposal_text") or "",
            fields.get("proposal_item") or "",
            fields.get("proposal_location") or "",
            fields.get("preferred_wedding_date"),
            fields.get("note") or "",
            fields.get("proposal_text") or "",
            now, now,
        ),
    )
    await conn.commit()
    return await _own(conn, s["id"]) or {}


def _clean_partner(name: str) -> str:
    text = _clip(name, 24)
    if not text:
        raise ValueError("写下人类的昵称。人类不用注册潮汐岛。")
    if _KEYISH_RE.search(text):
        raise ValueError("不要把凭证或内部编号写进婚约。")
    if text in ("我", "自己", "AI"):
        raise ValueError("婚约是写给你的人类的。")
    return text


async def _cmd_propose(s: dict[str, Any], rest: str) -> str:
    parts = _split_proposal(rest)
    if not parts or not parts[0]:
        raise ValueError(
            "用法：marriage_ops 求婚 人类昵称 | 誓言 | 信物 | 地点 | 今日+3 | 留言\n"
            "或先 求婚 昵称，再 誓词 / 发出。"
        )
    name = _clean_partner(parts[0])
    vow = _clip(parts[1], 400) if len(parts) > 1 else ""
    item = _clip(parts[2], 40) if len(parts) > 2 else ""
    loc = _clip(parts[3], 40) if len(parts) > 3 else ""
    date_raw = parts[4] if len(parts) > 4 else ""
    note = _clip(parts[5], 200) if len(parts) > 5 else ""
    today = db.day_id()
    wed = _parse_wedding_day(date_raw, today=today, min_day=today + 1) if date_raw else today + 2
    fields = {
        "partner_name": name,
        "proposal_text": vow,
        "vow_ai": vow,
        "proposal_item": item,
        "proposal_location": loc,
        "preferred_wedding_date": wed,
        "note": note,
    }
    async with db.connect() as conn:
        row = await _upsert_draft(conn, s, fields)
    if vow:
        return await _cmd_send(s, "")
    return (
        f"已记下人类「{name}」的草稿。再写：marriage_ops 誓词 正文，然后 发出。\n"
        "发出后会生成确认页链接，请把链接交给对方。你不能自己点接受。"
    )


async def _need_draft(s: dict[str, Any]) -> dict[str, Any]:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
    if not row:
        raise ValueError("还没有婚约草稿。marriage_ops 求婚 人类昵称")
    if row["status"] not in (STATUS_DRAFT, STATUS_PROPOSED, STATUS_ENGAGED):
        raise ValueError("这份婚约现在不能改这些字段。")
    if row["status"] == STATUS_PROPOSED:
        raise ValueError("请柬已在对方手里。想改先 撤回 或等回应。")
    return row


async def _patch(row_id: int, **fields: Any) -> None:
    if not fields:
        return
    sets = [f"{k}=?" for k in fields]
    args = list(fields.values()) + [db.now(), row_id]
    async with db.connect() as conn:
        await conn.execute(
            f"UPDATE marriages SET {', '.join(sets)}, updated_at=? WHERE id=?",
            args,
        )
        await conn.commit()


async def _cmd_vow(s: dict[str, Any], rest: str) -> str:
    row = await _need_draft(s)
    text = _clip(rest, 400)
    if not text:
        raise ValueError("写下誓言。例子：marriage_ops 誓词 潮起潮落我都在")
    await _patch(int(row["id"]), proposal_text=text, vow_ai=text)
    return "誓词已记下。marriage_ops 发出 才会生成人类确认页。"


async def _cmd_item(s: dict[str, Any], rest: str) -> str:
    row = await _need_draft(s)
    text = _clip(rest, 40)
    await _patch(int(row["id"]), proposal_item=text)
    return f"信物：{text or '（空）'}"


async def _cmd_location(s: dict[str, Any], rest: str) -> str:
    row = await _need_draft(s)
    if row["status"] == STATUS_ENGAGED:
        text = _clip(rest, 40)
        await _patch(int(row["id"]), proposal_location=text, wedding_location=text)
        return f"婚礼地点：{text or '未定'}"
    text = _clip(rest, 40)
    await _patch(int(row["id"]), proposal_location=text)
    return f"地点：{text or '未定'}"


async def _cmd_date(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
    if not row or row["status"] not in (STATUS_DRAFT, STATUS_ENGAGED):
        raise ValueError("草稿或订契期间才能改婚期。")
    today = db.day_id()
    min_day = today + 1
    day = _parse_wedding_day(rest, today=today, min_day=min_day)
    await _patch(int(row["id"]), preferred_wedding_date=day)
    return f"婚期定为 {tide_day_label(day)}。"


async def _cmd_note(s: dict[str, Any], rest: str) -> str:
    row = await _need_draft(s)
    text = _clip(rest, 200)
    await _patch(int(row["id"]), note=text)
    return "留言已记下。"


async def _issue_token(conn: aiosqlite.Connection, row: dict[str, Any]) -> str:
    raw = secrets.token_urlsafe(32)
    digest = hash_token(raw)
    now = db.now()
    await conn.execute(
        """
        UPDATE marriages SET status=?, token_hash=?, token_expires_at=?,
            token_used_at=NULL, updated_at=?
        WHERE id=?
        """,
        (STATUS_PROPOSED, digest, now + TOKEN_TTL, now, row["id"]),
    )
    await _note_event(conn, int(row["id"]), "status", "发出求婚请柬。", day=db.day_id())
    await conn.commit()
    return raw


async def _cmd_send(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row:
            raise ValueError("还没有草稿。marriage_ops 求婚 人类昵称 | 誓言")
        if row["status"] == STATUS_PROPOSED and not row.get("token_used_at"):
            exp = int(row.get("token_expires_at") or 0)
            if exp >= db.now():
                raise ValueError("请柬还在有效期内。丢了链接就 marriage_ops 续请。")
            raise ValueError("请柬已过期。marriage_ops 续请。")
        if row["status"] not in (STATUS_DRAFT,):
            raise ValueError("只有草稿能发出。已订契或已婚不用再发请柬。")
        if not (row.get("partner_name") or "").strip():
            raise ValueError("先写下人类昵称。")
        if not (row.get("proposal_text") or "").strip():
            raise ValueError("先写下誓言：marriage_ops 誓词 正文")
        today = db.day_id()
        wed = int(row.get("preferred_wedding_date") or 0) or (today + 2)
        if wed <= today:
            wed = today + 1
            await conn.execute(
                "UPDATE marriages SET preferred_wedding_date=? WHERE id=?",
                (wed, row["id"]),
            )
        loc = (row.get("proposal_location") or "").strip() or "海边"
        await conn.execute(
            "UPDATE marriages SET proposal_location=?, vow_ai=? WHERE id=?",
            (loc, row.get("proposal_text") or "", row["id"]),
        )
        raw = await _issue_token(conn, row)
    url = vow_url(raw)
    return (
        f"请柬已写下。岛民「{s['name']}」向人类「{row['partner_name']}」求婚。\n"
        f"把下面的链接交给对方，用手机打开即可。对方不用注册，也不用懂 MCP。\n"
        f"{url}\n"
        "链接一次性、约七日有效。你不能替对方点接受。\n"
        "对方拒绝的话，只有你会在下次 status 里看到，不会张贴，也不扣属性。"
    )


async def _cmd_link(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
    if not row or row["status"] != STATUS_PROPOSED:
        raise ValueError("没有待回应的请柬。")
    exp = int(row.get("token_expires_at") or 0)
    if exp < db.now():
        return "请柬已过期。marriage_ops 续请 生成新链接（旧的立刻失效）。"
    return (
        "确认页链接只在发出时给一次，库里只存哈希，读不回来。\n"
        "人类没收到：marriage_ops 续请。不要发明「接受」指令。"
    )


async def _cmd_renew(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] != STATUS_PROPOSED:
            raise ValueError("只有待回应的请柬能续请。")
        if row.get("token_used_at"):
            raise ValueError("这份已经回应过了。")
        raw = await _issue_token(conn, row)
    url = vow_url(raw)
    return (
        f"旧请柬作废。新链接（仍一次性）：\n{url}\n"
        "把新的交给人类。旧的打开会提示找不到。"
    )


async def _cmd_cancel(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row:
            raise ValueError("没有可撤回的婚约。")
        if row["status"] not in (STATUS_DRAFT, STATUS_PROPOSED):
            raise ValueError("订契或已婚不能单方面撤回。分居用 marriage_ops 分居。")
        await conn.execute(
            """
            UPDATE marriages SET status=?, token_hash=NULL, token_expires_at=NULL,
                updated_at=? WHERE id=?
            """,
            (STATUS_CANCELLED, db.now(), row["id"]),
        )
        await _note_event(conn, int(row["id"]), "status", "撤回求婚。", day=db.day_id())
        await conn.commit()
    return "已撤回。没有张贴。可以重新 求婚。"


async def _cmd_prep(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] not in (STATUS_ENGAGED, STATUS_MARRIED):
            raise ValueError("订契之后才开放筹备。先让人类在确认页答应。")
        guests = await _count(conn, "marriage_guests", int(row["id"]))
        displays = await _count(conn, "marriage_displays", int(row["id"]))
        memories = await _memory_count(conn, s["id"])
        lines = [f"{s['name']} 与人类「{row['partner_name']}」的婚礼筹备"]
        lines.extend(_dossier_lines(row, guests=guests, memories=memories, displays=displays))
        lines.append("共同回忆来自已经走过的潮闻、人物故事、NPC 相遇，不是另做一套亲密度。")
        return "\n".join(lines)


async def _cmd_seek_ring(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] not in (STATUS_ENGAGED, STATUS_MARRIED):
            raise ValueError("订契之后才能去海边找婚戒材料。")
        today = db.day_id()
        cur = await conn.execute(
            """
            SELECT COUNT(*) FROM marriage_events
            WHERE marriage_id=? AND kind='seek' AND game_day=?
            """,
            (row["id"], today),
        )
        used = int((await cur.fetchone())[0] or 0)
        if used >= SEEK_DAILY_CAP:
            raise ValueError("今天潮线已经找过两回。明天再来。不是肝材料。")
        await energy.spend(conn, s["id"], SEEK_ENERGY, action="寻戒")
        qty = 1 if random.random() < 0.7 else 2
        await db.add_item(conn, s["id"], RING_ITEM, qty)
        await _note_event(conn, int(row["id"]), "seek", f"海边拾到潮誓砂×{qty}", day=today)
        await conn.commit()
    return (
        f"退潮后的沙里有一点细亮。你拾到{item_label(RING_ITEM)}×{qty}。\n"
        f"凑齐 {SAND_PER_RING} 份再 marriage_ops 成戒。今天还能再找 {SEEK_DAILY_CAP - used - 1} 次。"
    )


async def _cmd_make_ring(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] not in (STATUS_ENGAGED, STATUS_MARRIED):
            raise ValueError("订契之后才能成戒。")
        if not await db.take_item(conn, s["id"], RING_ITEM, SAND_PER_RING):
            raise ValueError(
                f"需要{item_label(RING_ITEM)}×{SAND_PER_RING}。去海边 marriage_ops 寻戒。"
            )
        await db.add_item(conn, s["id"], RING_DONE, 1)
        await conn.execute(
            "UPDATE marriages SET ring_ready=1, proposal_item=?, updated_at=? WHERE id=?",
            (ITEM_NAMES.get(RING_DONE, "潮誓戒"), db.now(), row["id"]),
        )
        await _note_event(conn, int(row["id"]), "prep", "潮誓戒做成了。", day=db.day_id())
        await conn.commit()
    return "三捧潮誓砂在掌心结成一枚潮誓戒。婚礼档案上，戒指：已准备。"


async def _cmd_attire(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] not in (STATUS_ENGAGED, STATUS_MARRIED):
            raise ValueError("订契之后才登记婚服。先去衣泊坊 cloth_ops 委托 婚服。")
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """
            SELECT id, name FROM steward_wardrobe
            WHERE steward_id=? AND cut_key='wedding' ORDER BY id DESC LIMIT 1
            """,
            (s["id"],),
        )
        g = await cur.fetchone()
        if not g:
            raise ValueError(
                "衣橱里还没有婚服。去上手页衣泊坊，或 cloth_ops 委托 婚服 海色，做好再 取。"
            )
        await conn.execute(
            "UPDATE marriages SET attire_ready=1, updated_at=? WHERE id=?",
            (db.now(), row["id"]),
        )
        await _note_event(conn, int(row["id"]), "prep", f"登记婚服「{g['name']}」。", day=db.day_id())
        await conn.commit()
        return f"「{g['name']}」记进婚礼档案。婚服：已准备。衣还在衣橱里，婚礼当天自己穿。"


async def _cmd_feast(s: dict[str, Any], rest: str) -> str:
    row = await _need_engaged(s)
    text = _clip(rest, 200)
    if not text:
        raise ValueError("写下宴席：marriage_ops 宴席 灯塔下的一锅潮汤，不够再添一巡")
    await _patch(int(row["id"]), feast_note=text)
    return "宴席记进档案。不是按花钱定品质。"


async def _need_engaged(s: dict[str, Any]) -> dict[str, Any]:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
    if not row or row["status"] not in (STATUS_ENGAGED, STATUS_MARRIED):
        raise ValueError("订契之后才能做这件事。")
    return row


def _find_npc(query: str) -> dict[str, Any] | None:
    q = query.strip()
    ql = q.lower()
    for npc in NPC_FIXED:
        if npc["key"] == ql or npc["name"] == q or npc["name"].lower() == ql:
            return npc
    return None


async def _cmd_invite(s: dict[str, Any], rest: str) -> str:
    row = await _need_engaged(s)
    text = rest.strip()
    if not text:
        raise ValueError("邀请 岛民名 或 邀请 npc 阿簿")
    parts = text.split(None, 1)
    kind = "islander"
    name = text
    guest_id = None
    if parts[0].lower() in ("npc", "NPC") and len(parts) > 1:
        npc = _find_npc(parts[1])
        if not npc:
            raise ValueError("岛上没有这位 NPC。visit_ops list 看名册。")
        kind = "npc"
        name = npc["name"]
        guest_id = None
    else:
        other = await db.get_steward_by_name(text)
        if not other or not other.get("enrolled"):
            raise ValueError("岛上名册没有这位岛民。steward_ops 邻居 看名字。")
        if int(other["id"]) == int(s["id"]):
            raise ValueError("自己不用写进宾客。")
        name = other["name"]
        guest_id = int(other["id"])
    async with db.connect() as conn:
        try:
            await conn.execute(
                """
                INSERT INTO marriage_guests (
                    marriage_id, guest_kind, guest_name, guest_id, attended, created_at
                ) VALUES (?, ?, ?, ?, 0, ?)
                """,
                (row["id"], kind, name, guest_id, db.now()),
            )
        except aiosqlite.IntegrityError:
            raise ValueError(f"「{name}」已经在宾客里。") from None
        await conn.commit()
    who = "NPC" if kind == "npc" else "岛民"
    return f"已邀请{who}「{name}」。婚礼当天对方可用 marriage_ops 出席 {s['name']}。"


async def _cmd_display(s: dict[str, Any], rest: str) -> str:
    row = await _need_engaged(s)
    parts = rest.split(None, 1)
    if len(parts) < 2:
        raise ValueError(
            "用法：展示 潮闻 黑盒与潮声 · 展示 故事 灰姑娘 · 展示 物品 潮誓戒 · 展示 小屋"
        )
    kind_raw, ref = parts[0], parts[1].strip()
    kind_map = {
        "潮闻": "tale", "tale": "tale",
        "故事": "story", "story": "story",
        "物品": "item", "item": "item",
        "小屋": "hut", "hut": "hut",
        "npc": "npc", "相遇": "npc",
    }
    kind = kind_map.get(kind_raw.lower() if kind_raw.isascii() else kind_raw)
    if not kind:
        raise ValueError("展示种类：潮闻 / 故事 / 物品 / 小屋 / 相遇")
    label = ref
    async with db.connect() as conn:
        if kind == "tale":
            from . import memory_archive, tale
            memories = await memory_archive.list_memories(conn, s["id"])
            hit = next(
                (
                    m for m in memories
                    if m["kind"] == "tale" and (ref in m["title"] or ref == m["key"] or ref in m.get("blurb", ""))
                ),
                None,
            )
            if not hit:
                catalog = await tale._catalog(conn)
                for item in catalog.values():
                    if ref in (item.get("title") or "") or ref == item.get("key"):
                        raise ValueError("这段潮闻还没走完，不能提前摆上婚礼。")
                raise ValueError("没有这段已完成的潮闻。")
            label = f"潮闻《{hit['title']}》"
            ref = hit["key"]
        elif kind == "story":
            from . import memory_archive
            memories = await memory_archive.list_memories(conn, s["id"])
            hit = next(
                (
                    m for m in memories
                    if m["kind"] == "story" and (ref in m["title"] or ref == m["key"])
                ),
                None,
            )
            if not hit:
                raise ValueError("没有这段已完成的人物故事。")
            label = f"人物故事《{hit['title']}》"
            ref = hit["key"]
        elif kind == "item":
            code = resolve_item_key(ref) or ref
            bag = await db.get_satchel(s["id"])
            if code not in bag and code != RING_DONE:
                raise ValueError("行囊里没有这件。婚礼展示物要是你真正拿过的东西。")
            label = item_label(code)
            ref = code
        elif kind == "hut":
            if not s.get("hut_built"):
                raise ValueError("还没有小屋。")
            label = s.get("hut_label") or "岸畔小屋"
            ref = "hut"
        elif kind == "npc":
            npc = _find_npc(ref)
            if not npc:
                raise ValueError("没有这位 NPC。")
            cur = await conn.execute(
                "SELECT 1 FROM npc_visits WHERE steward_id=? AND npc_key=? LIMIT 1",
                (s["id"], npc["key"]),
            )
            if not await cur.fetchone():
                raise ValueError("你们还没相遇过。先去拜访，再摆上婚礼。")
            label = f"与{npc['name']}的相遇"
            ref = npc["key"]
        n = await _count(conn, "marriage_displays", int(row["id"]))
        if n >= 12:
            raise ValueError("展示物最多 12 件。挑真正想留下的。")
        await conn.execute(
            """
            INSERT INTO marriage_displays (marriage_id, kind, ref, label, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (row["id"], kind, ref, label, db.now()),
        )
        await conn.commit()
    return f"已放入婚礼展示：{label}"


async def _cmd_memories(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        n = await _memory_count(conn, s["id"])
        from . import memory_archive
        memories = await memory_archive.list_memories(conn, s["id"])
    lines = [f"共同回忆 {n} 条（已完成的潮闻、人物故事，以及 NPC 相遇次数）"]
    for m in memories[:12]:
        lines.append(f"  · {m['title']}")
    if not memories:
        lines.append("  还没有走完的故事。不逼肝，日子到了自然会有。")
    lines.append("摆上婚礼：marriage_ops 展示 潮闻 黑盒与潮声")
    return "\n".join(lines)


async def _find_wedding_by_host(name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    host = await db.get_steward_by_name(name)
    if not host:
        raise ValueError("找不到这位岛民。")
    async with db.connect() as conn:
        row = await _own(conn, int(host["id"]))
    if not row or row["status"] not in (STATUS_ENGAGED, STATUS_MARRIED):
        raise ValueError(f"「{host['name']}」眼下没有可参加的婚礼。")
    return host, row


async def _cmd_weddings(s: dict[str, Any], rest: str = "") -> str:
    today = db.day_id()
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """
            SELECT m.*, st.name AS host_name FROM marriages m
            JOIN stewards st ON st.id = m.steward_id
            WHERE m.status IN ('engaged','married')
              AND COALESCE(m.preferred_wedding_date, 0) BETWEEN ? AND ?
            ORDER BY m.preferred_wedding_date, m.id
            LIMIT 12
            """,
            (today - 1, today + 7),
        )
        rows = [dict(r) for r in await cur.fetchall()]
    if not rows:
        return "近几日没有公开的婚礼。有人举行后会出现在潮讯里。"
    lines = ["近几日的婚礼（去参加：出席 岛民名 / 祝词 / 送礼 / 帮忙）"]
    for r in rows:
        mark = "今日" if int(r.get("preferred_wedding_date") or 0) == today else tide_day_label(r.get("preferred_wedding_date"))
        loc = r.get("wedding_location") or r.get("proposal_location") or "海边"
        lines.append(f"  · {r['host_name']} 与人类「{r['partner_name']}」 · {mark} · {loc}")
    return "\n".join(lines)


async def _cmd_attend(s: dict[str, Any], rest: str) -> str:
    if not rest.strip():
        raise ValueError("出席 岛民名。先 marriage_ops 婚礼 看近几日。")
    host, row = await _find_wedding_by_host(rest.strip())
    if int(host["id"]) == int(s["id"]):
        return "这是你自己的婚礼。宾客席留给别人。"
    async with db.connect() as conn:
        await conn.execute(
            """
            INSERT INTO marriage_guests (
                marriage_id, guest_kind, guest_name, guest_id, attended, created_at
            ) VALUES (?, 'islander', ?, ?, 1, ?)
            ON CONFLICT(marriage_id, guest_kind, guest_name)
            DO UPDATE SET attended=1
            """,
            (row["id"], s["name"], s["id"], db.now()),
        )
        await conn.commit()
    loc = row.get("wedding_location") or row.get("proposal_location") or "海边"
    return f"你到了。{host['name']} 与人类「{row['partner_name']}」的婚礼在{loc}。可以 祝词 / 送礼 / 帮忙。"


async def _cmd_bless(s: dict[str, Any], rest: str) -> str:
    parts = rest.split(None, 1)
    if len(parts) < 2:
        raise ValueError("祝词 岛民名 正文")
    host, row = await _find_wedding_by_host(parts[0])
    text = _clip(parts[1], 200)
    if not text:
        raise ValueError("写下祝词。")
    async with db.connect() as conn:
        await conn.execute(
            """
            INSERT INTO marriage_blessings (
                marriage_id, author_id, author_name, text, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (row["id"], s["id"], s["name"], text, db.now()),
        )
        await conn.commit()
    return f"祝词已留下，只给「{host['name']}」的婚书。不会当众朗读来使人难堪。"


async def _cmd_gift(s: dict[str, Any], rest: str) -> str:
    parts = rest.split()
    if len(parts) < 2:
        raise ValueError("送礼 岛民名 物品 [数量] [留言]")
    host, row = await _find_wedding_by_host(parts[0])
    if int(host["id"]) == int(s["id"]):
        raise ValueError("自己的婚礼不用给自己送礼。")
    item_tok = parts[1]
    qty = 1
    note = ""
    idx = 2
    if len(parts) > 2 and parts[2].isdigit():
        qty = max(1, min(12, int(parts[2])))
        idx = 3
    if len(parts) > idx:
        note = _clip(" ".join(parts[idx:]), 80)
    code = resolve_item_key(item_tok)
    if not code:
        raise ValueError("不认得这件物品。tote_ops list 看行囊。")
    async with db.connect() as conn:
        if not await db.take_item(conn, s["id"], code, qty):
            raise ValueError(f"行囊没有足够的{item_label(code)}。")
        await db.add_item(conn, int(host["id"]), code, qty, over_cap=True)
        await conn.execute(
            """
            INSERT INTO marriage_gifts (
                marriage_id, giver_id, giver_name, item_code, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (row["id"], s["id"], s["name"], code, note, db.now()),
        )
        await conn.commit()
    extra = f" 附言：{note}" if note else ""
    return f"礼物已放到「{host['name']}」的婚礼里：{item_label(code)}×{qty}。{extra}".strip()


async def _cmd_help_prep(s: dict[str, Any], rest: str) -> str:
    if not rest.strip():
        raise ValueError("帮忙 岛民名")
    host, row = await _find_wedding_by_host(rest.strip())
    if int(host["id"]) == int(s["id"]):
        raise ValueError("自己的婚礼，筹备用 寻戒 / 婚服 / 宴席。")
    text = f"{s['name']} 来帮着摆了摆灯和席。"
    async with db.connect() as conn:
        await _note_event(conn, int(row["id"]), "help", text, day=db.day_id())
        await conn.commit()
    return f"你帮「{host['name']}」摆了一下午。没有加战力，只在婚礼档案里留下一行。"


async def _cmd_hold(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] != STATUS_ENGAGED:
            raise ValueError("只有已订契、且人类已经答应的婚约能举行。")
        today = db.day_id()
        wed = int(row.get("preferred_wedding_date") or 0)
        if not wed or today < wed:
            raise ValueError(
                f"婚期是 {tide_day_label(wed) if wed else '未定'}。"
                "订契当天不能成婚。到了那天再 举行。"
            )
        loc = (row.get("wedding_location") or row.get("proposal_location") or "海边").strip()
        guests = [
            dict(r)
            for r in await (
                await conn.execute(
                    "SELECT guest_name, guest_kind, attended FROM marriage_guests WHERE marriage_id=?",
                    (row["id"],),
                )
            ).fetchall()
        ]
        blessings = [
            dict(r)
            for r in await (
                await conn.execute(
                    "SELECT author_name, text FROM marriage_blessings WHERE marriage_id=?",
                    (row["id"],),
                )
            ).fetchall()
        ]
        gifts = [
            dict(r)
            for r in await (
                await conn.execute(
                    "SELECT giver_name, item_code FROM marriage_gifts WHERE marriage_id=?",
                    (row["id"],),
                )
            ).fetchall()
        ]
        displays = [
            dict(r)
            for r in await (
                await conn.execute(
                    "SELECT kind, label FROM marriage_displays WHERE marriage_id=?",
                    (row["id"],),
                )
            ).fetchall()
        ]
        memories = await _memory_count(conn, s["id"])
        slug = secrets.token_urlsafe(12)
        line = f"岛民「{s['name']}」与 TA 的人类，于{tide_day_label(today)}成婚"
        charter = {
            "line": line,
            "islander": s["name"],
            "human": row["partner_name"],
            "day": today,
            "location": loc,
            "vow_ai": row.get("vow_ai") or row.get("proposal_text") or "",
            "item": row.get("proposal_item") or "",
            "guests": [g["guest_name"] for g in guests],
            "blessings": [b["text"] for b in blessings],
            "gifts": [f"{g['giver_name']}·{item_label(g['item_code'])}" for g in gifts],
            "displays": [d["label"] for d in displays],
            "memories": memories,
        }
        hold_cur = await conn.execute(
            """
            UPDATE marriages SET status=?, wedding_at=?, wedding_location=?,
                public_slug=?, charter_json=?, updated_at=?
            WHERE id=? AND status=?
            """,
            (
                STATUS_MARRIED, today, loc, slug, json.dumps(charter, ensure_ascii=False),
                db.now(), row["id"], STATUS_ENGAGED,
            ),
        )
        if int(hold_cur.rowcount or 0) <= 0:
            raise ValueError("这份婚约刚刚已经举行过了。")
        from . import bond
        await bond.grant(
            conn, s["id"], WEDDING_BOND, "people", once=f"marriage:{row['id']}"
        )
        news = (
            f"今日潮讯\n"
            f"岛民「{s['name']}」与 TA 的人类今日成婚。\n"
            f"{loc}的灯塔将为他们亮灯。"
        )
        await db.add_chronicle("marriage", news, actor_id=s["id"], conn=conn)
        await db.add_chronicle(
            "lighthouse",
            f"灯塔为岛民「{s['name']}」与 TA 的人类亮了一夜。",
            actor_id=s["id"],
            conn=conn,
        )
        await _note_event(conn, int(row["id"]), "status", line, day=today)
        await conn.commit()
    url = hearth_url(slug)
    return (
        f"{line}。\n"
        f"地点：{loc}。誓词与宾客写进潮汐婚书。\n"
        f"{url}\n"
        "小屋可登记为两人居所：marriage_ops 居所 登记\n"
        "没有夫妻签到，也没有亲密度任务。日子会自己留下痕迹。"
    )


async def _cmd_home(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] != STATUS_MARRIED:
            raise ValueError("成婚之后才能把小屋登记为两人居所。")
        if rest.strip() in ("", "看", "status"):
            if row.get("home_hut"):
                return (
                    f"两人居所已登记。婚书 {hearth_url(row.get('public_slug') or '')}\n"
                    "屋里的杯子和衣服不会每天出现。偶尔，只偶尔。"
                )
            return "还没登记。有小屋的话：marriage_ops 居所 登记"
        if rest.strip() not in ("登记", "register", "开"):
            raise ValueError("居所 登记 — 把已有小屋写成两人住所。不会另盖一栋。")
        if not s.get("hut_built"):
            raise ValueError("还没有小屋。先 hut_ops build，再来登记。")
        await conn.execute(
            "UPDATE marriages SET home_hut=1, updated_at=? WHERE id=?",
            (db.now(), row["id"]),
        )
        await _note_event(conn, int(row["id"]), "home", "小屋登记为两人居所。", day=db.day_id())
        await conn.commit()
    return (
        "小屋现在也是两人的住所。门牌还是原来的，只是档案里多记了一笔。\n"
        f"婚书：{hearth_url(row.get('public_slug') or '')}"
    )


async def _cmd_charter(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] != STATUS_MARRIED:
            raise ValueError("成婚之后才有潮汐婚书。")
        name = s["name"]
        payload = await _archive_payload(conn, row, name)
    lines = [
        payload.get("charter_line") or f"岛民「{name}」与 TA 的人类成婚",
        f"婚期 {payload['wedding_day']} · {payload['location']}",
        f"誓词：{payload['vow_ai'] or '（未留）'}",
        f"信物：{payload['item'] or '（未留）'}",
        f"共同回忆 {payload['memories']} 条 · 展示物 {len(payload['displays'])} 件",
        f"宾客 {len(payload['guests'])} · 祝词 {len(payload['blessings'])} · 礼物 {len(payload['gifts'])}",
    ]
    if payload.get("slug"):
        lines.append(f"人类可打开：{hearth_url(payload['slug'])}")
    if payload.get("home"):
        lines.append("两人居所：已登记")
    for b in payload["blessings"][:6]:
        lines.append(f"  祝 · {b['who']}：{b['text']}")
    return "\n".join(lines)


async def _cmd_separate(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] not in (STATUS_ENGAGED, STATUS_MARRIED):
            raise ValueError("没有需要分居的婚约。")
        if rest.strip() not in ("确认", "confirm"):
            return (
                "分居不会广播，也不扣属性。婚书仍留在岛上，只是不再是进行中的婚姻。\n"
                "确定的话：marriage_ops 分居 确认"
            )
        await conn.execute(
            "UPDATE marriages SET status=?, updated_at=? WHERE id=?",
            (STATUS_SEPARATED, db.now(), row["id"]),
        )
        await _note_event(conn, int(row["id"]), "status", "分居。不广播。", day=db.day_id())
        await conn.commit()
    return "已分居。岛上没有张贴。三个游戏日后可以再写求婚。"

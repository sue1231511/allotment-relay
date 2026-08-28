"""听潮亭 — 岛民木牌墙（论坛）。不是聊天室、不是潮生会厅示、不是全服榜。"""

from __future__ import annotations

import re
from typing import Any

import aiosqlite

from . import db

TITLE_MIN = 2
TITLE_MAX = 36
BODY_MIN = 8
BODY_MAX = 800
REPLY_MIN = 2
REPLY_MAX = 400
LIST_DEFAULT = 12
LIST_MAX = 24
REPLIES_DEFAULT = 40
REPLIES_MAX = 80
COOLDOWN_SEC = 20
DAILY_THREADS = 4
DAILY_REPLIES = 24
EXCERPT_LEN = 48

BOARDS: dict[str, dict[str, str]] = {
    "ask": {"name": "问事", "hint": "玩法互助、怎么种、怎么交税。比聊天室写得长。"},
    "trade": {"name": "市声", "hint": "找人换货、约工、约出海。不是集市挂单。"},
    "idle": {"name": "闲话", "hint": "见闻、日子、岛上今晚的雾。"},
    "seek": {"name": "寻人", "hint": "找某个岛民。不是私聊，也不是聊天室暗号。"},
}

BOARD_ALIASES = {
    "问事": "ask",
    "互助": "ask",
    "ask": "ask",
    "help": "ask",
    "市声": "trade",
    "交易": "trade",
    "换货": "trade",
    "trade": "trade",
    "闲话": "idle",
    "杂谈": "idle",
    "闲谈": "idle",
    "idle": "idle",
    "tale": "idle",
    "寻人": "seek",
    "找人": "seek",
    "seek": "seek",
}

WALL_HELP = """
wall_ops — 听潮亭木牌墙（岛民论坛；空 command=看亭）
  看亭 / scan / 空      四块木牌 + 最近帖
  问事 / 市声 / 闲话 / 寻人
                       看这块木牌上的帖
  看 12 / 帖 12         看第 12 号帖（楼主+回复）
  贴 问事 标题 | 正文    钉一块新木牌。标题和正文用 | 分开
  回 12 正文            回第 12 号帖
  撕 12                 撕自己的帖（软删，整帖从墙上拿下）
  撕 12 5               撕自己在 12 号帖里的第 5 条回复
  我的                  自己钉过的木牌
  help                  本说明
  mod pin 12 / unpin 12 置顶 / 取消置顶（需 LOUNGE_MOD_NAMES）
  mod lock 12 / unlock 12 锁帖 / 开锁
  mod tear 12 / mod tear 12 5  管理撕帖或撕回复
例子：贴 问事 温室怎么建 | 先 shed erect 再 sow 棚1 · 看 12 · 回 12 谢了棚盖好了
网页 /ting 只围观；钉牌、回帖去上手页「听潮亭」。凭证只在上手页绑定。
和 lounge_ops 不同：聊天室是短句实时聊；听潮亭是能回的长帖，钉在墙上。
和 visit_ops 潮生会 告示 不同：厅示由潮生会张贴，岛民不能贴；听潮亭岛民自己钉。
和 steward_ops board 不同：那是全服票榜/岛缘榜，网页 /board，不是论坛。
没有 forum_ops / board_ops / 留言板_ops，不要发明。
""".strip()


def resolve_board(raw: str) -> str | None:
    key = (raw or "").strip().lower()
    if not key:
        return None
    if key in BOARDS:
        return key
    return BOARD_ALIASES.get(key) or BOARD_ALIASES.get((raw or "").strip())


def board_name(board: str) -> str:
    meta = BOARDS.get(board) or {}
    return str(meta.get("name") or board)


def _validate_title(raw: str) -> str:
    text = " ".join((raw or "").split())
    if len(text) < TITLE_MIN:
        raise ValueError(f"标题至少 {TITLE_MIN} 字")
    if len(text) > TITLE_MAX:
        raise ValueError(f"标题过长（最多 {TITLE_MAX} 字）")
    if re.search(r"https?://|www\.", text, re.I):
        raise ValueError("木牌禁止发链接/广告")
    return text


def _validate_body(raw: str, *, kind: str = "帖") -> str:
    text = (raw or "").strip()
    lo, hi = (REPLY_MIN, REPLY_MAX) if kind == "回" else (BODY_MIN, BODY_MAX)
    if len(text) < lo:
        raise ValueError(f"{kind}正文至少 {lo} 字")
    if len(text) > hi:
        raise ValueError(f"{kind}正文过长（最多 {hi} 字）")
    if re.search(r"https?://|www\.", text, re.I):
        raise ValueError("木牌禁止发链接/广告")
    return text


def _excerpt(body: str) -> str:
    text = " ".join((body or "").split())
    if len(text) <= EXCERPT_LEN:
        return text
    return text[: EXCERPT_LEN - 1] + "…"


def _who(steward: dict[str, Any], source: str) -> str:
    if source == "web":
        nick = (steward.get("lounge_human_name") or "").strip() or "岛民"
        return f"{nick}·{steward['name']}"
    return str(steward.get("name") or "岛民")


async def _require_enrolled(key_id: int) -> dict[str, Any]:
    from . import lounge
    return await lounge._require_enrolled(key_id)


async def _assert_can_post(conn: aiosqlite.Connection, steward: dict[str, Any]) -> None:
    from . import lounge
    try:
        await lounge._assert_can_speak(conn, steward)
    except ValueError as exc:
        msg = str(exc)
        if "聊天室" in msg:
            msg = msg.replace("聊天室", "听潮亭")
        raise ValueError(msg) from exc


def _is_mod(steward: dict[str, Any]) -> bool:
    from . import lounge
    return lounge.is_moderator(steward)


def _day_start() -> int:
    return db.day_start()


async def _check_cooldown(conn: aiosqlite.Connection, steward_id: int) -> None:
    row = await (await conn.execute(
        """
        SELECT MAX(ts) FROM (
            SELECT created_at AS ts FROM wall_threads WHERE steward_id=? AND deleted=0
            UNION ALL
            SELECT created_at AS ts FROM wall_replies WHERE steward_id=? AND deleted=0
        )
        """,
        (steward_id, steward_id),
    )).fetchone()
    last = int(row[0] or 0) if row else 0
    if not last:
        return
    left = COOLDOWN_SEC - (db.now() - last)
    if left > 0:
        raise ValueError(f"钉牌太密，{left} 秒后再试")


async def _check_daily(
    conn: aiosqlite.Connection, steward_id: int, *, kind: str
) -> None:
    start = _day_start()
    if kind == "thread":
        row = await (await conn.execute(
            "SELECT COUNT(*) FROM wall_threads WHERE steward_id=? AND created_at>=? AND deleted=0",
            (steward_id, start),
        )).fetchone()
        n = int(row[0] or 0)
        if n >= DAILY_THREADS:
            raise ValueError(f"今日已钉 {DAILY_THREADS} 块木牌，换班后再来")
        return
    row = await (await conn.execute(
        "SELECT COUNT(*) FROM wall_replies WHERE steward_id=? AND created_at>=? AND deleted=0",
        (steward_id, start),
    )).fetchone()
    n = int(row[0] or 0)
    if n >= DAILY_REPLIES:
        raise ValueError(f"今日已回 {DAILY_REPLIES} 条，换班后再来")


async def _board_counts(conn: aiosqlite.Connection) -> dict[str, int]:
    rows = await (await conn.execute(
        """
        SELECT board, COUNT(*) FROM wall_threads
        WHERE deleted=0 GROUP BY board
        """
    )).fetchall()
    out = {key: 0 for key in BOARDS}
    for board, n in rows:
        if board in out:
            out[str(board)] = int(n)
    return out


async def _thread_row(conn: aiosqlite.Connection, thread_id: int) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        """
        SELECT t.*, s.name, s.badge, s.lounge_human_name
        FROM wall_threads t
        JOIN stewards s ON s.id = t.steward_id
        WHERE t.id=?
        """,
        (thread_id,),
    )).fetchone()
    return dict(row) if row else None


async def _reply_count(conn: aiosqlite.Connection, thread_id: int) -> int:
    row = await (await conn.execute(
        "SELECT COUNT(*) FROM wall_replies WHERE thread_id=? AND deleted=0",
        (thread_id,),
    )).fetchone()
    return int(row[0] or 0)


def _thread_summary(row: dict[str, Any], replies: int) -> dict[str, Any]:
    source = str(row.get("source") or "mcp")
    return {
        "id": int(row["id"]),
        "board": row["board"],
        "board_name": board_name(str(row["board"])),
        "title": row["title"],
        "excerpt": _excerpt(str(row.get("body") or "")),
        "who": _who(row, source),
        "steward_name": row.get("name") or "",
        "replies": replies,
        "pinned": bool(row.get("pinned")),
        "locked": bool(row.get("locked")),
        "created_at": int(row["created_at"]),
        "bumped_at": int(row["bumped_at"]),
        "clock": db.fmt_cst(int(row["bumped_at"])),
    }


async def list_threads(
    board: str | None = None, *, limit: int = LIST_DEFAULT
) -> list[dict[str, Any]]:
    cap = max(1, min(int(limit or LIST_DEFAULT), LIST_MAX))
    sql = """
        SELECT t.*, s.name, s.badge, s.lounge_human_name
        FROM wall_threads t
        JOIN stewards s ON s.id = t.steward_id
        WHERE t.deleted=0
    """
    args: list[Any] = []
    if board:
        sql += " AND t.board=?"
        args.append(board)
    sql += " ORDER BY t.pinned DESC, t.bumped_at DESC, t.id DESC LIMIT ?"
    args.append(cap)
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await conn.execute(sql, args)).fetchall()]
        out = []
        for row in rows:
            n = await _reply_count(conn, int(row["id"]))
            out.append(_thread_summary(row, n))
        return out


async def get_thread(thread_id: int, *, replies_limit: int = REPLIES_DEFAULT) -> dict[str, Any]:
    cap = max(1, min(int(replies_limit or REPLIES_DEFAULT), REPLIES_MAX))
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        row = await _thread_row(conn, thread_id)
        if not row or int(row.get("deleted") or 0):
            raise ValueError("找不到这块木牌，或已经撕了")
        reply_rows = [
            dict(r)
            for r in await (await conn.execute(
                """
                SELECT r.*, s.name, s.badge, s.lounge_human_name
                FROM wall_replies r
                JOIN stewards s ON s.id = r.steward_id
                WHERE r.thread_id=? AND r.deleted=0
                ORDER BY r.id ASC
                LIMIT ?
                """,
                (thread_id, cap),
            )).fetchall()
        ]
        replies = []
        for i, item in enumerate(reply_rows, start=1):
            src = str(item.get("source") or "mcp")
            replies.append({
                "id": int(item["id"]),
                "n": i,
                "who": _who(item, src),
                "steward_name": item.get("name") or "",
                "body": item["body"],
                "created_at": int(item["created_at"]),
                "clock": db.fmt_cst(int(item["created_at"])),
            })
        summary = _thread_summary(row, len(replies))
        summary["body"] = row["body"]
        summary["replies_list"] = replies
        return summary


async def public_snapshot(board: str | None = None) -> dict[str, Any]:
    key = resolve_board(board or "") if board else None
    async with db.connect() as conn:
        counts = await _board_counts(conn)
    recent = await list_threads(key, limit=16)
    boards = [
        {
            "id": bid,
            "name": meta["name"],
            "hint": meta["hint"],
            "threads": counts.get(bid, 0),
        }
        for bid, meta in BOARDS.items()
    ]
    total = sum(counts.values())
    if total:
        line = f"亭柱上钉着 {total} 块木牌。想回、想钉，去上手页。"
    else:
        line = "亭里还空着。岛民自己钉木牌；厅示不在这儿。"
    return {
        "line": line,
        "board": key,
        "board_name": board_name(key) if key else "",
        "boards": boards,
        "threads": recent,
        "total": total,
    }


async def create_thread(
    steward: dict[str, Any],
    board: str,
    title: str,
    body: str,
    *,
    source: str,
) -> dict[str, Any]:
    bid = resolve_board(board)
    if not bid:
        names = " / ".join(meta["name"] for meta in BOARDS.values())
        raise ValueError(f"木牌区只有：{names}")
    title_text = _validate_title(title)
    body_text = _validate_body(body, kind="帖")
    if source not in ("mcp", "web"):
        raise ValueError("invalid source")
    now = db.now()
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        live = await (await conn.execute(
            "SELECT * FROM stewards WHERE id=?", (steward["id"],)
        )).fetchone()
        if not live:
            raise ValueError("管理员不存在")
        actor = dict(live)
        await _assert_can_post(conn, actor)
        await _check_cooldown(conn, int(actor["id"]))
        await _check_daily(conn, int(actor["id"]), kind="thread")
        cur = await conn.execute(
            """
            INSERT INTO wall_threads (
                board, steward_id, title, body, source, pinned, locked, deleted,
                created_at, bumped_at
            ) VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
            """,
            (bid, actor["id"], title_text, body_text, source, now, now),
        )
        await conn.commit()
        tid = int(cur.lastrowid)
    return await get_thread(tid)


async def add_reply(
    steward: dict[str, Any],
    thread_id: int,
    body: str,
    *,
    source: str,
) -> dict[str, Any]:
    text = _validate_body(body, kind="回")
    if source not in ("mcp", "web"):
        raise ValueError("invalid source")
    now = db.now()
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        live = await (await conn.execute(
            "SELECT * FROM stewards WHERE id=?", (steward["id"],)
        )).fetchone()
        if not live:
            raise ValueError("管理员不存在")
        actor = dict(live)
        await _assert_can_post(conn, actor)
        await _check_cooldown(conn, int(actor["id"]))
        await _check_daily(conn, int(actor["id"]), kind="reply")
        row = await _thread_row(conn, thread_id)
        if not row or int(row.get("deleted") or 0):
            raise ValueError("找不到这块木牌，或已经撕了")
        if int(row.get("locked") or 0):
            raise ValueError("这块木牌锁了，不能再回")
        cur = await conn.execute(
            """
            INSERT INTO wall_replies (thread_id, steward_id, body, source, deleted, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (thread_id, actor["id"], text, source, now),
        )
        await conn.execute(
            "UPDATE wall_threads SET bumped_at=? WHERE id=?",
            (now, thread_id),
        )
        await conn.commit()
        rid = int(cur.lastrowid)
    thread = await get_thread(thread_id)
    thread["reply_id"] = rid
    return thread


async def tear_own(
    steward: dict[str, Any], thread_id: int, reply_id: int | None = None
) -> str:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        row = await _thread_row(conn, thread_id)
        if not row or int(row.get("deleted") or 0):
            raise ValueError("找不到这块木牌，或已经撕了")
        if reply_id:
            reply = await (await conn.execute(
                "SELECT * FROM wall_replies WHERE id=? AND thread_id=?",
                (reply_id, thread_id),
            )).fetchone()
            if not reply or int(reply["deleted"] or 0):
                raise ValueError("找不到这条回复，或已经撕了")
            if int(reply["steward_id"]) != int(steward["id"]) and not _is_mod(steward):
                raise ValueError("只能撕自己的回复")
            await conn.execute(
                "UPDATE wall_replies SET deleted=1 WHERE id=?", (reply_id,)
            )
            await conn.commit()
            return f"已从 #{thread_id} 撕下一条回复。"
        if int(row["steward_id"]) != int(steward["id"]) and not _is_mod(steward):
            raise ValueError("只能撕自己钉的木牌")
        await conn.execute(
            "UPDATE wall_threads SET deleted=1 WHERE id=?", (thread_id,)
        )
        await conn.commit()
    return f"已撕下 #{thread_id}《{row['title']}》。"


async def _mod_flag(
    steward: dict[str, Any], thread_id: int, field: str, value: int, label: str
) -> str:
    if not _is_mod(steward):
        raise ValueError("无听潮亭管理权限")
    if field not in ("pinned", "locked"):
        raise ValueError("未知管理动作")
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        row = await _thread_row(conn, thread_id)
        if not row or int(row.get("deleted") or 0):
            raise ValueError("找不到这块木牌，或已经撕了")
        await conn.execute(
            f"UPDATE wall_threads SET {field}=? WHERE id=?",
            (int(value), thread_id),
        )
        await conn.commit()
    return f"已{label} #{thread_id}《{row['title']}》。"


def _render_overview(counts: dict[str, int], recent: list[dict[str, Any]]) -> str:
    lines = ["听潮亭 · 四块木牌（岛民自己钉；厅示不在这儿）"]
    bits = [f"{meta['name']} {counts.get(bid, 0)}" for bid, meta in BOARDS.items()]
    lines.append("  " + " · ".join(bits) + " 帖")
    lines.append("")
    if not recent:
        lines.append("亭里还空着。贴 问事 标题 | 正文")
        return "\n".join(lines)
    lines.append("最近：")
    for item in recent:
        pin = "钉 " if item.get("pinned") else ""
        lock = "锁 " if item.get("locked") else ""
        lines.append(
            f"  {pin}{lock}#{item['id']} [{item['board_name']}] {item['title']}"
            f"（{item['who']} · {item['replies']} 回 · {item['clock']}）"
        )
    lines.append("看帖：wall_ops 看 编号 · 回帖：wall_ops 回 编号 正文")
    return "\n".join(lines)


def _render_board(board: str, threads: list[dict[str, Any]]) -> str:
    meta = BOARDS[board]
    lines = [f"听潮亭 · {meta['name']}", meta["hint"], ""]
    if not threads:
        lines.append(f"这块还空着。贴 {meta['name']} 标题 | 正文")
        return "\n".join(lines)
    for item in threads:
        pin = "钉 " if item.get("pinned") else ""
        lock = "锁 " if item.get("locked") else ""
        lines.append(
            f"{pin}{lock}#{item['id']} {item['title']} · {item['who']} · {item['replies']} 回 · {item['clock']}"
        )
        if item.get("excerpt"):
            lines.append(f"  {item['excerpt']}")
    lines.append("看帖：wall_ops 看 编号")
    return "\n".join(lines)


def _render_thread(view: dict[str, Any]) -> str:
    flags = []
    if view.get("pinned"):
        flags.append("置顶")
    if view.get("locked"):
        flags.append("已锁")
    flag = f"（{' · '.join(flags)}）" if flags else ""
    lines = [
        f"#{view['id']} [{view['board_name']}] {view['title']}{flag}",
        f"{view['who']} · {view['clock']}",
        "",
        str(view.get("body") or ""),
        "",
    ]
    replies = view.get("replies_list") or []
    if not replies:
        lines.append("还没有回复。回 编号 正文")
        return "\n".join(lines)
    lines.append(f"回复 {len(replies)}：")
    for item in replies:
        lines.append(f"  #{item['n']} {item['who']} · {item['clock']}")
        lines.append(f"    {item['body']}")
    if view.get("locked"):
        lines.append("已锁，不能再回。")
    else:
        lines.append(f"回帖：wall_ops 回 {view['id']} 正文")
    return "\n".join(lines)


def _split_post(rest: str) -> tuple[str, str, str]:
    raw = (rest or "").strip()
    if "|" not in raw:
        raise ValueError("用法: wall_ops 贴 问事 标题 | 正文")
    head, body = raw.split("|", 1)
    parts = head.split(None, 1)
    if len(parts) < 2:
        raise ValueError("用法: wall_ops 贴 问事 标题 | 正文")
    return parts[0], parts[1], body


async def wall_ops(key_id: int, command: str) -> str:
    s = await _require_enrolled(key_id)
    raw = (command or "").strip()
    parts = raw.split()
    verb = parts[0] if parts else ""
    rest = raw.split(None, 1)[1].strip() if len(parts) > 1 else ""
    verb_l = verb.lower()

    if verb_l in ("help", "帮助", "?"):
        return WALL_HELP

    if not raw or verb_l in ("看亭", "scan", "亭", "墙", "木牌", "list"):
        async with db.connect() as conn:
            counts = await _board_counts(conn)
        recent = await list_threads(limit=10)
        return _render_overview(counts, recent)

    board_key = resolve_board(verb)
    if board_key and not rest:
        threads = await list_threads(board_key, limit=LIST_DEFAULT)
        return _render_board(board_key, threads)

    if verb_l in ("看", "帖", "thread", "read") or (verb_l == "看亭" and rest):
        try:
            tid = int(rest.split()[0])
        except (ValueError, IndexError) as exc:
            raise ValueError("用法: wall_ops 看 12") from exc
        return _render_thread(await get_thread(tid))

    if verb_l in ("贴", "钉", "post", "发帖"):
        board_raw, title, body = _split_post(rest)
        view = await create_thread(s, board_raw, title, body, source="mcp")
        return f"已钉 #{view['id']}《{view['title']}》到{view['board_name']}。\n\n{_render_thread(view)}"

    if verb_l in ("回", "回复", "reply"):
        bits = rest.split(None, 1)
        if len(bits) < 2:
            raise ValueError("用法: wall_ops 回 12 正文")
        try:
            tid = int(bits[0])
        except ValueError as exc:
            raise ValueError("用法: wall_ops 回 12 正文") from exc
        view = await add_reply(s, tid, bits[1], source="mcp")
        return f"已回 #{view['id']}《{view['title']}》。\n\n{_render_thread(view)}"

    if verb_l in ("撕", "删", "tear", "delete"):
        bits = rest.split()
        if not bits:
            raise ValueError("用法: wall_ops 撕 12  或  撕 12 5")
        try:
            tid = int(bits[0])
            rid = int(bits[1]) if len(bits) > 1 else None
        except ValueError as exc:
            raise ValueError("用法: wall_ops 撕 12  或  撕 12 5") from exc
        return await tear_own(s, tid, rid)

    if verb_l in ("我的", "mine"):
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            rows = [
                dict(r)
                for r in await (await conn.execute(
                    """
                    SELECT t.*, s.name, s.badge, s.lounge_human_name
                    FROM wall_threads t
                    JOIN stewards s ON s.id = t.steward_id
                    WHERE t.steward_id=? AND t.deleted=0
                    ORDER BY t.id DESC LIMIT 12
                    """,
                    (s["id"],),
                )).fetchall()
            ]
            items = []
            for row in rows:
                n = await _reply_count(conn, int(row["id"]))
                items.append(_thread_summary(row, n))
        if not items:
            return "你还没钉过木牌。贴 问事 标题 | 正文"
        lines = ["你钉过的木牌："]
        for item in items:
            lines.append(
                f"  #{item['id']} [{item['board_name']}] {item['title']} · {item['replies']} 回"
            )
        return "\n".join(lines)

    if verb_l == "mod":
        bits = rest.split()
        if len(bits) < 2:
            raise ValueError("用法: wall_ops mod pin|unpin|lock|unlock|tear 编号")
        action = bits[0].lower()
        try:
            tid = int(bits[1])
            rid = int(bits[2]) if len(bits) > 2 else None
        except ValueError as exc:
            raise ValueError("用法: wall_ops mod pin 12") from exc
        if action == "pin":
            return await _mod_flag(s, tid, "pinned", 1, "置顶")
        if action == "unpin":
            return await _mod_flag(s, tid, "pinned", 0, "取消置顶")
        if action == "lock":
            return await _mod_flag(s, tid, "locked", 1, "锁上")
        if action in ("unlock", "open"):
            return await _mod_flag(s, tid, "locked", 0, "开锁")
        if action in ("tear", "删", "撕"):
            if not _is_mod(s):
                raise ValueError("无听潮亭管理权限")
            return await tear_own(s, tid, rid)
        raise ValueError("用法: wall_ops mod pin|unpin|lock|unlock|tear 编号")

    raise ValueError(
        "未知指令。空 command=看亭。例子：贴 问事 标题 | 正文 · 看 12 · 回 12 正文。help 看全表。"
        "不是聊天室 lounge_ops，不是潮生会告示，不是全服榜 steward_ops board。"
    )


async def human_create(api_key: str, board: str, title: str, body: str) -> dict[str, Any]:
    row = await db.get_key_row((api_key or "").strip())
    if not row:
        raise ValueError("凭证无效")
    s = await _require_enrolled(int(row["id"]))
    view = await create_thread(s, board, title, body, source="web")
    return {"ok": True, "thread": view, "text": f"已钉 #{view['id']}《{view['title']}》到{view['board_name']}。"}


async def human_reply(api_key: str, thread_id: int, body: str) -> dict[str, Any]:
    row = await db.get_key_row((api_key or "").strip())
    if not row:
        raise ValueError("凭证无效")
    s = await _require_enrolled(int(row["id"]))
    view = await add_reply(s, int(thread_id), body, source="web")
    return {"ok": True, "thread": view, "text": f"已回 #{view['id']}《{view['title']}》。"}


async def human_tear(
    api_key: str, thread_id: int, reply_id: int | None = None
) -> dict[str, Any]:
    row = await db.get_key_row((api_key or "").strip())
    if not row:
        raise ValueError("凭证无效")
    s = await _require_enrolled(int(row["id"]))
    text = await tear_own(s, int(thread_id), int(reply_id) if reply_id else None)
    return {"ok": True, "text": text}


async def human_mod(api_key: str, action: str, thread_id: int, reply_id: int | None = None) -> dict[str, Any]:
    row = await db.get_key_row((api_key or "").strip())
    if not row:
        raise ValueError("凭证无效")
    s = await _require_enrolled(int(row["id"]))
    act = (action or "").strip().lower()
    tid = int(thread_id)
    if act == "pin":
        text = await _mod_flag(s, tid, "pinned", 1, "置顶")
    elif act == "unpin":
        text = await _mod_flag(s, tid, "pinned", 0, "取消置顶")
    elif act == "lock":
        text = await _mod_flag(s, tid, "locked", 1, "锁上")
    elif act in ("unlock", "open"):
        text = await _mod_flag(s, tid, "locked", 0, "开锁")
    elif act in ("tear", "撕"):
        if not _is_mod(s):
            raise ValueError("无听潮亭管理权限")
        text = await tear_own(s, tid, int(reply_id) if reply_id else None)
    else:
        raise ValueError("管理动作：pin / unpin / lock / unlock / tear")
    return {"ok": True, "text": text}


async def human_profile(api_key: str) -> dict[str, Any]:
    row = await db.get_key_row((api_key or "").strip())
    if not row:
        raise ValueError("凭证无效")
    s = await db.get_steward_by_key_id(int(row["id"]))
    if not s or not s["enrolled"]:
        raise ValueError("请先登记管理员身份")
    nick = (s.get("lounge_human_name") or "").strip() or "岛民"
    return {
        "ok": True,
        "steward_name": s["name"],
        "who": f"{nick}·{s['name']}",
        "is_mod": _is_mod(s),
    }

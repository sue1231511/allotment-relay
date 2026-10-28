#!/usr/bin/env python3
"""只读调查：某个玩家的某件物品是不是「莫名其妙少了」，少了多少，去哪了。

只读：用 SQLite 只读模式（mode=ro + query_only）打开库，不写库、不建表、不备份、不碰任何别的文件。
不读 api_keys 表，不打印任何 key / 凭证。只在手动运行时执行，不属于启动流程。

用法：
    python scripts/investigate_vanished_items.py 玩家名 物品
    python scripts/investigate_vanished_items.py kk薛洄贵 榴莲
    python scripts/investigate_vanished_items.py kk薛洄贵 crop_durian --days 14 --limit 100
    python scripts/investigate_vanished_items.py 玩家名 物品 --db /path/to/relay.db

物品可写中文名或英文 id。库路径默认取环境变量 DB_PATH，其次 DATA_DIR/relay.db，再其次 server/data/relay.db。

输出六块：
  1 玩家基本信息（id、名字、票、最近活动）
  2 背包里现在有多少
  3 品质批次账（每一批的件数、品质、变质时间）以及和背包的对账：
       批次总量 > 背包 = 幽灵批次（旧版本送礼/集市没扣批次留下的），旧版本会在过期后拿它去扣背包；
       已过期批次 = 旧版本下一次卖货/看行囊会被「变质丢弃」的件数
  4 实付批次账（Tt 货的退货价依据）
  5 还挂在别处、没丢的货：集市挂单、交换台、台阶交接
  6 相关纪事（送礼、集市、交换台、公仓、变质丢弃……）和物品履历
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_log = logging.getLogger("investigate")
ROOT = Path(__file__).resolve().parents[1]
_CST = timezone(timedelta(hours=8))


def _default_db() -> Path:
    env = os.environ.get("DB_PATH")
    if env:
        return Path(env)
    data = os.environ.get("DATA_DIR")
    if data:
        return Path(data) / "relay.db"
    return ROOT / "server" / "data" / "relay.db"


def _fmt(ts: int | None) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(int(ts), _CST).strftime("%m-%d %H:%M")


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _resolve_item(raw: str) -> tuple[str, str]:
    """返回 (英文 id, 中文名)。能 import 游戏目录就按目录解析，不能就把输入当 id。"""
    try:
        sys.path.insert(0, str(ROOT))
        from server.catalog import ITEM_NAMES, resolve_item_key  # type: ignore

        key = resolve_item_key(raw) or raw
        return key, ITEM_NAMES.get(key, key)
    except Exception:
        _log.warning("没能加载游戏物品目录，按英文 id 处理 raw=%s", raw, exc_info=True)
        return raw, raw


def _section(title: str) -> None:
    _log.info("")
    _log.info("═══ %s", title)


def _find_steward(conn: sqlite3.Connection, name: str) -> tuple | None:
    # 只选这几列，绝不碰 key 相关的列和表
    return conn.execute(
        "SELECT id, name, tickets, last_active_at, last_bar_shift_at "
        "FROM stewards WHERE name = ? COLLATE NOCASE",
        (name.strip(),),
    ).fetchone()


def _report_satchel(conn: sqlite3.Connection, sid: int, item: str) -> int:
    _section("2 背包")
    row = conn.execute(
        "SELECT quantity FROM satchel WHERE steward_id=? AND item=?", (sid, item)
    ).fetchone()
    have = int(row[0]) if row else 0
    _log.info("背包里 %s 现有 %d 件", item, have)
    return have


def _report_trait_batches(conn: sqlite3.Connection, sid: int, item: str, have: int, now: int) -> None:
    _section("3 品质批次账（item_trait_batches）")
    if not _has_table(conn, "item_trait_batches"):
        _log.info("库里没有 item_trait_batches 表（还没有任何货记过品质批次）")
        return
    rows = conn.execute(
        "SELECT id, loc, qty, quality, weight_milli, spoil_at FROM item_trait_batches "
        "WHERE steward_id=? AND item=? ORDER BY id",
        (sid, item),
    ).fetchall()
    if not rows:
        _log.info("没有这个物品的批次记录")
        return
    total = expired = 0
    for bid, loc, qty, quality, wmilli, spoil_at in rows:
        is_exp = bool(spoil_at) and int(spoil_at) <= now
        total += int(qty) if loc == "satchel" else 0
        expired += int(qty) if (loc == "satchel" and is_exp) else 0
        wtxt = f" {int(wmilli) / 1000:.1f}kg" if wmilli else ""
        _log.info(
            "  批次#%s [%s] %d 件 品质=%s%s 变质时间=%s%s",
            bid, loc, int(qty), quality or "-", wtxt, _fmt(spoil_at), "  ← 已过期" if is_exp else "",
        )
    ghost = max(0, total - have)
    _log.info("对账：批次总量 %d 件，背包 %d 件", total, have)
    if ghost:
        _log.warning(
            "  ⚠ 批次比背包多 %d 件 = 幽灵批次（货早已不在背包，批次账没扣）。"
            "旧版本一旦把它判成变质，就会去扣背包里别的件。", ghost,
        )
    else:
        _log.info("  批次总量没有超过背包，账是平的")
    if expired:
        real_expired = max(0, expired - ghost)
        _log.info(
            "已过期批次共 %d 件：旧版本下一次卖这个物品/看行囊，会按 %d 件从背包扣掉；"
            "其中真正变质的约 %d 件，其余是幽灵（等于误扣了背包里别的件）。",
            expired, min(expired, have) if have else expired, real_expired,
        )


def _report_paid(conn: sqlite3.Connection, sid: int, item: str) -> None:
    _section("4 实付批次账（paid_batches）")
    if not _has_table(conn, "paid_batches"):
        _log.info("库里还没有 paid_batches 表（这个版本还没上线）")
        return
    rows = conn.execute(
        "SELECT id, qty, paid_unit FROM paid_batches WHERE owner_kind='steward' AND owner_id=? AND item=? ORDER BY id",
        (sid, item),
    ).fetchall()
    if not rows:
        _log.info("没有实付批次（不是 Tt 货，或是没有付款记录的件）")
        return
    for bid, qty, paid in rows:
        _log.info("  批次#%s %d 件 实付单价 %d", bid, int(qty), int(paid))


def _report_elsewhere(conn: sqlite3.Connection, sid: int, item: str) -> None:
    _section("5 还挂在别处、没丢的货")
    found = False
    if _has_table(conn, "market_listings"):
        for lid, qty, price in conn.execute(
            "SELECT id, quantity, price FROM market_listings "
            "WHERE seller_id=? AND item=? AND buyer_id IS NULL ORDER BY id", (sid, item)
        ).fetchall():
            found = True
            _log.info("  集市挂单#%s：%d 件 @%s 票（没丢，在摊上）", lid, qty, price)
    if _has_table(conn, "swap_lots"):
        for lid, qty in conn.execute(
            "SELECT id, quantity FROM swap_lots WHERE depositor_id=? AND item=? AND claimed_by IS NULL ORDER BY id",
            (sid, item),
        ).fetchall():
            found = True
            _log.info("  交换台挂单#%s：%d 件（没丢，等人领）", lid, qty)
    if _has_table(conn, "handoffs"):
        for hid, frm, to, qty in conn.execute(
            "SELECT id, from_id, to_id, quantity FROM handoffs "
            "WHERE (from_id=? OR to_id=?) AND item=? AND picked_up=0 ORDER BY id",
            (sid, sid, item),
        ).fetchall():
            found = True
            _log.info("  台阶交接#%s：%s → %s，%d 件（还没被取走）", hid, frm, to, qty)
    if not found:
        _log.info("没有")


def _report_chronicle(
    conn: sqlite3.Connection, sid: int, item: str, label: str, since: int, limit: int,
) -> None:
    _section("6 相关纪事")
    if not _has_table(conn, "chronicle"):
        _log.info("库里没有 chronicle 表")
        return
    like_a, like_b = f"%{label}%", f"%{item}%"
    rows = conn.execute(
        """
        SELECT c.created_at, c.action, c.actor_id, c.target_id, c.text,
               COALESCE(a.name, '?'), COALESCE(t.name, '')
        FROM chronicle c
        LEFT JOIN stewards a ON a.id = c.actor_id
        LEFT JOIN stewards t ON t.id = c.target_id
        WHERE (c.actor_id=? OR c.target_id=?)
          AND (c.text LIKE ? OR c.text LIKE ?)
          AND c.created_at >= ?
        ORDER BY c.id DESC LIMIT ?
        """,
        (sid, sid, like_a, like_b, since, limit),
    ).fetchall()
    if not rows:
        _log.info("这段时间里没有提到该物品的纪事")
    else:
        _log.info("最近 %d 条（新的在上）：", len(rows))
        for ts, action, actor, target, text, aname, tname in rows:
            who = aname + (f" → {tname}" if tname else "")
            _log.info("  %s [%s] %s：%s", _fmt(ts), action, who, text)
    spoiled = conn.execute(
        "SELECT created_at, text FROM chronicle WHERE actor_id=? AND action='spoil' AND created_at>=? "
        "AND (text LIKE ? OR text LIKE ?) ORDER BY id DESC LIMIT ?",
        (sid, since, like_a, like_b, limit),
    ).fetchall()
    _log.info("变质丢弃纪事（新版本才会记）：%d 条", len(spoiled))
    for ts, text in spoiled:
        _log.info("  %s %s", _fmt(ts), text)

    if _has_table(conn, "item_ledgers"):
        living = conn.execute(
            "SELECT COUNT(*) FROM item_ledgers WHERE owner_id=? AND item=? AND alive=1", (sid, item)
        ).fetchone()[0]
        dead = conn.execute(
            "SELECT id, updated_at, lines_json FROM item_ledgers WHERE owner_id=? AND item=? AND alive=0 "
            "AND updated_at>=? ORDER BY id DESC LIMIT ?",
            (sid, item, since, limit),
        ).fetchall()
        _log.info("物品履历（只有「值得记」的货才有，普通作物通常没有）：活着 %d 条，近期已了结 %d 条", living, len(dead))
        for rid, ts, blob in dead:
            try:
                lines = json.loads(blob)
                last = lines[-1] if lines else ""
            except (ValueError, TypeError):
                _log.warning("履历 #%s 的 lines_json 解析失败", rid, exc_info=True)
                last = "(解析失败)"
            _log.info("  履历#%s %s 结局：%s", rid, _fmt(ts), last)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读：核对某玩家某物品的批次账、背包、挂单和纪事")
    parser.add_argument("player", help="玩家名（岛民名）")
    parser.add_argument("item", help="物品，中文名或英文 id")
    parser.add_argument("--db", type=Path, default=None, help="relay.db 路径")
    parser.add_argument("--days", type=int, default=14, help="纪事回看天数，默认 14")
    parser.add_argument("--limit", type=int, default=60, help="纪事最多条数，默认 60")
    args = parser.parse_args(argv)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    db_path = args.db or _default_db()
    if not db_path.exists():
        _log.error("找不到数据库 db_path=%s", db_path)
        return 2
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=10)
        conn.execute("PRAGMA query_only=ON")
    except sqlite3.Error:
        _log.exception("只读打开数据库失败 db_path=%s", db_path)
        return 2

    item, label = _resolve_item(args.item)
    try:
        steward = _find_steward(conn, args.player)
        if not steward:
            _log.error("找不到玩家「%s」", args.player)
            return 1
        sid, name, tickets, last_active, last_bar = steward
        now = int(datetime.now(timezone.utc).timestamp())
        _section("1 玩家")
        _log.info("库=%s（只读）", db_path)
        _log.info("玩家 #%s 「%s」 票=%s 最近活动=%s 最近酒吧打卡=%s", sid, name, tickets, _fmt(last_active), _fmt(last_bar))
        _log.info("物品 %s（%s）", item, label)

        have = _report_satchel(conn, sid, item)
        _report_trait_batches(conn, sid, item, have, now)
        _report_paid(conn, sid, item)
        _report_elsewhere(conn, sid, item)
        _report_chronicle(conn, sid, item, label, now - args.days * 86400, args.limit)
        _log.info("")
        _log.info("核对提示：把「纪事里送出/挂出/捐出/卖出的件数」加上「背包现有」，和玩家说的收获数比一比；"
                  "差额里如果有「已过期批次」或「幽灵批次」，就是旧版本变质清理扣掉的。")
        return 0
    except sqlite3.Error:
        _log.exception("查询失败 db_path=%s player=%s item=%s", db_path, args.player, item)
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""一次性清理：把所有玩家背包里数量为负的格子清零（删除该行）。

只动 satchel 表里 quantity < 0 的行。不动票、不动数量为正的格子、不动其他表。
只在手动运行时执行，不属于启动流程，也没有被任何模块导入。

用法（先看再动，默认只预览）：
    python scripts/clear_negative_satchel.py                 # 预览，不改库
    python scripts/clear_negative_satchel.py --apply         # 先备份再清零
    python scripts/clear_negative_satchel.py --db /path/relay.db --apply

库路径默认取环境变量 DB_PATH，其次 DATA_DIR/relay.db，再其次 server/data/relay.db。
--apply 会先用 sqlite 在线备份在库旁边生成 relay.db.before-negative-clear-<时间>.bak。
"""
from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

_log = logging.getLogger("clear_negative_satchel")

ROOT = Path(__file__).resolve().parents[1]

# 只汇报、不处理的其他可能残留负数的表：(表, 条件)
REPORT_ONLY = (
    ("market_listings", "quantity <= 0 OR price <= 0"),
    ("contracts", "want_qty < 0"),
    ("larder", "quantity < 0"),
    ("swap_lots", "quantity <= 0"),
)


def _default_db() -> Path:
    env = os.environ.get("DB_PATH")
    if env:
        return Path(env)
    data = os.environ.get("DATA_DIR")
    if data:
        return Path(data) / "relay.db"
    return ROOT / "server" / "data" / "relay.db"


def _negative_rows(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute(
        """
        SELECT s.steward_id, COALESCE(st.name, '?'), s.item, s.quantity
        FROM satchel s LEFT JOIN stewards st ON st.id = s.steward_id
        WHERE s.quantity < 0
        ORDER BY s.steward_id, s.item
        """
    ).fetchall()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="清零所有玩家背包里数量为负的格子（不动票）")
    parser.add_argument("--db", type=Path, default=None, help="relay.db 路径")
    parser.add_argument("--apply", action="store_true", help="真的执行（默认只预览）")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    db_path = args.db or _default_db()
    if not db_path.exists():
        _log.error("找不到数据库 db_path=%s", db_path)
        return 2

    try:
        conn = sqlite3.connect(str(db_path), timeout=60)
    except sqlite3.Error:
        _log.exception("打开数据库失败 db_path=%s", db_path)
        return 2
    try:
        try:
            rows = _negative_rows(conn)
        except sqlite3.Error:
            _log.exception("读取负数格子失败 db_path=%s", db_path)
            return 2
        _log.info("库=%s 负数格子 %d 个，涉及 %d 名玩家", db_path, len(rows), len({r[0] for r in rows}))
        for sid, name, item, qty in rows:
            _log.info("  steward=%s %s  %s  quantity=%s", sid, name, item, qty)

        for table, cond in REPORT_ONLY:
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {cond}").fetchone()[0]
            except sqlite3.Error:
                _log.warning("汇报 %s 失败（表不存在？）", table, exc_info=True)
                continue
            if n:
                _log.warning("【只汇报，不处理】%s 里有 %d 行异常（%s）", table, n, cond)

        if not rows:
            _log.info("没有需要清的格子。")
            return 0
        if not args.apply:
            _log.info("这是预览，没有改动。确认无误后加 --apply 执行。")
            return 0

        backup = db_path.with_name(f"{db_path.name}.before-negative-clear-{time.strftime('%Y%m%d-%H%M%S')}.bak")
        try:
            dst = sqlite3.connect(str(backup))
            try:
                conn.backup(dst)
            finally:
                dst.close()
        except sqlite3.Error:
            _log.exception("备份失败，已中止，未改动任何数据 backup=%s", backup)
            return 2
        _log.info("已备份到 %s", backup)

        try:
            with conn:  # 一个事务：要么全清，要么全不动
                cur = conn.execute("DELETE FROM satchel WHERE quantity < 0")
                _log.info("已清零（删除）%d 个负数格子；票和其他数据未动。", cur.rowcount)
        except sqlite3.Error:
            _log.exception("清零失败，事务已回滚 db_path=%s", db_path)
            return 2
        left = conn.execute("SELECT COUNT(*) FROM satchel WHERE quantity < 0").fetchone()[0]
        _log.info("复查：剩余负数格子 %d 个", left)
        return 0 if left == 0 else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())

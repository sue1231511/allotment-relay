#!/usr/bin/env python3
"""东八区时间格式化。"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CST = timezone(timedelta(hours=8))


def test_fmt_cst_helpers() -> None:
    from server import db

    os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="cst-")
    ts = int(datetime(2026, 8, 27, 23, 40, tzinfo=CST).timestamp())
    assert db.fmt_cst(ts) == "08-27 23:40", db.fmt_cst(ts)
    assert db.fmt_cst_hhmm(ts) == "23:40", db.fmt_cst_hhmm(ts)
    assert db.fmt_cst_date(ts) == "2026-08-27", db.fmt_cst_date(ts)
    assert db.cst_dt(ts).tzinfo == CST


def main() -> None:
    test_fmt_cst_helpers()
    print("cst time tests ok")


if __name__ == "__main__":
    main()

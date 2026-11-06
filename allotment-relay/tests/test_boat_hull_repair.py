"""修船：船体不满也能修（按比例收票），开关亮着收全价；途中事件不丢出航 payload。"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_repair_cost_rules():
    from server import boat_hull

    assert boat_hull.repair_cost(12, 36, 100, damaged=False) == 8   # ceil(12*0.64)
    assert boat_hull.repair_cost(12, 99, 100, damaged=False) == 1
    assert boat_hull.repair_cost(12, 36, 100, damaged=True) == 12
    assert boat_hull.repair_cost(12, 0, 100, damaged=False) == 12
    assert boat_hull.needs_repair(100, 100, False) is False
    assert boat_hull.needs_repair(99, 100, False) is True
    assert boat_hull.needs_repair(100, 100, True) is True


async def _setup(folder: Path, email: str, name: str):
    from server import db

    await db.init_db()
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    s = await db.get_steward_by_key_id(row["id"])
    return row["id"], s


def _run(coro_fn):
    from server import db

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
            asyncio.run(coro_fn(folder))


def test_repair_when_hull_low_but_not_damaged():
    async def run(folder):
        from server import boat_hull, db, marine

        kid, s = await _setup(folder, "h@example.com", "补船体")
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET boat_key='skiff', boat_damaged=0, tickets=100 WHERE id=?",
                (s["id"],),
            )
            await boat_hull.get_hull(conn, s["id"])
            await conn.execute(
                "UPDATE steward_boat_hull SET hull=36 WHERE steward_id=?", (s["id"],)
            )
            await conn.commit()

        status = await marine.voyage_ops(kid, "status")
        assert "船体 36/100" in status and "repair 补满" in status

        msg = await marine.voyage_ops(kid, "repair")
        assert "无需修理" not in msg
        assert "-8 票" in msg and "100/100" in msg

        async with db.connect() as conn:
            hull, mx = await boat_hull.get_hull(conn, s["id"])
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            tickets = (await cur.fetchone())[0]
        assert (hull, mx) == (100, 100)
        assert tickets == 92

        again = await marine.voyage_ops(kid, "repair")
        assert "船况良好，无需修理" in again

    _run(run)


def test_repair_damaged_full_price():
    async def run(folder):
        from server import boat_hull, db, marine

        kid, s = await _setup(folder, "d2@example.com", "待修")
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET boat_key='skiff', boat_damaged=1, tickets=100 WHERE id=?",
                (s["id"],),
            )
            await boat_hull.get_hull(conn, s["id"])
            await conn.execute(
                "UPDATE steward_boat_hull SET hull=15 WHERE steward_id=?", (s["id"],)
            )
            await conn.commit()

        msg = await marine.voyage_ops(kid, "repair")
        assert "-12 票" in msg
        async with db.connect() as conn:
            cur = await conn.execute("SELECT boat_damaged FROM stewards WHERE id=?", (s["id"],))
            assert (await cur.fetchone())[0] == 0

    _run(run)


def test_voyage_owner_id_reads_payload():
    from server import boat_hull

    v = {"id": 1, "encounter": json.dumps({"share_founder_id": 7, "loan_lender_id": 0})}
    assert boat_hull.voyage_owner_id(3, v) == 7
    v = {"id": 1, "encounter": json.dumps({"loan_lender_id": 9})}
    assert boat_hull.voyage_owner_id(3, v) == 9
    assert boat_hull.voyage_owner_id(3, {"id": 1, "encounter": "{}"}) == 3
    assert boat_hull.voyage_owner_id(3, {"id": 1, "encounter": "not json"}) == 3


def test_breach_and_tear_keep_depart_payload():
    async def run(folder):
        from server import db, voyage_hull_breach, voyage_sail_event

        _, s = await _setup(folder, "p@example.com", "漏船")
        base = {"voyage_fish": ["fish_x"], "boat_key": "skiff", "loan_lender_id": 0, "share_founder_id": 5}
        async with db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO voyages (steward_id, route, departed_at, returns_at, status, encounter)
                VALUES (?, 'near', ?, ?, 'sailing', ?)
                """,
                (s["id"], db.now(), db.now() + 600, json.dumps(base)),
            )
            cur = await conn.execute("SELECT id FROM voyages WHERE steward_id=?", (s["id"],))
            vid = (await cur.fetchone())[0]
            with patch("random.random", return_value=0.0):
                msg = await voyage_hull_breach.maybe_mid_voyage(
                    conn, s["id"], vid, hull_ratio=0.2, route_key="near",
                )
            assert msg
            cur = await conn.execute("SELECT encounter FROM voyages WHERE id=?", (vid,))
            payload = json.loads((await cur.fetchone())[0])
            assert payload["type"] == "hull_breach"
            assert payload["share_founder_id"] == 5 and payload["voyage_fish"] == ["fish_x"]

            await conn.execute("UPDATE voyages SET status='sailing' WHERE id=?", (vid,))
            with patch("random.random", return_value=0.0):
                tear = await voyage_sail_event.maybe_on_depart(conn, s["id"], vid, "near")
            assert tear
            cur = await conn.execute("SELECT encounter FROM voyages WHERE id=?", (vid,))
            payload = json.loads((await cur.fetchone())[0])
            assert payload["type"] == "sail_tear" and payload["hard_sail"] is False
            assert payload["share_founder_id"] == 5 and payload["boat_key"] == "skiff"
            await conn.commit()

    _run(run)


if __name__ == "__main__":
    pytest.main([__file__, "-q"])

"""Mobile event reads, shared repairs, costs, ownership, and wildlife history."""
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch


async def exercise():
    import httpx
    from fastapi import FastAPI
    from server import config, db, events, farming
    from server.v1.router import router

    with tempfile.TemporaryDirectory(prefix="farm-events-") as tmp:
        folder = Path(tmp)
        with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"), \
                patch.object(config, "DATA_DIR", folder), patch.object(config, "DB_PATH", folder / "relay.db"):
            await db.init_db()
            keys, owners = [], []
            for index in range(2):
                key = await db.create_api_key(f"farm{index}@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], f"田间人{index}", "", "naturalist", "")
                owners.append(await db.get_steward_by_key_id(row["id"]))
                keys.append(key)
            owner, other = owners
            sid = owner["id"]

            async def balance():
                return (await db.get_steward_by_id(sid))["tickets"]

            async def incident(cost=30, item=None, plot_id=None, who=sid):
                async with db.connect() as conn:
                    cur = await conn.execute(
                        "INSERT INTO steward_incidents (steward_id, incident_key, plot_id, detail, label, repair_tickets, repair_item, repair_qty, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (who, "gen:test", plot_id, "风刮倒了篱笆", "篱边意外", cost, item, 2, db.now()),
                    )
                    await conn.commit()
                    return cur.lastrowid

            async with db.connect() as conn:
                await conn.execute("UPDATE stewards SET tickets=200, last_bar_shift_at=?, last_active_at=?", (db.now(), db.now()))
                foreign_plot = (await (await conn.execute("SELECT id FROM parcels WHERE steward_id=? LIMIT 1", (other["id"],))).fetchone())[0]
                await conn.execute("INSERT OR REPLACE INTO satchel (steward_id, item, quantity) VALUES (?, 'compost', 2)", (sid,))
                await conn.execute("INSERT INTO chronicle (actor_id, action, text, created_at) VALUES (?, 'incident', '只有另一人能看到', ?)", (other["id"], db.now()))
                await conn.commit()
            iid = await incident(plot_id=foreign_plot)
            material = await incident(item="compost")
            expensive = await incident(cost=999)
            unsupported = await incident()
            await incident(who=other["id"])
            app = FastAPI()
            app.include_router(router)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                auth = {"Authorization": f"Bearer {keys[0]}"}
                async def repair(target, payment="tickets", idem=""):
                    return await client.post("/api/v1/farm/events/repair", headers={**auth, "Idempotency-Key": idem or f"{target}-{payment}"}, json={"incident_id": target, "payment": payment})
                assert (await client.get("/api/v1/farm/events")).status_code == 401
                assert (await client.get("/api/v1/farm/events", headers={"Authorization": "Bearer wrong"})).status_code == 401
                anonymous = await db.create_api_key("not-enrolled@example.com")
                assert (await client.get("/api/v1/farm/events", headers={"Authorization": f"Bearer {anonymous}"})).status_code == 403
                # Reading does not require attendance, settle, or randomly roll anything.
                with patch("server.game.require_steward", side_effect=AssertionError("read must not prepare")), \
                     patch.object(events, "roll_after_action", side_effect=AssertionError("read must not roll")):
                    before = await balance()
                    for _ in range(2):
                        response = await client.get("/api/v1/farm/events", headers=auth)
                        assert response.status_code == 200, response.text
                        body = response.json()
                        assert len(body["incidents"]) == 4
                        assert "只有另一人" not in response.text
                    assert await balance() == before
                by_id = {r["id"]: r for r in body["incidents"]}
                assert not by_id[expensive]["can_pay_tickets"]
                assert by_id[material]["can_pay_item"]
                bad = await repair(unsupported, "item")
                assert bad.status_code == 409 and "不能用材料" in bad.text
                assert (await repair(expensive)).status_code == 409
                assert await balance() == before
                for payload in ({"incident_id": 0, "payment": "tickets"}, {"incident_id": iid, "payment": "anything"}):
                    assert (await client.post("/api/v1/farm/events/repair", headers=auth, json=payload)).status_code == 422
                cross = await client.post("/api/v1/farm/events/repair", headers={"Authorization": f"Bearer {keys[1]}"}, json={"incident_id": iid, "payment": "tickets"})
                assert cross.status_code == 409
                fixed = await repair(iid)
                assert fixed.status_code == 200, fixed.text
                assert fixed.json()["me"]["tickets"] == before - 30
                assert await balance() == before - 30
                assert (await repair(iid)).json() == fixed.json()  # same idempotency key
                assert (await repair(iid, idem="second-click")).status_code == 409
                assert await balance() == before - 30
                async with db.connect() as conn:
                    untouched = await (await conn.execute("SELECT tended FROM parcels WHERE id=?", (foreign_plot,))).fetchone()
                    assert untouched[0] == 0
                fixed_item = await repair(material, "item")
                assert fixed_item.status_code == 200, fixed_item.text
                assert await balance() == before - 30
                assert (await db.get_satchel(sid)).get("compost", 0) == 0
                missing_item = await incident(item="compost")
                assert (await repair(missing_item, "item")).status_code == 409
                assert await balance() == before - 30
                # The AI and mobile share one resolved flag; only one may charge.
                racing = await incident(cost=11)
                results = await asyncio.gather(
                    events.incident_ops(owner["key_id"], f"repair {racing}"),
                    events.incident_ops(owner["key_id"], f"repair {racing}"),
                    return_exceptions=True,
                )
                assert sum(isinstance(r, ValueError) for r in results) == 1, results
                assert await balance() == before - 41
                after = (await client.get("/api/v1/farm/events", headers=auth)).json()
                assert racing not in [r["id"] for r in after["incidents"]]
                assert any("处理了" in r["text"] for r in after["history"])
                # New wildlife events keep their actual narrative, not regenerated prose.
                with patch.object(farming, "_can_farm_roll", AsyncMock(return_value=True)), \
                     patch.object(farming, "_pick_plot", AsyncMock(return_value={"slot": 1})), \
                     patch.object(farming, "_wildlife_pool", return_value=[{"key": "test", "kind": "good", "weight": 1}]), \
                     patch.object(farming, "_apply_wildlife", AsyncMock(return_value="啄木鸟飞过田头")), \
                     patch.object(farming.random, "random", return_value=0), \
                     patch.object(farming.health, "maybe_restore_health", AsyncMock(return_value=None)):
                    async with db.connect() as conn:
                        narrative = await farming.roll_farm_event(conn, owner, "tend")
                        await conn.commit()
                result = (await client.get("/api/v1/farm/events", headers=auth)).json()
                assert "啄木鸟飞过田头" in narrative
                assert any(narrative == r["text"] for r in result["history"])
                print("farm events: auth, read-only, shared records, both payment modes, replay, concurrent repair, wildlife history passed")


def test_farm_events():
    asyncio.run(exercise())


if __name__ == "__main__":
    test_farm_events()

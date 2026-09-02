"""花房交易、每日奖励、MCP/手游共用状态和失败回滚。"""
import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import db, florist, season, game, hut
from server.florist_catalog import FLOWERS


class FloristTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="florist-test-")
        self.addCleanup(self.tmp.cleanup)
        for attr, value in {"DATA_DIR": Path(self.tmp.name), "DB_PATH": Path(self.tmp.name) / "relay.db",
                            "_DB_PRAGMAS_READY": False, "_DB_MUTEX": asyncio.Lock()}.items():
            patcher = patch.object(db, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        await db.init_db()
        self.key = await db.create_api_key("florist@example.test")
        self.kid = (await db.get_key_row(self.key))["id"]
        await db.enroll_steward(self.kid, "花房来客", "", "naturalist", "")
        self.s = await db.get_steward_by_key_id(self.kid)
        self.sid = self.s["id"]
        await self.set_player(tickets=1000, energy=20, mist_wit=50, standing=50)

    async def set_player(self, **values):
        async with db.connect() as conn:
            await conn.execute("UPDATE stewards SET " + ",".join(f"{k}=?" for k in values) + " WHERE id=?", (*values.values(), self.sid))
            await conn.commit()

    async def row(self):
        return await db.get_steward_by_id(self.sid)

    async def view(self):
        async with db.connect() as conn:
            return await florist.player_view(conn, await self.row())

    async def test_read_only_daily_gift_and_flower_language(self):
        before = await self.row()
        await florist.command(self.sid, "scan")
        self.assertFalse((await self.view())["visited_today"])
        self.assertEqual((await self.row())["standing"], before["standing"])
        await florist.command(self.sid)
        bag = await db.get_satchel(self.sid)
        gifted = await self.row()
        await florist.command(self.sid)
        self.assertEqual(await db.get_satchel(self.sid), bag)
        self.assertEqual((await self.row())["mist_wit"], gifted["mist_wit"])
        self.assertIn("首次免费", await florist.command(self.sid, "花语"))
        await florist.command(self.sid, "花语")
        self.assertEqual((await self.row())["tickets"], 995)
        with patch.object(db, "day_id", return_value=db.day_id() + 1):
            self.assertIn("首次免费", await florist.command(self.sid, "花语"))
            await florist.command(self.sid)
            self.assertTrue((await self.view())["visited_today"])

    async def test_daily_menu_seasons_and_discount(self):
        for name in season.SEASONS:
            with season.pinned_season(name):
                variants = set()
                for day in range(50, 75):
                    menu = florist.daily_flowers(day)
                    self.assertEqual(len(menu), 3)
                    self.assertIn("rose", menu)
                    self.assertTrue(all(name in FLOWERS[k]["seasons"] for k in menu))
                    self.assertEqual(menu, florist.daily_flowers(day))
                    variants.add(tuple(menu))
                self.assertGreater(len(variants), 1)
        with patch("server.lili_catalog.steward_domain_levels", AsyncMock(return_value={"farm": 5, "beach": 5})):
            self.assertEqual((await self.view())["flowers"][0]["cost"], 60)
            await florist.command(self.sid, "买花 玫瑰")
            self.assertEqual((await self.row())["tickets"], 940)

    async def test_concurrent_retry_and_shared_purge_cannot_double_charge(self):
        replies = await asyncio.gather(*(florist.command(self.sid, "买花 玫瑰", idem="same-purchase") for _ in range(4)))
        self.assertEqual(len(set(replies)), 1)
        self.assertEqual((await self.row())["tickets"], 932)
        self.assertEqual((await db.get_satchel(self.sid))["flower_rose"], 1)
        from server.v1.idempotency import _purge
        async with db.connect() as conn:
            await _purge(conn, db.now() + 86400)
            await conn.commit()
        await florist.command(self.sid, "买花 玫瑰", idem="same-purchase")
        self.assertEqual((await self.row())["tickets"], 932)
        with self.assertRaises(ValueError):
            await florist.command(self.sid, "花茶 玫瑰花茶", idem="same-purchase")

    async def test_insufficient_tickets_and_full_bag_roll_back(self):
        await self.set_player(tickets=1)
        with self.assertRaisesRegex(ValueError, "工分票不足"):
            await florist.command(self.sid, "买花 玫瑰")
        self.assertEqual((await self.row())["tickets"], 1)
        await self.set_player(tickets=1000)
        with patch.object(db, "add_item", AsyncMock(side_effect=ValueError("行囊满了"))):
            with self.assertRaisesRegex(ValueError, "满"):
                await florist.command(self.sid, "买花 玫瑰", idem="failed")
        self.assertEqual((await self.row())["tickets"], 1000)
        await florist.command(self.sid, "买花 玫瑰", idem="failed")
        self.assertEqual((await self.row())["tickets"], 932)

    async def test_tea_pack_brew_and_caps(self):
        await florist.command(self.sid, "花茶 玫瑰花茶包")
        self.assertEqual((await self.row())["energy"], 20)
        self.assertEqual((await self.row())["tickets"], 970)
        await florist.command(self.sid, "花茶 冲泡 玫瑰花茶包")
        self.assertEqual((await self.row())["tickets"], 970)
        self.assertEqual((await self.row())["energy"], 30)
        self.assertEqual((await self.row())["mist_wit"], 52)
        with self.assertRaises(ValueError):
            await florist.command(self.sid, "花茶 冲泡 玫瑰花茶包")
        await self.set_player(mist_wit=100)
        await florist.command(self.sid, "花茶 桂花姜茶")
        self.assertEqual((await self.row())["tickets"], 922)
        self.assertEqual((await self.row())["mist_wit"], 100)

    async def test_dry_hut_empty_slot_and_no_overwrite(self):
        await florist.command(self.sid, "买花 玫瑰")
        with self.assertRaisesRegex(ValueError, "小屋"):
            await florist.command(self.sid, "干花 玫瑰")
        await self.set_player(hut_built=1, hut_level=1, tickets=1)
        with self.assertRaisesRegex(ValueError, "工分票不足"):
            await florist.command(self.sid, "干花 玫瑰")
        self.assertEqual((await db.get_satchel(self.sid))["flower_rose"], 1)
        await self.set_player(tickets=1000)
        await florist.command(self.sid, "干花 玫瑰")
        self.assertEqual((await self.row())["tickets"], 972)
        self.assertEqual(hut._fit_name("deco_flower_rose"), "玫瑰干花")
        self.assertGreater(hut._fitting_value("deco_flower_rose")["cost"], 0)
        async with db.connect() as conn:
            slots = await hut._fittings(conn, self.sid)
            self.assertIn("deco_flower_rose", slots.values())
            for slot in hut._slots(1)[1]:
                await conn.execute("INSERT OR IGNORE INTO hut_fittings VALUES(?,?,?,?)", (self.sid, slot, "deco_flower_rose", db.now()))
            await db.add_item(conn, self.sid, "flower_rose", 1)
            await conn.commit()
        with self.assertRaisesRegex(ValueError, "空软装槽"):
            await florist.command(self.sid, "干花 玫瑰")
        self.assertEqual((await self.row())["tickets"], 972)
        self.assertEqual((await db.get_satchel(self.sid))["flower_rose"], 1)

    async def test_stamp_title_and_mcp_aliases(self):
        from server import mcp_dispatch, progress
        with patch.object(game, "require_steward", AsyncMock(return_value=self.s)):
            self.assertIn("默语花房", await mcp_dispatch.visit_bundle(self.kid, "默默 scan"))
            self.assertIn("当季花", await mcp_dispatch.visit_bundle(self.kid, "花店 help"))
            await mcp_dispatch.visit_bundle(self.kid, "momo")
        day = db.day_id()
        for offset in range(7):
            with patch.object(db, "day_id", return_value=day + offset):
                await florist.command(self.sid)
                await florist.command(self.sid, "记名")
                await florist.command(self.sid, "记名")
        self.assertEqual((await self.view())["stamps"], 7)
        async with db.connect() as conn:
            self.assertTrue(await progress._check_florist_regular(conn, self.s))
            titles = await (await conn.execute("SELECT ach_key FROM steward_achievements WHERE steward_id=?", (self.sid,))).fetchall()
        self.assertIn("florist_regular", [r[0] for r in titles])

    async def test_http_auth_commands_and_shared_state(self):
        import httpx
        from fastapi import FastAPI
        from server.v1.florist_routes import router
        app = FastAPI()
        app.include_router(router)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            self.assertEqual((await client.get("/api/v1/florist")).status_code, 401)
            client.headers["Authorization"] = "Bearer " + self.key
            view = await client.get("/api/v1/florist")
            self.assertEqual(view.status_code, 200)
            self.assertFalse(view.json()["florist"]["visited_today"])
            with patch.object(game, "require_steward", AsyncMock(return_value=self.s)):
                for _ in range(2):
                    bought = await client.post("/api/v1/florist/act", json={"kind": "buy", "target": "rose", "price": 0}, headers={"Idempotency-Key": "http-buy"})
                    self.assertEqual(bought.status_code, 200, bought.text)
                self.assertEqual((await self.row())["tickets"], 932)
                bad = await client.post("/api/v1/florist/act", json={"kind": "buy", "target": "rose 任意命令"})
                self.assertEqual(bad.status_code, 400)
                tea = await client.post("/api/v1/florist/act", json={"kind": "tea", "target": "rose"})
                self.assertEqual(tea.status_code, 200)
        self.assertEqual((await db.get_satchel(self.sid))["flower_rose"], 1)
        self.assertEqual((await self.row())["tickets"], 894)


if __name__ == "__main__":
    unittest.main()

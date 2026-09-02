"""导演约会的权限、幂等扣费、失败恢复、旧库与真实 HTTP 协议回归。"""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import companion_date as dates, date_director as director, db


def card(kind="choice", action="meal", last=False):
    return director.normalize({"kind": kind, "title": "雨停前的两人", "narrative": "雨声落在窗边，两人商量着下一段路。",
        "options": [{"label": "一起吃饭", "action": action, "cost": -999}, {"label": "聊一会儿", "action": "stay"}] if kind == "choice" else []}, dates.ACTIONS, last=last)


class DateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="date-test-")
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"DATE_DIRECTOR_URL": "https://director.example/v1", "DATE_DIRECTOR_API_KEY": "test-secret", "DATE_DIRECTOR_MODEL": "test-model"})
        self.env.start()
        self.addCleanup(self.env.stop)
        db.DATA_DIR = Path(self.tmp.name)
        db.DB_PATH = db.DATA_DIR / "relay.db"
        db._DB_PRAGMAS_READY = False
        db._DB_MUTEX = asyncio.Lock()
        await db.init_db()
        self.key = await db.create_api_key("date@example.com")
        keyrow = await db.get_key_row(self.key)
        await db.enroll_steward(keyrow["id"], "同行者", "", "naturalist", "")
        self.s = await db.get_steward_by_key_id(keyrow["id"])
        self.sid = self.s["id"]
        async with db.connect() as conn:
            await conn.execute("UPDATE stewards SET tickets=5000 WHERE id=?", (self.sid,))
            await conn.commit()

    async def money(self):
        return (await db.get_steward_by_id(self.sid))["tickets"]

    async def start(self):
        await dates.command(self.s, "约会 小馆 | 想一起听雨")
        row = (await dates.snapshot(self.sid))["dates"][0]
        await dates.respond(self.sid, row["id"], "eatery", accept=True)
        return row

    async def test_end_to_end_and_paid_replay(self):
        before_stock = await db.get_satchel(self.sid)
        before_xp = (await db.get_steward_by_id(self.sid))["xp"]
        row = await self.start()
        await dates.respond(self.sid, row["id"], "eatery", accept=True)
        with patch.object(director, "generate", AsyncMock(side_effect=[card(), card("event"), card(action="go_灯塔"), card("ending")])) as model:
            self.assertIn("188 票", await dates.command(self.s, "继续 0"))
            await dates.command(self.s, "查看")
            self.assertEqual(model.await_count, 1)
            with self.assertRaisesRegex(ValueError, "有选项"):
                await dates.command(self.s, "继续 1")
            await dates.command(self.s, "选择 1 A")
            paid = await self.money()
            await dates.command(self.s, "选择 1 A")
            self.assertEqual(await self.money(), paid)
            self.assertEqual(model.await_count, 2)
            self.assertEqual(model.call_args.args[0]["history"][0]["choice"]["cost"], 188)
            await dates.command(self.s, "继续 2")
            await dates.command(self.s, "选择 3 A")
        end = (await dates.snapshot(self.sid))["dates"][0]
        self.assertEqual(end["status"], "completed")
        self.assertEqual(end["place"], "灯塔")
        self.assertEqual(end["total_spent"], 188 + 188 + 198)
        self.assertEqual(await self.money(), 5000 - end["total_spent"])
        self.assertEqual(await db.get_satchel(self.sid), before_stock)
        self.assertEqual((await db.get_steward_by_id(self.sid))["xp"], before_xp)
        from server import memory_archive
        async with db.connect() as conn:
            reviews = await memory_archive.list_memories(conn, self.sid)
            self.assertTrue(any(r["kind"] == "date" for r in reviews))
            review = await memory_archive._load_review(conn, self.sid, "date", str(row["id"]), "")
        self.assertIn("188", review["chapters"][0]["text"])
        await dates.invite(self.sid, "小馆")  # 同地点可以再次玩。

    async def test_auth_location_expiry_and_no_mcp_accept(self):
        with patch.dict(os.environ, {"DATE_DIRECTOR_MODEL": ""}):
            with self.assertRaisesRegex(ValueError, "尚未配置"):
                await dates.invite(self.sid, "小馆")
        self.assertEqual(await self.money(), 5000)
        await dates.invite(self.sid, "小馆")
        await dates.invite(self.sid, "小馆")
        self.assertEqual(await self.money(), 4812)
        row = (await dates.snapshot(self.sid))["dates"][0]
        with self.assertRaises(ValueError):
            await dates.respond(self.sid + 1, row["id"], "eatery", accept=True)
        with self.assertRaisesRegex(ValueError, "先到"):
            await dates.respond(self.sid, row["id"], "map", accept=True)
        with self.assertRaises(ValueError):
            await dates.command(self.s, "接受")
        with self.assertRaisesRegex(ValueError, "应邀"):
            await dates.advance(self.sid, 0)
        async with db.connect() as conn:
            await conn.execute("UPDATE companion_dates SET expires_at=1 WHERE id=?", (row["id"],))
            await conn.commit()
        with self.assertRaisesRegex(ValueError, "过期"):
            await dates.respond(self.sid, row["id"], "eatery", accept=True)

    async def test_generation_failure_and_exit_while_generating(self):
        await self.start()
        with patch.object(director, "generate", AsyncMock(return_value=card())):
            await dates.advance(self.sid, 0)
        with patch.object(director, "generate", AsyncMock(side_effect=ValueError("model failed"))):
            with self.assertRaises(ValueError):
                await dates.advance(self.sid, 1, "A")
        view = (await dates.snapshot(self.sid))["dates"][0]
        self.assertEqual(view["seq"], 1)
        self.assertFalse(view["generating"])
        self.assertEqual(await self.money(), 4812)
        ready, release = asyncio.Event(), asyncio.Event()
        async def delayed(*args, **kwargs):
            ready.set()
            await release.wait()
            return card("event")
        with patch.object(director, "generate", delayed):
            task = asyncio.create_task(dates.advance(self.sid, 1, "A"))
            await ready.wait()
            self.assertIn("正在生成", await dates.advance(self.sid, 1, "A"))
            await dates.leave(self.sid)
            release.set()
            with self.assertRaisesRegex(ValueError, "状态已变化"):
                await task
        self.assertEqual(await self.money(), 4812)
        self.assertEqual((await dates.snapshot(self.sid))["dates"][0]["status"], "exited")

    async def test_old_database_migration(self):
        await dates.invite(self.sid, "海边")
        async with db.connect() as conn:
            await conn.execute("UPDATE companion_dates SET event_json='[\"旧的沙滩回忆\"]',status='completed',completed_at=1")
            for name in ("state_json", "revision", "generating_until", "total_spent"):
                await conn.execute(f"ALTER TABLE companion_dates DROP COLUMN {name}")
            await conn.commit()
        await db.init_db()
        async with db.connect() as conn:
            row = await dates._latest(conn, self.sid)
        self.assertIn("旧的沙滩回忆", dates.archive_chapters(row)[0]["text"])

    async def test_director_http_contract_and_rejection(self):
        import httpx
        client_type = httpx.AsyncClient
        def respond(request):
            self.assertEqual(str(request.url), "https://director.example/v1/chat/completions")
            self.assertEqual(request.headers["authorization"], "Bearer test-secret")
            self.assertEqual(json.loads(request.content)["model"], "test-model")
            output = {"kind": "choice", "title": "特别菜单", "narrative": "他们翻开了菜单。", "options": [{"action": "meal", "label": "尝尝热菜", "cost": -100}, {"action": "stay", "label": "再聊一会儿"}]}
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(output)}}]})
        def client(**kwargs):
            return client_type(transport=httpx.MockTransport(respond), **kwargs)
        with patch.object(director.httpx, "AsyncClient", client):
            result = await director.generate({"scene_number": 1}, dates.ACTIONS)
        self.assertEqual(result["options"][0]["cost"], 188)
        with self.assertRaises(ValueError):
            director.normalize({"kind": "choice", "title": "x", "narrative": "x", "options": [{"action": "give_money", "label": "送钱"}]}, dates.ACTIONS, last=False)
        paid_only = director.normalize({"kind": "choice", "title": "x", "narrative": "x", "options": [{"action": "meal", "label": "吃饭"}, {"action": "feast", "label": "特别晚餐"}]}, dates.ACTIONS, last=False)
        self.assertEqual([o["id"] for o in paid_only["options"]], ["A", "B", "C"])
        self.assertEqual(paid_only["options"][-1]["cost"], 0)

    async def test_anniversary_and_married_outing(self):
        wedding = int(datetime(2025, 9, 2, 12, tzinfo=timezone.utc).timestamp()) // 86400
        anniversary = int(datetime(2026, 9, 2, 12, tzinfo=timezone.utc).timestamp())
        async with db.connect() as conn:
            await conn.execute("INSERT INTO marriages(steward_id,partner_name,status,wedding_at,created_at,updated_at) VALUES(?,?,'married',?,?,?)",
                               (self.sid, "人类伴侣", wedding, anniversary, anniversary))
            await conn.commit()
        with patch.object(db, "now", return_value=anniversary):
            await dates.invite(self.sid, "小馆")
            row = (await dates.snapshot(self.sid))["dates"][0]
            self.assertTrue(row["special"])
            self.assertEqual(row["kind_label"], "出去走走")
            self.assertEqual(row["partner"], "人类伴侣")
            await dates.respond(self.sid, row["id"], "eatery", accept=True)
            with patch.object(director, "generate", AsyncMock(return_value=card("event"))) as model:
                await dates.advance(self.sid, 0)
                self.assertTrue(model.call_args.args[0]["special"])

    async def test_balance_changes_while_generating_do_not_overdraw(self):
        await self.start()
        with patch.object(director, "generate", AsyncMock(return_value=card())):
            await dates.advance(self.sid, 0)
        async def spend_elsewhere(*args, **kwargs):
            async with db.connect() as conn:
                await conn.execute("UPDATE stewards SET tickets=100 WHERE id=?", (self.sid,))
                await conn.commit()
            return card("event")
        with patch.object(director, "generate", spend_elsewhere):
            with self.assertRaisesRegex(ValueError, "工分票不足"):
                await dates.advance(self.sid, 1, "A")
        row = (await dates.snapshot(self.sid))["dates"][0]
        self.assertEqual(row["seq"], 1)
        self.assertEqual(row["total_spent"], 188)
        self.assertFalse(row["generating"])
        self.assertEqual(await self.money(), 100)

    async def test_mobile_routes_only_respond_and_read(self):
        import httpx
        from fastapi import FastAPI
        from server.v1.date_routes import router
        app = FastAPI()
        app.include_router(router)
        await dates.invite(self.sid, "小馆")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            self.assertEqual((await client.get("/api/v1/dates")).status_code, 401)
            headers = {"Authorization": f"Bearer {self.key}"}
            response = await client.get("/api/v1/dates", headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("test-secret", response.text)
            date = response.json()["dates"][0]
            accepted = await client.post("/api/v1/dates/respond", headers=headers, json={"date_id": date["id"], "scene": "eatery", "accept": True})
            self.assertEqual(accepted.json()["dates"][0]["status"], "active")
            self.assertEqual((await client.post("/api/v1/dates/choose", headers=headers, json={})).status_code, 404)


if __name__ == "__main__":
    unittest.main()

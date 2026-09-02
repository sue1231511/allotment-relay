"""约会生成必须独立于 MCP 请求的取消和连接寿命。"""
import asyncio
from contextlib import asynccontextmanager
import contextvars
import os
import unittest
from unittest.mock import AsyncMock, patch

import anyio

import test_companion_date as base

card, dates, director = base.card, base.dates, base.director
db = base.db


class DateGenerationJobsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = base.DateTests.asyncSetUp
    start = base.DateTests.start
    money = base.DateTests.money

    async def settled(self):
        tasks = list(dates._generation_tasks)
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 5)

    async def test_cancelled_mcp_request_does_not_abandon_generation(self):
        await self.start()
        started, release = asyncio.Event(), asyncio.Event()
        request_scope = []

        async def model(*args, **kwargs):
            started.set()
            await release.wait()
            return card()

        async def request():
            with anyio.CancelScope() as scope:
                request_scope.append(scope)
                await dates.command(self.s, "继续 0")

        with patch.object(director, "generate", model):
            async with anyio.create_task_group() as group:
                group.start_soon(request)
                await asyncio.wait_for(started.wait(), 5)
                request_scope[0].cancel()
            release.set()
            for _ in range(100):
                row = (await dates.snapshot(self.sid))["dates"][0]
                if row["seq"] == 1:
                    break
                await asyncio.sleep(0.01)
        self.assertEqual(row["seq"], 1, "MCP 被取消后，已受理的导演生成也被中断，旁白未保存")
        self.assertFalse(row["generating"])
        self.assertEqual(row["director_error"], "")
        self.assertEqual(await self.money(), 4812)

    async def test_receipt_readonly_polling_and_duplicate_do_not_start_another_job(self):
        await self.start()
        started, release = asyncio.Event(), asyncio.Event()

        async def model(*args, **kwargs):
            started.set()
            await release.wait()
            return card()

        with patch.object(dates, "REPLY_WAIT_SECONDS", 0.01), patch.object(director, "generate", AsyncMock(side_effect=model)) as generate:
            reply = await dates.command(self.s, "继续 0")
            self.assertIn("已受理", reply)
            await asyncio.wait_for(started.wait(), 5)
            self.assertIn("后台生成", await dates.command(self.s, "查看"))
            self.assertIn("不要重复推进", await dates.command(self.s, "继续 0"))
            self.assertEqual(generate.await_count, 1)
            self.assertEqual(await self.money(), 4812)
            release.set()
            await self.settled()
            reply = await dates.command(self.s, "查看")
            self.assertIn("【导演旁白】", reply)
            self.assertEqual(generate.await_count, 1)
        self.assertFalse(dates._generation_tasks)

    async def test_paid_background_failure_keeps_current_scene_and_balance(self):
        await self.start()
        with patch.object(director, "generate", AsyncMock(return_value=card())):
            await dates.advance(self.sid, 0)
        release = asyncio.Event()

        async def model(*args, **kwargs):
            await release.wait()
            raise ValueError("剧情导演连接失败或超时。")

        with patch.object(dates, "REPLY_WAIT_SECONDS", 0.01), patch.object(director, "generate", AsyncMock(side_effect=model)) as generate:
            self.assertIn("已受理", await dates.command(self.s, "选择 1 A"))
            pending = (await dates.snapshot(self.sid))["dates"][0]
            self.assertIn("雨声", pending["current"]["narrative"])
            self.assertEqual(await self.money(), 4812)
            release.set()
            await self.settled()
            failed = (await dates.snapshot(self.sid))["dates"][0]
            self.assertEqual(failed["seq"], 1)
            self.assertEqual(failed["history"], [])
            self.assertEqual(failed["generation_state"], "failed")
            self.assertIn("连接失败", failed["director_error"])
            self.assertEqual(generate.await_count, 1)
            self.assertEqual(await self.money(), 4812)

    async def test_shutdown_clears_lease_and_saves_interruption(self):
        await self.start()
        started = asyncio.Event()

        async def model(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()

        with patch.object(dates, "REPLY_WAIT_SECONDS", 0.01), patch.object(director, "generate", model):
            await dates.command(self.s, "继续 0")
            await asyncio.wait_for(started.wait(), 5)
            await dates.shutdown_generations()
        row = (await dates.snapshot(self.sid))["dates"][0]
        self.assertEqual(row["generation_state"], "failed")
        self.assertIn("服务端中断", row["director_error"])
        self.assertFalse(row["generating"])
        self.assertEqual(row["seq"], 0)
        self.assertFalse(dates._generation_tasks)

    async def test_exit_cancels_background_choice_without_charge(self):
        await self.start()
        with patch.object(director, "generate", AsyncMock(return_value=card())):
            await dates.advance(self.sid, 0)
        started = asyncio.Event()

        async def model(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()

        with patch.object(dates, "REPLY_WAIT_SECONDS", 0.01), patch.object(director, "generate", model):
            await dates.command(self.s, "选择 1 A")
            await asyncio.wait_for(started.wait(), 5)
            await dates.command(self.s, "退出")
        row = (await dates.snapshot(self.sid))["dates"][0]
        self.assertEqual(row["status"], "exited")
        self.assertEqual(row["seq"], 1)
        self.assertEqual(await self.money(), 4812)
        self.assertFalse(dates._generation_tasks)

    async def test_worker_does_not_inherit_request_connection_or_context(self):
        await self.start()
        request_value = contextvars.ContextVar("date_request_only", default=None)
        token = request_value.set("request-private")

        async def model(*args, **kwargs):
            self.assertIsNone(request_value.get())
            self.assertIsNone(db._DB_CONN.get())
            return card()

        try:
            with patch.object(dates, "REPLY_WAIT_SECONDS", 0), patch.object(director, "generate", model):
                async with db.connect():
                    await dates.command(self.s, "继续 0")
                await self.settled()
        finally:
            request_value.reset(token)
        self.assertEqual((await dates.snapshot(self.sid))["dates"][0]["seq"], 1)

    async def test_model_deadline_is_independent_of_reply_wait(self):
        await self.start()

        async def model(*args, **kwargs):
            await asyncio.Event().wait()

        with patch.object(dates, "REPLY_WAIT_SECONDS", 0.01), patch.object(director, "request_timeout", return_value=1), patch.object(director, "generate", model):
            self.assertIn("已受理", await dates.command(self.s, "继续 0"))
            await self.settled()
        row = (await dates.snapshot(self.sid))["dates"][0]
        self.assertEqual(row["generation_state"], "failed")
        self.assertIn("超过 1 秒", row["director_error"])
        self.assertEqual(await self.money(), 4812)

    async def test_timeout_config_validated_before_booking_and_sent_to_http_client(self):
        for value in ["no", "14", "301"]:
            with patch.dict(os.environ, {"DATE_DIRECTOR_TIMEOUT_SECONDS": value}):
                with self.assertRaisesRegex(ValueError, "15～300"):
                    await dates.invite(self.sid, "小馆")
        self.assertEqual(await self.money(), 5000)
        with patch.dict(os.environ, {"DATE_DIRECTOR_TIMEOUT_SECONDS": "180"}):
            self.assertEqual(director.request_timeout(), 180)
            await self.start()
            job = await dates._prepare_generation(self.sid, 0)
            self.assertEqual(job["timeout"], 180)
            self.assertGreaterEqual(job["lease"], db.now() + 239)
        with patch.dict(os.environ, {"DATE_DIRECTOR_TIMEOUT_SECONDS": "120"}):
            import httpx
            client_type = httpx.AsyncClient

            def client(**kwargs):
                self.assertEqual(kwargs["timeout"].read, 120)
                self.assertEqual(kwargs["timeout"].connect, 10)
                output = {"choices": [{"message": {"content": base.json.dumps(card())}}]}
                return client_type(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=output)), **kwargs)

            with patch.object(director.httpx, "AsyncClient", client):
                result = await director.generate({"scene_number": 1}, dates.ACTIONS)
            self.assertIn("雨声", result["narrative"])

    async def test_cancel_during_preparation_still_hands_off_reserved_scene(self):
        await self.start()
        reserved, handoff, generated = asyncio.Event(), asyncio.Event(), asyncio.Event()
        scopes = []
        original = dates._prepare_generation

        async def prepare(*args, **kwargs):
            job = await original(*args, **kwargs)
            reserved.set()
            await handoff.wait()
            return job

        async def model(*args, **kwargs):
            generated.set()
            return card()

        async def request():
            with anyio.CancelScope() as scope:
                scopes.append(scope)
                await dates.command(self.s, "继续 0")

        with patch.object(dates, "_prepare_generation", prepare), patch.object(director, "generate", model):
            async with anyio.create_task_group() as group:
                group.start_soon(request)
                await asyncio.wait_for(reserved.wait(), 5)
                scopes[0].cancel()
                handoff.set()
            await asyncio.wait_for(generated.wait(), 5)
            await self.settled()
        self.assertEqual((await dates.snapshot(self.sid))["dates"][0]["seq"], 1)

    async def test_application_lifespan_shuts_down_jobs_even_on_error(self):
        from server import main

        @asynccontextmanager
        async def session():
            yield

        stopped = AsyncMock()
        with patch.object(main.db, "init_db", AsyncMock()), patch.object(main.mcp_session_manager, "run", session), patch.object(dates, "shutdown_generations", stopped):
            with self.assertRaisesRegex(RuntimeError, "lifespan-test"):
                async with main.lifespan(main.app):
                    raise RuntimeError("lifespan-test")
            stopped.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()

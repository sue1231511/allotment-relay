"""MiniMax 分离思考及 JSON 包装兼容；绝不从思考取旁白或猜补交易。"""
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import AsyncMock, patch

import httpx
import test_companion_date as base

director, dates = base.director, base.dates


def scene(**extra):
    return {"kind": "choice", "title": "窗边听雨", "narrative": '他说："再坐一会儿。"窗上有 {雨痕}，菜单写着 [甜点]。',
            "options": [{"label": "加一份甜点", "action": "dessert", "cost": -888},
                        {"label": "继续聊天", "action": "stay"}], **extra}


def response(content, **fields):
    return {"choices": [{"finish_reason": "stop", "message": {"content": content, **fields}}]}


class DirectorJsonTests(unittest.TestCase):
    def test_wrappers_preserve_actual_card_and_server_prices(self):
        raw = json.dumps(scene(), ensure_ascii=False)
        thoughts = '<think>private thoughts ' + json.dumps(scene(title="思考中的草稿")) + '</think>'
        for content in [raw, "\ufeff" + raw, "```JSON\n" + raw + "\n```",
                        "以下为本幕：\n```json\n" + raw + "\n```\n以上是本幕。",
                        thoughts + raw, thoughts + "\n" + thoughts + "\n```json\n" + raw + "\n```",
                        [{"type": "reasoning", "text": "private thoughts"}, {"type": "text", "text": thoughts},
                         {"type": "output_text", "text": raw}]]:
            with self.subTest(content=type(content).__name__):
                result = director._read_card(response(content, reasoning_details=[{"text": "private thoughts"}],
                                                     reasoning_content="private thoughts"), dates.ACTIONS, last=False)
                self.assertEqual(result["narrative"], scene()["narrative"])
                self.assertEqual(result["title"], "窗边听雨")
                self.assertEqual(result["options"][0]["cost"], 68)
                self.assertNotIn("private thoughts", str(result))

    def test_incomplete_or_ambiguous_cards_are_not_repaired(self):
        raw = json.dumps(scene())
        for content in [raw[:-1], raw + raw, "```json\n" + raw + "\n```\n```json\n" + raw + "\n```",
                        "[" + raw + "]", '{"broken": ' + raw, raw + ', "options": []}',
                        '{kind: event,title:标题,narrative:正文,options:[]}', "正在生成，请继续",
                        '<think>private thoughts ' + raw, '<think>private thoughts ' + raw + '</think>',
                        '前言 <think>private thoughts ' + raw + '</think>',
                        {"kind": "event"}]:
            with self.subTest(content=type(content).__name__):
                with self.assertRaises(ValueError) as error:
                    director._read_card(response(content), dates.ACTIONS, last=False)
                self.assertNotIn("private thoughts", str(error.exception))

    def test_reasoning_fields_never_substitute_for_final_content(self):
        for content in [None, "", " ", []]:
            with self.assertRaisesRegex(ValueError, "空正文"):
                director._read_card(response(content, reasoning_details=[{"text": json.dumps(scene())}],
                                             reasoning_content=json.dumps(scene())), dates.ACTIONS, last=False)

    def test_wrappers_do_not_bypass_action_or_ending_validation(self):
        for raw, last, expected in [
            (scene(options=[{"action": "give_money", "label": "返现"}, {"action": "stay", "label": "聊天"}]), False, "没有的项目"),
            (scene(options=[{"action": "stay", "label": "聊天"}]), False, "选项不完整"),
            (scene(), True, "结尾")]:
            with self.assertRaisesRegex(ValueError, expected):
                director._read_card(response("这是结果：\n```json\n" + json.dumps(raw) + "\n```"), dates.ACTIONS, last=last)

    def test_docs_explain_minimax_and_readonly_recovery(self):
        root = Path(__file__).resolve().parents[1]
        for path in [root / "README.md", root.parent / "README.md", root / "server/marriage.py", root / "server/game.py"]:
            content = path.read_text(encoding="utf-8")
            for text in ["MiniMax", "reasoning_split", "思考", "原幕"]:
                self.assertIn(text, content, str(path))
        manual = (root / "server/templates/partials/island-manual-content.html").read_text(encoding="utf-8")
        self.assertIn("思考不是旁白", manual)
        self.assertIn("不扣本次选项费", manual)


class DirectorJsonHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_minimax_split_is_top_level_and_other_models_unchanged(self):
        client_type = httpx.AsyncClient
        for model in ["MiniMax-M3", "MiniMax-M2.5", "minimax/MiniMax-M3", "test-model"]:
            requests = []
            def respond(request):
                body = json.loads(request.content)
                requests.append(body)
                self.assertEqual(body["model"], model)
                self.assertNotIn("extra_body", body)
                if "minimax" in model.casefold():
                    self.assertIs(body["reasoning_split"], True)
                else:
                    self.assertNotIn("reasoning_split", body)
                prompt = body["messages"][0]["content"]
                # 两个结构示例必须真的能被 JSON 解析且通过游戏验证。
                examples = re.findall(r"结构示例：(.*?)。(?=选择结构示例|示例只说明|event)", prompt)
                self.assertEqual(len(examples), 2)
                for example in examples:
                    director.normalize(json.loads(example), dates.ACTIONS, last=False)
                return httpx.Response(200, json=response(json.dumps(scene()), reasoning_details=[{"text": "private thoughts"}]))
            def client(**kwargs):
                return client_type(transport=httpx.MockTransport(respond), **kwargs)
            with patch.dict(os.environ, {"DATE_DIRECTOR_MODEL": model, "DATE_DIRECTOR_URL": "https://director.example/v1",
                                         "DATE_DIRECTOR_API_KEY": "test-secret"}), patch.object(director.httpx, "AsyncClient", client):
                result = await director.generate({"scene_number": 1}, dates.ACTIONS)
            self.assertEqual(len(requests), 1)
            self.assertEqual(result["options"][0]["cost"], 68)
            self.assertNotIn("private thoughts", str(result))


class DirectorJsonTransactionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = base.DateTests.asyncSetUp
    money = base.DateTests.money
    start = base.DateTests.start

    async def test_malformed_paid_scene_retry_keeps_narrative_and_charges_once(self):
        await self.start()
        with patch.object(director, "generate", AsyncMock(return_value=base.card())):
            await dates.advance(self.sid, 0)
        before = (await dates.snapshot(self.sid))["dates"][0]
        client_type = httpx.AsyncClient
        outputs = ["<think>private thoughts</think>\n{broken", "<think>private thoughts</think>\n" +
                   json.dumps(scene(kind="event", options=[]))]
        def respond(request):
            return httpx.Response(200, json=response(outputs.pop(0), reasoning_details=[{"text": "private thoughts"}]))
        def client(**kwargs):
            return client_type(transport=httpx.MockTransport(respond), **kwargs)
        with patch.object(director.httpx, "AsyncClient", client):
            with self.assertRaisesRegex(ValueError, "完整JSON"):
                await dates.command(self.s, "选择 1 A")
            failed = (await dates.snapshot(self.sid))["dates"][0]
            self.assertEqual(failed["seq"], 1)
            self.assertEqual(failed["current"], before["current"])
            self.assertEqual(failed["history"], before["history"])
            self.assertEqual(failed["generation_state"], "failed")
            self.assertEqual(await self.money(), 4812)
            self.assertNotIn("private thoughts", str(failed))
            await dates.command(self.s, "选择 1 A")
            self.assertEqual(await self.money(), 4624)
            await dates.command(self.s, "选择 1 A")
            self.assertEqual(await self.money(), 4624)
        ready = (await dates.snapshot(self.sid))["dates"][0]
        self.assertEqual(ready["seq"], 2)
        self.assertEqual(ready["director_error"], "")
        self.assertNotIn("private thoughts", str(ready))


if __name__ == "__main__":
    unittest.main()

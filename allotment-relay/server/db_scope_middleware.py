"""请求域数据库连接中间件：一次请求里所有 db.connect() 共用一个连接（见 db.request_scope）。

三条边界，都是为了「不让一个慢客户端或长连接占住全局数据库锁」：
- 请求体先在锁外读完再进请求域；超过上限或分块上传的不进请求域，走老路（每个块各开连接）。
- 响应先缓存，请求域结束、锁放掉以后才发给客户端。
- /mcp（长连接流）和 /static（静态文件，不碰库）不进请求域；MCP 工具调用在 mcp_dispatch._call_ops 里单独套。
"""
from __future__ import annotations

import asyncio
import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import db

_log = logging.getLogger(__name__)

MAX_BUFFERED_BODY = 4 * 1024 * 1024  # 比贴纸上限 3MB 略大
SKIP_PREFIXES = ("/mcp", "/static/")


class DbScopeMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._skip(scope):
            await self.app(scope, receive, send)
            return
        buffered: list[Message] = []
        total = 0
        try:
            while True:
                msg = await receive()
                buffered.append(msg)
                if msg["type"] != "http.request":
                    break  # 客户端已断开，照样交给应用处理
                total += len(msg.get("body") or b"")
                if total > MAX_BUFFERED_BODY:
                    raise _TooBig
                if not msg.get("more_body", False):
                    break
        except _TooBig:
            # 超限：把已读到的塞回去，走老路
            await self.app(scope, _replay(buffered, receive), send)
            return
        except Exception:
            _log.exception("请求体预读失败 位置=DbScopeMiddleware.__call__ 路径=%s", scope.get("path"))
            raise

        out: list[Message] = []

        async def capture(message: Message) -> None:
            out.append(message)

        failure: BaseException | None = None
        async with db.request_scope():
            try:
                await self.app(scope, _replay(buffered, receive), capture)
            except BaseException as exc:  # noqa: BLE001  先放锁、再把错误原样抛出
                failure = exc
        # 锁已经放掉，再往客户端写
        if failure is None or (out and not isinstance(failure, asyncio.CancelledError)):
            for message in out:
                await send(message)
        if failure is not None:
            raise failure

    @staticmethod
    def _skip(scope: Scope) -> bool:
        path = scope.get("path") or ""
        return path == "/mcp" or path.startswith(SKIP_PREFIXES)


class _TooBig(Exception):
    pass


def _replay(buffered: list[Message], receive: Receive) -> Receive:
    pending = list(buffered)

    async def replay() -> Message:
        if pending:
            return pending.pop(0)
        return await receive()

    return replay

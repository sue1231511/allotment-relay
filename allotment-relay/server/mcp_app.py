from contextvars import ContextVar

import aiosqlite
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from . import db, game
from . import mcp_dispatch as mux
from .config import DATA_DIR

current_key_id: ContextVar[int | None] = ContextVar("current_key_id", default=None)


def extract_api_key(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.query_params.get("api_key")


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        api_key = extract_api_key(request)
        if not api_key:
            return JSONResponse(
                {"detail": "缺少凭证。Authorization: Bearer <ar_sk_...> 或 ?api_key=<...>"},
                status_code=401,
            )
        try:
            row = await db.get_key_row(api_key)
        except (aiosqlite.Error, OSError) as exc:
            return JSONResponse(
                {
                    "detail": (
                        f"数据库不可用 ({DATA_DIR}): {exc}. "
                        "请检查 Zeabur 持久卷是否挂载到 /app/server/data"
                    )
                },
                status_code=503,
            )
        if not row:
            return JSONResponse({"detail": "无效的潮汐岛凭证"}, status_code=401)
        token = current_key_id.set(row["id"])
        try:
            return await call_next(request)
        finally:
            current_key_id.reset(token)


def _kid() -> int:
    kid = current_key_id.get()
    if kid is None:
        raise RuntimeError("未认证")
    return kid


mcp = MCPServer(
    "allotment-relay",
    instructions=(
        "潮汐岛沿海份地。11 个工具，子命令写在 command 里。"
        "先 steward_ops enroll，再 relay_manual / plot_ops status。"
    ),
)


@mcp.tool(description="潮汐岛手册：11 个工具、子命令、当前天气潮汐。")
async def relay_manual() -> str:
    return await game.relay_manual()


@mcp.tool(description="管理员：enroll 名字 / sheet / revise / peer 名字 / guild / board [tickets|level|me]。登记可另填 name/motto/badge/portrait")
async def steward_ops(
    command: str = "sheet",
    name: str = "",
    motto: str = "",
    badge: str = "naturalist",
    portrait: str = "",
) -> str:
    return await mux.steward_ops(_kid(), command, name, motto, badge, portrait)


@mcp.tool(description="份地：sow/tend/gather/chop/forage/weather；温室 shed；公共物资 commons；意外 incident/repair")
async def plot_ops(command: str = "") -> str:
    return await mux.plot_bundle(_kid(), command)


@mcp.tool(description="小屋 build/install；畜栏 barn；吉祥物 mascot。空 command 看子命令")
async def hut_ops(command: str = "") -> str:
    return await mux.hut_bundle(_kid(), command)


@mcp.tool(description="渔获 net/cast；渔排 pen；出海 voyage（fight/flee 可省略前缀）；赶海 beach/dig；渔具 gear；工具 tool；Boss boss")
async def tide_ops(command: str = "") -> str:
    return await mux.tide_bundle(_kid(), command)


@mcp.tool(description="行囊 list/vend/gift；交换台 swap；集市 market")
async def tote_ops(command: str = "") -> str:
    return await mux.tote_bundle(_kid(), command)


@mcp.tool(description="厨房：menu/cook/brew/eat/store/shop — 星级料理、灶台、岸畔小馆")
async def kitchen_ops(command: str = "") -> str:
    return await mux.kitchen_bundle(_kid(), command)


@mcp.tool(description="协作：online/assist；合约 contract；周目标 league；公告 beacon；漂流瓶 bottle")
async def alliance_ops(command: str = "") -> str:
    return await mux.alliance_bundle(_kid(), command)


@mcp.tool(description="访客：NPC list/visit；栗栗 lili（scan/trade/summon 贝壳/pet）；韶年 shaonian；Tt酱 tt 杂货店；lore；诊所 clinic（treat 可省略前缀）")
async def visit_ops(command: str = "") -> str:
    return await mux.visit_bundle(_kid(), command)


@mcp.tool(description="滨海酒吧：tonight/menu/order/work/chat/cheer — 老板娘营收心情·当晚事件·多岗位打工；心情由荔栀本人面板定，AI 可 cheer 提议哄她")
async def bar_ops(command: str) -> str:
    from . import bar
    return await bar.bar_ops(_kid(), command)


@mcp.tool(description="潮下（地下世界）：入口/影信/后室铺market/销赃sell/恶猫钱庄bank/监牢jail/深坑pit·fight·medic/赌场dice·lantern·draw/劫持hijack/强买muscle·push/寻仇grudge/哄猫猫cheer — undertide_ops help 看全表")
async def undertide_ops(command: str = "") -> str:
    from . import undertide
    return await undertide.undertide_ops(_kid(), command)


def _mcp_transport_security() -> TransportSecuritySettings:
    """Public cloud deploy: DNS rebinding guard blocks non-local Host headers (421)."""
    return TransportSecuritySettings(enable_dns_rebinding_protection=False)


def build_mcp_app():
    app = mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        host="0.0.0.0",
        transport_security=_mcp_transport_security(),
    )
    app.add_middleware(ApiKeyMiddleware)
    return app, mcp._lowlevel_server.session_manager

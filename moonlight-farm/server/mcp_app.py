from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp.server.mcpserver import MCPServer

from . import db, game

current_key_id: ContextVar[int | None] = ContextVar("current_key_id", default=None)


def extract_api_key(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.query_params.get("api_key")


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.rstrip("/") != "/mcp" and not request.url.path.startswith("/mcp/"):
            return await call_next(request)
        api_key = extract_api_key(request)
        if not api_key:
            return JSONResponse(
                {"detail": "缺少 API Key。使用 Authorization: Bearer <key> 或 ?api_key=<key>"},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="moonlight-farm"'},
            )
        row = await db.get_key_row(api_key)
        if not row:
            return JSONResponse({"detail": "无效的月光钥匙"}, status_code=401)
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
    "moonlight-farm",
    instructions="多人 AI 农场。先 garden_register，再 farm/fish/house/pet 等。",
)


@mcp.tool(description="查询玩法、工具列表与规则。开发或迷路时先看这个。")
async def garden_guide() -> str:
    return await game.garden_guide()


@mcp.tool(description="首次注册角色：取名、简介、物种、外观。每个 key 只能注册一次。")
async def garden_register(name: str, bio: str = "", species: str = "cat", appearance: str = "") -> str:
    player = await db.register_player(_kid(), name, bio, species, appearance)
    return (
        f"欢迎 {player['name']}！获得 {player['moon']} moon、{player['plot_count']} 块地、 starter 种子。\n"
        "接下来调用 garden_guide() 或直接 farm('status')"
    )


@mcp.tool(description="查看自己的农场、背包、小屋与宠物。")
async def garden_profile() -> str:
    return await game.garden_profile(_kid())


@mcp.tool(description="修改自己的简介或外观描述。")
async def garden_profile_edit(bio: str = "", appearance: str = "") -> str:
    return await game.garden_profile_edit(_kid(), bio, appearance)


@mcp.tool(description="查看其他园丁的公开资料。")
async def garden_whois(name: str) -> str:
    return await game.garden_whois(name)


@mcp.tool(description="打零工赚 moon。")
async def garden_work() -> str:
    return await game.garden_work(_kid())


@mcp.tool(description="农场命令：plant/water/harvest/steal/note/apologize/neighbors/status/buy。可用 ; 连接。")
async def farm(command: str) -> str:
    return await game.farm(_kid(), command)


@mcp.tool(description="钓鱼：cast [cost] 或 status。")
async def fish(command: str) -> str:
    return await game.fish(_kid(), command)


@mcp.tool(description="小屋：build/name/visit/gift/status。gift 例：gift Alice crop_cabbage 3")
async def house(command: str) -> str:
    return await game.house(_kid(), command)


@mcp.tool(description="宠物：adopt 名字 物种 / feed / play / status")
async def pet(command: str) -> str:
    return await game.pet(_kid(), command)


@mcp.tool(description="漂流瓶：throw 文本 [mood] / pick id / list / reply id 文本")
async def bottle(command: str) -> str:
    return await game.bottle(_kid(), command)


@mcp.tool(description="背包：list / sell item qty")
async def inventory(command: str) -> str:
    return await game.inventory(_kid(), command)


@mcp.tool(description="厨房：cook 食材1 食材2 [食材3] / recipes")
async def kitchen(command: str) -> str:
    return await game.kitchen(_kid(), command)


def build_mcp_app():
    app = mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
    )
    app.add_middleware(ApiKeyMiddleware)
    return app, mcp._lowlevel_server.session_manager

from contextvars import ContextVar
from typing import Annotated
from pydantic import Field

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
current_origin: ContextVar[str] = ContextVar("current_origin", default="")


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
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        scheme = proto.split(",")[0].strip() if proto else request.url.scheme
        host = (
            request.headers.get("x-forwarded-host")
            or request.headers.get("host")
            or request.url.netloc
        )
        host = host.split(",")[0].strip()
        origin_tok = current_origin.set(f"{scheme}://{host}".rstrip("/"))
        try:
            return await call_next(request)
        finally:
            current_origin.reset(origin_tok)
            current_key_id.reset(token)


def _kid() -> int:
    kid = current_key_id.get()
    if kid is None:
        raise RuntimeError("未认证")
    return kid


mcp = MCPServer(
    "allotment-relay",
    instructions=(
        "潮汐岛多人份地游戏，不是聊天沙盒；禁止发明工具。"
        "21个工具。先调 relay_manual；不会就 help。"
        "仅参数 command。细则在手册/help。"
    ),
)


@mcp.tool(description="必读手册，无参数。先调一次再动手；禁止发明指令。新号先 steward_ops enroll 名字。")
async def relay_manual() -> str:
    return await game.relay_manual()


@mcp.tool(description="身份档案。空=sheet。例：enroll 安 · 岛缘 · board tickets。人类地图左侧保留六项属性数值，右侧三项面板显示工分票/等级/岛缘；勿 invite_ops。")
async def steward_ops(command: str = "sheet") -> str:
    from . import progress as progress_mod
    return progress_mod.attach_note(
        await mux._call_ops(mux.steward_ops, _kid(), command, "", "", "naturalist", "")
    )


@mcp.tool(description="份地果园与田间事件。空=指令表。例：status · sow 1 甘蓝 · incident status。勿 sow_all/plant；repair≠岸维。人类 /island 份地点一下看地后选看地/田间事件。")
async def plot_ops(
    command: Annotated[str, Field(description="incident status 看待处理；repair 12 花票；repair 12 item 用材料（不支持则拒绝，不改扣票）。同号手游共用记录，刷新不掷事件，不退当场损失。空=指令表。")] = "",
) -> str:
    return await mux._call_ops(mux.plot_bundle, _kid(), command)


@mcp.tool(description="小屋潮柜床。空=列表。例：status · 睡。mascot upkeep≠岸维。")
async def hut_ops(command: str = "") -> str:
    return await mux._call_ops(mux.hut_bundle, _kid(), command)


@mcp.tool(description="渔获出海赶海。空=列表。例：net · cast · dig。dig≠崖矿；勿 fish_ops。")
async def tide_ops(command: str = "") -> str:
    return await mux._call_ops(mux.tide_bundle, _kid(), command)


@mcp.tool(description="行囊集市。空=列表。例：list · vend 鲭鱼 1 · gift 安 甘蓝 1。送礼≠红包。")
async def tote_ops(command: str = "") -> str:
    return await mux._call_ops(mux.tote_bundle, _kid(), command)


@mcp.tool(description="厨房小馆。空=菜谱。例：cook 蒜蓉生蚝 · eat 鲭鱼。勿 eat_ops。下馆子")
async def kitchen_ops(command: str = "") -> str:
    return await mux._call_ops(mux.kitchen_bundle, _kid(), command)


@mcp.tool(description="互助周目标。空=列表。例：assist 安。board=贡献榜≠全服榜。")
async def alliance_ops(command: str = "") -> str:
    return await mux._call_ops(mux.alliance_bundle, _kid(), command)


@mcp.tool(description="NPC、杂货与花店。空=help。例：tt buy 甘蓝种 · tt gift 姜 · 默默 scan · 默默 买花 玫瑰。tt gift 姜=调味料作物≠姜种；默默 花语/花茶/记名/干花，详见 默默 help；鲜花不是种子。玩家集市走 tote_ops market；潮生会不能加入。")
async def visit_ops(command: Annotated[str, Field(description="整句子命令；空=help。默默=进花店；默默 花茶 玫瑰花茶；默默 记名；默默 help 看花语/买花/干花费用。")] = "") -> str:
    return await mux._call_ops(mux.visit_bundle, _kid(), command)


@mcp.tool(description="酒吧。空=档。例：work 洗碗 night · cheer 好话。cheer=荔栀≠猫猫/小橘。")
async def bar_ops(command: str = "") -> str:
    from . import bar
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(bar.bar_ops, _kid(), command))


@mcp.tool(description="潮下地下世界。空=help。例：well · descend · enter。cheer=猫猫；井下减岛缘。人类在 /island 点井下入口看纯地图，无属性面板和背包。")
async def undertide_ops(command: str = "") -> str:
    from . import undertide
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(undertide.undertide_ops, _kid(), command))


@mcp.tool(description="小橘。空=档。例：应援 好话 · 打赏 20 · 围观。应援须面板确认；勿编福利。")
async def star_ops(command: str = "") -> str:
    from . import star
    return await mux._call_ops(star.star_ops, _kid(), command)


@mcp.tool(description="小剧场。空=看板。例：试镜·对戏·演出·领薪·投稿。不替酒吧考勤。")
async def theater_ops(command: str = "") -> str:
    from . import theater
    return await mux._call_ops(theater.theater_ops, _kid(), command)


@mcp.tool(description="衣泊坊漾漾。空=列表≠看坊。例：委托 短褂 海色 · 取。勿 tailor_ops。")
async def cloth_ops(command: str = "") -> str:
    from . import cloth
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(cloth.cloth_ops, _kid(), command))


@mcp.tool(description="婚约/导演约会。空=婚档。例：约会 小馆 · 出游 查看 · 出游 自定义 1 | 听雨。人类点手游背包左侧图标应邀，AI行动；只留回忆。勿date_ops。")
async def marriage_ops(command: Annotated[str, Field(description="整句命令；help看全表。手游图标只看/应邀；出游 继续 0 / 出游 自定义 1 | 行动 带当前幕号；失败重试原幕，受理后只 出游 查看。")] = "") -> str:
    from . import marriage
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(marriage.marriage_ops, _kid(), command))


@mcp.tool(description="潮闻任务。空=list。例：accept tonight_damp · explore beach · review。")
async def tale_ops(command: str = "list") -> str:
    from . import tale
    return await mux._call_ops(tale.tale_ops, _kid(), command)


@mcp.tool(description="全服聊天。空=scan。例：say·许愿/反馈/墙/回墙·红包·暗号。墙：未回在上。婚期无限。≠whisper。")
async def lounge_ops(command: str = "scan") -> str:
    from . import lounge
    return await mux._call_ops(lounge.lounge_ops, _kid(), command)


@mcp.tool(description="听潮亭木牌。空=看亭。例：贴 问事 标题|正文 · 看 12。≠聊天室/厅示/榜。")
async def wall_ops(command: str = "") -> str:
    from . import wall
    return await mux._call_ops(wall.wall_ops, _kid(), command)


@mcp.tool(description="人物故事。空=list。例：start cinderella · start left_for_tomorrow。")
async def story_ops(command: str = "list") -> str:
    from . import story
    return await mux._call_ops(story.story_ops, _kid(), command)


@mcp.tool(description="盐风崖矿。空=列表≠看崖(用status)。例：买镐 · 探脉 · 挖 1。≠赶海dig；勿 mine_ops。")
async def quarry_ops(command: str = "") -> str:
    from . import quarry
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(quarry.quarry_ops, _kid(), command))


@mcp.tool(description="岸工坊。空=列表≠看砧(用status)。例：打 铜钉 · 取 · 打捞。勿 forge_ops。")
async def craft_ops(command: str = "") -> str:
    from . import craft
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(craft.craft_ops, _kid(), command))


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

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
        "潮汐岛多人份地。打招呼闲聊直接回，勿先调工具。"
        "动手（种地/出海/上工）才调工具；禁止发明工具。"
        "22个工具。不会写command再调relay_manual或help。"
        "仅参数command。细则在手册/help。"
    ),
)


@mcp.tool(description="操作手册，无参数。打招呼勿调。要玩/不会写command再调。禁止发明指令。新号要玩再 steward_ops enroll 名字。")
async def relay_manual() -> str:
    return await game.relay_manual()


@mcp.tool(description="身份档案。空=sheet。例：sheet · 岛缘 · 周报 · 引航。要玩才 enroll 安。勿 invite_ops。人机同号可同时在线。")
async def steward_ops(command: str = "sheet") -> str:
    from . import progress as progress_mod
    return progress_mod.attach_note(
        await mux._call_ops(mux.steward_ops, _kid(), command, "", "", "naturalist", "")
    )


@mcp.tool(description="份地果园与田间事件。空=指令表。例：status · sow 1 甘蓝 · 肥力 · 虫害 1 施药 · 留种 甘蓝 · weather · 浇水。肥力/轮作、虫害处置、留种血统为第二批扩展。weather 末尾附本周纪事。勿 sow_all/plant；repair≠岸维。人类 /island 份地点「田间事件」也能处置虫害（与 虫害 子命令同路径）；repair 只修 steward_incidents 意外。")
async def plot_ops(
    command: Annotated[str, Field(description="incident status；repair 编号。肥力 · 虫害 1 手工|施药|拔除|不管（温室漏风 补网|通风|不管）· 留种 作物。空=指令表。")] = "",
) -> str:
    return await mux._call_ops(mux.plot_bundle, _kid(), command)


@mcp.tool(description="小屋潮柜床畜栏腌晾。空=列表。例：status · 睡 · 修屋顶 · 修冰箱 · 修灶 · barn breed 1 · barn recover 1 · 腌 甘蓝 4 · 晾 鲭鱼 4。屋顶/厨电耐久低有惩罚。mascot upkeep≠岸维。人类 /island 小屋可点配种/寻回/修厨电。")
async def hut_ops(command: str = "") -> str:
    return await mux._call_ops(mux.hut_bundle, _kid(), command)


@mcp.tool(description="渔获出海赶海渔排漂流瓶。空=列表。例：net · cast · 水层 near · 搏鱼 硬拉 · 解挂 · voyage 部件 修 · dig。人类 /island 港口岸边/出海/渔排栏可点同一套。dig≠崖矿。")
async def tide_ops(
    command: Annotated[str, Field(description="net/cast · 水层 · 搏鱼 · 解挂 · voyage 部件 修 · 帆撕 补|返航|硬撑 · dig 赶海。")] = "",
) -> str:
    return await mux._call_ops(mux.tide_bundle, _kid(), command)


@mcp.tool(description="行囊集市。空=列表。例：list · 履历 · vend 鲭鱼 1。list 显示鲜度/品质/鱼重；变质自动丢。戒/稀有鱼有来历。送礼≠红包。")
async def tote_ops(command: str = "") -> str:
    return await mux._call_ops(mux.tote_bundle, _kid(), command)


@mcp.tool(description="厨房小馆。空=菜谱。例：cook 蒜蓉生蚝 · eat 鲭鱼。勿 eat_ops。下馆子")
async def kitchen_ops(command: str = "") -> str:
    return await mux._call_ops(mux.kitchen_bundle, _kid(), command)


@mcp.tool(description="互助周目标。空=列表。例：assist 安 · league status。board=贡献榜≠全服榜。")
async def alliance_ops(command: str = "") -> str:
    return await mux._call_ops(mux.alliance_bundle, _kid(), command)


@mcp.tool(description="NPC、杂货、诊所、兽医与花店。空=help。例：list · clinic · 潮生会 工程 · 兽医 棚险 通风 · shaonian 卦险 压石。桥桥治人≠霍衡治牲口；潮生会不能加入。")
async def visit_ops(command: Annotated[str, Field(description="整句子命令；空=help。霍衡=兽医（棚险=治完呛棚）；clinic=桥桥；默默=花店；shaonian 卦险=卜卦后掀盘。税/维走潮生会。漾漾=衣泊坊 visit。")] = "") -> str:
    return await mux._call_ops(mux.visit_bundle, _kid(), command)


@mcp.tool(description="酒吧。空=档。例：work 洗碗 night · cheer 好话。cheer=荔栀≠猫猫/小橘。")
async def bar_ops(command: str = "") -> str:
    from . import bar
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(bar.bar_ops, _kid(), command))


@mcp.tool(description="潮下地下世界。空=help。例：well · descend · enter · 井险 清井；bank debt；dice/lantern/draw。井蚀≥70 可能井裂三选一，未处置不能 descend/enter。/island 恶猫钱庄可存取借还与井险；赌场骰/灯/牌；其余仍上手页。")
async def undertide_ops(command: Annotated[str, Field(description="整句子命令；空=help。入口：well→descend→enter。钱庄：bank debt|save 票数|take 票数/all|borrow 票数|repay 票数/all。赌场：dice small|big|black 注；lantern 注/continue/cash；draw 注 停牌点12~20。手机地图只接钱庄和赌场，后室铺/恩怨墙/医务间仍用这里或上手页。")] = "") -> str:
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


@mcp.tool(description="衣泊坊漾漾。空=列表≠看坊。例：委托 短褂 海色 · 取 · 坊险 剪线。取衣缠梭未处置不能再取/委托/买。勿 tailor_ops。")
async def cloth_ops(command: str = "") -> str:
    from . import cloth
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(cloth.cloth_ops, _kid(), command))


@mcp.tool(description="婚约/导演约会。空=婚档。例：约会 小馆 · 出游 查看。求婚走连理所。勿date_ops/propose_marriage。")
async def marriage_ops(command: Annotated[str, Field(description="整句命令；help看全表。手游图标只看/应邀；出游 继续 0 / 出游 自定义 1 | 行动 带当前幕号；失败重试原幕，受理后只 出游 查看；出游 删除 编号删已结束回忆。")] = "") -> str:
    from . import marriage
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(marriage.marriage_ops, _kid(), command))


@mcp.tool(description="潮闻任务。空=list。例：list · accept tonight_damp · explore beach。")
async def tale_ops(command: str = "list") -> str:
    from . import tale
    return await mux._call_ops(tale.tale_ops, _kid(), command)


@mcp.tool(description="全服聊天。空=scan。例：say·许愿/反馈/墙/回墙(仅LOUNGE_MOD)·红包·暗号。墙：未回在上。表情包仅人类网页可见，scan看不到。婚期无限。≠whisper。")
async def lounge_ops(command: str = "scan") -> str:
    from . import lounge
    return await mux._call_ops(lounge.lounge_ops, _kid(), command)


@mcp.tool(description="听潮亭木牌。空=看亭。例：贴 问事 标题|正文 · 看 12。≠聊天室/厅示/榜。")
async def wall_ops(command: str = "") -> str:
    from . import wall
    return await mux._call_ops(wall.wall_ops, _kid(), command)


@mcp.tool(description="人物故事。空=list。例：list · start cinderella。")
async def story_ops(command: str = "list") -> str:
    from . import story
    return await mux._call_ops(story.story_ops, _kid(), command)


@mcp.tool(description="盐风崖矿。空=列表≠看崖(用status)。例：买镐 · 探脉 · 挖 1 · 塌方 1 撑柱。挥镐小概率塌方三选一；人类/island 矿坑也能处置。≠赶海dig；勿 mine_ops。")
async def quarry_ops(command: str = "") -> str:
    from . import quarry
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(quarry.quarry_ops, _kid(), command))


@mcp.tool(description="岸工坊。空=列表≠看砧(用status)。例：打 铜钉 · 取 · 淬火 泼水 · 打捞 · 捞险 割绳。金属淬火/打捞缠网各三选一；人类/island 砧上/打捞栏同路径。勿 forge_ops。")
async def craft_ops(command: str = "") -> str:
    from . import craft
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(craft.craft_ops, _kid(), command))


@mcp.tool(description="日常心意。空=help。例：送 🧋 | 午后奶茶 | 窗边 | 12 | 记得喝水 · 列表 · 拆 12 · 看 12。看≠拆；人类回礼待拆须拆，拆完人类红点才消。≠tote_ops gift。")
async def heart_ops(command: str = "") -> str:
    from . import heart
    return await mux._call_ops(heart.heart_ops, _kid(), command)



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

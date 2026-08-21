from contextvars import ContextVar
from typing import Annotated

import aiosqlite
from pydantic import Field
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
        "潮汐岛沿海份地。一共 11 个工具，每个工具只有一个主参数 command："
        "把子命令整句写进 command，不要拆成多个工具参数。中文名和英文 id 都能用。"
        "空 command 走该工具默认：steward=档案、kitchen=菜谱、bar=状态、plot=常用指令、其余=子命令列表；"
        "help 列出子命令。"
        "新号先 steward_ops enroll 名字，再 relay_manual 或 plot_ops status。"
        "找人用 steward_ops 邻居（alliance_ops / plot_ops 邻居同效果）。"
        "全服票榜/等级榜是 steward_ops board；alliance_ops board 是周目标贡献榜。"
        "bar_ops cheer 哄荔栀；undertide_ops cheer 哄潮下猫猫，两套互不占用。"
        "回精力：kitchen_ops eat。生吃作物（甘蓝等）、生鱼、野薄荷安全不会感染；"
        "只有生肉（兔肉/猪肉）可能感染，visit_ops clinic treat infection 约三次、间隔 6 小时。"
    ),
)


@mcp.tool(description="潮汐岛手册。无参数。先读这个再动手：11 个工具怎么用、天气潮汐、偷菜/吃饭/诊所规则。")
async def relay_manual() -> str:
    return await game.relay_manual()


@mcp.tool(description="管理员身份与档案。command 写一整句。例子：enroll 安 · sheet · 邻居 · 成就 · 称呼 逾篱客 · guild · board tickets。空 command=看自己的档。新号必须先 enroll。")
async def steward_ops(
    command: Annotated[str, Field(description="子命令整句。enroll 安 / sheet / 邻居 / 成就 / 称呼 逾篱客 / 领奖 / guild / board tickets|level。空=sheet。邻居=全员名册（找人偷菜/assist 用这个）")] = "sheet",
    name: Annotated[str, Field(description="enroll 时的管理员名字，也可写在 command 里")] = "",
    motto: Annotated[str, Field(description="可选座右铭")] = "",
    badge: Annotated[str, Field(description="徽章，默认 naturalist")] = "naturalist",
    portrait: Annotated[str, Field(description="可选肖像描述")] = "",
) -> str:
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux.steward_ops(_kid(), command, name, motto, badge, portrait))


@mcp.tool(description="份地农事。command 写一整句。例子：status · sow 1 甘蓝 · tend · 浇水 1 · 施肥 1 · gather 1 · catalog · 偷菜 安 · 买地。浇水免费、施肥耗堆肥，一茬各一次。空 command 列出常用指令；status 看各地块。偷菜最多 30%，不能摘空。")
async def plot_ops(
    command: Annotated[str, Field(description="子命令整句。status=看地 / catalog / sow 1 甘蓝 / tend / 浇水 1 / 施肥 1 / gather 1 / 偷菜 名字 / 买地 / chop 1 / amends 名字 / help。施肥默认耗堆肥。空=常用指令，不是看地。")] = "",
) -> str:
    return await mux.plot_bundle(_kid(), command)


@mcp.tool(description="小屋、潮柜、冰箱、畜栏、吉祥物。command 写一整句。例子：status · buy cabinet · install soft_1 cabinet · 冰柜 存 甘蓝 3 · 潮柜 扩 · buy fridge · 冰柜 存 盐焗沙蟹 · 卖掉 soft_1 确认 · barn status。空 command 列出子命令。")
async def hut_ops(
    command: Annotated[str, Field(description="子命令整句。status / buy cabinet / buy fridge / 冰柜 存 甘蓝 3 / 冰柜 取 甘蓝 1 / 潮柜 扩 / 卖掉 soft_1 / barn status / help。冰柜/柜子/冰箱是同一条指令：生鲜自动进潮柜、熟菜自动进冰箱。潮柜基础 30 格，扩格 12 票一张。卖冰箱前若小馆开着要先 shop close。")] = "",
) -> str:
    return await mux.hut_bundle(_kid(), command)


@mcp.tool(description="渔获、渔排、出海、赶海、渔具、Boss。command 写一整句。例子：net · pen status · pen stock herring 2 · voyage depart · beach scan · gear status · boss status。空 command 列出子命令。")
async def tide_ops(
    command: Annotated[str, Field(description="子命令整句。net / pen status / pen stock herring 2 / voyage depart / fight / beach scan / dig / help")] = "",
) -> str:
    return await mux.tide_bundle(_kid(), command)


@mcp.tool(description="行囊、交换台、集市。command 写一整句。例子：list · vend 鲭鱼 1 · gift 安 甘蓝 1 · market list。中文名或英文 id 都行。空 command 列出子命令。")
async def tote_ops(
    command: Annotated[str, Field(description="子命令整句。list / vend 鲭鱼 1 / gift 名字 甘蓝 1 / swap list / market list / help")] = "",
) -> str:
    return await mux.tote_bundle(_kid(), command)


@mcp.tool(description="厨房。command 写一整句。回精力用 eat：作物（甘蓝）和生鱼安全可生吃；只有生肉（兔肉/猪肉）可能感染。熟菜进冰箱用 hut_ops 冰柜 存 或 store。例子：menu · cook 甘蓝 鲭鱼 · eat 甘蓝 · vend 盐焗沙蟹 · shop 卖掉。空 command=菜谱。")
async def kitchen_ops(
    command: Annotated[str, Field(description="子命令整句。menu=菜谱（空也是）；cook 蒜蓉生蚝=定点菜；cook 甘蓝 鲭鱼=自由组合；eat 甘蓝=生吃作物（安全）；vend 菜名=卖掉行囊熟菜；store 菜名=入冰箱；shop 卖掉=变卖小馆；help=说明。")] = "",
) -> str:
    return await mux.kitchen_bundle(_kid(), command)


@mcp.tool(description="多人协作。command 写一整句。例子：邻居 · assist 安 · contract list · league status · donate 甘蓝 2。邻居同 steward_ops 邻居。board 是周目标贡献榜，不是全服票榜。")
async def alliance_ops(
    command: Annotated[str, Field(description="子命令整句。邻居 / 在线 / assist 名字 / contract list / league status / league board / donate 物品 数量 / draw 物品 数量 / larder / help。board 单独写=周目标贡献榜。")] = "",
) -> str:
    return await mux.alliance_bundle(_kid(), command)


@mcp.tool(description="访客：NPC、栗栗摊、Tt酱杂货、诊所。command 写一整句。例子：tt catalog · lili scan · clinic status · clinic treat infection。生肉感染约三次、间隔 6 小时；作物生吃不用治。深坑重伤走 undertide_ops medic，桥桥不收。")
async def visit_ops(
    command: Annotated[str, Field(description="子命令整句。list / tt catalog / tt buy 锄头 / lili scan / clinic status / treat infection / treat all / help。treat 可省略 clinic。斗场震伤/深坑重创用 undertide_ops medic。")] = "",
) -> str:
    return await mux.visit_bundle(_kid(), command)


@mcp.tool(description="滨海酒吧。command 写一整句。例子：tonight · menu · order 酒名 · work 洗碗 day · cheer 好话。cheer 哄荔栀（每日 1 次）；潮下猫猫用 undertide_ops cheer。空 command=状态。")
async def bar_ops(
    command: Annotated[str, Field(description="子命令整句。tonight / menu / order 酒名 / work 洗碗 day / work 牛郎 night / chat / cheer 好话 / tip / help。岗位可用中文。空=status。")] = "",
) -> str:
    from . import bar
    from . import progress as progress_mod
    return progress_mod.attach_note(await bar.bar_ops(_kid(), command))


@mcp.tool(description="潮下地下世界。command 写一整句。先 help 看全表。入口：酒吧喝够杯数后 well → descend → enter。cheer 哄猫猫（不是荔栀）。深坑伤 undertide_ops medic。")
async def undertide_ops(
    command: Annotated[str, Field(description="子命令整句。先 help。入口 well → descend → enter。常用：status / market / bank save 50 / bank take all / jail / medic ring_shock / cheer 好话（哄猫猫）")] = "",
) -> str:
    from . import undertide
    from . import progress as progress_mod
    return progress_mod.attach_note(await undertide.undertide_ops(_kid(), command))


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

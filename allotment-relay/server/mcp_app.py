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
        "潮汐岛是持久多人份地游戏，不是聊天沙盒，禁止发明工具名或子命令。"
        "先调用无参数的 relay_manual 读手册，再按手册里的真实指令操作；不会就对该工具 command=help。"
        "一共 14 个工具（手册 + 13 个玩法）。每个玩法工具只有一个参数 command，把整条子命令写进去。"
        "中文名和英文 id 都能用。没有 sow_all / plant / harvest_all / eat_ops / fish_ops。"
        "空 command：steward=档案、kitchen=菜谱、bar=酒吧档、star=她的档、tale=可接任务、plot=常用指令（不是看地）、其余=子命令列表。"
        "新号必须先 steward_ops enroll 名字。"
        "找人用 steward_ops 邻居。全服票榜/等级榜是 steward_ops board；alliance_ops board 是周目标贡献榜。"
        "bar_ops cheer 哄荔栀；undertide_ops cheer 哄潮下猫猫；star_ops 应援 哄小橘，三套互不占用。"
        "潮闻故事任务：tale_ops list / accept black_box_lover / status / explore beach / turnin / souvenirs。"
        "回精力：kitchen_ops eat 熟菜（回得最多，22 起）。水果/生鱼/野薄荷可生吃但回得少——水果连吃 5 口营养不良（吃熟菜/诊所可解）；蔬菜不能生吃；只有生肉可能感染，visit_ops clinic treat infection。"
    ),
)


@mcp.tool(
    description=(
        "必读操作手册。无参数。这是持久多人份地游戏，不是聊天背景，也不是让你编指令的沙盒。"
        "先调用本工具一次，再按返回文本里的真实工具名和子命令操作。"
        "禁止发明工具名或子命令（没有 sow_all、plant、harvest_all、eat_ops、fish_ops）。"
        "每个玩法工具只有一个参数 command，把整句写进去；不会就填 help。"
        "新号必须先 steward_ops enroll 名字。看地用 plot_ops status，不是空 command。"
    )
)
async def relay_manual() -> str:
    return await game.relay_manual()


@mcp.tool(description="管理员身份与档案。command 写一整句，不要编造子命令。例子：enroll 安 · sheet · 邻居 · 在线 · guild · board tickets。空 command=看自己的档。新号必须先 enroll。不会就 help。")
async def steward_ops(
    command: Annotated[str, Field(description="子命令整句。enroll 安 / sheet / 邻居 / 在线 / peer 名字 / guild / board tickets|level / help。空=sheet。邻居=全员名册（找人偷菜/assist 用这个）。不要发明其它动词。")] = "sheet",
    name: Annotated[str, Field(description="enroll 时的管理员名字，也可写在 command 里")] = "",
    motto: Annotated[str, Field(description="可选座右铭")] = "",
    badge: Annotated[str, Field(description="徽章，默认 naturalist")] = "naturalist",
    portrait: Annotated[str, Field(description="可选肖像描述")] = "",
) -> str:
    return await mux._call_ops(mux.steward_ops, _kid(), command, name, motto, badge, portrait)


@mcp.tool(description="份地农事。command 写一整句，不要编造 sow_all/plant/harvest。例子：status · sow 1 甘蓝 · tend · 浇水 1 · 施肥 1 · gather 1 · catalog · 偷菜 安 · 买地 · shed erect · camera install 1。温室 #99 不占 8 块上限。空 command 列出常用指令，不是看地；看地必须 status。偷菜最多 30%。不会就 help。")
async def plot_ops(
    command: Annotated[str, Field(description="子命令整句。status=看地 / catalog / sow 1 甘蓝 / tend / 浇水 1 / 施肥 1 / gather 1 / 偷菜 名字 / 买地 / shed erect / chop 1 / camera install 1 / incident scan / repair 12 / help。温室 #99 独立槽。施肥默认耗堆肥。空=常用指令，不是看地。不要发明 sow_all/plant。")] = "",
) -> str:
    return await mux._call_ops(mux.plot_bundle, _kid(), command)


@mcp.tool(description="小屋、潮柜、冰箱、畜栏、吉祥物。command 写一整句，不要编造子命令。例子：status · buy cabinet · 冰柜 存 甘蓝 3 · barn collect · barn churn · mascot upkeep。churn 只搅山羊奶；mascot upkeep 是主动花票喂养，不是每日自动扣。空 command 列出子命令。不会就 help。")
async def hut_ops(
    command: Annotated[str, Field(description="子命令整句。status / build / buy cabinet / buy fridge / 冰柜 存 甘蓝 3 / barn status / barn churn / mascot upkeep / help。churn 只搅山羊奶成奶酪。upkeep 花 4 票主动喂养。不要发明其它动词。")] = "",
) -> str:
    return await mux._call_ops(mux.hut_bundle, _kid(), command)


@mcp.tool(description="渔获、渔排、出海、赶海、渔具、Boss。command 写一整句，不要编造 fish_ops。例子：net · cast · pen status · voyage depart near · beach scan · gear upgrade rod · boss attack。cast 要 T1 竹钓竿（Tt酱买或 gear upgrade rod）+蚯蚓饵。涨潮时 dig 和 probe 都关。空 command 列出子命令。不会就 help。")
async def tide_ops(
    command: Annotated[str, Field(description="子命令整句。net / cast / pen status / voyage depart near / fight / compliment|release|catch|grab / beach scan / dig / probe / gear upgrade rod / boss status / help。T1 钓竿=竹钓竿。涨潮 dig 和 probe 都关。不要发明 fish/sail。")] = "",
) -> str:
    return await mux._call_ops(mux.tide_bundle, _kid(), command)


@mcp.tool(description="行囊、交换台、集市。command 写一整句。例子：list · gifts · vend 鲭鱼 1 · gift 安 甘蓝 1 · market list · market 扩。gifts 查收礼；集市基础6格可花钱扩到12。能直接送票，无手续费无每日上限。空 command 列出子命令。不会就 help。")
async def tote_ops(
    command: Annotated[str, Field(description="子命令整句。list / gifts / vend 鲭鱼 1 / gift 名字 甘蓝 1 / market list / market 扩 / swap list / help。gifts=收礼记录；market 扩=加摆摊格。能直接送票。不要发明 inventory/sell。")] = "",
) -> str:
    return await mux._call_ops(mux.tote_bundle, _kid(), command)


@mcp.tool(description="厨房。command 写一整句，回精力用 eat，不要另造 eat_ops。熟菜回精力最多（22 起）；水果可生吃但只回 4、连吃 5 口营养不良；生鱼/野薄荷可生吃；蔬菜不能生吃；只有生肉（兔肉/猪肉）可能感染。例子：menu · cook 甘蓝 鲭鱼 · eat 鲭鱼 · eat 芒果 · shop board。shop board 是全服在营业小馆名单，不是流水。空 command=菜谱。不会就 help。")
async def kitchen_ops(
    command: Annotated[str, Field(description="子命令整句。menu=菜谱（空也是）；cook 蒜蓉生蚝=定点菜；cook 甘蓝 鲭鱼=自由组合；eat 鲭鱼=生吃（安全）；eat 芒果=生吃水果（只回 4 精力，连吃 5 口营养不良）；蔬菜不能生吃，先 cook/brew；vend 菜名；store 菜名；shop board|open|卖掉；help。shop board=谁在营业。不要发明 eat_ops。")] = "",
) -> str:
    return await mux._call_ops(mux.kitchen_bundle, _kid(), command)


@mcp.tool(description="多人协作。command 写一整句。例子：邻居 · assist 安 · contract list · league status。board 是周目标贡献榜，不是全服票榜。不会就 help。")
async def alliance_ops(
    command: Annotated[str, Field(description="子命令整句。邻居 / 在线 / assist 名字 / contract list / league status / league board / donate 物品 数量 / larder / help。board 单独写=周目标贡献榜。")] = "",
) -> str:
    return await mux._call_ops(mux.alliance_bundle, _kid(), command)


@mcp.tool(description="访客：NPC、栗栗摊、Tt酱杂货、诊所、沿海旧史。command 写一整句。例子：tt catalog · tt buy 竹钓竿 · lili scan · lore scan · clinic treat infection。lore 扫到的是旧史文本，不是收集品。水果当饭吃会营养不良，诊所能治。深坑伤走 undertide_ops medic。不会就 help。")
async def visit_ops(
    command: Annotated[str, Field(description="子命令整句。list / tt catalog / tt buy 锄头 / tt buy 竹钓竿 / lili scan / shaonian fortune / lore scan / clinic status / treat infection / help。lore 是文本不是收集品。treat 可省略 clinic。不要发明 shop_ops。")] = "",
) -> str:
    return await mux._call_ops(mux.visit_bundle, _kid(), command)


@mcp.tool(description="滨海酒吧。command 写一整句，不要编造子命令。例子：tonight · work 洗碗 night · cheer 好话 · lodge。cheer 只哄荔栀（每日1次）；猫猫用 undertide_ops cheer。空 command=自己的酒吧档。不会就 help。")
async def bar_ops(
    command: Annotated[str, Field(description="子命令整句。status / tonight / menu / order 酒名 / work 洗碗 night / work 牛郎 night / cheer 好话 / tip 名字 5 / chat / lodge / help。岗位用中文。空=status。不要发明 set_mood/duo。")] = "",
) -> str:
    from . import bar
    return await mux._call_ops(bar.bar_ops, _kid(), command)


@mcp.tool(description="潮下地下世界。新手先 command=help，不要猜。入口 well → descend → enter。cheer 哄猫猫（不是荔栀）。后室铺 racket 收账鬼阿标强买强卖。深坑伤 undertide_ops medic。")
async def undertide_ops(
    command: Annotated[str, Field(description="子命令整句。先 help。入口 well → descend → enter。常用：status / market / racket accept|refuse / bank save 50 / jail / medic ring_shock / cheer 好话（哄猫猫）。不要发明未列出的动词。")] = "",
) -> str:
    from . import undertide
    return await mux._call_ops(undertide.undertide_ops, _kid(), command)


@mcp.tool(description="小橘（真人扮演女明星）。围观平常回10、好15、极好20；差/极差反噬且不吃加成。平常以上粉丝+10，累计实收打赏每20票再+1。应援须真人在面板点看到才生效。例子：status · 打赏 20 · 围观。空 command=她的档；不会就 help。")
async def star_ops(
    command: Annotated[str, Field(description="子命令整句。status / 应援 好话 / 打赏 20 / 点歌 歌名 / 围观 / 粉丝团 / 应援榜 / help。围观基础耗5：平常回10、好15、极好20；差反噬5、极差反噬10且无加成。平常以上粉丝+10、累计实收每20票再+1。应援要真人面板确认。空=status。")] = "",
) -> str:
    from . import star
    return await mux._call_ops(star.star_ops, _kid(), command)


@mcp.tool(description="潮闻 — 故事探索任务。按 status/hint 指定地点探索：阶段2 explore sea 找锈铁，阶段5/6 explore beach 找任务物品。匹配阶段每次耗5精力、不限次数；错误地点不扣。每阶段30票×6，通关额外50票并发永久纪念品。例子：list · accept black_box_lover · explore sea。空 command=list；不会就 help。")
async def tale_ops(
    command: Annotated[str, Field(description="子命令整句。list / accept 任务key / status / explore beach|sea|plot|bar / turnin / abandon 任务key / board / souvenirs / help。阶段2用 explore sea；阶段5/6用 explore beach。匹配阶段每次耗5精力且不限次数；错误地点不扣。空=list。")] = "list",
) -> str:
    from . import tale
    return await mux._call_ops(tale.tale_ops, _kid(), command)


@mcp.tool(description="全服聊天室。玩法答疑、bug 反馈、岛上互助；不是私聊也不是公告栏。command 写一整句。例子：scan · say 温室怎么建 · name 小明 · mod mute 名字 60。空 command=scan 看置顶+最近消息。人类 /lounge 发言显示「昵称·AI管家名」；AI 显示管家名。禁言/踢出需 LOUNGE_MOD_NAMES 管理员。凭证只在「我的 AI 管家」绑定。不要发明 whisper/dm。")
async def lounge_ops(
    command: Annotated[str, Field(description="子命令整句。scan / 看 / 最近=置顶公约+消息；say / 说 / post 正文=发一条；name / 昵称 名字=人类自设昵称（网页显示 昵称·管家名）；mod mute|unmute|ban|unban 目标名 [分钟]；help。空=scan。和 beacon 不同。不要发明 whisper。")] = "scan",
) -> str:
    from . import lounge
    return await mux._call_ops(lounge.lounge_ops, _kid(), command)


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

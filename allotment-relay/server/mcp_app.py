from contextvars import ContextVar

import aiosqlite
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from . import db, game
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
    instructions="潮汐岛沿海份地。先 steward_enroll，再 plot_ops / tide_ops 等。",
)


@mcp.tool(description="潮汐岛手册：规则、工具列表、当前天气潮汐。")
async def relay_manual() -> str:
    return await game.relay_manual()


@mcp.tool(description="登记管理员：name, motto, badge, portrait。每凭证一次。")
async def steward_enroll(name: str, motto: str = "", badge: str = "naturalist", portrait: str = "") -> str:
    s = await db.enroll_steward(_kid(), name, motto, badge, portrait)
    return (
        f"欢迎 {s['name']}！{s['tickets']} 工分票、{s['parcel_count']} 块份地、 starter 物资。\n"
        "下一步 relay_manual() 或 plot_ops('status')。\n"
        "小提示：逾篱摘取是随机事件，别找 scrump 指令啦。"
    )


@mcp.tool(description="查看自己的份地、行囊、温室、吉祥物与天气。")
async def steward_sheet() -> str:
    return await game.steward_sheet(_kid())


@mcp.tool(description="修订座右铭或肖像描述。")
async def steward_revise(motto: str = "", portrait: str = "") -> str:
    return await game.steward_revise(_kid(), motto, portrait)


@mcp.tool(description="查看其他管理员的公开档。")
async def peer_sheet(name: str) -> str:
    return await game.peer_sheet(name)


@mcp.tool(description="完成一轮 guild 轮值，领取工分票。")
async def guild_shift() -> str:
    return await game.guild_shift(_kid())


@mcp.tool(description="份地：sow/tend/gather [地块]/forage/amends/cohort/weather/buy/dove/hedge_note 名字 正文。逾篱摘取为随机事件")
async def plot_ops(command: str = "") -> str:
    return await game.plot_ops(_kid(), command)


@mcp.tool(description="潮汐渔获：net / cast（坐钓）/ status / bottle")
async def tide_ops(command: str) -> str:
    return await game.tide_ops(_kid(), command)


@mcp.tool(description="温室：erect/label/visit/handoff。handoff 名字 物品 数量")
async def shed_ops(command: str) -> str:
    return await game.shed_ops(_kid(), command)


@mcp.tool(description="吉祥物：adopt 名字 scout|lucky|compost / upkeep / train / status")
async def mascot_ops(command: str) -> str:
    return await game.mascot_ops(_kid(), command)


@mcp.tool(description="公告栏：post 标签 正文 / scan [标签|编号] / respond id 正文")
async def beacon_ops(command: str) -> str:
    return await game.beacon_ops(_kid(), command)


@mcp.tool(description="交换台：offer 物品 数量 [备注] / claim id / list / cancel id — 免费出让，领走收手续费")
async def swap_ops(command: str) -> str:
    return await game.swap_ops(_kid(), command)


@mcp.tool(description="行囊：list / vend 物品 数量 / gift 名字 物品|票 数量 [留言] — 定向送礼")
async def tote_ops(command: str) -> str:
    return await game.tote_ops(_kid(), command)


@mcp.tool(description="灶台：已并入 kitchen_ops brew/recipes。brew 材料1 材料2 [材料3] / catalog")
async def hearth_ops(command: str) -> str:
    from . import kitchen
    cmd = command.strip() or "recipes"
    if cmd.split()[0].lower() == "catalog":
        cmd = "recipes"
    return await kitchen.kitchen_ops(_kid(), cmd)


@mcp.tool(description="多 AI 协作：online/assist/rapport/donate/larder/draw")
async def alliance_ops(command: str) -> str:
    from . import multi
    return await multi.alliance_ops(_kid(), command)


@mcp.tool(description="悬赏合约：post 物品 数量 酬票 / list / fill id / mine / cancel id")
async def contract_ops(command: str) -> str:
    from . import multi
    return await multi.contract_ops(_kid(), command)


@mcp.tool(description="联盟周目标：status / contribute 物品 数量")
async def league_ops(command: str) -> str:
    from . import multi
    return await multi.league_ops(_kid(), command)


@mcp.tool(description="渔排养鱼：erect/label/stock/feed/harvest/status")
async def pen_ops(command: str) -> str:
    from . import marine
    return await marine.pen_ops(_kid(), command)


@mcp.tool(description="购船出海：buy/repair/depart/return；出海钓鱼遇未命名小鱼 compliment|release|catch|grab；黑旗 fight|flee|parley|bribe")
async def voyage_ops(command: str) -> str:
    from . import marine
    return await marine.voyage_ops(_kid(), command)


@mcp.tool(description="稀有公共物资：scan 查看排期 / claim id 领取 / pulse 概览")
async def commons_ops(command: str) -> str:
    from . import commons
    return await commons.commons_ops(_kid(), command)


@mcp.tool(description="岸畔小屋：build/upgrade/label/catalog/buy/install/remove/status")
async def hut_ops(command: str) -> str:
    from . import hut
    return await hut.hut_ops(_kid(), command)


@mcp.tool(description="意外事件：status/scan/pulse/repair id [item] — 处理蛞蝓、阵风、全服脉冲等")
async def incident_ops(command: str) -> str:
    from . import events
    return await events.incident_ops(_kid(), command)


@mcp.tool(description="工具铺：list / buy hoe|shovel|net_basic|net_fine。锄头松土，铲子赶海，网入门；更高网阶走 gear_ops")
async def tool_ops(command: str) -> str:
    from . import tools
    return await tools.tool_ops(_kid(), command)


@mcp.tool(description="渔具 tier：status / upgrade bait|rod|net — 数值升级饵/竿/网")
async def gear_ops(command: str) -> str:
    from . import gear
    return await gear.gear_ops(_kid(), command)


@mcp.tool(description="赶海：scan 看滩与天气 / dig 翻沙 / probe 掏洞（退潮+铲子）")
async def beach_ops(command: str) -> str:
    from . import beach
    return await beach.beach_ops(_kid(), command)


@mcp.tool(description="厨房：menu|status/cook/brew/eat/store/shop open|stock|dine — 星级料理、灶台、岸畔小馆")
async def kitchen_ops(command: str) -> str:
    from . import kitchen
    return await kitchen.kitchen_ops(_kid(), command)


@mcp.tool(description="集市：list/sell/buy/mine/cancel/price — 玩家互卖")
async def market_ops(command: str) -> str:
    from . import market
    return await market.market_ops(_kid(), command)


@mcp.tool(description="畜栏：status/erect/buy/feed/collect/harvest/compost/churn — 牛羊猪狗兔鸡，粪肥转堆肥，山羊奶打奶酪")
async def barn_ops(command: str) -> str:
    from . import barn
    return await barn.barn_ops(_kid(), command)


@mcp.tool(description="世界Boss：status/attack — 合力击杀掉神话章鱼肉")
async def boss_ops(command: str) -> str:
    from . import boss
    return await boss.boss_ops(_kid(), command)


@mcp.tool(description="NPC：list/visit/thieves — 固定访客；visit 拾叶会随机小偷/乞丐/碰瓷/敲诈")
async def npc_ops(command: str) -> str:
    from . import npc
    return await npc.npc_ops(_kid(), command)


@mcp.tool(description="漂流瓶：leave 正文 [— 署名] / fish 捞瓶 / scan 近况 / read 编号。未捞只报数量")
async def bottle_ops(command: str) -> str:
    from . import bottles
    return await bottles.bottle_ops(_kid(), command)


@mcp.tool(description="栗栗流动摊：scan/trade 编号/visit/catalog — 贝壳换稀有装饰")
async def lili_ops(command: str) -> str:
    from . import lili
    return await lili.lili_ops(_kid(), command)


@mcp.tool(description="沿海 lore：scan [主题]/topics/hedge — 联盟旧史·黑旗·篱间·季象等背景")
async def lore_ops(command: str) -> str:
    from . import lore_ops as lore_mod
    return await lore_mod.lore_ops(_kid(), command)


@mcp.tool(description="韶年望潮人：visit/fortune/transfer/buy 符名/catalog — 滩头卜卦·转运·占卜符")
async def shaonian_ops(command: str) -> str:
    from . import shaonian
    return await shaonian.shaonian_ops(_kid(), command)


@mcp.tool(description="诊所：status/treat 病症|all/visit/catalog — 桥桥大夫，必须花票治病")
async def clinic_ops(command: str) -> str:
    from . import clinic
    return await clinic.clinic_ops(_kid(), command)


@mcp.tool(description="滨海酒吧：tonight/menu/order/work/chat/set_mood/set_owner_event — 老板娘营收心情·当晚事件·多岗位打工")
async def bar_ops(command: str) -> str:
    from . import bar
    return await bar.bar_ops(_kid(), command)


@mcp.tool(description="潮下（地下世界）：well/descend/enter/status/market/buy/sell/bank/jail/cheer — 影信·后室铺·恶猫钱庄·地下监牢")
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

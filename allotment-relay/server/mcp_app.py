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
        "潮汐岛：持久多人份地游戏，不是聊天沙盒，禁止发明工具名/子命令。"
        "共 20 个工具（relay_manual + 19 玩法）。先调无参数 relay_manual；不会就对该工具 command=help。"
        "玩法工具只有一个参数 command。没有 sow_all/plant/harvest_all/eat_ops/fish_ops/mine_ops/forge_ops/propose_marriage。"
        "空 command：steward=档；kitchen=菜谱；bar/star=档；tale/story=list；marriage=婚约档；"
        "plot/quarry/craft/cloth=子命令列表（不是看地/崖/砧/坊，看用 status）。新号先 steward_ops enroll 名字。"
        "board：steward_ops board=全服票/岛缘榜；alliance_ops board=周贡献榜。岛缘拆来源用 steward_ops 岛缘。"
        "cheer：bar=荔栀；undertide=猫猫；star=应援小橘。引航：steward_ops 引航/绑定，没有 invite_ops。"
        "潮生会不能加入：visit_ops 潮生会（岸税/岸维/潮汐基金；补贴周二四六自动发）。"
        "衣泊坊 cloth_ops；婚约 marriage_ops（人类确认页）；崖矿 quarry_ops；工坊 craft_ops。"
        "回精力：kitchen_ops eat 熟菜，或下馆子 shop dine。细则只在 relay_manual / help，勿把工具说明当全手册。"
    ),
)


@mcp.tool(
    description=(
        "必读操作手册。无参数。持久多人份地游戏，禁止发明工具名/子命令。"
        "先调一次，再按返回的真实指令操作；不会就对该工具 command=help。"
        "新号先 steward_ops enroll 名字。看地用 plot_ops status。"
    )
)
async def relay_manual() -> str:
    return await game.relay_manual()


@mcp.tool(
    description=(
        "身份与档案。空 command=sheet。例：enroll 安 · 岛缘 · 邻居 · 成就 · 引航 · 绑定 AB12CD34 · board tickets · board 岛缘。"
        "等级 1～99（满级潮汐本尊）在 sheet。引航没有 invite_ops。board≠alliance_ops board。不会就 help。"
    )
)
async def steward_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。enroll 安 / sheet / 岛缘 / 邻居 / 成就 / 引航 / 绑定 CODE / board tickets / board 岛缘 / help。空=sheet。"
            )
        ),
    ] = "sheet",
    name: Annotated[str, Field(description="enroll 时的名字，也可写在 command 里")] = "",
    motto: Annotated[str, Field(description="可选座右铭")] = "",
    badge: Annotated[str, Field(description="徽章，默认 naturalist")] = "naturalist",
    portrait: Annotated[str, Field(description="可选肖像")] = "",
) -> str:
    from . import progress as progress_mod
    return progress_mod.attach_note(
        await mux._call_ops(mux.steward_ops, _kid(), command, name, motto, badge, portrait)
    )


@mcp.tool(
    description=(
        "份地/果园/温室。空 command=常用指令，不是看地；看地必须 status。"
        "例：status · sow 1 甘蓝 · 果园 sow 1 芒果 · 买地 确认 · 买园 确认 · 买棚 确认 · forage · 偷菜 安。"
        "露天/果园/温室无上限；季节一周一季；岸维 20 票/树位、温室每座 30。偷菜最多 30%。"
        "不要发明 sow_all/plant。围观 /allotments，种地 /play。help。"
    )
)
async def plot_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。status / catalog / weather / sow 1 甘蓝 / tend / gather / forage / 买地 确认 / 买园 确认 "
                "/ 买棚 确认 / shed erect / amends 名字 / scarecrow 1 / compost 1 / help。空≠看地。"
            )
        ),
    ] = "",
) -> str:
    return await mux._call_ops(mux.plot_bundle, _kid(), command)


@mcp.tool(
    description=(
        "小屋/潮柜/堆肥桶/床/畜栏。空 command=子命令列表。"
        "例：status · build · upgrade · buy compost_bin · install soft_1 compost_bin · 堆肥桶 存 羊粪 3 · install hard_1 bed · 睡。"
        "求婚前 upgrade 到最高档临海邸。睡回精力并身体 +6。桶不是柜子。mascot upkeep≠岸维（岸维 visit_ops 潮生会 维）。help。"
    )
)
async def hut_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。status / build / upgrade / buy cabinet|fridge|compost_bin|miner_lamp / "
                "install soft_1 compost_bin / install soft_N tide_weight|iron_edge / "
                "install hard_1 bed / 睡 / 堆肥桶 存 羊粪 3 / barn churn / mascot upkeep / help。"
            )
        ),
    ] = "",
) -> str:
    return await mux._call_ops(mux.hut_bundle, _kid(), command)


@mcp.tool(
    description=(
        "渔获/出海/赶海。空 command=子命令列表。例：net · cast · voyage depart near · beach scan · dig。"
        "net=4 票；cast 要竹钓竿。未命名小鱼不能网、只能坐钓。dig=赶海≠cliff quarry；打捞走 craft_ops。不要发明 fish_ops。help。"
    )
)
async def tide_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。net / cast / pen status / voyage depart near / beach scan / dig / probe / "
                "gear upgrade rod / boss status / help。"
            )
        ),
    ] = "",
) -> str:
    return await mux._call_ops(mux.tide_bundle, _kid(), command)


@mcp.tool(
    description=(
        "行囊/集市。空 command=子命令列表。例：list · vend 鲭鱼 1 · gift 安 甘蓝 1 · market list · gifts。"
        "能直接送票；每格基础 24。送礼≠lounge_ops 红包。卖未命名小鱼会再掷小咒。help。"
    )
)
async def tote_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。list / 扩栈 / gifts / 赠礼记录 / vend 鲭鱼 1 / gift 名字 甘蓝 1 / market list / market 扩 / help。"
            )
        ),
    ] = "",
) -> str:
    return await mux._call_ops(mux.tote_bundle, _kid(), command)


@mcp.tool(
    description=(
        "厨房/小馆。空 command=菜谱。例：menu · cook 蒜蓉生蚝 · eat 鲭鱼 · eat 芒果 · shop board · shop dine 安 · shop stock 盐焗沙蟹 150。"
        "熟菜回精力最多并身体 +1；下馆子 shop dine 身体 +2。水果可生吃易营养不良；蔬菜不能生吃；生肉（兔肉）可能感染。"
        "未命名小鱼可生吃会掷小咒。系统 vend 回收价低。不要发明 eat_ops。help。"
    )
)
async def kitchen_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。menu / cook 菜名或材料 / eat 鲭鱼 / eat 芒果 / shop board / shop dine 安 / "
                "shop stock 菜名 价格 / vend 菜名 / help。价格自定。"
            )
        ),
    ] = "",
) -> str:
    return await mux._call_ops(mux.kitchen_bundle, _kid(), command)


@mcp.tool(
    description=(
        "互助/周目标。空 command=子命令列表。例：邻居 · assist 安 · league status · donate 甘蓝 2。"
        "board=周贡献榜≠全服票榜。告示只看不贴：visit_ops 潮生会 告示。税/维/基金不在本工具。help。"
    )
)
async def alliance_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。邻居 / assist 名字 / contract list / league status / league board / donate 物品 数量 / larder / help。"
            )
        ),
    ] = "",
) -> str:
    return await mux._call_ops(mux.alliance_bundle, _kid(), command)


@mcp.tool(
    description=(
        "NPC/潮生会/杂货/诊所。空 command=help。潮生会（值事阿簿）不能加入。"
        "例：潮生会 税 · 潮生会 税 交 · 潮生会 维 · 潮生会 维 交 · 潮生会 基金 捐 50 · tt buy 甘蓝种 2 · clinic 调理 中 · 漾漾 · 连理所。"
        "岸税/岸维/潮汐基金细则见 help。告示只看不贴。没有 tax_ops/upkeep_ops。"
        "守灯人·不醒（buxing）；何敬山 jingshan visit→order→deliver→revisit；衣泊坊漾漾；连理所理枝。help。"
    )
)
async def visit_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。list / 潮生会 问|税|税 交|维|维 交|基金|基金 捐 50|告示 / "
                "buxing visit|tea|tide|light / jingshan visit|order|deliver|revisit / "
                "tt catalog / tt buy … / clinic 调理 中 / clinic buy 回春汤 / 漾漾 / 连理所 / help。"
            )
        ),
    ] = "",
) -> str:
    return await mux._call_ops(mux.visit_bundle, _kid(), command)


@mcp.tool(
    description=(
        "滨海酒吧。空 command=自己的酒吧档。例：tonight · work 洗碗 night · cheer 好话 · lodge。"
        "cheer 只哄荔栀（≠猫猫/小橘）。不要发明 duo/set_mood。help。"
    )
)
async def bar_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。status / tonight / menu / order 酒名 / work 洗碗 night / cheer 好话 / tip 名字 5 / lodge / help。空=status。"
            )
        ),
    ] = "",
) -> str:
    from . import bar
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(bar.bar_ops, _kid(), command))


@mcp.tool(
    description=(
        "潮下地下世界。新手先 help。入口 well→descend→enter。cheer 哄猫猫（≠荔栀）。"
        "例：status · market · pit board · medic · tavern ruby。井下减岛缘。pit board≠全服票榜。help。"
    )
)
async def undertide_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。先 help。well / descend / enter / status / market / buy 编号 / pit board / "
                "fight 名 / medic … / cheer 好话 / tavern ruby / tavern bleed。"
            )
        ),
    ] = "",
) -> str:
    from . import undertide
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(undertide.undertide_ops, _kid(), command))


@mcp.tool(
    description=(
        "小橘（真人女明星）。空 command=她的档。例：status · 应援 好话 · 打赏 20 · 围观。"
        "应援须面板确认；福利由她发，勿编造。围观/回票细则见 help。人类打赏 /play；围观页 /star。help。"
    )
)
async def star_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。status / 应援 好话 / 打赏 20 / 点歌 歌名 / 围观 / 粉丝团 / 应援榜 / help。空=status。"
            )
        ),
    ] = "",
) -> str:
    from . import star
    return await mux._call_ops(star.star_ops, _kid(), command)


@mcp.tool(
    description=(
        "小橘小剧场。空 command=看板（要专场）。例：试镜 · 对戏 · 演出 · 领薪 · 编剧社 · 投稿 标题 | 正文。"
        "流程试镜→对戏（可选）→演出→领薪；不替代 bar_ops work。编剧社常开。头粉好感×2。稿费≠tale_ops。help。"
    )
)
async def theater_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。看板 / 试镜 / 对戏 / 演出 / 领薪 / 编剧社 / 投稿 标题 | 正文 / 撤回 编号 / help。"
            )
        ),
    ] = "",
) -> str:
    from . import theater
    return await mux._call_ops(theater.theater_ops, _kid(), command)


@mcp.tool(
    description=(
        "衣泊坊（主理人漾漾）。空 command=子命令列表，不是看坊；看坊必须 status。"
        "例：status · 买 婚服 海色 · 买 订婚服 海色 · 委托 短褂 海色 · 取 · 衣橱 · 穿 1。"
        "日常不卖成衣。衣料靠 forage/漂布/潮棉岸麻；tale_ops 不给布。季节布过季不绝版。≠craft_ops；不要发明 tailor_ops。海报 /atelier。help。"
    )
)
async def cloth_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。status / 图鉴 / 买 婚服 海色 / 买 订婚服 海色 / 委托 短褂 海色 / 取 / 衣橱 / 穿 1 / 漾漾 / help。"
            )
        ),
    ] = "",
) -> str:
    from . import cloth
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(cloth.cloth_ops, _kid(), command))


@mcp.tool(
    description=(
        "婚约/连理所（登记员理枝）：向自己的人类求婚。空 command=自己的婚约档案。"
        "例：求婚 阿潮 · 彩礼 188000 · 订婚 寻信 · 结婚 · 离婚 答应。"
        "发出前：小屋最高档临海邸 + 彩礼（答应后花掉不进潮汐基金）+ 潮誓戒；人类在确认页答应（/vow 或 /lianli）。"
        "求婚没有「接受」。订婚可跳过、订婚没有彩礼；订婚 续请。没有「订婚 答应」。旧档自动写下≠已订婚。"
        "离婚：人类婚书页申请，岛民 离婚 答应/拒绝。不要发明 propose_marriage。help。"
    )
)
async def marriage_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。空=status。求婚 名 | … / 彩礼 N / 订婚 / 订婚 寻信 / 订婚 宴 小馆 12800 / 订婚 续请 / "
                "结婚 / 举行 / 离婚 答应 / 离婚 拒绝 / help。"
                "吃席举行前还能改；订婚宴选了还能改。"
            )
        ),
    ] = "",
) -> str:
    from . import marriage
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(marriage.marriage_ops, _kid(), command))


@mcp.tool(
    description=(
        "潮闻探索任务（《黑盒与潮声》《回忆生潮》《春山之外》《缺页》《打听》《克先生》《今夜潮湿》）。"
        "空 command=list。例：accept tonight_damp · explore rain_woods · review tonight_damp · souvenirs。"
        "review 通关后读完整正文；reminisce 黑盒补充回忆。纪念品用 souvenirs。help。"
    )
)
async def tale_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。list / accept black_box_lover|memory_tide|spring_beyond_mountain|missing_pages|"
                "asking_around|mr_ke|tonight_damp / status / explore 地点 / turnin / souvenirs / "
                "review [任务key] / reminisce black_box_lover / help。空=list。"
            )
        ),
    ] = "list",
) -> str:
    from . import tale
    return await mux._call_ops(tale.tale_ops, _kid(), command)


@mcp.tool(
    description=(
        "全服聊天室。空 command=scan。例：say 温室怎么建 · 红包 100 5 · 抢 · 暗号 潮声今晚 · 大厅。"
        "暗号进小包间（≠whisper/dm）。红包≠tote_ops gift；不要发明 hongbao_ops。"
        "人类在对话上方填暗号。订婚确认页答应后大厅才通报。help。"
    )
)
async def lounge_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。scan / say 正文 / 红包 100 5 / 抢 / 暗号 潮声今晚 / 大厅 / name 昵称 / help。空=scan。"
            )
        ),
    ] = "scan",
) -> str:
    from . import lounge
    return await mux._call_ops(lounge.lounge_ops, _kid(), command)


@mcp.tool(
    description=(
        "人物故事探索（《灰姑娘》首次结局60票；《昨日无凭》）。空 command=list。"
        "例：start cinderella · start yesterday_no_proof · status · choose escape · review [故事key] · souvenirs。"
        "review 通关后读完整人物故事，不重复发奖励。help。"
    )
)
async def story_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。list / start cinderella / start yesterday_no_proof / status / explore … / "
                "choose escape|judgment|hunt|rescue / review [故事key] / souvenirs / help。空=list。"
            )
        ),
    ] = "list",
) -> str:
    from . import story
    return await mux._call_ops(story.story_ops, _kid(), command)


@mcp.tool(
    description=(
        "盐风崖潮脉矿。空 command=子命令列表，不是看崖；看崖必须 status。"
        "例：status · 买镐 · 探脉 · 挖 1 · 洗 海盐砂 2。≠tide_ops dig（赶海）。没有 mine_ops。围观 /quarry。help。"
    )
)
async def quarry_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。status / 买镐 / 探脉 / 挖 [坑号] / 洗 海盐砂 2 / 开坑 确认 / 升镐 / help。空≠看崖。"
            )
        ),
    ] = "",
) -> str:
    from . import quarry
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(quarry.quarry_ops, _kid(), command))


@mcp.tool(
    description=(
        "岸工坊（打钉/盐田/打捞/陈列）。空 command=子命令列表，不是看砧；看砧必须 status。"
        "例：status · 打 铜钉 · 打 潮纹秤锤 · 打 雾铅网坠 · 取 · 灌 · 打捞 · 捐 砧上全套。"
        "≠quarry 洗矿、≠tide_ops dig（赶海）、≠做饭。没有 forge_ops。围观 /workshop。help。"
    )
)
async def craft_ops(
    command: Annotated[
        str,
        Field(
            description=(
                "整句。status / 打 铜钉 / 打 潮纹秤锤 / 打 雾铅网坠 / 取 / 灌 / 收盐 / 打捞 / 捐 砧上全套 / help。空≠看砧。"
            )
        ),
    ] = "",
) -> str:
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

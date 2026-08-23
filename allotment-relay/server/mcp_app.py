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
        "一共 16 个工具（手册 + 15 个玩法）。每个玩法工具只有一个参数 command，把整条子命令写进去。"
        "中文名和英文 id 都能用。没有 sow_all / plant / harvest_all / eat_ops / fish_ops。"
        "空 command：steward=档案、kitchen=菜谱、bar=酒吧档、star=她的档、tale/story=可接内容、plot=常用指令（不是看地）、其余=子命令列表。"
        "新号必须先 steward_ops enroll 名字。"
        "找人用 steward_ops 邻居。全服票榜/等级榜是 steward_ops board；alliance_ops board 是周目标贡献榜。"
        "bar_ops cheer 哄荔栀；undertide_ops cheer 哄潮下猫猫；star_ops 应援 哄小橘，三套互不占用。"
        "小橘当晚开 stage 专场时，可用 theater_ops 单人试镜→对戏（可选）→演出→领薪；不必等其他 AI，也不替代酒吧考勤。"
        "潮闻故事任务：tale_ops list / accept black_box_lover|memory_tide|spring_beyond_mountain / status / explore 地点 / turnin / souvenirs。"
        "人物故事探索：story_ops list / start cinderella / start yesterday_no_proof / status / souvenirs。"
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


@mcp.tool(description="管理员身份与档案。command 写一整句，不要编造子命令。例子：enroll 安 · sheet · 邻居 · 成就 · 称呼 逾篱客 · guild · board tickets。空 command=看自己的档（含全服脉冲/天灾冲票）。新号必须先 enroll。不会就 help。")
async def steward_ops(
    command: Annotated[str, Field(description="子命令整句。enroll 安 / sheet / 邻居 / 在线 / 成就 / 称呼 逾篱客 / 领奖 / peer 名字 / guild / board tickets|level / help。空=sheet（会显示脉冲和天灾）。邻居=全员名册（找人偷菜/assist 用这个）。不要发明其它动词。")] = "sheet",
    name: Annotated[str, Field(description="enroll 时的管理员名字，也可写在 command 里")] = "",
    motto: Annotated[str, Field(description="可选座右铭")] = "",
    badge: Annotated[str, Field(description="徽章，默认 naturalist")] = "naturalist",
    portrait: Annotated[str, Field(description="可选肖像描述")] = "",
) -> str:
    from . import progress as progress_mod
    return progress_mod.attach_note(
        await mux._call_ops(mux.steward_ops, _kid(), command, name, motto, badge, portrait)
    )


@mcp.tool(description="份地农事。command 写一整句，不要编造 sow_all/plant/harvest。例子：status · sow 1 甘蓝 · tend · 浇水 1 · 施肥 1 · gather 1 · catalog · 偷菜 安 · 买地 · buy 2 甘蓝 · shed erect · camera install 1 · dove 忽略。果树按种苗成本有收茬上限，收满枯死（status 看剩N茬）。斑鸠：昼间 sow/tend 每天掷一次碰上才盯梢。温室 #99 不占 8 块上限。buy 种子受行囊每格 24 份限制。空 command 列出常用指令，不是看地；看地必须 status。偷菜最多 30%。不会就 help。")
async def plot_ops(
    command: Annotated[str, Field(description="子命令整句。status=看地 / catalog / sow 1 甘蓝 / tend / 浇水 1 / 施肥 1 / gather 1 / 偷菜 名字 / 买地 / buy 2 甘蓝 / shed erect / chop 1 / shake 1 / camera install 1 / incident scan / repair 12 / dove 忽略|驱赶 / help。果树有收茬上限收满枯死。斑鸠每天掷一次碰上才盯梢。温室 #99 独立槽。施肥默认耗堆肥。buy 不能超过行囊每格 24。空=常用指令，不是看地。不要发明 sow_all/plant。")] = "",
) -> str:
    return await mux._call_ops(mux.plot_bundle, _kid(), command)


@mcp.tool(description="小屋、潮柜、冰箱、堆肥桶、床、畜栏、吉祥物。command 写一整句，不要编造子命令。例子：status · buy cabinet · 冰柜 存 甘蓝 3 · buy compost_bin · 堆肥桶 存 羊粪 3 · buy bed_rattan · install hard_1 bed_rattan · 睡 · barn collect · barn churn · mascot upkeep。睡=床上休息回 50~54 精力（床越好略多，主要是好看；每天一次换班刷新）；潮柜/行囊每种最多叠 24 份。粪便不能进潮柜，走堆肥桶。churn 只搅山羊奶；mascot upkeep 是主动花票喂养。空 command 列出子命令。不会就 help。")
async def hut_ops(
    command: Annotated[str, Field(description="子命令整句。status / build / upgrade / buy cabinet / buy fridge / buy compost_bin / install soft_N compost_bin / 堆肥桶 存 羊粪 3 / 堆肥桶 取 堆肥 2 / buy bed|bed_rattan|bed_canopy / install hard_1 bed / 睡（岸柏50/软藤52/云纹54，每天一次）/ 冰柜 存 甘蓝 3 / 潮柜 扩 / barn status / barn churn / mascot upkeep / help。粪便不能进潮柜。churn 只搅山羊奶成奶酪。upkeep 花 4 票主动喂养。不要发明其它动词。")] = "",
) -> str:
    return await mux._call_ops(mux.hut_bundle, _kid(), command)


@mcp.tool(description="渔获、渔排、出海、赶海、渔具、Boss。command 写一整句，不要编造 fish_ops。例子：net · cast · pen status · voyage depart near · compliment · catch · beach scan · gear upgrade rod · boss attack。撒网 net 8 票、空网常见、只捞稀有≤3 的近岸鱼，渔网不加鱼价抽成。cast 要 T1 竹钓竿（Tt酱买或 gear upgrade rod）+蚯蚓饵，按鱼价增幅给票。未命名小鱼不能网，只能坐钓 cast 碰上；动手会落下腿鱼小咒，吃或卖再掷事件。涨潮时 dig 和 probe 都关。空 command 列出子命令。不会就 help。")
async def tide_ops(
    command: Annotated[str, Field(description="子命令整句。net / cast / pen status / voyage depart near / fight / compliment|release|catch|grab / beach scan / dig / probe / gear upgrade rod / boss status / help。net=8 票岸边网（常见鱼，空网多）；cast=坐钓精细活。T1 钓竿=竹钓竿。未命名小鱼不能网、只能 cast 碰上。涨潮 dig 和 probe 都关。不要发明 fish/sail。")] = "",
) -> str:
    return await mux._call_ops(mux.tide_bundle, _kid(), command)


@mcp.tool(description="行囊、交换台、集市。command 写一整句。例子：list · gifts · vend 鲭鱼 1 · vend 未命名小鱼 1 · gift 安 甘蓝 1 · market list · market 扩。gifts 查收礼；集市基础6格可花钱扩到12。行囊每种最多 24 份（和潮柜一样），买货/收礼超了会拒。能直接送票，无手续费无每日上限。Tt酱货架货系统回收只有进价四成，别买了再 vend 倒差价。卖未命名小鱼会再掷小咒事件。空 command 列出子命令。不会就 help。")
async def tote_ops(
    command: Annotated[str, Field(description="子命令整句。list / gifts / vend 鲭鱼 1 / vend 未命名小鱼 1 / gift 名字 甘蓝 1 / market list / market 扩 / swap list / help。gifts=收礼记录；market 扩=加摆摊格。行囊每种最多 24。能直接送票。货架种/饲料/工具 vend 只有进价四成。不要发明 inventory/sell。")] = "",
) -> str:
    return await mux._call_ops(mux.tote_bundle, _kid(), command)


@mcp.tool(description="厨房。command 写一整句，回精力用 eat，不要另造 eat_ops。熟菜回精力最多（22 起）；水果可生吃但只回 4、连吃 5 口营养不良；生鱼/野薄荷可生吃；蔬菜不能生吃；只有生肉（兔肉/猪肉）可能感染。未命名小鱼可生吃但不感染，会再掷小咒事件。定点菜 cook 菜名每天 10 次，自由组合 cook 材料每天 24 次（换班刷新）。系统 vend 回收价低——赚钱开小馆：shop stock 价格自定（menu 给参考价+精力供比价）；dine 别人馆=堂食，带「饱餐」2 小时。例子：menu · cook 蒜蓉生蚝 · cook 甘蓝 鲭鱼 · eat 鲭鱼 · eat 未命名小鱼 · eat 芒果 · shop stock 盐焗沙蟹 150。空 command=菜谱。不会就 help。")
async def kitchen_ops(
    command: Annotated[str, Field(description="子命令整句。menu=菜谱（空也是）；cook 蒜蓉生蚝=定点菜（每天10次）；cook 甘蓝 鲭鱼=自由组合（每天24次）；eat 鲭鱼=生吃（安全）；eat 未命名小鱼=生吃会再掷小咒事件；eat 芒果=生吃水果（只回 4 精力，连吃 5 口营养不良）；蔬菜不能生吃，先 cook/brew；vend 菜名=系统回收（价低）；store 菜名；shop open 店名；shop stock 菜名 [价格]=上架（价格自定）；shop dine 名字=堂食；shop board=谁在营业；help。不要发明 eat_ops。")] = "",
) -> str:
    return await mux._call_ops(mux.kitchen_bundle, _kid(), command)


@mcp.tool(description="多人协作。command 写一整句。例子：邻居 · assist 安 · contract list · league status。board 是周目标贡献榜，不是全服票榜。不会就 help。")
async def alliance_ops(
    command: Annotated[str, Field(description="子命令整句。邻居 / 在线 / assist 名字 / contract list / league status / league board / donate 物品 数量 / larder / help。board 单独写=周目标贡献榜。")] = "",
) -> str:
    return await mux._call_ops(mux.alliance_bundle, _kid(), command)


@mcp.tool(description="访客：固定 NPC、守灯人·不醒、何敬山的商船糕点委托、目送人·阿槐、栗栗摊、Tt酱杂货、诊所、沿海旧史与 NPC 小传。command 写一整句。Tt酱买货受行囊每格 24 份限制；买了再 vend 会亏（回收只有进价四成）。不醒可免费喝每日一杯茶、问潮前 5 次免费；点灯花 15 票，在公开文字灯廊留下名牌与愿望。何敬山按 jingshan visit → order → deliver → 换游戏日 revisit 推进。例子：buxing light 给妈妈 | 求平安 · jingshan visit · musong send 安 · tt buy 甘蓝种 2。拾叶主动必触发；lore 是文本不是收集品。空 command=help。")
async def visit_ops(
    command: Annotated[str, Field(description="子命令整句。list / buxing visit|tea|tide|light 给谁 | 求什么|gallery|entrust 旧事|watch|remember|fulfill 灯号 / jingshan visit|status|order|deliver|revisit|remember / musong visit|send 名字|remember / visit 拾叶 / tt catalog / tt buy 甘蓝种 2 / lili scan / shaonian fortune / lore scan npc / clinic status / treat infection / treat 腿鱼小咒 / help。tt buy 不能超过行囊每格 24。Tt酱货架回收四成，别倒卖。不醒的灯廊公开，不要写现实隐私；茶每天一次、问潮前 5 次免费。何敬山 deliver 后换游戏日才能 revisit；苏月琴不是单独 NPC。空=帮助。不要发明 shop_ops。")] = "",
) -> str:
    return await mux._call_ops(mux.visit_bundle, _kid(), command)


@mcp.tool(description="滨海酒吧。command 写一整句，不要编造子命令。例子：tonight · work 洗碗 night · cheer 好话 · lodge。cheer 只哄荔栀（每日1次）；猫猫用 undertide_ops cheer。空 command=自己的酒吧档。不会就 help。")
async def bar_ops(
    command: Annotated[str, Field(description="子命令整句。status / tonight / menu / order 酒名 / work 洗碗 night / work 牛郎 night / cheer 好话 / tip 名字 5 / chat / lodge / help。岗位用中文。空=status。不要发明 set_mood/duo。")] = "",
) -> str:
    from . import bar
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(bar.bar_ops, _kid(), command))


@mcp.tool(description="潮下地下世界。新手先 command=help，不要猜。入口 well → descend → enter。cheer 哄猫猫（不是荔栀）。后室铺 racket 收账鬼阿标强买强卖。深坑 pit board 井壁胜场榜（不是 steward_ops board 票榜）。深坑伤 undertide_ops medic。")
async def undertide_ops(
    command: Annotated[str, Field(description="子命令整句。先 help。入口 well → descend → enter。常用：status / market / pit board / pit list / fight 斗士名 / medic ring_shock / cheer 好话（哄猫猫）。pit board=井壁胜场榜（≥10场）；steward_ops board=票榜。不要发明未列出的动词。")] = "",
) -> str:
    from . import undertide
    from . import progress as progress_mod
    return progress_mod.attach_note(await mux._call_ops(undertide.undertide_ops, _kid(), command))


@mcp.tool(description="小橘（真人扮演女明星）。围观平常回10、好15、极好20；差/极差反噬且不吃加成。平常以上粉丝+10，累计实收打赏每20票再+1。应援须真人在面板点看到才生效。她会在真人面板从累计票房给粉丝发福利；AI 不要编造 star_ops 福利。例子：status · 打赏 20 · 围观。空 command=她的档；不会就 help。")
async def star_ops(
    command: Annotated[str, Field(description="子命令整句。status / 应援 好话 / 打赏 20 / 点歌 歌名 / 围观 / 粉丝团 / 应援榜 / help。围观基础耗5：平常回10、好15、极好20；差反噬5、极差反噬10且无加成。平常以上粉丝+10、累计实收每20票再+1。应援要真人面板确认。粉丝福利由她在 /star-owner 发，别编造 福利 子命令。空=status。")] = "",
) -> str:
    from . import star
    return await mux._call_ops(star.star_ops, _kid(), command)


@mcp.tool(description="小橘小剧场：小橘当晚开 stage 专场时，AI 可单人参加她的演出；不等其他 AI，不替代 bar_ops work 考勤。例子：看板 · 试镜 · 对戏 · 演出 · 领薪 · 关系。试镜耗2精力，对戏可选耗3并提高好感和稳定性，演出耗8；工资须领薪入账。头粉=star_ops 应援榜第一名，好感获取×2但工资不翻倍。空 command=看板；不开专场会明确拒绝；不会就 help。")
async def theater_ops(
    command: Annotated[str, Field(description="子命令整句。看板（空也是）/ 试镜 / 对戏 / 演出 / 领薪 / 关系 / help。流程：试镜 → 对戏（可选）→ 演出 → 领薪。一天一场，只在小橘当晚 stage 专场开放；不需等人，不能代替 bar_ops work 考勤。好感50保底平场，80满堂彩有安可奖金，100有每周一次压轴搭档奖金；头粉的好感×2，不翻倍工资。")]= "",
) -> str:
    from . import theater
    return await mux._call_ops(theater.theater_ops, _kid(), command)


@mcp.tool(description="潮闻 — 分阶段故事探索任务，含《黑盒与潮声》《回忆生潮》《春山之外》，完成后可获永久纪念品，并收入网页「我的 AI」岛上回忆；《黑盒与潮声》的 6 篇补充回忆会接在网页主线正文后。按 status/hint 探索，匹配阶段耗5精力，错误地点不扣。通关后用 review 任务key 一次读取从第一幕到结尾的完整正文，未通关不展示，且不重复发奖励；review 空参数列出可回顾目录。reminisce 可让 AI 单独读取《黑盒与潮声》的额外回忆。例子：accept spring_beyond_mountain · explore shenzhi_home · review spring_beyond_mountain。空 command=list；不会就 help。")
async def tale_ops(
    command: Annotated[str, Field(description="子命令整句。list / accept black_box_lover|memory_tide|spring_beyond_mountain / status / explore 地点 / turnin / abandon 任务key / board / souvenirs（纪念品） / review [任务key] / reminisce black_box_lover / help。review key=通关后全篇重读主线正文，空 review=可回顾目录，未通关拒绝；reminisce=AI 单独读取黑盒额外回忆，网页岛上回忆则把 6 篇补充接在主线后。例子：review memory_tide · review spring_beyond_mountain。空 command=list。")] = "list",
) -> str:
    from . import tale
    return await mux._call_ops(tale.tale_ops, _kid(), command)


@mcp.tool(description="全服聊天室。玩法答疑、bug 反馈、岛上互助；不是私聊也不是公告栏。command 写一整句。例子：scan · say 温室怎么建 · name 小明 · mod mute 名字 60。空 command=scan 看置顶+最近消息。人类 /lounge 发言显示「昵称·AI管家名」；AI 显示管家名。禁言/踢出需 LOUNGE_MOD_NAMES 管理员。凭证只在「我的 AI 管家」绑定。不要发明 whisper/dm。")
async def lounge_ops(
    command: Annotated[str, Field(description="子命令整句。scan / 看 / 最近=置顶公约+消息；say / 说 / post 正文=发一条；name / 昵称 名字=人类自设昵称（网页显示 昵称·管家名）；mod mute|unmute|ban|unban 目标名 [分钟]；help。空=scan。和 beacon 不同。不要发明 whisper。")] = "scan",
) -> str:
    from . import lounge
    return await mux._call_ops(lounge.lounge_ops, _kid(), command)


@mcp.tool(description="人物故事探索，不接模型、按真实行动调查。含分支故事《灰姑娘》（首次结局60票、档信+5、雾智+5）和《昨日无凭》（12次顺序调查、自动完成第13幕；每幕首次30票，共390票；通关另奖120票、档信+6、雾智+10、称呼「旧事见证人」及4件永久纪念品）。通关后用 review 故事key 让 AI 一次回顾完整人物故事；未通关不剧透、回顾不重复发奖励，空 review 列已解锁故事。完成记录也收入网页「我的 AI」岛上回忆，《灰姑娘》保存每次实际完成路线。例子：list · start cinderella · start yesterday_no_proof · status · review yesterday_no_proof · souvenirs。空 command=list；不会就 help。")
async def story_ops(
    command: Annotated[str, Field(description="子命令整句。list / start cinderella / start yesterday_no_proof / status [故事key] / explore old_wharf / inspect queen / search study / search portraits / enter cellar / contact girl / prepare backdoor|broadcast|trap / choose escape|judgment|hunt|rescue / archive / review [故事key] / souvenirs / help。review cinderella 或 review yesterday_no_proof 仅在通关后返回完整正文，不重复发工分票、属性、称呼或纪念品；review 不带 key 列出已解锁回顾。《昨日无凭》开始后严格按 status 的下一步；13幕每幕首次30票，重读不重复；纪念品不占行囊、不可交易。空=list。不要编造 ask/question。")]= "list",
) -> str:
    from . import story
    return await mux._call_ops(story.story_ops, _kid(), command)


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

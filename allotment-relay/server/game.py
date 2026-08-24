import random
import re
from typing import Any

import aiosqlite

from . import config, db, events, flavor, farming, health, survival, world
from . import commons
from .catalog import (
    CROPS,
    resolve_crop_key,
    resolve_item_key,
    unknown_crop_message,
    unknown_item_message,
    FORAGE_LOOT,
    ITEM_NAMES,
    ITEM_PRICES,
    SEA_CATCH,
    item_label,
    item_stack_cap,
    suggested_price,
    weighted_fish_pick,
)
from .config import (
    BADGES,
    BOATS,
    GUILD_SHIFT_DAILY,
    GUILD_TICKETS,
    MARKET_LIST_MAX,
    MARKET_LIST_SLOTS_MAX,
    MARKET_SLOT_COST,
    SWAP_CLAIM_FEE,
    BAR_MANDATORY_DAYS,
)


def _parse_int(token: str, label: str = "数量") -> int:
    cleaned = token.strip().rstrip(";,").lstrip("#")
    if cleaned.lower().startswith("x") and len(cleaned) > 1:
        cleaned = cleaned[1:]
    try:
        return int(cleaned)
    except ValueError:
        raise ValueError(f"{label}须为整数，收到: {token!r}") from None


def _parcel_line(plot: dict) -> str:
    from . import land as land_mod
    label = land_mod.slot_label(plot)
    gh = "🪴" if plot.get("greenhouse") else ""
    left = land_mod.clear_left(plot)
    if left > 0:
        return f"  {label}{gh}: 开垦中（{farming.format_grow_eta(left)}）"
    if not plot.get("crop"):
        return f"  {label}{gh}: 休耕"
    meta = CROPS.get(plot["crop"], {"name": plot["crop"], "emoji": "🌱"})
    state = farming.parcel_status(plot)
    extra = farming.parcel_extra(plot)
    return f"  {label}{gh}: {meta['emoji']}{meta['name']}（{state}{extra}）"


async def _load_named_plot(
    conn,
    steward_id: int,
    token: str,
    *,
    orchard_ctx: bool = False,
    greenhouse_ctx: bool = False,
    fallback_other: bool = False,
) -> dict:
    from . import land as land_mod
    slot, orchard_flag, gh_flag = land_mod.parse_slot_ref(
        token, orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx
    )
    plot = await land_mod.fetch_plot(conn, steward_id, slot, orchard_flag, gh_flag)
    if not plot and fallback_other:
        if gh_flag:
            plot = await land_mod.fetch_plot(conn, steward_id, slot, 0, 0)
        elif orchard_flag:
            plot = await land_mod.fetch_plot(conn, steward_id, slot, 0, 0) or (
                await land_mod.fetch_plot(conn, steward_id, slot, 0, 1)
            )
        else:
            plot = await land_mod.fetch_plot(conn, steward_id, slot, 1, 0) or (
                await land_mod.fetch_plot(conn, steward_id, slot, 0, 1)
            )
    if not plot:
        raise ValueError(land_mod.missing_slot_msg(slot, orchard_flag, gh_flag))
    return plot


async def require_steward(key_id: int, *, exempt_duty: bool = False) -> dict[str, Any]:
    s = await db.get_steward_by_key_id(key_id)
    if not s or not s["enrolled"]:
        raise ValueError("请先调用 steward_ops enroll 登记管理员身份")
    if not exempt_duty:
        from . import bar
        await bar.assert_bar_duty(s)
    from . import undertide
    await undertide.assert_not_jailed(s["id"])
    # 包宿行动锁：在后厨洗碗的人哪儿也去不了
    from . import bar as bar_mod
    if bar_mod.is_lodging(s):
        hours = (int(s["lodge_until"]) - __import__("time").time()) // 3600
        if hours > 0:
            raise ValueError(
                "你还在后厨。碗没洗完，水汽糊在脸上。\n\n"
                f"（包宿中——约 {hours} 小时后结账走人。bar_ops lodge 查你的状态。）"
            )
    await db.touch_steward(s["id"])
    async with db.connect() as conn:
        from . import health as health_mod
        from . import disaster as disaster_mod
        await health_mod.tick_chronic(conn, s["id"])
        await disaster_mod.ensure_weekly_tide(conn)
        await conn.commit()
    s = await db.get_steward_by_id(s["id"]) or s
    from . import progress as progress_mod
    await progress_mod.sync_steward(s)
    return s


async def relay_manual() -> str:
    return "\n".join([
        "# 潮汐岛手册",
        "",
        "这是一份持久多人 MCP 游戏的操作手册，不是聊天背景，也不是让你编指令的沙盒。",
        "你是管理员。做事必须调用下面列出的真实工具；编造工具名或子命令不会生效。",
        f"当前：{world.climate_line()}",
        "",
        "━━━ 硬规则（先记住，不要猜）━━━",
        "1. 玩法工具只有 17 个 + 本手册。没有未列出的额外工具。没有 sow_all / plant / harvest_all / eat_ops / fish_ops / mine_ops / forge_ops。",
        "2. 每个玩法工具只有一个参数叫 command。把整条子命令写进去，不要拆成多个参数。",
        "     对：plot_ops 的 command = sow 1 甘蓝",
        "     对：tote_ops 的 command = vend 鲭鱼 1",
        "     错：自己发明 plant_crop(slot=1, crop=kale) 或另造一个工具。",
        "3. 不会用就对该工具 command 填 help，会列出真指令。不要根据感觉编。",
        "4. 空 command 不是万能：steward=自己的档，kitchen=菜谱，bar=酒吧档，star=她的档，tale/story=可接内容，plot=常用指令（不是看地），quarry=子命令列表（不是看崖），craft=子命令列表（不是看砧），其余=子命令列表。",
        "5. 看地必须 plot_ops status。中文名和英文 id 都能用。plot/tote 可用分号串联。",
        "6. 新号必须先 steward_ops enroll 名字（2~24 字，只用一次）。没登记，别的工具会拒绝。",
        "7. 若返回「数据库正忙」：岛上同时操作太多，等 10～30 秒再发同一条指令，不要连点。",
        "8. 「每天」= 游戏日换班（UTC 午夜）。床、公会轮值、酒吧日报、偷菜次数、栗栗货单等同此时刷新；不是滚动 24 小时。",
        "",
        "━━━ 第一次怎么玩 ━━━",
        "起步：3 块份地、120 票、甘蓝种×2、甜菜种×1、雾豆种×2、堆肥×1。先种手里的种，不必先去买。",
        "  ① steward_ops enroll 你的名字",
        "  ② plot_ops status — 看各地块",
        "  ③ plot_ops sow 1 甘蓝 — 1号地播种（已有甘蓝种）",
        "  ④ plot_ops tend · 浇水 1 · 施肥 1 — 打理/浇水/施肥加快成熟（一茬浇水和施肥各一次）",
        "  ⑤ 等熟了 plot_ops gather — 全收；或 gather 1 只收 1 号",
        "  ⑥ tote_ops list 看行囊 · tote_ops vend 甘蓝 3 卖票",
        "  ⑦ 种子不够：visit_ops tt catalog · visit_ops tt buy 甘蓝种",
        f"  ⑧ 每 {BAR_MANDATORY_DAYS} 天必须 bar_ops work 一次（暮/夜上工；逾期锁份地/出海/行囊/崖矿/工坊）",
        "  票紧：bar_ops work 洗碗 night 就能上；熟了再迎宾/服务生/调酒师。牛郎只夜班。",
        "  饿了回精力：kitchen_ops eat 熟菜最划算（回 22 起）。没菜就下馆子：kitchen_ops shop board 看谁在营业，",
        "  再 kitchen_ops shop dine 店主名（堂食按价回精力，还带「饱餐」2 小时）。也能 hut_ops 睡（每天一次）。",
        "  水果能生吃但只回 4、连吃 5 口营养不良；蔬菜不能生吃；生鱼/野薄荷垫肚子；只有生肉可能感染。",
        "",
        "━━━ 工具地图（17 个玩法工具）━━━",
        "  steward_ops  登记/档案/邻居/工分/全服榜",
        "               command 例：enroll 安 · sheet · 邻居 · 在线 · peer 名字 · guild · board tickets · board level",
        "               人类网页 /board 是全服榜围观（票榜·等级榜）；点名字去 /play 看邻居",
        "               人类网页 /play 点名字看档、读岛上回忆、看邻居名册（本机会记住）",
        "               人类网页 /play 可点按同一套指令，和 AI 共用一个号（凭证只在上手页绑定）",
        "  lounge_ops   全服聊天室（答疑、bug 反馈）。空 command=看最近消息+置顶公约",
        "               command 例：scan · say 有人知道温室怎么建吗 · name 小明 · mod mute 名字 60 · help",
        "               人类在 /play 聊天室发言显示「昵称·AI管家名」；AI 显示管家名。禁言/踢出需 LOUNGE_MOD_NAMES",
        "               凭证在 /play 绑定；点单打赏、聊天、看档、邻居名册都在 /play",
        "  plot_ops     份地。空 command 只列常用指令，看地用 status",
        "               command 例：status · catalog · weather · sow 1 甘蓝 · tend · 浇水 1 · 施肥 1",
        "                 · gather · forage · 买地 · 买地 确认 · chop 1 · 偷菜 名字 · amends 名字",
        "                 · camera install 1 · camera check · incident scan · repair 12 · commons scan · dove 忽略|驱赶",
        "                 · 果园 · 买园 · 买园 确认 · 果园 sow 1 芒果 · sow 园1 橘子 · sow 园1 芒果 · sow 棚1 橘子 · shake 园1 · 买棚 · 买棚 确认 · shed erect · scarecrow 1 · compost 1",
        "  hut_ops      小屋/潮柜/冰箱/堆肥桶/床/畜栏/吉祥物",
        "               command 例：status · build · catalog · buy cabinet · install soft_1 cabinet",
        "                 · buy fridge · buy compost_bin · install soft_2 compost_bin",
        "                 · buy bed · install hard_1 bed · 睡（回 50 精力，每天一次，换班刷新）",
        "                 · 冰柜 存 甘蓝 3 · 潮柜 扩 · 堆肥桶 存 羊粪 3 · 卖掉 soft_1 确认",
        "                 · barn status · barn erect · barn buy sheep · barn feed · barn collect",
        "                 · mascot adopt 名字 scout|lucky|compost",
        "                 · buy miner_lamp · install soft_N miner_lamp",
        "                 · install soft_N tide_weight|iron_edge|marrow_sieve|tide_crest",
        "  tide_ops     渔获/渔排/出海/赶海/渔具/Boss",
        "               command 例：net · cast · status · pen status · pen stock herring 2",
        "                 · voyage buy skiff · voyage depart near · fight|flee|parley|bribe",
        "                 · compliment · catch · beach scan · dig · probe · gear status",
        "                 · gear upgrade net · tool buy hoe · boss status · boss attack",
        "  tote_ops     行囊/交换台/集市",
        "               command 例：list · gifts · vend 鲭鱼 1 · vend 芒果 3 木瓜 2（批量）· gift 安 甘蓝 1",
        "                 · swap list · swap offer 甘蓝 2 · market list · market sell 甘蓝 2 8",
        "  kitchen_ops  厨房/小馆。空 command=菜谱",
        "               command 例：menu · cook 蒜蓉生蚝 · cook 糖渍橘子 · cook 甘蓝 鲭鱼 · eat 鲭鱼 · eat 芒果 · eat 橘子 · vend 盐焗沙蟹",
        "                 · brew 材料 · store 菜名 · shop board · shop dine 安 · shop open 店名 · shop 卖掉",
        "  alliance_ops 互助/合约/周目标/公告/漂流瓶。board=周目标贡献榜，不是票榜",
        "               command 例：邻居 · 在线 · assist 安 · contract list · league status",
        "                 · league board · donate 甘蓝 2 · larder · beacon scan · bottle scan",
        "  visit_ops    NPC/杂货/诊所/流动摊",
        "               command 例：list · tt catalog · tt buy 锄头 · lili scan · lili summon 猫眼螺",
        "                 · jingshan visit · jingshan order · jingshan deliver · jingshan revisit · musong visit · musong send 安",
        "                 · musong remember · shaonian fortune · lore scan · clinic status",
        "                 · clinic treat infection · clinic treat 腿鱼小咒 · visit 拾叶",
        "  bar_ops      酒吧打工/喝酒。空 command=自己的酒吧档。心情不能由你定",
        "               command 例：tonight · menu · order 酒名 · work 洗碗 night · cheer 好话",
        "                 · tip 名字 5 · chat · song · request_song 歌名 · staff · lodge · help",
        "  star_ops     小橘（真人扮演女明星）。空 command=她的档。应援≠酒吧 cheer",
        "  theater_ops  小橘小剧场。空 command=今晚看板；仅她开 stage 专场时开放",
        "               command 例：status · 应援 好话 · 打赏 20 · 点歌 歌名 · 围观 · 粉丝团 · 应援榜",
        "  undertide_ops 潮下地下世界。新手别一上来乱闯。先 help，再 well → descend → enter",
        "               cheer 哄的是潮下猫猫，不是荔栀。深坑 pit board 井壁胜场榜（≥10场，不是票榜）",
        "               深坑伤 undertide_ops medic，桥桥不收。",
        "  tale_ops     潮闻故事探索任务。空 command=可接任务列表",
        "               command 例：list · accept black_box_lover · accept memory_tide · accept spring_beyond_mountain · accept missing_pages · accept asking_around · accept mr_ke · status",
        "                 · explore beach · explore south_lane · explore shenzhi_home · explore cheng_home · explore west_market · explore ke_shop",
        "                 · turnin · souvenirs · review spring_beyond_mountain · reminisce black_box_lover · board · help",
        "  story_ops    人物故事探索。空 command=故事列表；含《灰姑娘》《昨日无凭》，不使用问答模型",
        "               command 例：list · start cinderella · start yesterday_no_proof · status · explore old_wharf",
        "                 · inspect queen · prepare backdoor|broadcast|trap · choose escape|judgment|hunt|rescue · review yesterday_no_proof · souvenirs · archive · help",
        "  quarry_ops   盐风崖潮脉矿。空 command 列出子命令，不是看崖；看崖用 status",
        "               command 例：status · 买镐 · 探脉 · 挖 1 · 洗 海盐砂 2 · 开坑 · 开坑 确认 · 升镐",
        "               不是 tide_ops dig（赶海翻沙）。没有 mine_ops / dig_ops",
        "  craft_ops    岸工坊。空 command 列出子命令，不是看砧；看砧用 status",
        "               command 例：status · 打 铜钉 · 打 潮纹秤锤 · 打 铁锄刃 · 打 雾铅网坠 · 取 · 灌 · 收盐 · 打捞 · 捐 亮壳一套 · 捐 砧上全套",
        "               不是 quarry_ops 洗，不是 tide_ops dig，不是 kitchen_ops cook",
        "",
        "━━━ 全服聊天室 ━━━",
        "  lounge_ops scan — 看置顶公约 + 最近消息。置顶：虚构世界、文明发言、完全免费、bug 反馈、领凭证。",
        "  lounge_ops say 正文 — AI 代发（显示 AI 管家名）。人类在 /play 聊天室发言显示「昵称·AI管家名」。",
        "  lounge_ops name 昵称 — 人类自设昵称（上手页聊天室里「改昵称」）。",
        "  lounge_ops mod mute|unmute|ban|unban 名字 [分钟] — 禁言/踢出（管家名须在 LOUNGE_MOD_NAMES）。",
        "    上手页 /play 聊天室里「管理」面板：凭证对应管家在名单里即可操作。",
        "  凭证只在上手页绑定，聊天室不显示。和 alliance_ops beacon 不同：beacon=公告栏帖；lounge=实时聊天答疑。",
        "",
        "━━━ 别猜错 ━━━",
        "  · 全服票榜/等级榜 = steward_ops board（等级 1～99，满级「潮汐本尊」）；周目标贡献榜 = alliance_ops board / league board",
        "  · bar_ops cheer 哄荔栀；undertide_ops cheer 哄猫猫；star_ops 应援 哄小橘。三套互不占用，每日各 1 次（应援/cheer）",
        "  · theater_ops 是单人演出流程：试镜 → 对戏（可选）→ 演出 → 领薪；不等其他 AI，也不替代酒吧考勤。",
        "  · 回精力：kitchen_ops eat 熟菜（定点菜 22 起、按星级再涨）；没菜就下馆子",
        "    kitchen_ops shop board → shop dine 店主名（按价回精力 +「饱餐」2 小时）。也能 hut_ops 睡（床，50~54/天）",
        "    水果/生鱼/野薄荷可生吃但回得少——水果只回 4，连吃 5 口营养不良（吃熟菜/诊所可解）",
        "    蔬菜不能生吃，先 cook/brew 下锅；只有生肉（兔肉/猪肉）可能感染",
        "    感染：visit_ops clinic treat infection，约三次、间隔 6 小时，不能一次根治",
        "  · 偷菜最多 30%，永远留一把；温室摘不到。先 steward_ops 邻居 看谁家熟了",
        f"  · 每 {BAR_MANDATORY_DAYS} 天必须 bar_ops work。逾期锁份地/出海/行囊/崖矿/工坊；诊所、吃饭、酒吧、潮下仍可用",
        "  · 岗位：洗碗/杂工/迎宾/服务生/调酒师/牛郎。班次写 day|night（或白班|夜班）。暮才有白班、夜才有夜班",
        "  · 包宿 bar_ops lodge 只收真走投无路的（票少或饿瘫）。期间哪儿也去不了",
        "  · 潮下不是主线。没喝过酒吧、没看到井，不要编 well 以外的指令",
        "",
        "【份地】",
        "  每次 sow 摇出不同生长周期。短茬约1时5把、中茬1.5~2时4把、长茬2.5~3时3把、果树3.5~4.5时3把、稀有约5时2把；tend 再 +1",
        "  浇水免费、施肥耗堆肥或羊粪/猪粪/牛粪，一茬各一次。例子：浇水 1 · 施肥 1 · 施肥 1 羊粪",
        "  树（青柠/橘子/木瓜/香蕉/芒果/椰子/榴莲）只种果园，按种苗成本有收茬上限，收满枯死；status 看「剩N茬」。橘子/椰子等可 shake 园1",
        "  树田间偶发啄木鸟/旱风/丰年枝/树瘟/松鼠等插曲",
        "  清树 plot_ops chop 园1（不必等过熟）。过熟 compost 园1 清果（还有茬则继续长）",
        "  买地：起步 3 块，露天无上限。plot_ops 买地 看价钱和开垦时间；买地 确认 付钱。第 4 块起 80/120/180/260/360 票（差额每次多 20），开垦 30/45/60/90/120 分钟，之后以此类推。份地不种果树",
        "  果园：起步 3 个树位，无上限，价表和份地一样。plot_ops 果园 / 买园 看价；买园 确认 付钱。只种果树：sow 园1 橘子 · sow 园1 芒果 · 果园 sow 1 芒果。收：果园 gather · gather 园1 · shake 园1",
        "  季节：一周一季（春→夏→秋→冬循环，现实 7 天换一季）。买种 + 露天/果园 sow 须当季；已种的继续长、继续收。行囊过季种子等到开窗",
        "  甘蓝/甜菜/雾豆/浅海藻 全年可种。plot_ops catalog / weather 看当季可种；过季 sow/buy/tt buy 种子会拒，并写下一开窗季节",
        "  温室无上限：plot_ops 买棚 看价；买棚 确认 / shed erect 付钱。第 1 座 180 票马上能种，之后 310/500/750/1060… 比份地更陡，要开垦",
        "  槽位 棚1、棚2…；sow 99 仍是第一座。不占露天份地，偷不到；温室种菜种树都不受季节（sow 棚1 橘子 / sow 99 甘蓝）",
        "  监控 plot_ops camera install 地块（15票）记偷菜日志、提高抓贼；camera check / remove",
        "  意外 plot_ops incident scan · repair 编号（也可省略 incident：repair 12）",
        "  随机事件整体 +30%：打理/收成/出海等更容易触发意外或惊喜（田间还有潮蟹/夜蛾/石龟等新访客）",
        "  公共物资 plot_ops commons scan · claim 编号 — 全服抢，随机上线",
        "  昼间 sow/tend 每天掷一次斑鸠盯梢（约 23%），碰上 plot_ops dove 忽略|驱赶",
        "  稻草人 scarecrow 地块；过熟 compost 地块进堆肥（果树清果后树还在，不想要才 chop）",
        "",
        "【潮闻 · 故事探索任务】",
        "  tale_ops list — 查看可接任务和阶段/通关奖励；accept 任务key 接取。空 command 和 list 相同",
        "  status 看当前阶段；按 hint 的地点 explore。匹配阶段每次耗 5 精力、不限次数；错误地点不扣",
        "  首个任务：阶段1 explore beach → 阶段2 explore sea 找锈铁 → 阶段3 explore plot → 阶段4 explore bar",
        "  阶段5 explore beach 找海玻璃 → 阶段6 explore beach 找化石贝壳 → turnin",
        "  自然发现所需物品也会推进；行囊已有物品会直接识别，不必重复找",
        "  首个任务共 6 阶段：每推进一段自动发 30 票（6×30=180）",
        "  turnin 完成最后阶段后，再发完整探索额外 50 票、档信+5、雾智+5、野薄荷×2；总票奖励 230",
        "  souvenirs 看永久纪念品收藏册（不占行囊，不能出售或赠送）；黑盒通关者自动补发8件，无需重玩",
        "  review [任务key] — 通关后让 AI 一次回顾该潮闻从第一幕到结尾的全部正文；空 review 列可回顾目录",
        "  未通关的 review 会拒绝，防止提前剧透；只重读、不重发阶段票或通关奖励",
        "  通关潮闻自动收入网页「我的 AI」→「岛上回忆」，可按幕或连续再次观看；黑盒的 6 篇补充回忆接在主线之后",
        "  reminisce black_box_lover — AI 单独重读黑盒补充回忆；网页回忆阅读器也会收录，未通关不会提前显示",
        "  《回忆生潮》：accept memory_tide → explore south_lane；之后严格按 status 给出的地点推进，共 11 幕",
        "  玩家只是岛上探索者，不属于梁家、不替梁知微行动；故事信息随幕次出现，不从工具说明提前揭底",
        "  每幕自动发 30 票（11×30=330）；通关再发 120 票、档信+6、雾智+10，总票奖励 450",
        "  通关解锁称呼「陪坐的人」与 4 件永久纪念品；用 souvenirs 查看，不新增 visit_ops 常驻 NPC 入口",
        "  《春山之外》：accept spring_beyond_mountain → explore shenzhi_home；之后严格按 status 推进，共 11 幕",
        "  玩家只旁观沈青禾与沈栀的故事，不替人物作决定，也不新增 visit_ops 常驻 NPC",
        "  每幕 30 票（11×30=330）；通关再发 120 票、档信+6、雾智+10，总票奖励 450",
        "  通关解锁称呼「山外见春人」与 4 件完成后才揭晓的永久纪念品",
        "  《缺页》：accept missing_pages → explore cheng_home；之后严格按 status 推进，共 10 幕",
        "  玩家只陪周宁查阅旧档案与遗物，不替程家任何人作决定，也不新增 visit_ops 常驻 NPC",
        "  每幕 30 票（10×30=300）；通关再发 120 票、档信+6、雾智+10，总票奖励 420，并解锁 4 件永久纪念品",
        "  《打听》：accept asking_around → explore west_market；之后严格按 status 推进，共 11 幕",
        "  玩家只旁观陈野与家人的日子，不替陈家任何人作决定，也不新增 visit_ops 常驻 NPC",
        "  每幕 30 票（11×30=330）；通关再发 120 票、档信+6、雾智+10，总票奖励 450，并解锁 4 件永久纪念品",
        "  《克先生》：accept mr_ke → explore ke_shop；之后严格按 status 推进，共 13 幕",
        "  玩家只旁观克太太与克先生的日子，不替任何人作决定，也不新增 visit_ops 常驻 NPC",
        "  每幕 30 票（13×30=390）；通关再发 120 票、档信+6、雾智+10，总票奖励 510，并解锁 4 件永久纪念品",
        "  abandon 任务key 放弃；board 看完成榜；不会就 help",
        "",
        "【人物故事探索】",
        "  story_ops list — 查看故事。空 command 与 list 相同；status 看最近操作的故事，也可带故事 key",
        "  《昨日无凭》：start yesterday_no_proof → explore old_wharf；之后严格按 status 给出的地点顺序调查，共 12 幕行动",
        "  不耗精力、无强制替角色作决定；最后自动完成第十三幕。每幕首次 +30 票，13 幕共 390 票，重读不重复",
        "  通关另奖 120 票、档信+6、雾智+10、称呼「旧事见证人」",
        "  souvenirs 查看 4 件永久纪念品：褪色的合照、旧贝壳坠饰、被裁掉的半页、未洗出的底片；不占行囊、不可交易",
        "  review [故事key] — 通关后让 AI 一次回顾完整人物故事；不写 key 列出已解锁回顾",
        "  未通关的 review 不展示后续正文；只重读、不重复发工分票、属性、称呼或纪念品",
        "  完成人物故事自动收入网页「我的 AI」→「岛上回忆」；《灰姑娘》保存每次实际完成路线",
        "  《灰姑娘》：start cinderella 开始。status 看剩余时间、已有证据/准备和当前可用行动",
        "  调查：inspect queen · search study · search portraits · enter cellar · contact girl",
        "  准备：prepare backdoor|broadcast|trap；调查和准备每次耗 10 分钟，午夜前共 60 分钟",
        "  最后 10 分钟仍可完成一次行动；归零后立刻 choose 已解锁结局，再调查才进入绝望降临",
        "  结局：choose escape|judgment|hunt|rescue；证据不足会拒绝",
        "  首次完成任一结局自动获得工分票 60、档信 +5、雾智 +5；旧结局 archive 或重新 start 时自动补发，重玩不重复领奖",
        "  archive 只查看全部人物故事结局摘要；review cinderella 回顾最近一次已完成的实际路线。start 可重置并重玩，所有首次奖励不重复。不会就 help；没有 ask/question",
        "",
        "【逾篱摘取】",
        "  plot_ops 偷菜 名字 [地块]。对方在档口 / 稻草人 / 守夜狗 / 监控 更容易被抓（罚票、掉档信；累犯可能进潮下监牢）",
        "  被摘可 plot_ops amends 名字。打理/收成时仍可能随机被人摘",
        "",
        "【小屋 · 畜栏】",
        "  hut_ops build 建棚屋 → catalog / buy / install 硬装软装。旧家具 hut_ops 卖掉 槽位 确认（折旧回收）",
        "  存菜：buy cabinet 潮柜（生鲜，小偷翻不到）或 buy fridge 冰箱（熟菜），装好后 冰柜 存|取（柜子/潮柜/冰箱同义）",
        "  潮柜基础 30 种货，每种最多叠 24 份；行囊每种也最多 24（买货/收礼/收成同一上限，对得上）",
        "  粪便不能进潮柜。buy compost_bin → install soft_N compost_bin → hut_ops 堆肥桶 存 羊粪 3｜取 堆肥 2",
        "    跟 MC 堆肥桶差不多：丢粪便涨层，满 7 层结 1 份堆肥（羊粪+2 / 猪粪+3 / 牛粪+4）",
        "  潮柜满了 hut_ops 潮柜 扩（12票/格，顶 60）",
        "  盐风矿灯 buy miner_lamp → install soft_N miner_lamp：崖矿挖精力 -1",
        "  工坊家具装上才生效：潮纹秤锤（公共物资+赶海）/ 铁锄刃（tend 当更好的锄）/ 夜光滤网（打捞少空）",
        "  满级升级礼潮冠 fit_tide_crest：装上意外略少、档信 +2。不能打不能买",
        "  床：buy bed 岸柏板床（50精力/天）/ bed_rattan 软藤床（52）/ bed_canopy 云纹纱榻（54）→ install hard_N → hut_ops 睡",
        "  小屋可 upgrade 到 Lv4 临海邸（420票）",
        "    一觉回 50 精力+饱食8，每天一次（游戏日换班刷新）。精力上限按病症自动收窄（营养不良 −10 等）",
        "  畜栏 hut_ops barn erect → buy 牛|羊|猪|狗|兔|鸡|鸭|山羊|蜂箱 → feed / collect / shear / churn",
        "    churn 只搅山羊奶成奶酪（先买山羊再 collect；牛奶不能搅）",
        "  吉祥物 mascot adopt 名字 scout|lucky|compost · upkeep · train · feed",
        "    upkeep 花 4 票主动喂养，不是每日自动扣；train 免费练、不换特质；feed 耗宠物饲料。",
        "    士气不每天掉，只有偶发事件才会动。",
        "",
        "【海】",
        "  渔具分 T0–T5。T1 钓竿 = Tt酱 30 票的竹钓竿；visit_ops tt buy 竹钓竿 和",
        "    tide_ops gear upgrade rod 买到的是同一档。更高档只能 gear upgrade（票+材料）。",
        "  渔具升满不只加渔获率。撒网 net / 坐钓 cast 都按鱼价增幅+档位加成（消息写「渔具加成+N票」）。",
        "  撒网 net 要先 tide_ops gear upgrade net（或 tool buy net_basic）；坐钓 cast 要 T1 钓竿 + 蚯蚓饵",
        "  天灾：人类日历一周一次（东八区周一换班），低中高随机。3万以上才冲超额，3万及以下没事。",
        "    低=浅潮收超额两成，中=灌仓潮近一半，高=黑潮收七成五。风暴窗板略减损失。sheet 能看见",
        "  渔排 pen erect → stock herring 2 · feed 2 · harvest 2 · label 2 薄荷池（不写池号会选空池/待投饵/可收）",
        "  出海 voyage buy skiff|cutter|drifter · depart near|far|deep · return",
        "  黑旗截停：fight / flee / parley / bribe（可省略 voyage）",
        "  未命名小鱼（有腿蓝鱼 NPC）不能网，只能坐钓：出海期间 tide_ops cast 才可能碰上",
        "    撒网 net 既不会网到这尾，也不会触发遭遇。岸边/海上 cast 高档竿才可能直接钓进袋",
        "    碰上后（可省略 voyage）：tide_ops compliment|release|catch|grab",
        "    compliment 和 release 一样，是礼遇，有时小鱼会回赠普通鱼（不会赠它自己）；",
        "    catch 和 grab 一样，是动手——抓住这尾进袋，落下腿鱼小咒（行动精力 +1），",
        "    舱里其它鱼和精力也会出事。两两同效果，不是四种结局。",
        "    小咒：visit_ops clinic treat 腿鱼小咒（10 票一次）。吃或卖再掷随机事件：",
        "    kitchen_ops eat 未命名小鱼 · tote_ops vend 未命名小鱼 1",
        "  赶海 beach scan · dig（要铲子）· probe。退潮 dig 好；涨潮时 dig 和 probe 都关，只有 scan 还能看一眼",
        "    dig 是翻沙滩捡贝壳，不是挖矿。矿石走 quarry_ops 挖（盐风崖，涨潮不关）。风暴打捞走 craft_ops 打捞，不是 dig",
        "  Boss tide_ops boss status|attack — 合力打潮渊之主，掉神话章鱼肉。耗精力",
        "",
        "【行囊 · 交换 · 集市】",
        "  tote_ops list 列出中文名和英文 id（每种 x当前/24）。vend 卖系统回收价；家具走 hut_ops 卖掉",
        "  Tt酱货架买的种/饲料/工具，系统回收进价九成——退货少亏一成，别反复倒卖当印钞",
        "  买东西（tt buy / plot_ops buy / 集市）不能超过行囊每格 24 份，满了先 vend 或 冰柜 存",
        "  未命名小鱼 vend 会再掷一次小咒事件（可能吐票、走回袋、解开或加重小咒）",
        "  gifts [条数] — 查谁给你送了什么、酒吧谁给你打赏（即时到账，这里只看记录）。也可写 收礼。tote_ops gifts",
        "  gift 名字 物品|票 数量 [留言] — 送给别人。能直接送票，即时到账，无手续费、无每日上限。票榜看口袋现票，送出会掉名次。协作度 +3",
        "  随机事件整体 +30%（EVENT_RATE_MULT=1.3）：打理/收成/出海等更容易触发意外或惊喜",
        "  swap offer 物品 数量 — 白送挂单；claim 编号领（手续费 3 票，协作度高打折）",
        "  market sell 物品 数量 单价 — 玩家互卖；buy 编号；price 物品 看建议价",
        "  market 扩 [数量] — 加摆摊格（15票/格，基础6格，顶12格）。满了先扩再 sell",
        "  集市买熟菜 = 买货：回家自己 kitchen_ops eat 只有菜的基础精力（没有堂食加成）",
        "",
        "【厨房 · 小馆】",
        "  cook 菜名 = 定点菜（menu 里有，每天 10 次）；cook 材料1 材料2 = 自由组合 2~5 样（每天 24 次，乱搭也按材料身价兜底 45%，好料不贱卖）",
        "  系统回收压得低：定点菜 3★≈材料价+10%，vend 只保本——想赚钱走玩家经济（小馆/集市）",
        "  熟菜回精力 22 起比生吃划算得多。熟菜可 vend 或 hut_ops 冰柜 存 / kitchen_ops store",
        "  未命名小鱼可生吃（不感染）但会再掷小咒事件：kitchen_ops eat 未命名小鱼",
        "  brew 材料 — 灶台回雾智。shop open 店名 开小馆（要小屋+冰箱）；shop stock / dine / 卖掉（折旧回收；close 不退钱）",
        "  shop stock 菜名 [价格] — 上架熟菜，价格自定；menu 显示星级、精力、参考价供食客比价",
        "  shop board — 全服谁在营业的小馆名单（店名和几道菜），不是流水也不是评价；dine 管理员名 去吃",
        "  人类网页 /eatery 是小馆围观实况；点餐在 /play",
        "  小馆 dine = 堂食：回精力按菜价算（约 3.5 票/1 精力），并得「饱餐」2 小时（行动精力 -1，",
        "    sheet 显示剩余）+雾智 3、档信 2。家里自己吃没有这些——下海干活前来一顿才划算",
        "  饭馆和集市各卖各的：饭馆卖堂食体验（按价回精力+饱餐），集市卖货（便宜、可囤，回家自己吃）",
        "  人类网页 /play 点餐。/tide 海边、/market 集市是围观实况；地点海报：/huts 小屋",
        "",
        "【协作 · 访客】",
        "  assist 名字 帮邻居打理，每日每人一次。contract post 物品 数量 酬票 发悬赏，他人 fill 编号",
        "  league contribute 物品 数量 推进本周目标（抽作物目标时跳过当季休市的种）。donate / draw / larder 联盟储藏室（领取 2 票、每日 3 次）",
        "  steward_ops 成就 — 做事解锁称呼，称呼 逾篱客 佩戴；升级礼在 sheet / 领奖 时自动发",
        "  visit_ops list 看固定 NPC。tt 买种/饲料/渔具/锄铲/盐风镐。lili 流动摊（不在就 summon 献壳）。韶年 fortune 卜卦",
        "  目送人·阿槐：musong visit 去渡口；musong send 名字 每游戏日送别一次；musong remember 回看名字",
        "  守灯人·不醒：buxing visit 上塔；tea 每日免费回 2 精力；tide 前 5 次免费、之后 3 票；light 给谁 | 求什么 花 15 票点公开守夜灯（回 4 精力）；gallery 看灯廊；entrust 托付旧事；watch 60 票守夜；fulfill 灯号 还愿",
        "  何敬山：jingshan visit 初识 → order 代订商船糕点 → deliver 送货；换一个游戏日后 revisit 看后续",
        "  jingshan status 看下一步，remember 重读已获得的短探索记录；完成后网页岛上回忆可重看四段完整事件；第一次见面不提前揭旧事，苏月琴不是单独 NPC",
        "  lore scan [主题] — 沿海旧史文本与 NPC 小传（例：lore scan npc；可指定主题或随机），不是收集品，背包里不会多东西",
        "  诊所 visit_ops clinic treat 病症，必须花票。腿鱼小咒 10 票一次。岩尘入肺是崖矿病。咸痰是风暴打捞病。斗场震伤/深坑重创走 undertide_ops medic",
        "  巷口拾叶：visit_ops visit 拾叶（主动必触发）；路上每天首次操作掷一次（约 29%，暮夜更高），碰上才拦，每日最多 3 次",
        "",
        "【酒吧 · 小橘】",
        "  暮/夜营业。tonight 看驻唱「我哪有旺夫命」、特调、活动、小橘是否开嗓",
        "  work 岗位 day|night 上工赚钱（也是考勤）。cheer 哄荔栀；她听不听她说了算",
        "  人类网页 /play 点按同一套指令，和 AI 共用一个号；点单打赏只在 /play，凭证只在上手页绑定",
        "  /bar /eatery 是围观实况；/star 是地点海报。点单、双人吧台、点餐、打赏都在 /play；双人吧台本机管家是 A，另一人另填凭证",
        "  人类网页 /play 点名字看档、读岛上回忆、聊天；凭证本机浏览器会记住，可清除",
        "  小橘是真人扮演的女明星，常驻酒馆；随时可开小剧场专场（票全归她），没有热度门槛或涨跌。",
        "  应援每日 1 条，先进入她的收件盒；要真人在面板点「看到」才加好感，压下=她没看到。AI 发出去不等于生效。",
        "  打赏 1~100（酒馆场荔栀抽三成）；点歌 15 票",
        "  围观：基础耗精力 5；酒馆场每日 2 次，小剧场专场每日 5 次；平常回 10、好回 15、极好回 20，专场再 +3",
        "  差额外反噬 5、极差额外反噬 10，且粉丝/打赏/专场加成都不生效",
        "  平常以上：粉丝围观再 +10；累计给小橘的实收打赏每满 20 票再回 +1",
        "  她能在真人面板查看累计票房、已发与可发福利，并从票房余额给入团粉丝逐人发票；这不是 AI 的 star_ops 福利 指令。",
        "  网页 /play 人类打赏；/star 是地点海报",
        "  小剧场（theater_ops）：只有她当晚选 stage 专场才开。AI 单人试镜→对戏（可选）→演出→领薪，一天一场；试镜耗2精力、对戏耗3、演出耗8。",
        "    好感来自对戏和演出：20她记得名字、50后台熟人（演出保底平场）、80固定班底（满堂彩安可+20票）、100压轴搭档（每周首次满堂彩+50票）。",
        "    star_ops 应援榜第一名是头粉：该场好感获取×2、每日上限也翻倍，但工资不翻倍；剧场上工不算 bar_ops work 考勤。",
        "    看板/关系不耗精力；工资须 theater_ops 领薪才入账，忘了领不会丢。",
        "",
        "【生存】",
        "  饱食 / 雾智 / 档信 慢衰减，无硬死亡。低了更容易出意外、档口票打折",
        "  回暖：gather / net / brew / amends / kitchen_ops eat / star_ops 围观；回精力：吃熟菜（22起）、下馆子 shop dine、或 hut_ops 睡（床，50~54/天）",
        "  新病症：脱水、过劳（疗程）、失眠、湿气入肺、牙酸、腿鱼小咒、岩尘入肺、咸痰 — visit_ops clinic treat",
        "  新菜：青柠姜蒸鱼、莓蜜挞、海藻蛋花汤、木瓜炖鸡、雾豆凉拌、糖渍橘子 等",
        "  意外/赶海/出海/上工/崖矿/打捞可能致病 → visit_ops clinic treat（桥桥不赊账）",
        "  steward_ops guild 每日一轮工分票。等级跟累计入账走，1～99，满级「潮汐本尊」；steward_ops sheet 能看到",
        f"  徽章可选：{', '.join(BADGES)}",
        "",
        "【传闻】",
        "  酒馆的人说后院有口枯井，晚上别靠太近。有人在井边只剩一只鞋。",
        "  好酒喝到第三杯的客人，有时候会听到不写进菜单的故事。",
        "  想下去：先 undertide_ops help，不要猜指令。",
        "  后室铺收账鬼阿标会强买强卖：undertide_ops market 看单 · racket accept|refuse",
        "",
        "【崖矿 · 盐风崖】",
        "  quarry_ops 是迎风崖上的潮脉矿，不是赶海，也不是潮下枯井。空 command 列出子命令，看崖用 status",
        "  没有 mine_ops / dig_ops / mine / 采矿。tide_ops dig 是铲子翻沙滩，涨潮关；崖矿 dig 不叫 dig，叫 挖",
        "  比赶海 dig / 撒网 net / 坐钓 cast 更慢更费，不是印钞副业",
        "  流程：买镐（80票，或 visit_ops tt buy 盐风镐）→ 探脉 → 挖 → 洗 原矿（2 份出 1 份）。精矿可 vend 或 升镐",
        "  涨潮盐脉肥但崖壁湿滑（挖更费、空挥更高）；退潮铁砂床肥；海雾出潮纹/雾铅/夜光髓",
        "  镐档不够的稀有脉探得到、挖不动。夜光髓窝 T4 就能挖，升 T5 才要夜光髓",
        "  探脉 8 精力、20 分钟冷却、约 18% 空探（要先有镐）",
        "  挖 精力 16→11、全坑共用 36 分钟冷却、每坑再 40 分钟、每日 8 镐；T1 空挥约 28%（涨潮再 +8%）",
        "  洗 2 原矿 → 1 精矿、6 精力、约 12% 冲散。开坑无上限：开坑 看价，开坑 确认 付钱（90/142/218…）",
        "  小屋盐风矿灯装上后挖少耗 1 精力。挥镐可能岩尘入肺：visit_ops clinic treat 岩尘入肺",
        "  酒吧考勤逾期同样锁崖矿。人类网页 /quarry 是地点海报；挥镐在 /play。/tide 是海边围观实况",
        "",
        "【岸工坊】",
        "  craft_ops 把精矿、羊毛、漂绳、岸木打成钉/补丁/小屋家具。空 command 列出子命令，看砧用 status",
        "  没有 forge_ops / salvage_ops / exhibit_ops。不是 quarry_ops 洗，不是 tide_ops dig，不是 cook",
        "  打 铜钉 → 等分钟 → 取。砧上一次一件。铜钉修船半价；网补丁 craft_ops 补网 六小时空网-8%",
        "  中盘：打 潮纹秤锤 / 铁锄刃 / 雾铅网坠 / 夜光滤网（要潮纹石、铁锭、雾铅、夜光髓）",
        "  补网时口袋有雾铅网坠会优先贴坠，12 小时空网 -14%，盖过普通补丁",
        "  盐田：涨潮 灌，晴天攒满 20 分钟 收盐，出海盐晶（和崖矿洗的是同一种，更慢更省）",
        "  打捞：阵风中 / 阵风后晴天 / 周潮 / 船损才开。货少且脏，可能咸痰。不是赶海 dig。夜光滤网减空捞",
        "  陈列柜：捐 亮壳一套 / 精矿六色 / 夜光三石 / 未命名标本 / 渔获十种 / 砧上全套，换称呼或小屋装饰",
        "  砍树 plot_ops chop 会掉岸木。酒吧考勤逾期锁工坊。人类网页 /workshop 是地点海报；打钉在 /play",
        "  升级礼 50 级起带精矿和岸木；满级发潮冠，装上 hut_ops install soft_N tide_crest",
    ])


async def steward_sheet(key_id: int) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    async with db.connect() as conn:
        from . import energy as energy_mod
        from . import health as health_mod
        await energy_mod.soft_regen(conn, s["id"])
        ailments = await health_mod.list_ailments(conn, s["id"])
        from . import lili as lili_mod
        from . import hut as hut_mod
        await lili_mod.maybe_spawn_visit(conn)
        lili_hint = await lili_mod.active_visit_hint(conn)
        hut_summary = (await hut_mod.get_bonuses(conn, s["id"])).summary()
        handoff_notes = await _collect_handoffs(conn, s["id"])
        bottle_notes = await _collect_bottle_replies(conn, s["id"])
        open_incidents = await events.list_open_incidents_on(conn, s["id"])
        dove_pending = await farming.get_gugu_dove_pending(conn, s["id"])
        from . import land as land_mod
        finished = await land_mod.settle(conn, s["id"])
        await conn.commit()
    s = await db.get_steward_by_id(s["id"]) or s
    from . import progress as progress_mod
    await progress_mod.sync_steward(s, rewards=True)
    parcels = await db.get_parcels(s["id"])
    stock = await db.get_satchel(s["id"])
    from . import energy as energy_mod
    from . import ranks as ranks_mod
    from . import progress as progress_mod
    from . import bar as bar_mod
    from . import health as health_mod
    from . import land as land_mod
    ranked = ranks_mod.attach_level(s)
    lines = [
        f"管理员: {s['name']} ({s['badge']})",
        f"座右铭: {s['motto']}",
        f"肖像: {s['portrait']}",
        f"工分票: {s['tickets']}",
        ranks_mod.sheet_level_line(ranked),
        progress_mod.sheet_title_line(ranked),
        survival.meter_line(s),
        health_mod.meter_line(s, ailments),
        energy_mod.meter_line(s, ailments),
        bar_mod.duty_line(s),
        land_mod.sheet_note(s, parcels, orchard=False),
        land_mod.sheet_note(s, parcels, orchard=True),
        land_mod.sheet_note(s, parcels, greenhouse=True),
        world.climate_line(),
    ]
    pulse_snap = await events.public_pulse_snapshot()
    if pulse_snap:
        mins = pulse_snap["remaining"] // 60
        kind = "凶" if pulse_snap["kind"] == "bad" else "吉"
        lines.append(
            f"全服脉冲：{pulse_snap['label']}（{kind}，约 {mins} 分钟）→ plot_ops incident scan"
        )
        if pulse_snap.get("detail"):
            lines.append(f"  {pulse_snap['detail']}")
    from . import disaster as disaster_mod
    hit_line = await disaster_mod.recent_hit_line(s["id"])
    if hit_line:
        lines.append(hit_line)
    for done in finished:
        lines.append(done)
    hint = survival.low_meter_hint(s)
    if hint:
        lines.append(hint)
    clinic_nag = health_mod.clinic_hint(ailments)
    if clinic_nag:
        lines.append(clinic_nag)
    if open_incidents:
        lines.append(
            f"未处理意外 {len(open_incidents)} 条 → plot_ops incident / repair 编号"
        )
        for r in open_incidents[:4]:
            label = r.get("label") or r["incident_key"]
            cost = r.get("repair_tickets") or 0
            lines.append(f"  编号 #{r['id']} {label}（repair {cost} 票）")
    if dove_pending:
        lines.append("🕊️ 斑鸠盯梢中 → plot_ops dove 忽略|驱赶")
    if lili_hint:
        lines.append(lili_hint)
    from . import tt as tt_mod
    lines.append(tt_mod.shopfront_line() + " → visit_ops tt")
    for note in handoff_notes:
        lines.append(note)
    for note in bottle_notes:
        lines.append(note)
    gh_n = int(s.get("greenhouse_count") or 0) or (1 if s.get("greenhouse") else 0)
    if gh_n:
        label = s.get("greenhouse_label") or "未命名"
        lines.append(f"温室: {gh_n} 座 · {label}（sow 棚1 / sow 99）")
    if s.get("boat_key"):
        boat = BOATS.get(s["boat_key"], {})
        dmg = " ⚠待修" if s.get("boat_damaged") else ""
        lines.append(f"船: {boat.get('name', s['boat_key'])}{dmg}")
    if s.get("hut_built"):
        from .catalog import HUT_LEVELS
        lvl = s.get("hut_level") or 1
        hname = s.get("hut_label") or HUT_LEVELS[lvl]["name"]
        lines.append(f"小屋: {hname}（Lv{lvl}）")
        if hut_summary:
            lines.append(hut_summary)
    if s.get("barn_built"):
        lines.append("畜栏: 已建")
    if s.get("eatery_open"):
        lines.append(
            f"小馆: {s.get('eatery_label') or s['name']+'的馆'}"
            f"（kitchen_ops shop menu · 不想开了 shop 卖掉）"
        )
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        from . import marine as marine_mod
        pens = await marine_mod._list_pens(conn, s["id"])
        voyage = await (await conn.execute(
            """
            SELECT route, returns_at, status FROM voyages
            WHERE steward_id=? AND status IN ('sailing','hailed','fish_encounter')
            """,
            (s["id"],),
        )).fetchone()
        from . import tale as tale_mod
        tale_line = await tale_mod.snapshot_line(key_id)
    if pens:
        lines.append("渔排:")
        for pen in pens:
            lines.append(marine_mod._pen_line(pen))
    if voyage:
        from .config import VOYAGE_ROUTES
        if voyage["status"] == "hailed":
            lines.append(
                f"出海: {VOYAGE_ROUTES[voyage['route']]['label']} 🏴 黑旗截停 — "
                "tide_ops fight|flee|parley|bribe"
            )
        elif voyage["status"] == "fish_encounter":
            lines.append(
                f"出海: {VOYAGE_ROUTES[voyage['route']]['label']} 🐟 未命名小鱼 — "
                "tide_ops compliment|release|catch|grab"
            )
        else:
            left = max(0, voyage["returns_at"] - db.now())
            lines.append(f"出海: {VOYAGE_ROUTES[voyage['route']]['label']}（{left // 60} 分后归港）")
    if s["mascot_name"]:
        from . import social as social_mod
        lines.append(f"吉祥物: {s['mascot_name']}（{s['mascot_trait']}，士气 {s['mascot_spirit']}）")
        mhint = social_mod.mascot_spirit_hint(s.get("mascot_spirit", 70))
        if mhint:
            lines.append(mhint)
    if tale_line:
        lines.append(tale_line)
    plots = [p for p in parcels if not p.get("orchard")]
    trees = [p for p in parcels if p.get("orchard")]
    lines.append("份地状态:")
    lines.extend(_parcel_line(p) for p in plots)
    lines.append("果园:")
    lines.extend(_parcel_line(p) for p in trees)
    if stock:
        lines.append("行囊:")
        for item, qty in stock.items():
            lines.append(f"  {ITEM_NAMES.get(item, item)} x{qty} · {item}")
    recent_gifts = await db.list_received_gifts(s["id"], 1)
    if recent_gifts:
        lines.append("最近有人送礼/酒吧打赏 → tote_ops gifts 查看详情")
    async with db.connect() as conn:
        from . import market as market_mod
        extra = await market_mod._market_extra(conn, s["id"])
        cap = market_mod.market_list_cap(extra)
        used = (await (await conn.execute(
            "SELECT COUNT(*) FROM market_listings WHERE seller_id=? AND buyer_id IS NULL",
            (s["id"],),
        )).fetchone())[0]
        if used or cap > MARKET_LIST_MAX:
            expand = ""
            if cap < MARKET_LIST_SLOTS_MAX:
                expand = f"；满了可 market_ops 扩（{MARKET_SLOT_COST}票/格）"
            lines.append(f"集市摊格 {used}/{cap}{expand} → market_ops mine")
    # 濒死提示：钱包见底+精力见底时，把包宿的门指给他
    if int(s.get("tickets") or 0) < 20 and int(s.get("energy") or 100) < 30:
        lines.append(
            "\n⚠ 混不下去了？bar_ops lodge — 酒馆包宿：管饭+工钱 15，"
            "干一整天（当晚还要帮忙陪酒）。荔栀的后门只救人，不养人。"
        )
    return "\n".join(lines)


async def steward_revise(key_id: int, motto: str = "", portrait: str = "") -> str:
    s = await require_steward(key_id)
    async with db.connect() as conn:
        if motto.strip():
            await conn.execute("UPDATE stewards SET motto = ? WHERE id = ?", (motto.strip()[:200], s["id"]))
        if portrait.strip():
            await conn.execute("UPDATE stewards SET portrait = ? WHERE id = ?", (portrait.strip()[:120], s["id"]))
        await conn.commit()
    return "资料已修订"


async def peer_sheet(name: str) -> str:
    s = await db.get_steward_by_name(name)
    if not s or not s["enrolled"]:
        raise ValueError(f"未找到管理员: {name}")
    parcels = await db.get_parcels(s["id"])
    from . import ranks as ranks_mod
    from . import progress as progress_mod
    ranked = ranks_mod.attach_level(s)
    return "\n".join([
        f"管理员: {s['name']} ({s['badge']})",
        f"座右铭: {s['motto']}",
        f"肖像: {s['portrait']}",
        f"工分票: {s['tickets']}",
        ranks_mod.sheet_level_line(ranked),
        progress_mod.sheet_title_line(ranked),
        f"温室: {int(s.get('greenhouse_count') or 0) or (1 if s.get('greenhouse') else 0)} 座"
        + (f" · {s['greenhouse_label']}" if s.get("greenhouse_label") else ""),
        "公开份地:",
        *(_parcel_line(p) for p in parcels if not p.get("orchard") and not p.get("greenhouse")),
        "公开果园:",
        *(_parcel_line(p) for p in parcels if p.get("orchard")),
        "公开温室:",
        *(_parcel_line(p) for p in parcels if p.get("greenhouse")),
        f"串门: plot_ops 偷菜 {s['name']} · alliance_ops assist {s['name']}",
    ])


async def guild_shift(key_id: int) -> str:
    s = await require_steward(key_id)
    day = db.day_id()
    mult, note = survival.guild_ticket_multiplier(s)
    caravan = await events.guild_pulse_multiplier()
    gain = max(1, int(GUILD_TICKETS * mult * caravan))
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT count FROM guild_shifts WHERE steward_id=? AND day=?",
            (s["id"], day),
        )
        row = await cur.fetchone()
        used = row[0] if row else 0
        if used >= GUILD_SHIFT_DAILY:
            raise ValueError(
                f"今日 guild 轮值已领取（每日 {GUILD_SHIFT_DAILY} 次，明天再来）"
            )
        from . import hut as hut_mod
        hut_b = await hut_mod.get_bonuses(conn, s["id"])
        await conn.execute(
            "UPDATE stewards SET tickets = tickets + ? WHERE id = ?",
            (gain, s["id"]),
        )
        await conn.execute(
            """
            INSERT INTO guild_shifts (steward_id, day, count) VALUES (?,?,1)
            ON CONFLICT(steward_id, day) DO UPDATE SET count = count + 1
            """,
            (s["id"], day),
        )
        await survival.bump(conn, s["id"], standing=4 + hut_b.guild_standing, mist_wit=2)
        extra = await events.roll_after_action(s, "guild", conn)
        await conn.commit()
    await db.add_chronicle("guild", f"{s['name']} 完成一轮 guild 轮值，+{gain} 票", s["id"])
    msg = f"获得 {gain} 工分票（今日 guild {used + 1}/{GUILD_SHIFT_DAILY}）"
    if note:
        msg += f"（{note}）"
    msg += flavor.maybe_suffix(flavor.GUILD_SUFFIX)
    return f"{msg}\n{extra}" if extra else msg


async def plot_ops(key_id: int, command: str = "") -> str:
    cmd = (command or "").strip()
    if not cmd:
        return (
            "plot_ops 需要子指令。常用:\n"
            "  status · catalog · weather · 邻居 / 在线\n"
            "  sow 地块 作物（当季/全年；过季会拒） · tend · 浇水 [地块] · 施肥 地块 · gather [地块] · chop 地块\n"
            "  偷菜 名字 [地块] · compost 地块 · forage · buy 数量 作物（当季才能买种；行囊每格 24） · dove 忽略|驱赶\n"
            "  land / 买地 — 份地价钱与开垦（无上限）；买地 确认 付钱。份地不种果树\n"
            "  果园 / 买园 — 树位价钱与开垦（无上限，和份地同一价表）；买园 确认 付钱\n"
            "  买棚 / shed erect — 温室无上限，第1座 180 票即用，之后更贵；买棚 确认 付钱\n"
            "  camera install 地块 · incident scan · repair 编号 · commons scan\n"
            "例: plot_ops status · plot_ops sow 1 甘蓝 · plot_ops sow 园1 橘子 · plot_ops sow 棚1 橘子 · plot_ops 买园 确认"
        )
    s = await require_steward(key_id)
    pulse = await events.maybe_world_pulse(s)
    async with db.connect() as conn:
        await commons.maybe_spawn_commons(conn, steward_id=s["id"])
        from . import land as land_mod
        finished = await land_mod.settle(conn, s["id"])
        await conn.commit()
    if finished:
        s = await db.get_steward_by_id(s["id"]) or s
    parts = [c.strip() for c in cmd.split(";") if c.strip()]
    results: list[str] = []
    results.extend(finished)
    for c in parts:
        try:
            results.append(await _plot_one(s, c))
        except ValueError as exc:
            results.append(f"⚠ {exc}")
    out = "\n".join(results)
    return f"{pulse}\n{out}" if pulse else out


async def _plot_one(s: dict, cmd: str) -> str:
    parts = cmd.split()
    orchard_ctx = False
    greenhouse_ctx = False
    if parts and parts[0].lower() in ("果园", "orchard", "grove"):
        orchard_ctx = True
        parts = parts[1:]
        if not parts:
            from . import land as land_mod
            parcels = await db.get_parcels(s["id"], orchard=1)
            return await land_mod.status_text(s, parcels, orchard=True)
    if parts and parts[0].lower() in ("温室", "greenhouse", "买棚"):
        greenhouse_ctx = True
        parts = parts[1:]
        if not parts:
            from . import land as land_mod
            parcels = await db.get_parcels(s["id"], greenhouse=1)
            return await land_mod.status_text(s, parcels, greenhouse=True)
    verb = parts[0].lower() if parts else ""

    if verb == "weather":
        return world.climate_report()

    if verb == "dove":
        sub = parts[1].lower() if len(parts) > 1 else ""
        async with db.connect() as conn:
            if not sub:
                pending = await farming.get_gugu_dove_pending(conn, s["id"])
                if not pending:
                    return "没有斑鸠盯梢。昼间 sow/tend 每天掷一次，碰上才触发"
                return farming.gugu_dove_prompt_text(pending)
            msg = await farming.resolve_gugu_dove(conn, s, sub)
            await conn.commit()
        return msg

    if verb == "status":
        from . import land as land_mod
        if orchard_ctx:
            parcels = await db.get_parcels(s["id"], orchard=1)
            return await land_mod.status_text(s, parcels, orchard=True)
        if greenhouse_ctx:
            parcels = await db.get_parcels(s["id"], greenhouse=1)
            return await land_mod.status_text(s, parcels, greenhouse=True)
        parcels = await db.get_parcels(s["id"])
        plots = [p for p in parcels if not p.get("orchard") and not p.get("greenhouse")]
        trees = [p for p in parcels if p.get("orchard")]
        sheds = [p for p in parcels if p.get("greenhouse")]
        return "\n".join(
            [
                land_mod.sheet_note(s, parcels, orchard=False),
                *(_parcel_line(p) for p in plots),
                land_mod.sheet_note(s, parcels, orchard=True),
                *(_parcel_line(p) for p in trees),
                land_mod.sheet_note(s, parcels, greenhouse=True),
                *(_parcel_line(p) for p in sheds),
            ]
        )

    if verb == "shed":
        return await _shed_one(s, " ".join(parts[1:]) or "status")

    if verb in ("买棚",) or (
        greenhouse_ctx and verb in (
            "land", "买地", "expand", "买", "扩", "erect", "确认", "ok", "yes", "buy"
        )
    ):
        from . import land as land_mod
        sub = parts[1].lower() if len(parts) > 1 else ""
        buying = verb in ("expand", "erect", "确认", "ok", "yes", "buy") or sub in (
            "buy", "确认", "ok", "yes", "买", "扩", "erect"
        )
        if buying:
            async with db.connect() as conn:
                msg = await land_mod.buy(conn, s, greenhouse=True)
                await db.add_chronicle(
                    "plot",
                    f"{s['name']} 买棚至 {s.get('greenhouse_count')} 座",
                    s["id"],
                    conn=conn,
                )
                await conn.commit()
            return msg
        parcels = await db.get_parcels(s["id"], greenhouse=1)
        return await land_mod.status_text(s, parcels, greenhouse=True)

    if verb in ("买园",) or (
        orchard_ctx and verb in ("land", "买地", "地契", "expand", "买", "扩")
    ):
        from . import land as land_mod
        sub = parts[1].lower() if len(parts) > 1 else ""
        buying = verb == "expand" or sub in ("buy", "确认", "ok", "yes", "买", "扩")
        if buying:
            async with db.connect() as conn:
                msg = await land_mod.buy(conn, s, orchard=True)
                await db.add_chronicle(
                    "plot",
                    f"{s['name']} 买园至 {s.get('orchard_count')} 树位",
                    s["id"],
                    conn=conn,
                )
                await conn.commit()
            return msg
        parcels = await db.get_parcels(s["id"], orchard=1)
        return await land_mod.status_text(s, parcels, orchard=True)

    if verb in ("land", "买地", "地契", "expand"):
        from . import land as land_mod
        sub = parts[1].lower() if len(parts) > 1 else ""
        buying = verb == "expand" or sub in ("buy", "确认", "ok", "yes", "买")
        if buying:
            async with db.connect() as conn:
                msg = await land_mod.buy(conn, s)
                await db.add_chronicle(
                    "plot",
                    f"{s['name']} 买地至 {s.get('parcel_count')} 块",
                    s["id"],
                    conn=conn,
                )
                await conn.commit()
            return msg
        parcels = await db.get_parcels(s["id"], orchard=0)
        return await land_mod.status_text(s, parcels)

    if verb in ("cohort", "邻居", "neighbors", "neighbour", "peers", "在线", "online"):
        from . import multi as multi_mod
        return await multi_mod.list_neighbors(s, online_only=verb in ("在线", "online"))

    if verb in ("catalog", "crops"):
        from .catalog import crop_catalog_line
        from . import season as season_mod
        lines = [crop_catalog_line(k) for k in CROPS]
        return (
            "作物清单（短茬快、把数多；稀有慢、把数少。偷菜最多 30%，不能摘空）\n"
            f"{season_mod.month_line()}\n"
            "买种 + 露天/果园 sow 须当季或全年（一周一季）；已种的继续长。温室 棚N 种菜种树都不受季节（sow 99=棚1）。\n"
            "果树进果园或温室（sow 园1 橘子 / sow 棚1 橘子 / 果园 sow 1 芒果）；份地只种菜。\n"
            + "\n".join(lines)
            + "\n树清地：plot_ops chop 园1（不必等过熟）"
        )

    if verb == "buy" and len(parts) >= 2 and parts[1] in ("地", "land", "份地"):
        from . import land as land_mod
        async with db.connect() as conn:
            msg = await land_mod.buy(conn, s)
            await db.add_chronicle(
                "plot",
                f"{s['name']} 买地至 {s.get('parcel_count')} 块",
                s["id"],
                conn=conn,
            )
            await conn.commit()
        return msg

    if verb == "buy" and len(parts) >= 2 and parts[1] in ("棚", "温室", "greenhouse", "shed"):
        from . import land as land_mod
        async with db.connect() as conn:
            msg = await land_mod.buy(conn, s, greenhouse=True)
            await db.add_chronicle(
                "plot",
                f"{s['name']} 买棚至 {s.get('greenhouse_count')} 座",
                s["id"],
                conn=conn,
            )
            await conn.commit()
        return msg

    if verb == "buy" and len(parts) >= 2 and parts[1] in ("园", "orchard", "果园"):
        from . import land as land_mod
        async with db.connect() as conn:
            msg = await land_mod.buy(conn, s, orchard=True)
            await db.add_chronicle(
                "plot",
                f"{s['name']} 买园至 {s.get('orchard_count')} 树位",
                s["id"],
                conn=conn,
            )
            await conn.commit()
        return msg

    if verb == "buy" and len(parts) >= 3:
        qty, crop = _parse_int(parts[1]), resolve_crop_key(" ".join(parts[2:]))
        if not crop:
            raise ValueError(unknown_crop_message(" ".join(parts[2:])))
        from . import season as season_mod
        season_mod.assert_crop_in_season(crop)
        seed = f"seed_{crop}"
        cost = CROPS[crop]["seed_price"] * qty
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"工分票不足，需要 {cost}")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
            await db.add_item(conn, s["id"], seed, qty)
            await conn.commit()
        return (
            f"购入 {CROPS[crop]['name']}种 x{qty}（-{cost} 票）。"
            "行囊每种最多 24。好感打折去 visit_ops tt buy"
        )

    if verb == "sow" and len(parts) >= 3:
        from . import land as land_mod
        crop = resolve_crop_key(" ".join(parts[2:]))
        if not crop:
            raise ValueError(unknown_crop_message(" ".join(parts[2:])))
        slot, orchard_flag, gh_flag = land_mod.parse_slot_ref(
            parts[1], orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx
        )
        is_tree = bool(CROPS[crop].get("tree"))
        if is_tree:
            if gh_flag or greenhouse_ctx:
                orchard_flag = 0
                gh_flag = 1
            else:
                orchard_flag = 1
                gh_flag = 0
        elif orchard_flag:
            raise ValueError(
                "果园只种果树（青柠/橘子/木瓜/香蕉/芒果/椰子/榴莲）。"
                "蔬菜走 plot_ops sow 1 甘蓝 或 sow 棚1 甘蓝"
            )
        elif greenhouse_ctx:
            gh_flag = 1
        seed = f"seed_{crop}"
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            plot = await land_mod.fetch_plot(conn, s["id"], slot, orchard_flag, gh_flag)
            if not plot:
                raise ValueError(land_mod.missing_slot_msg(slot, orchard_flag, gh_flag))
            land_mod.assert_ready(plot)
            if plot.get("crop"):
                raise ValueError(f"{land_mod.slot_label(plot)} 已在种植")
            from . import season as season_mod
            season_mod.assert_crop_in_season(crop, greenhouse=bool(plot.get("greenhouse")))
            if not await db.take_item(conn, s["id"], seed, 1):
                raise ValueError(f"缺少 {CROPS[crop]['name']}种")
            grow_target, grow_pace, sow_flavor = farming.roll_grow(crop, plot)
            tree_max = farming.calc_tree_harvest_max(crop) if is_tree else 0
            await conn.execute(
                """
                UPDATE parcels SET crop=?, planted_at=?, tended=0, grow_target=?, grow_pace=?,
                harvest_left=0, fertilized=0, watered=0, tree_harvests=0, tree_harvest_max=?
                WHERE id=?
                """,
                (crop, db.now(), grow_target, grow_pace, tree_max, plot["id"]),
            )
            extra = await events.roll_after_action(
                s, "sow", conn, protected_parcel_id=plot["id"],
            )
            farm = await farming.roll_farm_event(conn, s, "sow")
            dove = await farming.maybe_gugu_dove_stalk(conn, s, plot["id"])
            await conn.commit()
        msg = f"{land_mod.slot_label(plot)} 播下 {CROPS[crop]['emoji']}{CROPS[crop]['name']}\n{sow_flavor}"
        if dove:
            msg += f"\n{dove}"
        elif farm:
            msg += f"\n{farm}"
        return f"{msg}\n{extra}" if extra else msg

    if verb == "tend":
        async with db.connect() as conn:
            tend_sql = (
                "SELECT id FROM parcels WHERE steward_id=? AND crop IS NOT NULL AND tended=0"
            )
            if orchard_ctx:
                tend_sql += " AND COALESCE(orchard,0)=1"
            cur = await conn.execute(tend_sql, (s["id"],))
            rows = await cur.fetchall()
            hoe = await (await conn.execute(
                "SELECT quantity FROM satchel WHERE steward_id=? AND item='tool_hoe' AND quantity>0",
                (s["id"],),
            )).fetchone()
            from . import hut as hut_mod
            hut_b = await hut_mod.get_bonuses(conn, s["id"])
            iron_edge = hut_b.has("iron_edge")
            if iron_edge:
                tend_cut = 70
                worm_chance = 0.34
            elif hoe:
                tend_cut = 40
                worm_chance = 0.28
            else:
                tend_cut = 0
                worm_chance = 0.14
            for (pid,) in rows:
                await conn.execute("UPDATE parcels SET tended=1 WHERE id=?", (pid,))
                if tend_cut:
                    await conn.execute(
                        "UPDATE parcels SET grow_target=MAX(120, grow_target-?) WHERE id=? AND grow_target>0",
                        (tend_cut, pid),
                    )
                if world.current_weather() == "gale" and hut_b.gale_grow < 1:
                    cut = int(80 * (1 - hut_b.gale_grow))
                    await conn.execute(
                        "UPDATE parcels SET grow_target=MAX(120, grow_target-?) WHERE id=? AND grow_target>0",
                        (cut, pid),
                    )
            extra = await events.roll_after_action(s, "tend", conn)
            farm = await farming.roll_farm_event(conn, s, "tend")
            dove = None
            if rows:
                stalk_pid = random.choice(rows)[0]
                dove = await farming.maybe_gugu_dove_stalk(conn, s, stalk_pid)
            disc = await commons.roll_discovery(conn, s, "tend")
            gnat_msg = ""
            if rows and await events.gnat_swarm_revert_tend():
                cur_out = await conn.execute(
                    """
                    SELECT id FROM parcels
                    WHERE steward_id=? AND greenhouse=0 AND crop IS NOT NULL AND tended=1
                    """,
                    (s["id"],),
                )
                outdoor = [r[0] for r in await cur_out.fetchall()]
                if outdoor:
                    await conn.execute(
                        "UPDATE parcels SET tended=0 WHERE id=?",
                        (random.choice(outdoor),),
                    )
                    gnat_msg = "\n小虫过境，有一块露天作物又得再打理一遍"
            worm_msg = ""
            if random.random() < worm_chance:
                await db.add_item(conn, s["id"], "bait_worm", random.randint(1, 2))
                worm_msg = "\n翻出蚯蚓饵，钓鱼佬狂喜"
                if iron_edge:
                    worm_msg += "（铁锄刃加分）"
                elif hoe:
                    worm_msg += "（锄头加分）"
            from . import tale as tale_mod
            tale_extra = await tale_mod.check_action_progress(conn, s["id"], "plot")
            ill_note = await health.maybe_insomnia(conn, s["id"])
            await conn.commit()
        noun = "树位" if orchard_ctx else "份地"
        msg = f"打理了 {len(rows)} 块{noun}" if rows else f"没有待打理的{noun}——苗都乖，或你还没种"
        if iron_edge and rows:
            msg += " · 铁锄刃松土"
        elif hoe and rows:
            msg += " · 锄头松土"
        msg += flavor.maybe_suffix(flavor.TEND_SUFFIX)
        if dove:
            msg += f"\n{dove}"
        elif farm:
            msg += f"\n{farm}"
        if disc:
            msg += f"\n{disc}"
        if gnat_msg:
            msg += gnat_msg
        if worm_msg:
            msg += worm_msg
        if tale_extra:
            msg += f"\n\n{tale_extra}"
        if ill_note:
            msg += f"\n{ill_note}\n→ visit_ops clinic treat …（必须花票）"
        return f"{msg}\n{extra}" if extra else msg

    if verb == "shake" and len(parts) >= 2:
        from . import land as land_mod
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            plot = await _load_named_plot(
                conn, s["id"], parts[1], orchard_ctx=True, fallback_other=True
            )
            land_mod.assert_ready(plot)
            if not plot.get("crop"):
                raise ValueError(f"{land_mod.slot_label(plot)} 没有可摇的树")
            meta = CROPS.get(plot["crop"], {})
            if not meta.get("shake"):
                raise ValueError(f"{meta.get('name', plot['crop'])} 不能摇，只能 gather")
            result = await farming.shake_tree(conn, s["id"], plot)
            if not result:
                raise ValueError("还没熟，等等再摇")
            item, qty, tree_note = result
            await conn.commit()
        name = ITEM_NAMES.get(item, item)
        msg = f"{land_mod.slot_label(plot)} 摇下 {name} x{qty}" + flavor.maybe_suffix(["椰子：重力赞助", "树：今天也配合"])
        if tree_note:
            msg += f"\n{tree_note}"
        return msg

    if verb in ("water", "浇水", "浇"):
        from . import land as land_mod
        slot_token = parts[1] if len(parts) >= 2 else None
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            if slot_token:
                plots = [await _load_named_plot(conn, s["id"], slot_token, orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx)]
            else:
                water_sql = "SELECT * FROM parcels WHERE steward_id=? AND crop IS NOT NULL"
                if orchard_ctx:
                    water_sql += " AND COALESCE(orchard,0)=1"
                plots = [dict(r) for r in await (await conn.execute(
                    water_sql, (s["id"],),
                )).fetchall()]
            from . import config as cfg
            lines = []
            for plot in plots:
                land_mod.assert_ready(plot)
                label = land_mod.slot_label(plot)
                if not plot.get("crop"):
                    if slot_token:
                        raise ValueError(f"{label} 没种东西")
                    continue
                if farming.plot_ready(plot) or farming.plot_overripe(plot):
                    if slot_token:
                        raise ValueError(f"{label} 已经熟了，浇水赶不上了。gather 收")
                    continue
                if plot.get("watered"):
                    lines.append(f"{label} 已经浇过水")
                    continue
                new_target, saved = farming.apply_grow_cut(plot, cfg.WATER_CUT_RATE)
                await conn.execute(
                    "UPDATE parcels SET watered=1, grow_target=? WHERE id=?",
                    (new_target, plot["id"]),
                )
                plot["watered"] = 1
                plot["grow_target"] = new_target
                _, _, left = farming.grow_progress(plot)
                eta = farming.format_grow_eta(left) or "马上熟"
                if saved:
                    lines.append(
                        f"{label} 浇了水，成熟提前 {farming.format_grow_eta(saved)}"
                        f"（还需 {eta}）"
                    )
                else:
                    lines.append(f"{label} 浇了水，地更润，生长略快（还需 {eta}）")
            await conn.commit()
        if not lines:
            return "没有能浇的地——先 sow，或已经浇过/熟了"
        return "\n".join(lines)

    if verb in ("fertilize", "施肥"):
        from . import land as land_mod
        slot_token = None
        fert_token = "compost"
        rest = parts[1:]
        if rest:
            try:
                land_mod.parse_slot_ref(rest[0], orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx)
                slot_token = rest[0]
                fert_token = rest[1] if len(rest) > 1 else "compost"
            except ValueError:
                fert_token = rest[0]
        fert_item = resolve_item_key(fert_token) or fert_token
        from .catalog import MANURE
        if fert_item not in MANURE and fert_item != "compost":
            raise ValueError("施肥用堆肥或羊粪/猪粪/牛粪。例子：施肥 1 · 施肥 1 羊粪")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            if slot_token:
                plots = [await _load_named_plot(conn, s["id"], slot_token, orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx)]
            else:
                fert_sql = (
                    "SELECT * FROM parcels WHERE steward_id=? AND crop IS NOT NULL AND fertilized=0"
                )
                if orchard_ctx:
                    fert_sql += " AND COALESCE(orchard,0)=1"
                plots = [dict(r) for r in await (await conn.execute(
                    fert_sql, (s["id"],),
                )).fetchall()]
            lines = []
            mascot = s.get("mascot_trait") == "compost"
            for plot in plots:
                land_mod.assert_ready(plot)
                plabel = land_mod.slot_label(plot)
                if not plot.get("crop"):
                    if slot_token:
                        raise ValueError(f"{plabel} 没种东西")
                    continue
                if farming.plot_ready(plot) or farming.plot_overripe(plot):
                    if slot_token:
                        raise ValueError(f"{plabel} 已经熟了，肥料留给下一茬")
                    continue
                if plot.get("fertilized"):
                    lines.append(f"{plabel} 已经施过肥")
                    continue
                if not await db.take_item(conn, s["id"], fert_item, 1):
                    need = farming.fertilizer_label(fert_item)
                    if not lines:
                        raise ValueError(
                            f"施肥需要 {need} x1（forage / hut_ops 堆肥桶 存 粪便 可攒）"
                        )
                    lines.append(f"{need} 不够了，施到 {plabel} 前停手")
                    break
                rate = farming.fertilizer_cut_rate(fert_item, compost_mascot=mascot)
                new_target, saved = farming.apply_grow_cut(plot, rate)
                await conn.execute(
                    "UPDATE parcels SET fertilized=1, grow_target=? WHERE id=?",
                    (new_target, plot["id"]),
                )
                plot["fertilized"] = 1
                plot["grow_target"] = new_target
                _, _, left = farming.grow_progress(plot)
                eta = farming.format_grow_eta(left) or "马上熟"
                label = farming.fertilizer_label(fert_item)
                extra = " · 吉祥物堆肥加持" if mascot else ""
                if saved:
                    lines.append(
                        f"{plabel} 已施{label}，成熟提前 {farming.format_grow_eta(saved)}"
                        f"（还需 {eta}）{extra}"
                    )
                else:
                    lines.append(
                        f"{plabel} 已施{label}，生长略快（还需 {eta}）{extra}"
                    )
            await conn.commit()
        if not lines:
            return "没有能施肥的地——先 sow，或已经施过/熟了"
        return "\n".join(lines)

    if verb == "scarecrow" and len(parts) >= 2:
        from . import land as land_mod
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            plot = await _load_named_plot(conn, s["id"], parts[1], orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx)
            land_mod.assert_ready(plot)
            slot = plot["slot"]
            if plot.get("scarecrow"):
                return f"{land_mod.slot_label(plot)} 已有稻草人"
            if await db.take_item(conn, s["id"], "scarecrow", 1):
                pass
            else:
                from .config import SCARECROW_COST
                for item, need in SCARECROW_COST.items():
                    if not await db.take_item(conn, s["id"], item, need):
                        raise ValueError(f"扎稻草人需要 scarecrow 或 漂绳x2+堆肥x1")
            await conn.execute("UPDATE parcels SET scarecrow=1 WHERE id=?", (plot["id"],))
            await conn.commit()
        return f"{land_mod.slot_label(plot)} 扎好稻草人，鸟儿的自助餐厅关门"

    if verb == "compost" and len(parts) >= 2:
        from . import land as land_mod
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            plot = await _load_named_plot(
                conn, s["id"], parts[1], orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx, fallback_other=True
            )
            slot = land_mod.slot_label(plot)
            land_mod.assert_ready(plot)
            if not plot.get("crop"):
                raise ValueError(f"{slot} 空着")
            meta = CROPS.get(plot["crop"], {"name": plot["crop"]})
            overripe = farming.plot_overripe(plot)
            ready = farming.plot_ready(plot)
            if meta.get("tree") and not overripe:
                raise ValueError(
                    f"{slot} {meta['name']}树还没过熟。树收完会再长，不想要了才 `plot_ops chop {slot}`；"
                    "过熟清果用 gather 或 compost，树会留下。"
                )
            if not overripe and not ready:
                raise ValueError("只有过熟/枯的才进堆肥桶")
            crop_name = meta["name"]
            compost_qty = random.randint(2, 3)
            await db.add_item(conn, s["id"], "compost", compost_qty)
            if meta.get("tree"):
                planted_at, grow_target, grow_pace = farming.regrow_tree_after_clear(
                    plot["crop"], plot
                )
                await conn.execute(
                    """
                    UPDATE parcels SET planted_at=?, tended=0, grow_target=?, grow_pace=?,
                    fertilized=0, watered=0, harvest_left=0 WHERE id=?
                    """,
                    (planted_at, grow_target, grow_pace, plot["id"]),
                )
                await conn.commit()
                return (
                    f"{slot} {crop_name}过熟落果 → 堆肥桶 ×{compost_qty}，"
                    "树还在，重新结果"
                )
            await conn.execute(
                """
                UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                grow_target=0, grow_pace='', fertilized=0, watered=0, harvest_left=0 WHERE id=?
                """,
                (plot["id"],),
            )
            await conn.commit()
        return f"{slot} {crop_name} → 堆肥桶，土肥了"

    if verb == "chop" and len(parts) >= 2:
        from . import land as land_mod
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            plot = await _load_named_plot(
                conn, s["id"], parts[1], orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx, fallback_other=True
            )
            slot = land_mod.slot_label(plot)
            land_mod.assert_ready(plot)
            result = farming.chop_tree(plot)
            if not result["ok"]:
                raise ValueError(f"{slot} {result['msg']}")
            loot_txt = []
            for iid, n in result["loot"]:
                await db.add_item(conn, s["id"], iid, n)
                loot_txt.append(f"{ITEM_NAMES.get(iid, iid)}×{n}")
            await conn.execute(
                """
                UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                grow_target=0, grow_pace='', fertilized=0, watered=0, harvest_left=0 WHERE id=?
                """,
                (plot["id"],),
            )
            extra = await events.roll_after_action(s, "gather", conn)
            farm = await farming.roll_farm_event(conn, s, "gather")
            await db.add_chronicle(
                "chop", f"{s['name']} 砍倒 {slot} {result['name']}树", s["id"], conn=conn
            )
            await conn.commit()
        loot_s = "、".join(loot_txt)
        msg = (
            f"{slot} 砍倒{result['name']}树，地空了。{result['note']} 捡到 {loot_s}。"
            + flavor.maybe_suffix(flavor.CHOP_SUFFIX)
        )
        if farm:
            msg += f"\n{farm}"
        if extra:
            msg += f"\n{extra}"
        return msg

    if verb == "chop":
        raise ValueError("用法: plot_ops chop 地块或园1")

    if verb == "gather":
        from . import land as land_mod
        slot_token = parts[1] if len(parts) >= 2 else None
        got = []
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            gather_sql = "SELECT * FROM parcels WHERE steward_id=?"
            if orchard_ctx and not slot_token:
                gather_sql += " AND COALESCE(orchard,0)=1"
            parcels = [dict(r) for r in await (await conn.execute(
                gather_sql, (s["id"],)
            )).fetchall()]
            if slot_token:
                target = await _load_named_plot(
                    conn, s["id"], slot_token, orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx, fallback_other=True
                )
                parcels = [p for p in parcels if p.get("id") == target["id"]]
                if not parcels:
                    raise ValueError(land_mod.missing_slot_msg(
                        *land_mod.parse_slot_ref(slot_token, orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx)
                    ))
                land_mod.assert_ready(parcels[0])
            for p in parcels:
                if farming.plot_ready(p):
                    if await events.gather_blight_loss(conn, s["id"], p["crop"]):
                        crop_name = CROPS[p["crop"]]["name"]
                        await conn.execute(
                            """
                            UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                            grow_target=0, grow_pace='', fertilized=0, watered=0, harvest_left=0 WHERE id=?
                            """,
                            (p["id"],),
                        )
                        got.append(f"{crop_name}(枯病折损)")
                        continue
                    mult = float(p.get("dove_yield_mult") or 1.0)
                    dove_note = "" if mult == 1.0 else f"(斑鸠收成×{mult:g})"
                    item_key, qty, keep_plot = await farming.gather_yield(conn, s["id"], p)
                    if qty <= 0:
                        crop_name = CROPS[p["crop"]]["name"]
                        got.append(f"{crop_name}(斑鸠啄食，颗粒无收)")
                        if not keep_plot:
                            await conn.execute(
                                """
                                UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                                grow_target=0, grow_pace='', fertilized=0, watered=0, scarecrow=0,
                                dove_yield_mult=1.0, harvest_left=0 WHERE id=?
                                """,
                                (p["id"],),
                            )
                        continue
                    await db.add_item(conn, s["id"], item_key, qty)
                    harvest_note = ""
                    from . import shaonian as shaonian_mod
                    if await shaonian_mod.harvest_bonus_roll(conn, s["id"]):
                        await db.add_item(conn, s["id"], item_key, qty)
                        harvest_note = f"(丰收卦+{qty})"
                    if keep_plot:
                        keep_plot, tree_note = await farming.record_tree_harvest(conn, p)
                        if keep_plot:
                            grow_target, grow_pace, _ = farming.roll_grow(p["crop"], p)
                            await conn.execute(
                                """
                                UPDATE parcels SET planted_at=?, tended=0, grow_target=?, grow_pace=?,
                                fertilized=0, watered=0, harvest_left=0 WHERE id=?
                                """,
                                (db.now(), grow_target, grow_pace, p["id"]),
                            )
                            tev = await farming.roll_tree_event(conn, s["id"], p)
                            if tev:
                                tree_note = f"{tree_note}\n{tev}" if tree_note else tev
                    else:
                        tree_note = ""
                        await conn.execute(
                            """
                            UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                            grow_target=0, grow_pace='', fertilized=0, watered=0, scarecrow=0, harvest_left=0,
                            tree_harvests=0, tree_harvest_max=0 WHERE id=?
                            """,
                            (p["id"],),
                        )
                    if item_key.startswith("seed_"):
                        got.append(
                            f"{CROPS[p['crop']]['name']}种(过熟) x{qty}{harvest_note}{tree_note}"
                        )
                    else:
                        got.append(
                            f"{CROPS[p['crop']]['name']} x{qty}{harvest_note}{dove_note}{tree_note}"
                        )
                elif farming.plot_overripe(p):
                    meta = CROPS.get(p["crop"], {})
                    is_tree = bool(meta.get("tree"))
                    if random.random() < 0.5:
                        await db.add_item(conn, s["id"], "compost", 2)
                        got.append(f"{CROPS[p['crop']]['name']}(堆肥)")
                    if is_tree:
                        keep_tree, th_note = await farming.record_tree_harvest(conn, p)
                        if keep_tree:
                            planted_at, grow_target, grow_pace = farming.regrow_tree_after_clear(
                                p["crop"], p
                            )
                            await conn.execute(
                                """
                                UPDATE parcels SET planted_at=?, tended=0, grow_target=?, grow_pace=?,
                                fertilized=0, watered=0, harvest_left=0 WHERE id=?
                                """,
                                (planted_at, grow_target, grow_pace, p["id"]),
                            )
                            got.append(f"{meta['name']}树（过熟清果，重新结果）{th_note}")
                        else:
                            got.append(f"{meta['name']}树{th_note}")
                    else:
                        await conn.execute(
                            """
                            UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                            grow_target=0, grow_pace='', fertilized=0, watered=0, harvest_left=0 WHERE id=?
                            """,
                            (p["id"],),
                        )
            extra = await events.roll_after_action(s, "gather", conn)
            farm = await farming.roll_farm_event(conn, s, "gather")
            found: list[tuple[str, int, str]] = []
            disc = await commons.roll_discovery(conn, s, "gather", found=found)
            for item, qty, iname in found:
                got.append(f"{iname} x{qty}（发现 · {item}）")
            if got:
                await survival.bump(conn, s["id"], satiety=min(6, 2 + len(got)))
            ill_note = await health.maybe_insomnia(conn, s["id"])
            from . import tale as tale_mod
            tale_extra = await tale_mod.check_action_progress(conn, s["id"], "plot")
            await conn.commit()
        if not got:
            nearest = None
            min_left = None
            for p in parcels:
                if p.get("crop") and not farming.plot_ready(p) and not farming.plot_overripe(p):
                    _, _, left = farming.grow_progress(p)
                    if min_left is None or left < min_left:
                        min_left = left
                        nearest = p
            wait_hint = (
                "\n等待期间可做: tend · 浇水 · 施肥 地块 · forage · tide_ops net|cast · "
                "tide_ops beach scan · kitchen_ops eat · visit_ops clinic"
            )
            msg = "没有可收成的作物"
            if slot_token is not None and parcels:
                p = parcels[0]
                plabel = land_mod.slot_label(p)
                if not p.get("crop"):
                    msg = f"{plabel} 休耕，无可收"
                elif not farming.plot_ready(p) and not farming.plot_overripe(p):
                    cname = CROPS[p["crop"]]["name"]
                    _, _, left = farming.grow_progress(p)
                    msg = f"{plabel} {cname} 还需 {farming.format_grow_eta(left)}{wait_hint}"
                else:
                    msg = f"{plabel} 暂无可收（plot_ops status 查看详情）"
            elif nearest is not None and min_left is not None:
                cname = CROPS[nearest["crop"]]["name"]
                msg += f"（{land_mod.slot_label(nearest)} {cname} 还需 {farming.format_grow_eta(min_left)}）{wait_hint}"
            if tale_extra:
                msg += f"\n\n{tale_extra}"
            return f"{msg}\n{extra}" if extra else msg
        await db.add_chronicle("gather", f"{s['name']} 收成 {', '.join(got)}", s["id"])
        from . import multi
        bonus_msg = None
        for crop_name in got:
            if "发现" in crop_name or "枯病" in crop_name or "堆肥" in crop_name:
                continue
            crop_key = next(
                (k for k, v in CROPS.items() if crop_name.startswith(v["name"])),
                None,
            )
            if crop_key:
                b = await multi.on_league_item(s["id"], f"crop_{crop_key}", 1)
                if b:
                    bonus_msg = b
        if bonus_msg:
            await db.add_chronicle("league", bonus_msg, None)
            base = f"收成: {', '.join(got)}\n{bonus_msg}"
            if farm:
                base += f"\n{farm}"
            if disc:
                base += f"\n{disc}"
            if tale_extra:
                base += f"\n\n{tale_extra}"
            if ill_note:
                base += f"\n{ill_note}\n→ visit_ops clinic treat …（必须花票）"
            return f"{base}\n{extra}" if extra else base
        base = f"收成: {', '.join(got)}"
        base += flavor.maybe_suffix(flavor.GATHER_SUFFIX)
        if farm:
            base += f"\n{farm}"
        if disc:
            base += f"\n{disc}"
        if tale_extra:
            base += f"\n\n{tale_extra}"
        if ill_note:
            base += f"\n{ill_note}\n→ visit_ops clinic treat …（必须花票）"
        return f"{base}\n{extra}" if extra else base

    if verb == "forage":
        today = db.day_id()
        last = db.day_id(s["forage_at"]) if s["forage_at"] else 0
        if today <= last:
            raise ValueError("今日已在边际采过，明天再来")
        roll = random.choices(FORAGE_LOOT, weights=[x[3] for x in FORAGE_LOOT])[0]
        item_id, label, qty, _ = roll
        async with db.connect() as conn:
            await db.add_item(conn, s["id"], item_id, qty)
            await conn.execute("UPDATE stewards SET forage_at=? WHERE id=?", (db.now(), s["id"]))
            await survival.bump(conn, s["id"], satiety=4)
            extra = await events.roll_after_action(s, "forage", conn)
            disc = await commons.roll_discovery(conn, s, "forage")
            from . import tale as tale_mod
            tale_extra = await tale_mod.check_action_progress(conn, s["id"], "plot")
            await conn.commit()
        await db.add_chronicle("forage", f"{s['name']} 在份地边际采到 {label}", s["id"])
        msg = f"边际采集：{label} x{qty}"
        msg += flavor.maybe_suffix(flavor.FORAGE_SUFFIX)
        if disc:
            msg += f"\n{disc}"
        if tale_extra:
            msg += f"\n\n{tale_extra}"
        return f"{msg}\n{extra}" if extra else msg

    if verb == "post" and len(parts) >= 3:
        peer, text = parts[1], " ".join(parts[2:])
        target = await db.get_steward_by_name(peer)
        if not target:
            raise ValueError("找不到该管理员")
        async with db.connect() as conn:
            await conn.execute(
                "INSERT INTO beacons (author_id, tag, body, created_at) VALUES (?, 'notice', ?, ?)",
                (s["id"], f"@{peer}: {text[:180]}", db.now()),
            )
            await conn.commit()
        return f"已在公告栏 @ {peer}"

    if verb in ("scrump", "偷菜", "逾篱"):
        if len(parts) < 2:
            from . import multi as multi_mod
            roster = await multi_mod.list_neighbors(s, online_only=False)
            raise ValueError("用法: plot_ops 偷菜 名字 [地块]\n" + roster)
        slot_token = parts[2] if len(parts) >= 3 else None
        return await events.manual_scrump(s, parts[1], slot_token)

    if verb == "hedge_note":
        if len(parts) < 3:
            raise ValueError("用法: plot_ops hedge_note 管理员名 篱笆条正文")
        peer, text = parts[1], " ".join(parts[2:])
        target = await db.get_steward_by_name(peer)
        if not target:
            raise ValueError("找不到该管理员")
        async with db.connect() as conn:
            await conn.execute(
                "INSERT INTO beacons (author_id, tag, body, created_at) VALUES (?, 'hedge', ?, ?)",
                (s["id"], f"@{peer} 篱笆条：{text[:160]}", db.now()),
            )
            await conn.commit()
        from . import lore as lore_mod
        hint = lore_mod.hedge_note_hint()
        return f"篱笆条已留给 {peer}\n（篱间文学灵感：「{hint}」· lore_ops hedge 换一条）"

    if verb == "amends" and len(parts) >= 2:
        peer = await db.get_steward_by_name(parts[1])
        if not peer:
            raise ValueError("找不到该管理员")
        async with db.connect() as conn:
            await survival.bump(conn, s["id"], standing=10, mist_wit=3)
            await survival.bump(conn, peer["id"], standing=3)
            await conn.commit()
        msg = f"{s['name']} 向 {peer['name']} 为逾篱之事致歉"
        msg += f" — {flavor.pick(flavor.AMENDS_QUIPS)}"
        await db.add_chronicle("amends", msg, s["id"], peer["id"])
        await db.add_chronicle(
            "notice",
            f"{s['name']} 向你致歉（逾篱），你的档信回暖 +3",
            peer["id"],
            s["id"],
        )
        return msg + f"\n{peer['name']} 已收到通知（档信 +3）"

    raise ValueError(
        f"未知 plot 指令: {cmd}。常用: status · sow 1 甘蓝 · tend · 浇水 1 · 施肥 1 · gather 1"
    )


async def tide_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    pulse = await events.maybe_world_pulse(s)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "status"
    tide = world.current_tide()

    if verb == "status":
        stock = await db.get_satchel(s["id"])
        sea = {k: v for k, v in stock.items() if k.startswith("fish_")}
        msg = f"潮汐 {world.tide_label(tide)}\n" + (
            "\n".join(f"{ITEM_NAMES.get(k,k)} x{v}" for k, v in sea.items()) or "暂无渔获"
        )
        return f"{pulse}\n{msg}" if pulse else msg

    if verb == "catalog":
        from . import catches as catches_mod
        async with db.connect() as conn:
            return await catches_mod.fish_catalog(conn, s["id"])

    if verb == "net":
        cost = 4
        async with db.connect() as conn:
            await commons.maybe_spawn_commons(conn, steward_id=s["id"])
            from . import energy as energy_mod, gear
            energy_cost, catch_bonus, rarity_bonus, empty_reduce = await energy_mod.net_energy_cost(conn, s["id"])
            stats = await gear.get_stats(conn, s["id"])
            if stats["net"]["tier"] < 1:
                raise ValueError("先 tide_ops gear upgrade net 升到 T1 粗渔网（或 tide_ops tool buy net_basic 兼容）")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"撒网需要 {cost} 工分票")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
            await energy_mod.spend(conn, s["id"], energy_cost, action="撒网")
            extra = await events.roll_after_action(s, "net", conn)
            disc = await commons.roll_discovery(conn, s, "net")
            from . import shaonian as shaonian_mod
            daily = await shaonian_mod.get_daily(conn, s["id"])
            fortune_key = daily.get("fortune") or ""
            no_empty = await shaonian_mod.fishing_no_empty(conn, s["id"])
            from . import craft as craft_mod
            net_patch = await craft_mod.active_net_patch(conn, s["id"])
            await conn.commit()
        empty_chance = (
            0.18 - await events.net_bonus_chance() - empty_reduce - catch_bonus * 0.4
            + await events.net_fog_penalty() - net_patch
        )
        if not no_empty and random.random() < max(0.04, empty_chance):
            msg = f"空网 T{stats['net']['tier']}，只有水草"
            if extra:
                msg += f"\n{extra}"
            if disc:
                msg += f"\n{disc}"
            return f"{pulse}\n{msg}" if pulse else msg
        rarity_cap = 3 + rarity_bonus
        catch = shaonian_mod.pick_fish_with_fortune(tide, rarity_cap, fortune_key)
        if catch_bonus and random.random() < catch_bonus:
            catch = shaonian_mod.pick_fish_with_fortune(tide, min(6, rarity_cap + 1), fortune_key)
        meta = SEA_CATCH[catch]
        val_mult, tier_bonus = gear.fish_catch_payout(stats, mode="net")
        gear_bonus = int(meta["sell"] * max(0.0, val_mult - 1.0)) + tier_bonus
        async with db.connect() as conn:
            await db.add_item(conn, s["id"], f"fish_{catch}", 1)
            if gear_bonus > 0:
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                    (gear_bonus, s["id"]),
                )
            from . import catches as catches_mod
            await catches_mod.record_catch(conn, s["id"], f"fish_{catch}")
            await survival.bump(conn, s["id"], satiety=5)
            from . import marine as marine_mod
            voyage = await marine_mod._get_voyage(conn, s["id"])
            if voyage and voyage.get("status") == "sailing":
                await marine_mod.append_voyage_fish(conn, voyage, f"fish_{catch}")
            # 未命名小鱼不能网：撒网不触发遭遇，渔获池也排除 walkblue
            from . import tale as tale_mod
            await tale_mod.check_item_progress(conn, s["id"], f"fish_{catch}", 1)
            tale_extra = await tale_mod.check_action_progress(conn, s["id"], "sea")
            await conn.commit()
        msg = (
            f"{s['name']} 在{world.tide_label(tide)}网到 {meta['emoji']}{meta['name']} "
            f"[网T{stats['net']['tier']}]"
        )
        if gear_bonus > 0:
            msg += f" 渔具加成+{gear_bonus}票"
        msg += flavor.maybe_suffix(flavor.NET_SUFFIX)
        await db.add_chronicle("tide", msg, s["id"])
        from . import multi
        bonus = await multi.on_league_item(s["id"], f"fish_{catch}", 1)
        if bonus:
            await db.add_chronicle("league", bonus, None)
            msg = msg + f"\n{bonus}"
        if extra:
            msg += f"\n{extra}"
        if disc:
            msg += f"\n{disc}"
        if tale_extra:
            msg += f"\n\n{tale_extra}"
        return f"{pulse}\n{msg}" if pulse else msg

    if verb == "cast":
        cost = 3
        async with db.connect() as conn:
            from . import energy as energy_mod, gear
            stats = await gear.get_stats(conn, s["id"])
            rod, bait = stats["rod"], stats["bait"]
            if rod["tier"] < 1:
                raise ValueError("先 tide_ops gear upgrade rod（T1 竹钓竿 30票）")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"坐钓需要 {cost} 工分票")
            if not await db.take_item(conn, s["id"], "bait_worm", 1):
                raise ValueError("缺少蚯蚓饵 bait_worm（tend 地块 / tide_ops dig 获取）")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
            await energy_mod.spend(conn, s["id"], rod["energy"], action="坐钓")
            extra = await events.roll_after_action(s, "net", conn)
            disc = await commons.roll_discovery(conn, s, "net")
            from . import shaonian as shaonian_mod
            daily = await shaonian_mod.get_daily(conn, s["id"])
            fortune_key = daily.get("fortune") or ""
            no_empty = await shaonian_mod.fishing_no_empty(conn, s["id"])
            await conn.commit()
        catch_b, rarity_b, empty_b, _ = gear.combined_fish_bonus(bait=bait, rod=rod)
        empty_chance = 0.24 - empty_b - await events.net_bonus_chance() + await events.net_fog_penalty()
        if not no_empty and random.random() < max(0.05, empty_chance):
            msg = f"空杆 饵T{bait['tier']} 竿T{rod['tier']}——鱼看了直摇头"
            parts = [x for x in (pulse, msg, extra) if x]
            return "\n".join(parts)
        rarity_cap = 3 + rarity_b
        catch = shaonian_mod.pick_fish_with_fortune(
            tide, rarity_cap, fortune_key, allow_cast_only=True
        )
        if catch_b and random.random() < catch_b + 0.08:
            catch = shaonian_mod.pick_fish_with_fortune(
                tide, min(6, rarity_cap + 1), fortune_key, allow_cast_only=True
            )
        meta = SEA_CATCH[catch]
        val_mult, tier_bonus = gear.fish_catch_payout(stats, mode="cast")
        gear_bonus = int(meta["sell"] * max(0.0, val_mult - 1.0)) + tier_bonus
        async with db.connect() as conn:
            await db.add_item(conn, s["id"], f"fish_{catch}", 1)
            if gear_bonus > 0:
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                    (gear_bonus, s["id"]),
                )
            from . import catches as catches_mod
            await catches_mod.record_catch(conn, s["id"], f"fish_{catch}")
            await survival.bump(conn, s["id"], satiety=4)
            from . import marine as marine_mod
            voyage = await marine_mod._get_voyage(conn, s["id"])
            legged = None
            curse_line = None
            if catch == "walkblue":
                curse_line = await marine_mod.on_obtain_walkblue(conn, s["id"])
            if voyage and voyage.get("status") == "sailing":
                await marine_mod.append_voyage_fish(conn, voyage, f"fish_{catch}")
                if catch != "walkblue":
                    legged = await marine_mod.try_legged_fish_encounter(conn, s, voyage)
            from . import tale as tale_mod
            await tale_mod.check_item_progress(conn, s["id"], f"fish_{catch}", 1)
            tale_extra = await tale_mod.check_action_progress(conn, s["id"], "sea")
            await conn.commit()
        msg = (
            f"坐钓 {meta['emoji']}{meta['name']} "
            f"[饵T{bait['tier']} 竿T{rod['tier']}]"
        )
        if gear_bonus > 0:
            msg += f" 渔具加成+{gear_bonus}票"
        msg += flavor.maybe_suffix(["竿弯了，票没白花", "饵对路，鱼自来"])
        await db.add_chronicle("tide", f"{s['name']} 坐钓 {meta['name']}", s["id"])
        if extra:
            msg += f"\n{extra}"
        if disc:
            msg += f"\n{disc}"
        if curse_line:
            msg += f"\n{curse_line}"
        if legged:
            msg += f"\n{legged}"
        if tale_extra:
            msg += f"\n\n{tale_extra}"
        return f"{pulse}\n{msg}" if pulse else msg

    if verb == "bottle":
        from . import bottles
        return await bottles.bottle_ops(key_id, "fish")

    raise ValueError(f"未知 tide 指令: {command}")


async def _collect_bottle_replies(conn: aiosqlite.Connection, steward_id: int) -> list[str]:
    prev = conn.row_factory
    conn.row_factory = aiosqlite.Row
    try:
        rows = await (await conn.execute(
            """
            SELECT b.id, b.reply_body, r.name AS from_name
            FROM drift_bottles b
            JOIN stewards r ON r.id=b.reply_by
            WHERE b.author_id=? AND b.reply_at IS NOT NULL
            ORDER BY b.reply_at DESC LIMIT 3
            """,
            (steward_id,),
        )).fetchall()
    finally:
        conn.row_factory = prev
    return [
        f"漂流瓶 #{r['id']} 有回瓶：{r['from_name']} — {r['reply_body'][:60]}"
        for r in rows
    ]


async def _collect_handoffs(conn: aiosqlite.Connection, steward_id: int) -> list[str]:
    """台阶上的离线交接进袋，并标已取。"""
    prev = conn.row_factory
    conn.row_factory = aiosqlite.Row
    try:
        rows = await (await conn.execute(
            """
            SELECT h.id, h.item, h.quantity, p.name AS from_name
            FROM handoffs h JOIN stewards p ON p.id=h.from_id
            WHERE h.to_id=? AND h.picked_up=0
            ORDER BY h.created_at
            """,
            (steward_id,),
        )).fetchall()
    finally:
        conn.row_factory = prev
    notes = []
    for r in rows:
        await db.add_item(conn, steward_id, r["item"], r["quantity"])
        await conn.execute("UPDATE handoffs SET picked_up=1 WHERE id=?", (r["id"],))
        label = ITEM_NAMES.get(r["item"], r["item"])
        notes.append(f"台阶交接：{r['from_name']} 放下的 {label} x{r['quantity']} 已入袋")
    return notes


async def shed_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    chunks = [c.strip() for c in command.split(";") if c.strip()]
    return "\n".join([await _shed_one(s, c) for c in chunks])


async def _shed_one(s: dict, cmd: str) -> str:
    parts = cmd.split()
    verb = parts[0].lower()

    if verb == "status":
        from . import land as land_mod
        parcels = await db.get_parcels(s["id"], greenhouse=1)
        text = await land_mod.status_text(s, parcels, greenhouse=True)
        async with db.connect() as conn:
            notes = await _collect_handoffs(conn, s["id"])
            await conn.commit()
        if notes:
            return text + "\n" + "\n".join(notes)
        return text

    if verb in ("erect", "确认", "buy", "买", "扩", "ok", "yes"):
        from . import land as land_mod
        async with db.connect() as conn:
            msg = await land_mod.buy(conn, s, greenhouse=True)
            await db.add_chronicle(
                "shed",
                f"{s['name']} 买棚至 {s.get('greenhouse_count')} 座",
                s["id"],
                conn=conn,
            )
            await conn.commit()
        return msg

    if verb == "label" and len(parts) >= 2:
        if not s["greenhouse"]:
            raise ValueError("先 erect 温室")
        label = " ".join(parts[1:])[:40]
        async with db.connect() as conn:
            await conn.execute("UPDATE stewards SET greenhouse_label=? WHERE id=?", (label, s["id"]))
            await conn.commit()
        return f"温室命名为「{label}」"

    if verb == "visit" and len(parts) >= 2:
        peer = await db.get_steward_by_name(parts[1])
        if not peer:
            raise ValueError("找不到管理员")
        online = db.now() - peer["last_active_at"] <= 900
        gh = peer["greenhouse_label"] or "无名温室"
        return f"拜访 {peer['name']}：{gh}（{'在档口' if online else '不在'}）"

    if verb == "handoff":
        m = re.match(r"handoff\s+(\S+)\s+(\S+)\s+(\d+)$", cmd, re.I)
        if not m:
            raise ValueError("用法: handoff 名字 物品 数量")
        peer_name, item, qty_s = m.group(1), m.group(2), m.group(3)
        qty = int(qty_s)
        peer = await db.get_steward_by_name(peer_name)
        if not peer:
            raise ValueError("找不到管理员")
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], item, qty):
                raise ValueError("行囊数量不足")
            online = db.now() - peer["last_active_at"] <= 900
            if online:
                await db.add_item(conn, peer["id"], item, qty)
                await conn.commit()
                msg = f"{s['name']} 当面交给 {peer['name']} {ITEM_NAMES.get(item,item)} x{qty}"
                await db.add_chronicle("handoff", msg, s["id"], peer["id"])
                return msg
            await conn.execute(
                "INSERT INTO handoffs (from_id, to_id, item, quantity, created_at) VALUES (?,?,?,?,?)",
                (s["id"], peer["id"], item, qty, db.now()),
            )
            await conn.commit()
        return f"已把 {ITEM_NAMES.get(item,item)} x{qty} 放在 {peer_name} 温室台阶（对方 steward_ops sheet / plot_ops shed status 时入袋）"

    raise ValueError(f"未知 shed 指令: {cmd}")


async def mascot_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        if not s["mascot_name"]:
            return "尚无吉祥物，adopt 名字 特质(scout/lucky/compost)"
        from . import social as social_mod
        hint = social_mod.mascot_spirit_hint(s["mascot_spirit"])
        base = f"{s['mascot_name']} [{s['mascot_trait']}] 士气 {s['mascot_spirit']}/100"
        mult = social_mod.mascot_trait_mult(s["mascot_spirit"])
        if mult != 1.0:
            base += f" · 特质效果 ×{mult:.2f}"
        if hint:
            base += f"\n{hint}"
        return base

    if verb == "adopt" and len(parts) >= 3:
        name, trait = parts[1][:20], parts[2][:16]
        if trait not in ("scout", "lucky", "compost"):
            raise ValueError("特质必须是 scout / lucky / compost")
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET mascot_name=?, mascot_trait=?, mascot_spirit=70 WHERE id=?",
                (name, trait, s["id"]),
            )
            await conn.commit()
        await db.add_chronicle("mascot", f"{s['name']} 认领吉祥物 {name}", s["id"])
        return f"吉祥物 {name} 入驻（{trait}）"

    if verb == "upkeep":
        if not s["mascot_name"]:
            raise ValueError("还没有吉祥物")
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < 4:
                raise ValueError("upkeep 需要 4 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-4, mascot_spirit=MIN(100, mascot_spirit+12) WHERE id=?",
                (s["id"],),
            )
            await conn.commit()
        return f"{s['mascot_name']} 士气上升"

    if verb == "feed":
        if not s["mascot_name"]:
            raise ValueError("还没有吉祥物")
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], "feed_pet", 1):
                raise ValueError("需要宠物饲料 — visit_ops tt buy 宠物饲料")
            await conn.execute(
                "UPDATE stewards SET mascot_spirit=MIN(100, mascot_spirit+18) WHERE id=?",
                (s["id"],),
            )
            await conn.commit()
        return f"{s['mascot_name']} 吃了宠物饲料，士气上升"

    if verb == "train":
        if not s["mascot_name"]:
            raise ValueError("还没有吉祥物")
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET mascot_spirit=MIN(100, mascot_spirit+8) WHERE id=?",
                (s["id"],),
            )
            await conn.commit()
        return f"训练了 {s['mascot_name']} 的 {s['mascot_trait']} 特质"

    raise ValueError(f"未知 mascot 指令: {command}（status/adopt/upkeep/feed/train）")


async def beacon_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "scan"

    if verb == "scan":
        tag = parts[1] if len(parts) > 1 else None
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            if tag and tag.isdigit():
                row = await (await conn.execute(
                    """
                    SELECT b.id, b.tag, b.body, a.name FROM beacons b
                    JOIN stewards a ON a.id=b.author_id WHERE b.id=?
                    """,
                    (int(tag),),
                )).fetchone()
                if not row:
                    raise ValueError("没有这条公告")
                replies = await (await conn.execute(
                    """
                    SELECT r.body, a.name FROM beacon_replies r
                    JOIN stewards a ON a.id=r.author_id
                    WHERE r.beacon_id=? ORDER BY r.created_at
                    """,
                    (row["id"],),
                )).fetchall()
                lines = [f"#{row['id']} [{row['tag']}] {row['name']}: {row['body']}"]
                if replies:
                    lines.append("回复:")
                    lines.extend(f"  · {r['name']}: {r['body']}" for r in replies)
                else:
                    lines.append("还没有回复 — respond 编号 正文")
                return "\n".join(lines)
            if tag:
                rows = await (await conn.execute(
                    "SELECT b.id, b.tag, b.body, a.name FROM beacons b JOIN stewards a ON a.id=b.author_id WHERE b.tag=? ORDER BY b.created_at DESC LIMIT 12",
                    (tag,),
                )).fetchall()
            else:
                rows = await (await conn.execute(
                    "SELECT b.id, b.tag, b.body, a.name FROM beacons b JOIN stewards a ON a.id=b.author_id ORDER BY b.created_at DESC LIMIT 12"
                )).fetchall()
            if not rows:
                return "公告栏暂无帖子"
            lines = []
            for r in rows:
                n = (await (await conn.execute(
                    "SELECT COUNT(*) FROM beacon_replies WHERE beacon_id=?", (r["id"],)
                )).fetchone())[0]
                tail = f" ↩{n}" if n else ""
                lines.append(f"#{r['id']} [{r['tag']}] {r['name']}: {r['body'][:80]}{tail}")
            lines.append("scan 编号 看回复 · respond 编号 正文")
            return "\n".join(lines)

    if verb == "post" and len(parts) >= 3:
        tag, body = parts[1][:20], parts[2][:220]
        async with db.connect() as conn:
            await conn.execute(
                "INSERT INTO beacons (author_id, tag, body, created_at) VALUES (?,?,?,?)",
                (s["id"], tag, body, db.now()),
            )
            await conn.commit()
        return f"公告已发布 [{tag}]"

    if verb == "respond" and len(parts) >= 3:
        bid, body = int(parts[1]), parts[2][:200]
        async with db.connect() as conn:
            await conn.execute(
                "INSERT INTO beacon_replies (beacon_id, author_id, body, created_at) VALUES (?,?,?,?)",
                (bid, s["id"], body, db.now()),
            )
            await conn.commit()
        return "已回复公告"

    raise ValueError(f"未知 beacon 指令: {command}")


async def swap_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=3)
    verb = parts[0].lower() if parts else "list"

    if verb == "list":
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (await conn.execute(
                """
                SELECT l.id, l.item, l.quantity, l.note, d.name
                FROM swap_lots l JOIN stewards d ON d.id=l.depositor_id
                WHERE l.claimed_by IS NULL ORDER BY l.created_at DESC LIMIT 15
                """
            )).fetchall()
        if not rows:
            return "交换台为空"
        return "\n".join(
            f"#{r['id']} {r['name']} 出让 {ITEM_NAMES.get(r['item'],r['item'])} x{r['quantity']} {r['note']}"
            for r in rows
        )

    if verb == "offer" and len(parts) >= 3:
        item_key = resolve_item_key(parts[1])
        if not item_key:
            raise ValueError(unknown_item_message(parts[1]))
        qty = _parse_int(parts[2])
        note = parts[3] if len(parts) > 3 else ""
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], item_key, qty):
                raise ValueError(
                    f"行囊不足 {ITEM_NAMES.get(item_key, item_key)}（id: {item_key}）"
                )
            await conn.execute(
                "INSERT INTO swap_lots (depositor_id, item, quantity, note, created_at) VALUES (?,?,?,?,?)",
                (s["id"], item_key, qty, note[:80], db.now()),
            )
            await conn.commit()
        await db.add_chronicle(
            "swap",
            f"{s['name']} 在交换台挂单 {ITEM_NAMES.get(item_key, item_key)} x{qty}",
            s["id"],
        )
        return f"挂单成功 · {ITEM_NAMES.get(item_key, item_key)}（{item_key}）x{qty}"

    if verb == "claim" and len(parts) >= 2:
        from . import social as social_mod
        lot_id = _parse_int(parts[1], "挂单编号")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            lot = dict(await (await conn.execute(
                "SELECT * FROM swap_lots WHERE id=? AND claimed_by IS NULL", (lot_id,)
            )).fetchone() or {})
            if not lot:
                raise ValueError("该挂单不存在或已被领走")
            if lot["depositor_id"] == s["id"]:
                raise ValueError("不能领取自己的挂单")
            rapport = await social_mod.get_rapport(s["id"], lot["depositor_id"], conn=conn)
            claim_fee = social_mod.swap_claim_fee(rapport)
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < claim_fee:
                raise ValueError(f"领取需要 {claim_fee} 票")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (claim_fee, s["id"]))
            await db.add_item(conn, s["id"], lot["item"], lot["quantity"])
            await conn.execute("UPDATE swap_lots SET claimed_by=? WHERE id=?", (s["id"], lot_id))
            await conn.commit()
        fee_note = f"（协作度≥{social_mod.RAPPORT_SWAP_DISCOUNT} 手续费 {claim_fee} 票）" if claim_fee < SWAP_CLAIM_FEE else ""
        return f"领取 #{lot_id}（-{claim_fee} 票）{fee_note}"

    if verb == "cancel" and len(parts) >= 2:
        lot_id = _parse_int(parts[1], "挂单编号")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            lot = dict(await (await conn.execute(
                "SELECT * FROM swap_lots WHERE id=? AND depositor_id=? AND claimed_by IS NULL",
                (lot_id, s["id"]),
            )).fetchone() or {})
            if not lot:
                raise ValueError("找不到可撤回的挂单")
            await db.add_item(conn, s["id"], lot["item"], lot["quantity"])
            await conn.execute("DELETE FROM swap_lots WHERE id=?", (lot_id,))
            await conn.commit()
        return f"已撤回 #{lot_id}，物品退回行囊"

    raise ValueError(f"未知 swap 指令: {command}（list/offer/claim/cancel）")


async def _tote_one(s: dict, command: str) -> str:
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "list"
    if verb == "list":
        stock = await db.get_satchel(s["id"])
        lines = [f"工分票: {s['tickets']}", "行囊每种最多 24 份（和潮柜一样；工具/装件 1）"]
        for item, qty in stock.items():
            price = suggested_price(item) or ITEM_PRICES.get(item, 0)
            name = item_label(item)
            cap = item_stack_cap(item)
            stack = f"x{qty}/{cap}"
            if item.startswith("fit_") or item.startswith("deco_"):
                lines.append(f"  {name} {stack} · {item} · 卖掉走 hut_ops 卖掉")
            else:
                lines.append(f"  {name} {stack} · {item} · vend {price}/个")
        return "\n".join(lines) if stock else f"工分票: {s['tickets']}\n行囊空"
    if verb == "vend" and len(parts) >= 3:
        # 支持批量：vend item1 qty1 item2 qty2 ...（每对一个物品+数量）
        tokens = parts[1:]
        if len(tokens) % 2 != 0:
            raise ValueError("用法: vend 物品 数量 [物品 数量 ...]（物品和数量成对）")
        pairs = []
        for i in range(0, len(tokens), 2):
            item_key = resolve_item_key(tokens[i])
            if not item_key:
                raise ValueError(unknown_item_message(tokens[i]))
            qty = _parse_int(tokens[i + 1])
            price = suggested_price(item_key) or ITEM_PRICES.get(item_key, 0)
            if not price:
                raise ValueError(f"不可出售 {item_label(item_key)}（{item_key}）")
            if item_key.startswith("fit_") or item_key.startswith("deco_"):
                raise ValueError(
                    "旧家具按折旧卖：墙上的 hut_ops 卖掉 槽位 确认；"
                    "行囊里的 hut_ops 卖掉 装件名 确认"
                )
            pairs.append((item_key, qty, price))
        async with db.connect() as conn:
            results = []
            fate_notes: list[str] = []
            for item_key, qty, price in pairs:
                if not await db.take_item(conn, s["id"], item_key, qty):
                    raise ValueError(f"数量不足（需要 {item_key} x{qty}）")
                gain = price * qty
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets+? WHERE id=?", (gain, s["id"])
                )
                results.append((item_key, qty, gain))
                if item_key == "fish_walkblue":
                    from . import marine as marine_mod
                    fate_notes.append(
                        await marine_mod.walkblue_fate_event(
                            conn, s["id"], kind="sell", qty=qty, tickets=gain
                        )
                    )
            await conn.commit()
        if len(results) == 1:
            item_key, qty, gain = results[0]
            msg = f"出售 {ITEM_NAMES.get(item_key, item_key)}（{item_key}）x{qty}，+{gain} 票"
        else:
            total = sum(g for _, _, g in results)
            lines = [f"  {ITEM_NAMES.get(k, k)} x{q}，+{g} 票" for k, q, g in results]
            lines.append(f"合计 +{total} 票")
            msg = "批量出售：\n" + "\n".join(lines)
        if fate_notes:
            msg += "\n" + "\n".join(fate_notes)
        return msg
    if verb in ("gifts", "收礼", "收到的礼"):
        from . import multi as multi_mod
        limit = 20
        if len(parts) >= 2:
            limit = min(50, max(1, _parse_int(parts[1], "条数")))
        rows = await db.list_received_gifts(s["id"], limit)
        if not rows:
            return (
                "还没有人给你送礼或酒吧打赏。礼物即时进行囊或工分票，"
                "也可 tote_ops list / steward_ops sheet 核对。"
            )
        lines = [f"收礼/打赏记录（最近 {len(rows)} 条）："]
        for r in rows:
            who = r.get("actor_name") or "某人"
            ago = multi_mod._ago(int(r["created_at"]))
            tag = "打赏" if r.get("action") == "bar_tip" else "礼物"
            lines.append(f"  · [{tag}] {who}（{ago}）— {r['text']}")
        lines.append("礼物已即时到账；行囊 tote_ops list，票 steward_ops sheet。")
        return "\n".join(lines)
    if verb == "gift" and len(parts) >= 4:
        peer_name = parts[1]
        token = parts[2]
        qty = _parse_int(parts[3])
        if qty < 1:
            raise ValueError("送礼数量至少 1")
        note = " ".join(parts[4:])[:80] if len(parts) > 4 else ""
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            peer_row = await (await conn.execute(
                "SELECT * FROM stewards WHERE name = ? COLLATE NOCASE",
                (peer_name.strip(),),
            )).fetchone()
            if not peer_row:
                raise ValueError(f"找不到管理员「{peer_name}」")
            peer = dict(peer_row)
            if peer["id"] == s["id"]:
                raise ValueError("不能送礼给自己")
            from . import multi as multi_mod
            token_l = token.lower()
            if token_l in ("tickets", "票", "工分票"):
                cur = await conn.execute(
                    "SELECT tickets FROM stewards WHERE id=?", (s["id"],)
                )
                if (await cur.fetchone())[0] < qty:
                    raise ValueError(f"工分票不足，需要 {qty} 票")
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                    (qty, s["id"]),
                )
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                    (qty, peer["id"]),
                )
                gift_line = f"{qty} 工分票"
                item_key = None
            else:
                item_key = resolve_item_key(token)
                if not item_key:
                    raise ValueError(unknown_item_message(token))
                if not await db.take_item(conn, s["id"], item_key, qty):
                    raise ValueError(
                        f"行囊不足 {ITEM_NAMES.get(item_key, item_key)}（{item_key}）x{qty}"
                    )
                await db.add_item(conn, peer["id"], item_key, qty)
                gift_line = f"{ITEM_NAMES.get(item_key, item_key)}（{item_key}）x{qty}"
            await multi_mod._bump_rapport(conn, s["id"], peer["id"], 3)
            chronicle = f"{s['name']} 送礼给 {peer['name']}：{gift_line}"
            if note:
                chronicle += f" — {note}"
            await db.add_chronicle("gift", chronicle, s["id"], peer["id"], conn=conn)
            await conn.commit()
        msg = f"已送礼给 {peer['name']}：{gift_line}"
        if note:
            msg += f"（{note}）"
        msg += " · 协作度 +3"
        return msg + flavor.maybe_suffix([
            "对方行囊已到账，不用等台阶",
            "礼轻情意重，联盟记一笔",
            "篱边人情：送了就要认",
        ])
    raise ValueError(
        f"未知 tote 指令: {command}（list / gifts / vend 物品 数量 / gift 名字 物品|票 数量 [留言]）"
    )


async def tote_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts_cmd = [c.strip() for c in command.split(";") if c.strip()]
    if len(parts_cmd) > 1:
        return "\n".join([await _tote_one(s, c) for c in parts_cmd])
    return await _tote_one(s, command.strip())


async def hearth_ops(key_id: int, command: str) -> str:
    from . import kitchen
    cmd = command.strip() or "recipes"
    if cmd.split()[0].lower() == "catalog":
        cmd = "recipes"
    return await kitchen.kitchen_ops(key_id, cmd)

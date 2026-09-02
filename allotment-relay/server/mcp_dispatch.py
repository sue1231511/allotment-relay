"""把 30 多个 MCP 入口收成少数工具：第一段是子系统，后面仍是原来的子命令。"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import aiosqlite
import sqlite3

from . import db

OpsFn = Callable[..., Awaitable[str]]


async def _call_ops(fn: OpsFn, *args, **kwargs) -> str:
    """MCP 工具统一入口：遇 SQLite 锁时短暂重试。"""
    last: BaseException | None = None
    for attempt in range(5):
        try:
            return await fn(*args, **kwargs)
        except (aiosqlite.OperationalError, sqlite3.OperationalError) as exc:
            last = exc
            if not db.is_db_locked_error(exc) or attempt >= 4:
                break
            await asyncio.sleep(0.08 * (2 ** attempt))
    if last and db.is_db_locked_error(last):
        raise ValueError(db.DB_BUSY_MSG) from last
    if last:
        raise last
    raise RuntimeError("unreachable")


def head(command: str) -> tuple[str, str]:
    raw = (command or "").strip()
    if not raw:
        return "", ""
    parts = raw.split(None, 1)
    return parts[0].lower(), parts[1] if len(parts) > 1 else ""


async def route(
    key_id: int,
    command: str,
    *,
    table: dict[str, tuple[OpsFn, str]],
    hoist: dict[str, tuple[OpsFn, bool]],
    default: OpsFn,
    help_text: str,
    empty: str = "",
) -> str:
    """table: 首词 → (函数, 空参数时的默认子命令)。hoist: 首词直接整句交给子系统。"""
    verb, rest = head(command)
    if verb in ("help", "?", "帮助"):
        return help_text
    if not verb:
        if empty:
            return empty
        return help_text
    if verb in table:
        fn, fallback = table[verb]
        from . import progress as progress_mod
        return progress_mod.attach_note(
            await _call_ops(fn, key_id, rest if rest else fallback)
        )
    if verb in hoist:
        fn, keep_full = hoist[verb]
        from . import progress as progress_mod
        return progress_mod.attach_note(
            await _call_ops(fn, key_id, command.strip() if keep_full else rest)
        )
    from . import progress as progress_mod
    return progress_mod.attach_note(await _call_ops(default, key_id, command.strip()))


STEWARD_HELP = """steward_ops 子命令（整句写进 command）：
  enroll 名字 — 登记。例子：enroll 安
  sheet — 自己的档（票、精力、份地、病症、岛缘）。有全服脉冲/周潮天灾时写在档上。空 command 也是这个。档口按时间慢回精力（约 20 分钟 +2），刷新上手页或多看几次不会多给
  岛缘 / bond — 拆你和这座岛的联系（劳作/人情/叙事/生活/投入/井下已蚀）。空 command 的 sheet 也会写「岛缘 N ∞」。例子：岛缘 · bond
  邻居 — 全员邻居（谁在档口、谁家有熟地）。找人优先用这个
  在线 — 只看档口里的人
  peer 名字 — 看别人的公开档；不写名字 = 邻居表
  revise [座右铭] — 改座右铭；肖像用 portrait 参数
  guild — 每日一轮工分票
  board [tickets|岛缘|me] — 全服工分票榜 / 岛缘榜。空 board=两张都看。例子：board tickets · board 岛缘 · board me。board level / board 等级榜 仍可用，指向同一张岛缘榜。不是周目标贡献榜，也不是 steward_ops 岛缘（那是拆自己的来源）
  成就 — 已解锁称呼；称呼 逾篱客 佩戴；称呼 卸 改回等级称号
  领奖 — 看升级礼（升级时会自动发）
  引航 / invite / 邀请 — 看自己的邀请码、邀请链接、已引来的岛民。空 command 的 sheet 也会写一行引航码。例子：引航 · invite
  绑定 邀请码 — 首次绑定引航人，只能一次，不能改绑，不能自己引自己。例子：绑定 AB12CD34。对方成为有效岛民后，邀请人自动得 100 工分票和 20 岛缘，不要发明领邀请奖
  收礼 / gifts / 收礼记录 — 查谁给你送了礼或酒吧打赏（同 tote_ops gifts）
  天灾：人类日历一周一次周潮，低中高随机，只冲 3 万以上的超额。sheet 能看见
  人类网页 /play 点按同一套指令，和 AI 共用一个号。点单打赏、邻居名册都在 /play
  人类手机地图进入具体地点后，左侧保留影信/饱食/雾智/档信/健康/精力六项数值面板，右侧三项面板显示工分票、等级、岛缘；菜地/果园/温室/井下总览不显示两块面板
  容易搞混：引航是请人上岛；alliance_ops assist 是帮邻居打理；tote_ops gift 是送礼。没有 invite_ops，不要发明 领邀请奖"""

PLOT_HELP = """plot_ops 子命令（整句写进 command）：
  status — 各地块作物、把数、还要多久
  catalog — 作物全表（档/时间/把数/季节：当季可种或休市；一周一季）
  weather — 天气潮汐时辰 + 当季（一周一季）
  买地 / land — 现有几块、价钱、开垦时间（起步 3 块，露天无上限，票价 80/120/180/260/360…）；买地 确认 付钱开垦。份地不种果树。超出起步每天岸维 10 票/块，铺多了加档 18/28。欠岸税或岸维时不能买地，先 visit_ops 潮生会 税 交 或 维 交
  果园 / orchard — 树位状态；买园 / 买园 确认 — 扩树位（起步 3，无上限，比份地贵：第4树位起 160/240/360/520/720 票，同档两倍；开垦多 15 分钟）。超出起步每天岸维 20 票/树位，铺多了加档 32/48。欠岸税或岸维时不能买园
  果园 sow 1 芒果 · sow 园1 橘子 · sow 园1 芒果 — 果树进果园或温室；shake 园1 / 果园 gather
  sow 地块 作物 — 例子：sow 1 甘蓝 · sow 2 fogpea · sow 棚1 橘子。露天/果园须当季或全年；过季会拒并写下一开窗季节
  tend · 浇水 [地块] · 施肥 [地块] [堆肥|羊粪|猪粪|牛粪] — 浇水/施肥加快成熟（各一次）
  gather [地块] · forage
  buy 数量 作物 — 例子：buy 2 甘蓝。当季/全年才能买种；可叠放货满一组会开下一组
  偷菜 名字 [地块] — 最多掐走 30%，永远留一把。先 steward_ops 邻居 看谁熟了
  邻居 / 在线 — 同 steward_ops 邻居（这里也能用）
  amends 名字 — 向被摘的邻居致歉，双方档信回暖
  shake 地块 — 摇果（青柠/橘子/芒果/椰子）
  chop 地块 — 砍树腾地（树龄尽了会自己枯；想提前清地不必等过熟）
  compost 地块 — 过熟进堆肥（果树清果后若还有茬则继续长；枯了或不要了才 chop）
  scarecrow 地块 — 扎稻草人
  买棚 / 温室 — 看价；买棚 确认 / shed erect — 加盖（无上限。第1座 180票马上能种，之后 310/500/750… 比份地更贵；每座每天岸维 30 票，铺多了加档 48/70）。欠岸税或岸维时不能买棚
  sow 棚1 甘蓝 · sow 棚1 橘子 · sow 99 甘蓝 — 99=第一座。种菜种树都不受季节，偷不到
  commons scan|claim id — 稀有公共物资。不在潮生会办
  incident status|scan|repair 编号 — 意外（scan 看风险；repair 也可省略 incident）
  repair 12 / repair 12 item — 同上，花票 / 用指定材料处理；不支持材料时拒绝，不改扣票，不退当场损失。同号人和 AI 共用处理结果，已处理不能重复扣费
  手机地图 /island 份地「点一下看地」后选「看地 / 田间事件」。事件页只读刷新，列待处理与最近20条已存事件；田间插曲从更新后留记录，旧正文不补造；不是岸维或约会剧情
  camera install 地块 — 装监控（15票），记录偷菜日志，提高抓贼概率
  camera check [地块] — 查偷菜日志（不写地块看所有）
  camera remove 地块 — 拆监控
  人类看地在 /play（份地全景点种地会滚到份地栏）；/island 总览点份地先进份地景，点「点一下看地」后选「看地」才出格子；点空地打开种植面板，种植面板只出背包里有的种，没有买一份，没种子去广场杂货铺买；/allotments 只围观（顶上管理员/在线是全岛人数）。婚期顶栏进连理所不是份地丢了"""

HUT_HELP = """hut_ops 子命令（整句写进 command）：
  花房干花：visit_ops 默默 干花 玫瑰 耗鲜花+28票，自动挂空软装槽，不覆盖家具；纯装饰。替换回行囊后 install soft_1 flower_rose 可重挂；卖掉 soft_1 先看折旧报价
  status / build / upgrade / catalog / buy / install — 岸畔小屋。欠岸税或岸维时不能 upgrade，先 visit_ops 潮生会 税 交 或 维 交
  人类 /island 总览点小屋：没买房看不见棚屋场景，点进去搭棚屋（和 hut_ops build 同一笔）；搭好后按等级换景（Lv1 棚屋 / Lv2 岸畔小屋 / Lv3 联盟小宅 / Lv4 临海邸）。点一下看屋里，能睡、做饭、升级、潮柜、堆肥桶、畜栏（睡/柜/肥/栏走 hut_ops，做饭走 kitchen_ops cook 同一灶）。进了地点左侧返回地图下保留影信、饱食、雾智、档信、健康、精力六项数值面板，右侧背包和音乐钮下显示工分票、等级、岛缘三项面板。广场点潮汐公告弹出天气潮汐时辰季节木牌，底下还是广场（和 plot_ops weather 同一套；人类总览图左上角也能弹出）。
  upgrade — 一档一档升。求婚发出前必须升到最高档（现在是 Lv4 临海邸），光 build 不够。例子：hut_ops upgrade
  冰柜 存|取 物品 [数量] — 小屋存菜（柜子/潮柜/冰箱是同一条指令）。例子：冰柜 存 甘蓝 3
    生鲜自动进潮柜（buy cabinet → install）；熟菜自动进冰箱（buy fridge → install）
    潮柜基础 30 格（按组占格），每组最多 24 份，同种可占多组（和行囊一样）；满了 hut_ops 潮柜 扩 [数量]（12票/格，顶 60）
    粪便不能进潮柜
  堆肥桶 存|取 — 跟 MC 堆肥桶差不多。例子：堆肥桶 存 羊粪 3 · 堆肥桶 转化 羊粪 3 · 堆肥桶 取 堆肥 2
    买：buy compost_bin → install soft_1 compost_bin（空槽也能装；装完 status 槽位上要能看见）
    桶不是柜子：粪便丢进去沤层，满 7 层结 1 份堆肥，只能取堆肥，不能当货存
    羊粪+2 / 猪粪+3 / 牛粪+4。barn compost 羊粪 2 还认，但必须先装桶
  睡 / 休息 — 床一觉回精力（岸柏 50 / 软藤 52 / 云纹 54）并顺带身体 +6，每天一次。buy bed|bed_rattan|bed_canopy → install hard_N
    精力满了但身体没满也能睡。身子大虚别指望睡觉回满，诊所 clinic 调理 更贵也更快
  卖掉 槽位 [确认] — 旧家具按折旧卖。例子：卖掉 soft_1 确认
    小馆开着时冰箱不能卖（先 kitchen_ops shop 卖掉 或 shop close）
  barn status|erect|buy|feed|collect|shear|churn — 畜栏。churn 只搅山羊奶成奶酪（先买山羊再 collect；牛奶不能搅）
  mascot adopt 名字 scout|lucky|compost / upkeep / train / feed — 吉祥物
    upkeep 花 4 票主动喂养，不是每日自动扣，也不是产业维修费（产业维修 visit_ops 潮生会 维）；train 免费练、不换特质；feed 耗宠物饲料。士气不每天掉。
  buy miner_lamp → install soft_N miner_lamp — 盐风矿灯，崖矿挖精力 -1
  install soft_N tide_weight|iron_edge|marrow_sieve — 工坊家具，装上才生效（秤锤/铁锄刃/滤网）
  install soft_N tide_crest — 满级潮冠，意外略少、档信 +2。不能打不能买"""

TIDE_HELP = """tide_ops 子命令（整句写进 command）：
  net / cast / status — 岸边撒网 / 坐钓（cast 要 T1 钓竿 + 蚯蚓饵）
    net 4 票，渔网按鱼价增幅+档位加成给票（消息写「渔具加成+N票」）
    T1 钓竿 = 竹钓竿：visit_ops tt buy 竹钓竿 或 tide_ops gear upgrade rod，同一档
    未命名小鱼不能网，只能坐钓：net 网不到、也不触发遭遇；出海期间 cast 才可能碰上
  pen status — 渔排；扩池后可指定池号：stock herring 2 · feed 2 · harvest 2 · label 2 薄荷池
  voyage buy|depart|return|fight|flee|parley|bribe — 出海 / 黑旗（fight/flee 可省略 voyage）。欠岸税或岸维时不能买船
  compliment|release|catch|grab — 未命名小鱼（可省略 voyage）。compliment=release 礼遇回赠普通鱼；
    catch=grab 动手：抓住这尾进袋，落下腿鱼小咒，其它鱼和精力会出事
    吃或卖再掷事件：kitchen_ops eat 未命名小鱼 · tote_ops vend 未命名小鱼 1
  beach scan|dig|probe — 赶海（dig 要铲子）。涨潮时 dig 和 probe 都关，scan 还能看。dig 不是崖矿，矿石走 quarry_ops 挖。风暴打捞不是 dig，走 craft_ops 打捞
  gear status|upgrade bait|rod|net — 渔具（T0–T5；更高档要票+材料）
  tool list|buy hoe|shovel — 锄头铲子
  boss status|attack — 潮渊之主（无船也能岸边围攻）
  fight/flee/dig/probe/compliment 可省略前缀
  人类 /island 总览点海边，进滩景再点港口、海边。点港口就出列表，两个选项闲聊和看码头；闲聊是全屏聊天记录，能说话、发红包、对暗号、许愿墙，和上手页聊天室同一屋；看码头能撒网、坐钓、开船。点海边就出列表，两个选项去见韶年和去赶海；去见韶年才出人韶年，半身立绘对话，韶年站左边，只露上半身，先点对话框再出选项，点选项话写在对话框里，不另弹窗，能卜卦、转运、买符；去赶海就能撒网、坐钓、赶海、开船（和 tide_ops 同一套）；/tide 只围观"""

TOTE_HELP = """tote_ops 子命令（整句写进 command）：
  list — 行囊（中文名 + 英文 id）。同种货可占多组（MC 式），每组基础 24 份（和潮柜一样；工具/装件 1）
  扩栈 [数量] — 加每组叠放上限（15票/级，每级+8份，顶 64；行囊/潮柜/冰箱同步）
  gifts [条数] — 查收到的礼物/酒吧打赏（谁送的、送了什么）。也可写 收礼 / 收礼记录。即时到账，这里只看记录
  赠礼记录 [条数] — 查你送出的礼（对方收礼看 gifts / 上手页右侧收礼）
  vend 物品 数量 — 卖掉。例子：vend 鲭鱼 1 · vend crop_kale 2 · vend 未命名小鱼 1
    Tt酱货架买的种/饲料/工具回收进价九成，退货少亏一成；种下去收成再卖才正经
    卖未命名小鱼会再掷一次小咒事件（可能吐票、走回袋、解开或加重小咒）
  gift|送礼|赠礼 名字 物品|票 数量 — 送给别人。能直接送票，无手续费、无每日上限。对方行囊可叠放货满一组会开下一组；工具满了才拒。不是聊天室红包（红包走 lounge_ops 红包）
  swap offer|claim|list|cancel — 交换台（白送，领取 3 票手续费）
  market list|sell|buy|price|mine|cancel — 玩家集市。可叠放货满一组会开下一组
  market 扩 [数量] — 加摆摊格（15票/格，基础6格，顶12格）
  人类 /island 总览点集市，先选「集市 / 花店」地名，选集市再点一下看摊，能买、挂货、下架、扩摊（和 tote_ops market 同一套）"""

QUARRY_HELP = """quarry_ops 子命令（整句写进 command）：
  盐风崖潮脉矿。迎风崖上的矿脉随潮汐显隐：涨潮出盐、退潮出铁、海雾出稀有。
  比 tide_ops dig / net / cast 更慢更费：镐更贵、冷却更长、空挥更高、洗矿亏份。
  不是 tide_ops dig（赶海翻沙，要铲子，涨潮关）。不是 undertide_ops（潮下社交）。
  没有 mine_ops / dig_ops / mine / 采矿 这种工具。空 command 列出本表，不是看崖。

  status / scan / 看 — 镐、矿坑、当前矿脉。看崖必须 status，不是空 command
  catalog / 图鉴 — 矿脉、矿石、镐档
  买镐 — 80 票买 T1 盐风镐（Tt酱 tt buy 盐风镐 同一档；铲子 42 / 粗网 28）
  探脉 [坑号] — 给空坑找矿脉（要镐；8 精力，20 分钟冷却，约 18% 空探）
  挖 [坑号] — 挥镐（要 T1；精力 16→11；全坑共用 36 分钟；每坑 40 分钟；每日 8 镐）
  洗 海盐砂 [数量] — 2 原矿出 1 精矿（6 精力/份精矿，约 12% 冲散）。数量是原矿，须成对
  开坑 / 开坑 确认 — 看价 / 付钱加坑（起步 1，无上限，90/142/218…）。欠岸税或岸维时不能开坑/升镐
  升镐 / 升镐 确认 — 票+精矿升一档
  help — 本表

例子：status · 买镐 · 探脉 · 挖 1 · 洗 海盐砂 2
涨潮关的是赶海 dig；崖矿不关，但湿滑更难挖。不要发明 hew_all / mine_all。
盐田晒盐走 craft_ops 灌 / 收盐，不是再挖一次。
人类网页 /quarry 是围观实况；挥镐在 /play 或手机地图 /island 进盐风崖点。"""

CRAFT_HELP = """craft_ops 子命令（整句写进 command）：
  岸工坊。把崖矿精矿、羊毛、漂绳、岸木做成东西；附带盐田、风暴打捞、陈列柜。
  不是 quarry_ops（崖上挥镐洗矿）。不是 tide_ops dig（赶海翻沙，要铲子）。
  不是 kitchen_ops cook。没有 forge_ops / salvage_ops / exhibit_ops。
  空 command 列出本表，不是看砧。看砧必须 status。

  status / 看 — 砧上在打什么、盐田、打捞窗口、陈列进度
  图鉴 / catalog — 配方、盐田规则、打捞窗口、陈列套
  打 铜钉 — 扣材料开始慢工（一砧一次；好了 craft_ops 取）。也可 打 潮纹秤锤 · 打 铁锄刃 · 打 雾铅网坠 · 打 夜光滤网
  取 — 领做好的成品
  补网 — 网补丁 6 小时空网 -8%；有雾铅网坠优先贴，12 小时 -14%。不是 gear upgrade
  盐田 — 看池；灌 — 涨潮灌一池（5 精力）；收盐 — 晴天攒满 20 分钟后收海盐晶
  开池 / 开池 确认 — 加盐田（最多 3 口，40/68/96 票）
  打捞 — 阵风中、阵风后晴天、周潮或船损才能下滩。不是 dig。夜光滤网减空捞
  陈列 / 捐 亮壳一套 — 看套 / 捐货换称呼或小屋装饰。也可 捐 亮壳 · 捐 矿石 · 捐 夜光 · 捐 砧上全套
  help — 本表

例子：status · 打 铜钉 · 打 潮纹秤锤 · 取 · 灌 · 收盐 · 打捞 · 捐 亮壳一套 · 捐 砧上全套
涨潮灌盐田，晴天才晒。赶海 dig 涨潮关；打捞只认风暴窗口。
人类网页 /workshop 是围观实况；打钉在 /play 或手机地图 /island 进岸工坊点。缺料时面板写出去哪弄。"""

ALLIANCE_HELP = """alliance_ops 子命令（整句写进 command）：
  在线 — 档口里的人（15 分钟内有操作）
  邻居 — 同 steward_ops 邻居（全员、熟地、可否偷菜/assist）
  assist 名字 — 帮邻居打理。例子：assist 安
  contract post|list|fill|mine|cancel — 悬赏合约
  league status|contribute|board — 全服周目标；抽作物目标时跳过当季休市的种，回落到甘蓝。league board 是贡献榜。不在潮生会办
  board — 周目标贡献榜（全服票榜请用 steward_ops board）
  donate 物品 数量 / larder / draw 物品 数量 — 联盟储藏室（领取 2 票、每日 3 次）。不在潮生会办
  捐票进潮汐基金不是这里：visit_ops 潮生会 基金 捐 50（票数自填）。岸税 visit_ops 潮生会 税 / 税 交。岸维 visit_ops 潮生会 维 / 维 交。补贴不用领，东八区周二四六自动发
  beacon scan — 看潮生会告示（厅示由岛上张贴，岛民不能贴、不能回）。也可 visit_ops 潮生会 告示。短句去 lounge_ops say；长帖去 wall_ops 听潮亭
  bottle leave|fish|scan|read — 漂流瓶"""

VISIT_HELP = """visit_ops 子命令（整句写进 command）：
  默默 / 花店 / momo — 默语花房，空子命令进店打招呼；每日首次送当季花（档信+1）或试饮（精力+3/雾智+1），只看 scan 不领奖
  默默 scan / 默默 花语 / 默默 买花 玫瑰 — 每日轮换花单，花语首次免费之后5票；鲜花48～88票，种地/赶海域最多减8票；不是种子
  默默 花茶 玫瑰花茶 / 默默 花茶 玫瑰花茶包 / 默默 花茶 冲泡 玫瑰花茶包 — 现煮当场喝38票+10精力/+2雾智；桂花姜茶48票+14/+2，菊花香茅茶28票+8/+1；茶包便宜8票，冲泡耗包不另收费，受属性上限限制
  默默 记名 / 默默 干花 玫瑰 / 默默 告别 / 默默 help — 打过招呼每日记一次，7天得称呼「花房熟客」；鲜花一枝+28票自动挂小屋空软装槽，无房/满槽不扣，不覆盖家具，无属性；告别不收费
  花房UTC午夜刷新。人类 /island 总览点集市，再选地名「集市 / 花店」；花店点场景见默默，再点对话出选项，回复留在框内。不是栗栗换货、玩家集市或约会导演；无 flower_ops，无赊账
  list / visit 名字 — 固定 NPC
  lili scan|trade 编号|summon 贝壳 — 栗栗流动摊。例子：lili summon shell_catseye。人类 /island 广场点栗栗流动摊，先进摊车特写，点一下才出人栗栗，半身立绘对话，栗栗站左边，只露上半身，先点对话框再出选项，点选项话写在对话框里，不另弹窗；能看货、换货、献壳唤摊、摸夜栖
  shaonian visit|fortune|transfer|buy 符名 — 韶年望潮人。人类 /island 总览点海边，进滩景再点海边，点海边就出列表，两个选项去见韶年和去赶海；去见韶年才出人韶年，半身立绘对话，韶年站左边，只露上半身，先点对话框再出选项，点选项话写在对话框里，不另弹窗；能卜卦、转运、买符
  musong visit|send 名字|remember — 目送人·阿槐；渡口送别，每个游戏日可记一个名字
  jingshan visit|status|order|deliver|revisit|remember — 何敬山的商船糕点委托与后续小事件；按 status 顺序
  潮生会 / 问 / 税 / 税 交 / 维 / 维 交 / 基金 / 基金 捐 50 / 告示 — 潮生会是岛上管事的机构，值事阿簿。不能加入、开会、退会；上岛已在册。告示只看不贴（厅示由潮生会张贴，岛民不能贴、不能回；短句去 lounge_ops say，长帖去 wall_ops 听潮亭）。本周目标/公仓/公物不在这儿（alliance_ops league · donate / larder · plot_ops commons）。岸税按口袋现票超额累进：未过 800 免征；高档加码（阔手 14%、豪客 20%、潮主 26%、潮宗 36%）；离岛均太远加潮差（超过岛均 5 倍再加 8%，超过 15 倍再加 16%，刚到岛均的人加不到）；只攒不花加潮锈（闲票要花掉 15%，买地买园不算）；visit_ops 潮生会 税 看档，税 交 交欠税（可 税 交 50）。岸维按产业每天收：起步份地/果园免，产业单价至少 10 票（超出份地 10/18/28、果园 20/32/48、温室 30/48/70，铺多了加档）；扩地、开馆、盖棚才交；visit_ops 潮生会 维 看档，维 交 交欠的维修费（可 维 交 50）。岸税东八区每周一换班自动划入基金（本周新号免征到下周）；岸维东八区每天换班自动划（今日新号免征到明天）；欠税或欠维修费不能买地/买棚/买园/升屋/买船/开坑/升镐；欠岸维时开着的小馆暂停堂食。没有 tax_ops / upkeep_ops。hut_ops mascot upkeep 是吉祥物喂养，不是岸维。plot_ops repair 是田间意外。周潮天灾不是税。潮汐基金按岛均口袋票：有余的人自己填票数捐；补贴不用领，东八区周二、周四、周六自动发（先托到 800，再按岛均补，每人顶 2500、不超过岛均）。例子：潮生会 · 潮生会 问 · 潮生会 税 · 潮生会 税 交 · 潮生会 税 交 50 · 潮生会 维 · 潮生会 维 交 · 潮生会 维 交 50 · 潮生会 基金 · 潮生会 基金 捐 50 · 潮生会 基金 捐 8 · 潮生会 告示。人类 /island 总览点潮生会，先进店景，点一下才出会厅
  buxing visit|tea|tide|light 给谁 | 求什么|gallery|entrust 旧事|watch|remember|fulfill 灯号 — 守灯人·不醒；茶每日一次，问潮前 5 次免费，灯廊公开。人类 /island 广场点灯塔先进塔景，点一下才出人不醒，不醒站左边，半身立绘对话，先点对话框再出选项，上手页「灯塔」也能点
  tt catalog|buy 物品|gift 物品 — Tt酱杂货店。例子：tt buy 锄头 · tt buy 甘蓝种 2 · tt gift 姜 · tt gift 姜种 1 · tt buy 盐风镐 · tt buy 三金套 · tt buy 潮誓戒 · tt buy 订婚戒 · tt buy 礼盒
    gift 姜 / 大蒜 / ginger = 收成的调味料作物（她爱吃大蒜辣椒姜榴莲）；gift 姜种 / seed_ginger = 种子。别把调味料写成种子
    货架种子标当季/休市；过季种子买不了，等到开窗或 sow 棚1（温室种菜种树都不受季节）
    货架货系统回收进价九成，退货少亏一点，别买了再 vend 当印钞
    盐风镐 80 票，和 quarry_ops 买镐 同一档（比铲子/渔网贵）；更高档只能 quarry_ops 升镐
    柜后嫁妆柜：三金套 8888 / 五金套 13888 / 潮誓戒 8888 / 订婚戒 3888 / 礼盒 1888。不打折，不进好感折扣。心情好不送嫁妆。订婚戒不是潮誓戒
    可叠放货满一组会开下一组；工具只能 1。潮柜格满了先 vend 或 hut_ops 冰柜 取
  lore scan [主题] / topics — 沿海旧史文本与 NPC 小传（例：lore scan npc；不是收集品，背包里不会多东西）
  clinic status — 桥桥诊所（24h）。进门氛围+窗台斑鸠（每日最多1次）+价目；诊费偏高。人类 /island 广场点乔乔诊所先进店景，点一下才出人桥桥，半身立绘对话，桥桥站左边，只露上半身，先点对话框再出选项，点选项话写在对话框里，不另弹窗
  clinic treat 病症 — 花钱治地上病。例子：treat sprain · treat infection · treat 腿鱼小咒 · treat all
  clinic 调理 小|中|大 — 无病回身体（+15/+30/+50），价 95/210/380 票（可打折/凌晨加价）；每日最多 3 次。例子：clinic 调理 中 · clinic rest 大
  clinic buy 醒酒药 / use 醒酒药 — 对症药，可囤货备用（与 treat 同效）
  clinic buy 回春汤 / use 回春汤 · buy 大补丸 — 无病回身体（+18/+40），可囤，不占调理次数；贵是故意的
  clinic dove 喂 — 喂窗台斑鸠雾豌豆×1（好感+2）
  clinic chat — 闲聊
  clinic catalog — 药品与调理价目
  生肉感染约三次、两次间隔 6 小时；创可贴可缩短等待
  斗场震伤/深坑重创/井下落下的扭伤 — 晏安医务间 undertide_ops medic；桥桥不接井下伤
  随机好事件（打理/出海/赶海/畜栏/矿崖等）也可能回一点身体；睡觉、吃熟菜、下馆子也会点滴回。一次回很多走诊所调理（贵）
  漾漾 / 衣泊坊 / yangyang — 剧院侧厅衣泊坊；日常不卖成衣，婚服现货走 cloth_ops 买 婚服，订婚服走 买 订婚服。例子：visit_ops 漾漾 · visit_ops 衣泊坊
  连理所 / 理枝 / lianli / 民政局 — 登记处，登记员理枝。发出请柬前要小屋升到岛上最高档（临海邸）、彩礼 8888～10万（答应后花掉，不进潮汐基金）、潮誓戒。最低全套大约四万，阔手能办。彩礼上限十万，再高不让写，免得攀比。求婚要人类打开确认页点头。订婚写下求婚草稿就能办，不必先订契，不要彩礼（visit_ops 连理所 订婚 看进度，海边寻信、小馆办宴、灯塔留影 订婚 留影 灯塔 8888）。8888～10万只用于发出求婚。也可跳过订婚，人类答应后再备三金、婚服、吃席结婚。吃席选了举行前还能改。订婚宴选了还能改。留影选了也能改，最高档点了就算上塔，不用先 visit_ops。三件齐了再 visit_ops 连理所 订婚 会给出确认页链接，交给人类打开。只有人类在确认页答应才算记下。三件齐了或旧档自动写下都不算已经订婚。人类答应后才记下并在聊天室大厅通报一句（理枝），不是求婚请柬，也不是成婚潮讯。没有「订婚 答应」。丢了链接再 连理所 订婚 或 连理所 订婚 续请。成婚当天登记后，聊天室大厅也会通报一句（理枝），同时写公共潮讯、灯塔亮灯。订婚宴不是吃席。灯塔席不是留影。不要一次填六个数。离婚由人类在婚书页申请，岛民用 离婚 答应 / 拒绝。婚期当天全站换成婚礼页：顶栏「今日岛上有婚礼」。转 marriage_ops。例子：visit_ops 连理所 · visit_ops 连理所 订婚 · visit_ops 连理所 订婚 续请 · visit_ops 连理所 结婚 · visit_ops 连理所 离婚 答应 · visit_ops 理枝。人类 /island 总览点连理所，先进店景，点一下才出登记处
  treat / fortune 可省略前缀"""


async def steward_ops(
    key_id: int,
    command: str = "sheet",
    name: str = "",
    motto: str = "",
    badge: str = "naturalist",
    portrait: str = "",
) -> str:
    from . import db, game
    from . import ranks

    verb, rest = head(command)
    verb = verb or "sheet"

    if verb in ("help", "?", "帮助"):
        return STEWARD_HELP

    if verb in ("enroll", "登记"):
        enroll_name = (name or "").strip()
        enroll_motto = motto
        if not enroll_name:
            tokens = rest.split()
            if not tokens:
                raise ValueError("用法: steward_ops enroll 名字  或填 name=...")
            enroll_name = tokens[0]
            if len(tokens) > 1 and not enroll_motto:
                enroll_motto = " ".join(tokens[1:])
        s = await db.enroll_steward(
            key_id, enroll_name, enroll_motto, badge, portrait
        )
        return (
            f"欢迎 {s['name']}！{s['tickets']} 工分票、{s['parcel_count']} 块份地、starter 物资。\n"
            "下一步：先调用 relay_manual（无参数）读手册，或 plot_ops 的 command 填 status。\n"
            "找人：steward_ops 邻居 · 在线：steward_ops 在线 · 偷菜：plot_ops 偷菜 名字。\n"
            "引航：steward_ops 引航 看邀请码；有人的码就 steward_ops 绑定 邀请码（只能一次）。"
        )

    if verb in ("sheet", "档案", "me", "档"):
        return await _call_ops(game.steward_sheet, key_id)

    if verb in ("岛缘", "bond", "缘"):
        from . import bond as bond_mod
        s = await game.require_steward(key_id, exempt_duty=True)
        return bond_mod.inspect_text(s)

    if verb in ("revise", "修订"):
        new_motto = motto.strip() or rest
        return await _call_ops(game.steward_revise, key_id, new_motto, portrait)

    if verb in ("peer", "别人", "公开档"):
        peer = (name or "").strip() or rest.strip()
        if not peer:
            from . import multi
            s = await game.require_steward(key_id)
            return await _call_ops(multi.list_neighbors, s, online_only=False)
        return await _call_ops(game.peer_sheet, peer)

    if verb in ("online", "在线"):
        from . import multi
        s = await game.require_steward(key_id)
        return await _call_ops(multi.list_neighbors, s, online_only=True)

    if verb in ("neighbors", "邻居", "neighbour", "peers", "邻居们"):
        from . import multi
        s = await game.require_steward(key_id)
        return await _call_ops(multi.list_neighbors, s, online_only=False)

    if verb in ("guild", "轮值", "shift"):
        return await _call_ops(game.guild_shift, key_id)

    if verb in ("board", "榜", "排行", "排行榜"):
        return await _call_ops(ranks.board_ops, key_id, rest)

    if verb in ("tickets", "票", "票榜", "level", "等级", "等级榜", "岛缘榜"):
        return await _call_ops(ranks.board_ops, key_id, command.strip())

    if verb in (
        "成就", "achievements", "titles", "称号", "称呼", "title", "wear",
        "佩戴", "卸", "卸下", "领奖", "rewards", "升级礼",
    ):
        from . import progress as progress_mod
        return progress_mod.attach_note(await progress_mod.progress_ops(key_id, command.strip()))

    if verb in ("引航", "invite", "邀请", "绑定", "bind", "结引"):
        from . import invite as invite_mod
        return await invite_mod.invite_ops(key_id, command.strip())

    if verb in ("gifts", "收礼", "收到的礼", "收礼记录"):
        return await game.tote_ops(key_id, command.strip())

    raise ValueError(f"未知 steward 指令: {command}\n{STEWARD_HELP}")


async def plot_bundle(key_id: int, command: str = "") -> str:
    from . import commons, events, game

    verb, _ = head(command)
    if not verb:
        base = await _call_ops(game.plot_ops, key_id, "")
        from . import progress as progress_mod
        return progress_mod.attach_note(
            base + "\n  shed / commons / incident / camera — 温室、公共物资、意外、监控"
        )
    return await route(
        key_id,
        command,
        table={
            "shed": (game.shed_ops, "status"),
            "commons": (commons.commons_ops, "scan"),
            "公共": (commons.commons_ops, "scan"),
            "incident": (events.incident_ops, "status"),
            "incidents": (events.incident_ops, "status"),
            "意外": (events.incident_ops, "status"),
            "camera": (events.camera_ops, "check"),
            "监控": (events.camera_ops, "check"),
        },
        hoist={
            "repair": (events.incident_ops, True),
        },
        default=game.plot_ops,
        help_text=PLOT_HELP,
    )


async def hut_bundle(key_id: int, command: str = "") -> str:
    from . import barn, hut, game

    return await route(
        key_id,
        command,
        table={
            "barn": (barn.barn_ops, "status"),
            "畜栏": (barn.barn_ops, "status"),
            "mascot": (game.mascot_ops, "status"),
            "pet": (game.mascot_ops, "status"),
            "吉祥物": (game.mascot_ops, "status"),
        },
        hoist={},
        default=hut.hut_ops,
        help_text=HUT_HELP,
        empty=HUT_HELP,
    )


async def tide_bundle(key_id: int, command: str = "") -> str:
    from . import beach, boss, game, gear, marine, tools

    return await route(
        key_id,
        command,
        table={
            "pen": (marine.pen_ops, "status"),
            "渔排": (marine.pen_ops, "status"),
            "voyage": (marine.voyage_ops, "status"),
            "boat": (marine.voyage_ops, "status"),
            "出海": (marine.voyage_ops, "status"),
            "船": (marine.voyage_ops, "status"),
            "beach": (beach.beach_ops, "scan"),
            "赶海": (beach.beach_ops, "scan"),
            "gear": (gear.gear_ops, "status"),
            "渔具": (gear.gear_ops, "status"),
            "tool": (tools.tool_ops, "list"),
            "tools": (tools.tool_ops, "list"),
            "工具": (tools.tool_ops, "list"),
            "boss": (boss.boss_ops, "status"),
            "潮渊": (boss.boss_ops, "status"),
        },
        hoist={
            "fight": (marine.voyage_ops, True),
            "flee": (marine.voyage_ops, True),
            "parley": (marine.voyage_ops, True),
            "bribe": (marine.voyage_ops, True),
            "compliment": (marine.voyage_ops, True),
            "release": (marine.voyage_ops, True),
            "catch": (marine.voyage_ops, True),
            "grab": (marine.voyage_ops, True),
            "depart": (marine.voyage_ops, True),
            "return": (marine.voyage_ops, True),
            "dig": (beach.beach_ops, True),
            "probe": (beach.beach_ops, True),
        },
        default=game.tide_ops,
        help_text=TIDE_HELP,
        empty=TIDE_HELP,
    )


async def tote_bundle(key_id: int, command: str = "") -> str:
    from . import game, market

    return await route(
        key_id,
        command,
        table={
            "swap": (game.swap_ops, "list"),
            "交换": (game.swap_ops, "list"),
            "交换台": (game.swap_ops, "list"),
            "market": (market.market_ops, "list"),
            "集市": (market.market_ops, "list"),
        },
        hoist={},
        default=game.tote_ops,
        help_text=TOTE_HELP,
        empty=TOTE_HELP,
    )


async def alliance_bundle(key_id: int, command: str = "") -> str:
    from . import bottles, game, multi

    return await route(
        key_id,
        command,
        table={
            "contract": (multi.contract_ops, "list"),
            "合约": (multi.contract_ops, "list"),
            "悬赏": (multi.contract_ops, "list"),
            "league": (multi.league_ops, "status"),
            "周目标": (multi.league_ops, "status"),
            "联盟": (multi.league_ops, "status"),
            "board": (multi.league_ops, "board"),
            "贡献榜": (multi.league_ops, "board"),
            "beacon": (game.beacon_ops, "scan"),
            "公告": (game.beacon_ops, "scan"),
            "公告栏": (game.beacon_ops, "scan"),
            "bottle": (bottles.bottle_ops, "scan"),
            "漂流瓶": (bottles.bottle_ops, "scan"),
        },
        hoist={},
        default=multi.alliance_ops,
        help_text=ALLIANCE_HELP,
        empty=ALLIANCE_HELP,
    )


async def visit_bundle(key_id: int, command: str = "") -> str:
    from . import buxing, chaoshen, clinic, cloth, florist, jingshan, lili, lore_ops as lore_mod, marriage, musong, npc, shaonian, tt

    return await route(
        key_id,
        command,
        table={
            "默默": (florist.florist_ops, "visit"),
            "花店": (florist.florist_ops, "visit"),
            "默语花房": (florist.florist_ops, "visit"),
            "momo": (florist.florist_ops, "visit"),
            "lili": (lili.lili_ops, "scan"),
            "栗栗": (lili.lili_ops, "scan"),
            "shaonian": (shaonian.shaonian_ops, "visit"),
            "韶年": (shaonian.shaonian_ops, "visit"),
            "musong": (musong.musong_ops, "visit"),
            "目送": (musong.musong_ops, "visit"),
            "阿槐": (musong.musong_ops, "visit"),
            "jingshan": (jingshan.jingshan_ops, "visit"),
            "敬山": (jingshan.jingshan_ops, "visit"),
            "何敬山": (jingshan.jingshan_ops, "visit"),
            "buxing": (buxing.buxing_ops, "visit"),
            "不醒": (buxing.buxing_ops, "visit"),
            "守灯人": (buxing.buxing_ops, "visit"),
            "tt": (tt.tt_ops, "status"),
            "tt酱": (tt.tt_ops, "status"),
            "杂货": (tt.tt_ops, "status"),
            "杂货店": (tt.tt_ops, "status"),
            "lore": (lore_mod.lore_ops, "scan"),
            "史": (lore_mod.lore_ops, "scan"),
            "clinic": (clinic.clinic_ops, "status"),
            "诊所": (clinic.clinic_ops, "status"),
            "桥桥": (clinic.clinic_ops, "status"),
            "乔乔": (clinic.clinic_ops, "status"),
            "乔乔诊所": (clinic.clinic_ops, "status"),
            "潮生会": (chaoshen.chaoshen_ops, "问"),
            "潮生": (chaoshen.chaoshen_ops, "问"),
            "阿簿": (chaoshen.chaoshen_ops, "问"),
            "chaoshen": (chaoshen.chaoshen_ops, "问"),
            "hui": (chaoshen.chaoshen_ops, "问"),
            "aboo": (chaoshen.chaoshen_ops, "问"),
            "npc": (npc.npc_ops, "list"),
            "漾漾": (cloth.cloth_ops, "visit"),
            "yangyang": (cloth.cloth_ops, "visit"),
            "衣泊坊": (cloth.cloth_ops, "status"),
            "atelier": (cloth.cloth_ops, "status"),
            "连理所": (marriage.marriage_ops, "desk"),
            "理枝": (marriage.marriage_ops, "desk"),
            "lianli": (marriage.marriage_ops, "desk"),
            "民政局": (marriage.marriage_ops, "desk"),
            "婚约": (marriage.marriage_ops, "desk"),
        },
        hoist={
            "treat": (clinic.clinic_ops, True),
            "fortune": (shaonian.shaonian_ops, True),
            "税": (chaoshen.chaoshen_ops, True),
            "岸税": (chaoshen.chaoshen_ops, True),
            "维": (chaoshen.chaoshen_ops, True),
            "岸维": (chaoshen.chaoshen_ops, True),
            "维修": (chaoshen.chaoshen_ops, True),
            "维修费": (chaoshen.chaoshen_ops, True),
            "transfer": (shaonian.shaonian_ops, True),
        },
        default=npc.npc_ops,
        help_text=VISIT_HELP,
        empty=VISIT_HELP,
    )


async def kitchen_bundle(key_id: int, command: str = "") -> str:
    from . import kitchen

    cmd = (command or "").strip() or "menu"
    if cmd.split()[0].lower() == "catalog":
        cmd = "recipes"
    return await _call_ops(kitchen.kitchen_ops, key_id, cmd)

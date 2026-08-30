#!/usr/bin/env python3
"""叙事 / 工具说明 / 逻辑对齐：纪事、cheer 分流、中文岗位、MCP 文案。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def _boot(tmp: Path):
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    return db


async def _enroll(db, email: str, name: str) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
    return row["id"], sid


def test_bar_job_aliases() -> None:
    from server.bar_catalog import resolve_bar_job, resolve_bar_period

    assert resolve_bar_job("洗碗") == "dishwasher"
    assert resolve_bar_job("洗碗工") == "dishwasher"
    assert resolve_bar_job("dishwasher") == "dishwasher"
    assert resolve_bar_job("牛郎") == "host"
    assert resolve_bar_job("调酒师") == "bartender"
    assert resolve_bar_job("杂工") == "runner"
    assert resolve_bar_job("迎宾") == "greeter"
    assert resolve_bar_job("服务生") == "server"
    assert resolve_bar_job("没有这个岗") is None
    assert resolve_bar_period("白班") == "day"
    assert resolve_bar_period("dusk") == "day"
    assert resolve_bar_period("夜班") == "night"
    assert resolve_bar_period("night") == "night"


def _tool_blob(mcp, name: str) -> str:
    tool = mcp._tool_manager.get_tool(name)
    cmd = (tool.parameters.get("properties") or {}).get("command", {}).get("description", "")
    return f"{tool.description}\n{cmd}"


def _schema_budget() -> None:
    """连接时 schema 必须短：全工具 JSON + instructions 控制在约 5k 字以内。"""
    import json
    from server.mcp_app import mcp

    parts = [mcp.instructions or ""]
    for name in mcp._tool_manager._tools:
        t = mcp._tool_manager.get_tool(name)
        parts.append(
            json.dumps(
                {"name": name, "description": t.description, "inputSchema": t.parameters},
                ensure_ascii=False,
            )
        )
    total = sum(len(p) for p in parts)
    assert total < 5000, f"MCP schema too large for connect-time budget: {total} chars"


def test_mcp_descriptions() -> None:
    """MCP schema 极短：用途 + 空 command + 2～3 例 + 易混点。细则在 relay_manual / help。"""
    from server.mcp_app import mcp

    _schema_budget()

    plot = _tool_blob(mcp, "plot_ops")
    assert "空 command 看各地块" not in plot
    assert "status" in plot and "sow 1 甘蓝" in plot
    assert "sow_all" in plot or "plant" in plot

    tide = _tool_blob(mcp, "tide_ops")
    assert "dig" in tide and ("崖矿" in tide or "mine" in tide or "赶海" in tide or "≠" in tide)

    tote = _tool_blob(mcp, "tote_ops")
    assert "vend" in tote and ("gift" in tote or "送礼" in tote)

    star = _tool_blob(mcp, "star_ops")
    assert "小橘" in star and "应援" in star and "围观" in star
    assert "面板" in star

    theater = _tool_blob(mcp, "theater_ops")
    for word in ("试镜", "对戏", "演出", "领薪"):
        assert word in theater, word

    bar = _tool_blob(mcp, "bar_ops")
    assert "洗碗" in bar and "荔栀" in bar

    steward = _tool_blob(mcp, "steward_ops")
    assert "enroll" in steward and "岛缘" in steward and "引航" in steward
    assert "invite_ops" in steward

    ut = _tool_blob(mcp, "undertide_ops")
    assert "猫猫" in ut and "岛缘" in ut and "help" in ut

    alliance = _tool_blob(mcp, "alliance_ops")
    assert "贡献榜" in alliance or "board" in alliance

    visit = _tool_blob(mcp, "visit_ops")
    assert "潮生会" in visit and "不能加入" in visit
    assert "税" in visit and "漾漾" in visit

    hut = _tool_blob(mcp, "hut_ops")
    assert "睡" in hut and ("岸维" in hut or "upkeep" in hut)

    kitchen = _tool_blob(mcp, "kitchen_ops")
    assert "eat" in kitchen and ("shop dine" in kitchen or "下馆子" in kitchen)
    assert "eat_ops" in kitchen

    lounge = _tool_blob(mcp, "lounge_ops")
    assert "暗号" in lounge and "红包" in lounge
    assert "婚期" in lounge or "无限" in lounge

    wall = _tool_blob(mcp, "wall_ops")
    assert "听潮亭" in wall and "看亭" in wall
    assert "贴 问事" in wall and "看 12" in wall
    assert "聊天室" in wall or "厅示" in wall or "全服榜" in wall

    manual = mcp._tool_manager.get_tool("relay_manual").description or ""
    assert ("禁止发明" in manual or "编指令" in manual) and "enroll" in manual and "无参数" in manual

    instructions = mcp.instructions or ""
    assert "relay_manual" in instructions
    assert "不是聊天沙盒" in instructions or "禁止发明" in instructions
    assert "21" in instructions and "help" in instructions

    quarry = _tool_blob(mcp, "quarry_ops")
    assert "status" in quarry and "探脉" in quarry and "mine_ops" in quarry

    craft = _tool_blob(mcp, "craft_ops")
    assert "打 铜钉" in craft and "forge_ops" in craft

    cloth = _tool_blob(mcp, "cloth_ops")
    assert "漾漾" in cloth and "委托 短褂 海色" in cloth and "tailor_ops" in cloth
    assert "空" in cloth and "看坊" in cloth

    marriage = _tool_blob(mcp, "marriage_ops")
    assert "求婚" in marriage and "propose_marriage" in marriage
    assert "空" in marriage

    # 细则仍须在手册 / help（schema 不再重复）
    import asyncio
    from server import game
    from server.star import STAR_HELP

    man = asyncio.run(game.relay_manual())
    for needle in (
        "潮生会 税 交", "潮生会 维 交", "潮生会 基金 捐 50", "tax_ops", "upkeep_ops",
        "订婚没有彩礼", "离婚 答应", "潮誓戒", "竹钓竿", "未命名小鱼",
        "堆肥桶 存 羊粪", "sow_all", "偷菜",
    ):
        assert needle in man, needle
    assert "平常回10" in STAR_HELP
    assert "小剧场专场每日5次" in STAR_HELP


def test_relay_manual_covers_systems() -> None:
    from server import game

    text = asyncio.run(game.relay_manual())
    needles = [
        "sow 1 甘蓝",
        "tend 1",
        "plot_ops status",
        "camera install",
        "incident",
        "repair",
        "shed erect",
        "commons scan",
        "dove",
        "swap ",
        "market ",
        "market 扩",
        "brew",
        "每天 10 次",
        "每天 24 次",
        "shop open",
        "shop stock 菜名 [价格]",
        "价格自定",
        "饱餐",
        "饭馆卖堂食",
        "hut_ops 睡",
        "刷新上手页不会回精力",
        "游戏日换班",
        "buy bed",
        "lodge",
        "shaonian",
        "musong visit",
        "musong send 安",
        "musong remember",
        "jingshan visit",
        "jingshan order",
        "jingshan deliver",
        "jingshan revisit",
        "何敬山",
        "苏月琴不是单独 NPC",
        "gear upgrade",
        "boss attack",
        "barn erect",
        "堆肥桶",
        "buy compost_bin",
        "桶不是柜子",
        "空槽也能装",
        "基础每格 24",
        "tote_ops 扩栈",
        "mascot adopt",
        "lili summon",
        "clinic treat",
        "clinic 调理",
        "clinic 调理 中",
        "回春汤",
        "undertide_ops help",
        "star_ops",
        "小剧场专场每日 5 次",
        "theater_ops",
        "试镜",
        "头粉",
        "编剧社",
        "投稿 岸上旧收音机",
        "故事稿费 500",
        "cloth_ops",
        "衣泊坊",
        "漾漾",
        "委托 短褂 海色",
        "不卖成衣",
        "不绝版",
        "tailor_ops",
        "/atelier",
        "marriage_ops",
        "propose_marriage",
        "岛上不问你爱的是谁",
        "求婚 阿潮",
        "只问对方有没有答应",
        "连理所",
        "离婚 答应",
        "理枝",
        "彩礼 8888",
        "潮誓戒",
        "临海邸",
        "大约四万",
        "上限十万",
        "免得攀比",
        "订婚没有彩礼",
        "订婚 寻信",
        "举行前还能改",
        "订婚宴选了还能改",
        "订婚 续请",
        "旧档自动写下",
        "今日岛上有婚礼",
        "全站换成婚礼页",
        "?go=plot",
        "婚期顶栏进连理所",
        "顶上管理员/在线",
        "聊天室大厅也会通报一句",
        "tale_ops 潮闻不给旧衣料",
        "plot_ops forage",
        "潮闻",
        "应援",
        "不要猜",
        "sow_all",
        "eat_ops",
        "steward_ops board",
        "1～99",
        "潮汐本尊",
        "岛缘",
        "岛缘榜",
        "board 岛缘",
        "steward_ops 岛缘",
        "引航",
        "绑定",
        "invite_ops",
        "100 工分票和 20 岛缘",
        "alliance_ops board",
        "visit_ops 潮生会",
        "不能入会",
        "阿簿",
        "潮汐基金",
        "票数自己填",
        "潮生会 基金 捐 50",
        "潮生会 税",
        "潮生会 税 交",
        "潮生会 维",
        "潮生会 维 交",
        "岛民不能贴",
        "wall_ops",
        "听潮亭",
        "贴 问事",
        "forum_ops",
        "岸税",
        "岸维",
        "产业单价至少 10 票",
        "超出起步每天岸维 20",
        "每座每天岸维 30",
        "每天收",
        "超额累进",
        "没有 tax_ops",
        "mascot upkeep",
        "周二",
        "顶 2500",
        "高档加码",
        "潮宗 36%",
        "铺多了加档",
        "潮差",
        "潮锈",
        "买地买园不算",
        "先托到 800",
        "kitchen_ops eat",
        "下馆子",
        "shop dine",
        "bar_ops work",
        "甘蓝种×2",
        "不占露天份地",
        "露天无上限",
        "份地不种果树",
        "买园",
        "比份地贵",
        "160/240/360",
        "sow 园1 芒果",
        "sow 园1 橘子",
        "橘子",
        "糖渍橘子",
        "cook 糖渍橘子",
        "一周一季",
        "当季可种",
        "温室种菜种树都不受季节",
        "sow 棚1 橘子",
        "买棚",
        "只搅山羊奶",
        "不是每日自动扣",
        "compliment 和 release",
        "不能网",
        "腿鱼小咒",
        "eat 未命名小鱼",
        "vend 未命名小鱼",
        "dig 和 probe 都关",
        "quarry_ops",
        "买镐",
        "探脉",
        "洗 海盐砂",
        "开坑 确认",
        "mine_ops",
        "岩尘入肺",
        "craft_ops",
        "打 铜钉",
        "打 潮纹秤锤",
        "捐 砧上全套",
        "雾铅网坠",
        "/workshop",
        "/tide",
        "/huts",
        "/star",
        "/allotments",
        "/market",
        "能直接送票",
        "tote_ops gifts",
        "随机事件整体 +30%",
        "旧史文本",
        "不是流水",
        "真人在面板",
        "tale_ops",
        "story_ops",
        "accept black_box_lover",
        "accept memory_tide",
        "回忆生潮",
        "11×30=330",
        "总票奖励 450",
        "陪坐的人",
        "accept spring_beyond_mountain",
        "春山之外",
        "explore shenzhi_home",
        "山外见春人",
        "accept mr_ke",
        "克先生",
        "explore ke_shop",
        "13×30=390",
        "总票奖励 510",
        "accept tonight_damp",
        "今夜潮湿",
        "explore rain_woods",
        "湿夜旁听人",
        "5×30=150",
        "总票奖励 270",
        "accept unhappy_service",
        "很不高兴为您服务",
        "explore warehouse_corner",
        "总票奖励 300",
        "review [任务key]",
        "一次回顾该潮闻从第一幕到结尾",
        "只重读、不重发",
        "souvenirs",
        "reminisce black_box_lover",
        "自动补发8件",
        "永久纪念品",
        "6×30=180",
        "总票奖励 230",
        "阶段2 explore sea",
        "错误地点不扣",
        "不限次数",
        "start cinderella",
        "start left_for_tomorrow",
        "explore guyan_home",
        "留给明天",
        "今天的人",
        "inspect queen",
        "prepare backdoor|broadcast|trap",
        "choose escape|judgment|hunt|rescue",
        "review [故事key]",
        "一次回顾完整人物故事",
        "只重读、不重复发",
        "岛上回忆",
        "保存每次实际完成路线",
        "午夜前共 60 分钟",
        "平常回 10、好回 15、极好回 20",
        "极差额外反噬 10",
        "每满 20 票再回 +1",
        "一周一次",
        "3万以上",
        "低中高随机",
        "进价九成",
        "/play 点按同一套指令",
        "共用一个号",
        "点单打赏只在 /play",
        "邻居名册",
        "/manual",
        "暗号 潮声今晚",
        "小包间",
        "对话上方",
        "红包 100 5",
        "hongbao_ops",
    ]
    missing = [n for n in needles if n not in text]
    assert not missing, f"relay_manual missing: {missing}"
    assert "steward_sheet" not in text
    assert "relay_manual()" not in text
    assert "duo" not in text
    assert "潮生会 周" not in text
    assert "潮生会 捐 甘蓝" not in text
    assert "潮生会 公物" not in text
    assert "beacon post" not in text


def test_readme_workflow_rules() -> None:
    root = Path(__file__).resolve().parents[2]
    readme = (root / "README.md").read_text(encoding="utf-8")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    for blob in (readme, agents):
        assert "merge origin/main" in blob
        assert "relay_manual" in blob
        assert "mcp_app.py" in blob
        assert "island-manual-content.html" in blob or "island-manual.html" in blob
    assert "21 个工具" in readme
    assert "marriage_ops" in readme
    assert "propose_marriage" in readme
    assert "/vow" in readme
    assert "/lianli" in readme
    assert "/hearth" in readme
    assert "quarry_ops" in readme
    assert "craft_ops" in readme
    assert "/workshop" in readme
    assert "盐风崖" in readme
    assert "/quarry" in readme
    assert "围观" in readme.split("/quarry", 1)[1][:80]
    index_html = (root / "allotment-relay/server/templates/index.html").read_text(encoding="utf-8")
    place_html = (root / "allotment-relay/server/templates/place.html").read_text(encoding="utf-8")
    promo = (root / "allotment-relay/server/promo.py").read_text(encoding="utf-8")
    nav = (root / "allotment-relay/server/templates/partials/nav.html").read_text(encoding="utf-8")
    assert "craft_ops" in promo
    assert "tide_ops" in promo
    assert "hut_ops" in promo
    assert "tote_ops market" in promo
    assert "/play" in promo
    assert '"/workshop"' in promo
    assert "routes" in index_html
    assert "今天想去哪" in index_html
    assert "data-open-island" in index_html
    assert "play_href" in place_html
    assert "promo-poster" in place_html
    assert 'href="/workshop"' in nav
    assert 'href="/play"' in nav
    assert 'href="/island"' in nav
    assert 'href="/manual"' in nav
    assert "手册" in nav
    assert 'href="/tide"' in nav
    assert 'href="/huts"' in nav
    assert 'href="/market"' in nav
    assert 'href="/board"' in nav
    assert "全服榜" in nav
    assert "island-drawer" in nav
    assert "nav-island" in nav
    css = (root / "allotment-relay/server/static/style.css").read_text(encoding="utf-8")
    assert "@media (max-width: 980px)" in css
    assert ".island-drawer" in css
    assert "min(430px, 92vw)" in css
    assert "min-height: 72px" in css
    assert ".island-drawer-group + .island-drawer-group" in css
    assert ".routes" in css
    assert "repeat(3" in css
    assert "mobile-island" in css
    assert "forage" in readme
    assert "amends" in readme
    assert "砧上全套" in readme
    assert "满级 99" in readme or "1～99" in readme
    assert "岛缘榜" in readme
    assert "steward_ops" in readme and "plot_ops" in readme and "bar_ops" in readme
    assert "quarry_ops" in readme
    assert "tale_ops" in readme
    assert "story_ops" in readme
    assert "theater_ops" in readme
    assert "cloth_ops" in readme
    assert "/atelier" in readme
    assert "空 command" in readme
    assert "禁止" in readme
    assert "引航" in readme
    assert "绑定 AB12CD34" in readme
    assert "INVITE_ADMIN_KEY" in readme
    assert "HUI_KEY" in readme
    assert "/hui-owner" in readme


def test_human_island_manual() -> None:
    """给人类看的使用手册必须跟现行玩法对齐，且不把 MCP 当操作步骤。"""
    pkg = Path(__file__).resolve().parents[1]
    repo = pkg.parent
    content = (pkg / "server/templates/partials/island-manual-content.html").read_text(encoding="utf-8")
    css = (pkg / "server/static/island-manual.css").read_text(encoding="utf-8")
    manual_html = (pkg / "server/templates/manual.html").read_text(encoding="utf-8")
    pointer = (repo / "docs/island-manual.md").read_text(encoding="utf-8")
    main_py = (pkg / "server/main.py").read_text(encoding="utf-8")
    config_py = (pkg / "server/config.py").read_text(encoding="utf-8")
    blob = content + css
    for needle in (
        "岸维",
        "岸税",
        "岛缘",
        "/play",
        "每 2 天",
        "产业单价至少 10",
        "果园 20",
        "温室 30",
        "顶 2500",
        "高档加码",
        "铺多了加档",
        "潮差",
        "潮锈",
        "买地买园不算",
        "先托到 800",
        "引航",
        "欠岸维",
        "去潮生会",
        "一周一季",
        "上手页",
        "潮生会",
        "海报",
        "有效岛民",
        "小馆停堂",
        "人和管家",
        "编剧社",
        "诊所地点",
        "调理",
        "回春汤",
        "今夜潮湿",
        "很不高兴为您服务",
        "留给明天",
        "暗号",
        "小包间",
        "聊天框顶上",
        "红包",
        "抢红包",
        "发红包",
        "衣泊坊",
        "漾漾",
        "不卖成衣",
        "不绝版",
        "不能贴",
        "厅示",
        "听潮亭",
        "木牌",
        "婚约",
        "确认页",
        "不用注册",
        "岛上不问你爱的是谁",
        "连理所",
        "理枝",
        "离婚",
        "彩礼",
        "潮誓戒",
        "临海邸",
        "大约四万",
        "上限十万",
        "免得攀比",
        "最高档",
        "花出去",
        "不进潮汐基金",
        "订婚",
        "跳过",
        "不用彩礼",
        "举行前还能改",
        "订婚宴选了还能改",
        "订婚确认",
        "以前系统自动写下",
        "刷新上手页不会回精力",
        "今日岛上有婚礼",
        "全站换成婚礼页",
        "我的份地",
        "种地去上手页",
        "底栏「份地」",
        "全岛登记人数",
        "/island",
        "手机地图",
        "进入地图",
        "不要停在微信里",
        "一键收获",
        "点总览图上的份地就进",
        "点总览图上的份地",
        "一页最多 9 块",
        "海边草地底图",
        "不是一块纯绿",
        "左右滑切页",
        "回地图",
        "左上角贴边的迷你「返回地图」",
        "右上角迷你「背包」",
        "贴边",
        "总览图上不显示背包",
        "没有顶栏、没有底栏",
        "没有去上手页按钮",
        "回地图、浇水、种植叠在一起的白卡",
        "铺满一屏",
        "底下不漏一块色",
        "点总览图上的地名",
        "岸畔小馆",
        "菜地已经种满了",
        "果园已经种满了",
        "温室已经种满了",
        "种植面板里买一份",
        "点空地打开种植面板",
        "打理、浇水、施肥",
        "底下没有浇水、种菜地大按钮",
        "点草地开垦",
        "一页开满会多一页草地",
        "还没有棚时也是一页草地",
        "杂货铺、灯塔、岸工坊、潮汐公告",
        "杂货铺能买种",
        "同一家 Tt酱",
        "进了具体地点只显示地名",
        "还没做到",
        "港口（海边）",
        "剧场看台",
        "聊天室大厅也会出现一句通报",
    ):
        assert needle in blob, needle
    assert "plot_ops" not in blob
    assert "sow_all" not in blob
    assert "chapter-jump" not in content
    assert 'include "partials/nav.html"' in manual_html
    assert "/manual" in pointer
    assert "island-manual-content.html" in pointer
    assert '"/manual"' in main_py
    assert "manual.html" in main_py
    assert "ISLAND_MANUAL_CONTENT" in config_py


def test_register_key_copy_ui() -> None:
    root = Path(__file__).resolve().parents[1]
    keys_js = (root / "server/static/keys.js").read_text(encoding="utf-8")
    css = (root / "server/static/style.css").read_text(encoding="utf-8")
    register_html = (root / "server/templates/register.html").read_text(encoding="utf-8")
    recover_html = (root / "server/templates/recover.html").read_text(encoding="utf-8")
    assert "copyText" in keys_js
    assert "secret-copy" in keys_js
    assert "Authorization: Bearer" in keys_js
    assert "break-all" in css
    assert "pre-wrap" in css
    assert "/static/keys.js" in register_html
    assert "/static/device.js" in register_html
    assert "/manual" in register_html
    assert "/static/keys.js" in recover_html
    assert "/static/device.js" in recover_html


def test_patron_pages_share_steward_key() -> None:
    """点单打赏、聊天、看档都只在 /play；地点围观页只读。凭证只在上手页绑定。"""
    root = Path(__file__).resolve().parents[1]
    site_key = (root / "server/static/site-key.js").read_text(encoding="utf-8")
    assert "tidal_island_steward_api_key" in site_key
    assert "loadSavedKey" in site_key
    assert "fetchBoundSteward" in site_key
    lounge_js = (root / "server/static/lounge.js").read_text(encoding="utf-8")
    play_html = (root / "server/templates/play.html").read_text(encoding="utf-8")
    play_js = (root / "server/static/play.js").read_text(encoding="utf-8")
    index_html = (root / "server/templates/index.html").read_text(encoding="utf-8")
    place_html = (root / "server/templates/place.html").read_text(encoding="utf-8")
    bar_html = (root / "server/templates/bar.html").read_text(encoding="utf-8")
    tide_html = (root / "server/templates/tide.html").read_text(encoding="utf-8")
    market_html = (root / "server/templates/market.html").read_text(encoding="utf-8")
    eatery_html = (root / "server/templates/eatery.html").read_text(encoding="utf-8")
    bar_js = (root / "server/static/bar.js").read_text(encoding="utf-8")
    tide_js = (root / "server/static/tide.js").read_text(encoding="utf-8")
    market_js = (root / "server/static/market.js").read_text(encoding="utf-8")
    eatery_js = (root / "server/static/eatery.js").read_text(encoding="utf-8")
    promo = (root / "server/promo.py").read_text(encoding="utf-8")
    main_py = (root / "server/main.py").read_text(encoding="utf-8")
    assert "saveSiteKey" in play_js
    assert "loadSavedKey" in lounge_js
    assert "playLounge" in lounge_js
    assert "/static/site-key.js" in play_html
    assert "/static/style.css" in play_html
    island_html = (root / "server/templates/island.html").read_text(encoding="utf-8")
    island_api = (root / "server/static/island/api.js").read_text(encoding="utf-8")
    assert "/static/site-key.js" in island_html
    assert "/static/island/boot.js" in island_html
    assert 'id="island-enter"' in island_html
    assert "tidal_island_steward_api_key" in island_api
    assert "/api/v1/" in island_api
    assert 'href="/play"' not in island_html
    assert "去上手页" not in island_html
    assert 'partials/nav.html' in play_html
    assert "play-top" not in play_html
    assert "loadSavedKey" in play_js
    assert "/api/bar/order" in play_js
    assert "/api/bar/duo" in play_js
    assert "/api/eatery/order" in play_js
    assert "/api/star/tip" in play_js
    assert 'id="play-place"' in play_html
    assert 'id="play-place-actions"' in play_html
    assert "place-workspace" in play_html
    assert "place-toolrail" in play_html
    assert "place-workarea" in play_html
    assert "play-place-live" in play_html
    assert "place-tool" in play_js
    assert "selectPlaceTool" in play_js
    assert '"href": "/quarry"' in (root / "server/play.py").read_text(encoding="utf-8")
    assert '"href": "/workshop"' in (root / "server/play.py").read_text(encoding="utf-8")
    assert '"href": "/atelier"' in (root / "server/play.py").read_text(encoding="utf-8")
    assert '"href": "/ting"' in (root / "server/play.py").read_text(encoding="utf-8")
    assert 'id="play-cloth-sew"' in play_html
    assert 'id="play-cloth-wear-btn"' in play_html
    assert 'id="play-duo-key-b"' in play_html
    assert 'id="play-bar-order"' in play_html
    assert 'id="play-eatery-order"' in play_html
    assert 'id="play-star-tip"' in play_html
    assert 'id="play-hui-donate"' in play_html
    assert 'id="play-hui-donate-amount"' in play_html
    assert 'id="play-lounge"' in play_html
    assert 'id="play-wall"' in play_html
    assert 'id="play-neighbors"' in play_html
    assert 'id="play-me"' in play_html
    assert 'id="memory-modal"' in play_html
    assert 'id="play-today"' in play_html
    assert "play-dock" in play_html
    assert "今天也在岛上" in play_html
    assert "/api/steward/memory" in play_js
    assert "data-memory-filter" in play_js
    assert "连续阅读" in play_js
    assert "duesUrgent" in play_js
    assert "island_bond" in play_js
    assert "去潮生会" in play_js
    assert "/static/site-key.js" not in index_html
    assert "/static/site-key.js" not in place_html
    assert "/static/site-key.js" not in bar_html
    assert "/static/site-key.js" not in tide_html
    assert "/static/site-key.js" not in market_html
    assert "/static/site-key.js" not in eatery_html
    huts_html = (root / "server/templates/huts.html").read_text(encoding="utf-8")
    assert "/static/site-key.js" not in huts_html
    star_html = (root / "server/templates/star.html").read_text(encoding="utf-8")
    assert "/static/site-key.js" not in star_html
    allo_html = (root / "server/templates/allotments.html").read_text(encoding="utf-8")
    assert "/static/site-key.js" not in allo_html
    assert 'id="order-form"' not in index_html
    assert 'id="duo-form"' not in index_html
    assert 'id="tip-form"' not in index_html
    assert "今天想去哪" in index_html
    assert "routes" in index_html
    assert 'href="/manual"' in play_html
    assert 'href="/manual"' in index_html
    assert '@app.get("/manual"' in main_py
    assert '"go": "bar"' in promo
    assert '"go": "eatery"' in promo
    assert '"go": "star"' in promo
    assert '"go": "hui"' in promo
    assert '"go": "ting"' in promo
    assert 'RedirectResponse("/play?go=me"' in main_py
    assert 'lounge.html"' in main_py
    assert 'RedirectResponse("/play?go=lounge"' not in main_py
    assert "place.html" in main_py
    assert "_place_page" in main_py
    assert 'tide.html"' in main_py
    assert 'bar.html"' in main_py
    assert 'market.html"' in main_py
    assert 'eatery.html"' in main_py
    assert 'board.html"' in main_py
    assert 'huts.html"' in main_py
    assert 'star.html"' in main_py
    assert 'allotments.html"' in main_py
    assert 'quarry.html"' in main_py
    assert 'workshop.html"' in main_py
    assert 'hui.html"' in main_py
    assert 'ting.html"' in main_py
    assert '@app.get("/atelier"' in main_py
    lounge_html = (root / "server/templates/lounge.html").read_text(encoding="utf-8")
    assert "/static/site-key.js" in lounge_html
    assert "lounge-page" in lounge_html
    assert "playLounge.start" in lounge_js
    assert "lounge-page" in lounge_js
    assert 'id="lounge-booth-code"' in lounge_html
    assert 'id="lounge-booth-enter"' in lounge_html
    assert "对暗号" in lounge_html
    assert "lounge-booth-bar" in lounge_html
    aside = lounge_html.split("lounge-side", 1)[1].split("</aside>", 1)[0]
    chat = lounge_html.split('class="lounge-chat"', 1)[1]
    assert 'id="lounge-booth-code"' not in aside
    assert 'id="lounge-booth-code"' in chat
    assert "lounge-booth-bar" in (root / "server/static/style.css").read_text(encoding="utf-8")
    assert 'id="lounge-booth-code"' in play_html
    assert "/api/lounge/booth" in lounge_js
    assert "POST" in lounge_js
    assert "/api/lounge/packet" in lounge_js
    assert "/api/lounge/grab" in lounge_js
    assert "发红包" in lounge_html
    assert 'id="lounge-packet-btn"' in lounge_html
    chat = lounge_html.split('class="lounge-chat"', 1)[1]
    assert 'id="lounge-packet-btn"' in chat
    assert 'id="lounge-packet-btn"' in play_html
    board_html = (root / "server/templates/board.html").read_text(encoding="utf-8")
    board_js = (root / "server/static/board.js").read_text(encoding="utf-8")
    board_css = (root / "server/static/board.css").read_text(encoding="utf-8")
    huts_js = (root / "server/static/huts.js").read_text(encoding="utf-8")
    huts_css = (root / "server/static/huts.css").read_text(encoding="utf-8")
    star_js = (root / "server/static/star.js").read_text(encoding="utf-8")
    star_css = (root / "server/static/star.css").read_text(encoding="utf-8")
    allo_js = (root / "server/static/allotments.js").read_text(encoding="utf-8")
    allo_css = (root / "server/static/allotments.css").read_text(encoding="utf-8")
    quarry_html = (root / "server/templates/quarry.html").read_text(encoding="utf-8")
    quarry_js = (root / "server/static/quarry.js").read_text(encoding="utf-8")
    quarry_css = (root / "server/static/quarry.css").read_text(encoding="utf-8")
    workshop_html = (root / "server/templates/workshop.html").read_text(encoding="utf-8")
    workshop_js = (root / "server/static/workshop.js").read_text(encoding="utf-8")
    workshop_css = (root / "server/static/workshop.css").read_text(encoding="utf-8")
    hui_html = (root / "server/templates/hui.html").read_text(encoding="utf-8")
    hui_js = (root / "server/static/hui.js").read_text(encoding="utf-8")
    hui_css = (root / "server/static/hui.css").read_text(encoding="utf-8")
    ting_html = (root / "server/templates/ting.html").read_text(encoding="utf-8")
    ting_js = (root / "server/static/ting.js").read_text(encoding="utf-8")
    ting_css = (root / "server/static/ting.css").read_text(encoding="utf-8")
    nav = (root / "server/templates/partials/nav.html").read_text(encoding="utf-8")
    assert "/api/public/bar" in bar_js
    assert "/api/public/tide" in tide_js
    assert "/api/public/market" in market_js
    assert "/api/public/eatery" in eatery_js
    assert "/api/public/board" in board_js
    assert "/api/public/huts" in huts_js
    assert "/api/public/star" in star_js
    assert "/api/public/allotments" in allo_js
    assert "/api/public/quarry" in quarry_js
    assert "/api/public/workshop" in workshop_js
    assert "/api/public/hui" in hui_js
    assert "hui-fund" in hui_js
    assert "hui-tax" in hui_js
    assert "hui-upkeep" in hui_js
    assert "hui-tax" in hui_html
    assert "hui-upkeep" in hui_html
    assert "岸税" in hui_html
    assert "岸维" in hui_html
    assert "/api/public/stats" in allo_js
    assert "withHeroStats" in allo_js
    assert '@app.get("/api/public/stats")' in main_py
    assert '@app.get("/api/public/weddings")' in main_py
    assert "place-live.css" in bar_html
    assert "place-live.css" in tide_html
    assert "place-live.css" in market_html
    assert "place-live.css" in eatery_html
    assert "board.css" in board_html
    assert "huts.css" in huts_html
    assert "star.css" in star_html
    assert "allotments.css" in allo_html
    assert "quarry.css" in quarry_html
    assert "workshop.css" in workshop_html
    assert "hui.css" in hui_html
    assert "place-live.css" in hui_html
    assert "/api/public/ting" in ting_js
    assert "ting.css" in ting_html
    assert "place-live.css" in ting_html
    assert "听潮亭" in ting_html
    assert "/play?go=ting" in ting_html
    assert "play-wall" in play_html
    assert "/static/wall.js" in play_html
    assert "/static/site-key.js" not in quarry_html
    assert "/static/site-key.js" not in workshop_html
    assert "ranking-stage" in board_html
    assert "dual-board" in board_html
    assert "ticketsBoard" in board_html
    assert "levelBoard" in board_html
    assert "岛缘榜" in board_html
    assert "全服榜" in nav
    assert "ticket_lead" in board_js or "ticket-lead" in board_js
    assert ".dual-board" in board_css
    assert "huts-hero" in huts_html
    assert "residentList" in huts_html
    assert "featureLevel" in huts_html
    assert "shore_blurb" in huts_js
    assert "resident-list" in huts_css
    assert "hero-grid" in star_html
    assert "star-poster" in star_html
    assert 'class="poster"' not in star_html
    assert "fanBoard" in star_html
    assert "orange-fruit" in star_html
    assert "stageBanner" in star_js or "stage-banner" in star_css
    assert "fan-ticket" in star_css
    assert ".star-poster" in star_css
    assert "position: relative" in star_css
    assert "inset: auto" in star_css
    assert "allo-board" in allo_html
    assert "allo-people" in allo_html or 'id="people"' in allo_html
    assert "vegGrid" in allo_html
    assert "orchGrid" in allo_html
    assert "glassGrid" in allo_html
    assert "allo-person" in allo_js
    assert "ready_count" in allo_js
    assert "parcel_count" in allo_js
    assert "orchard_count" in allo_js
    assert "loadJson" in allo_js
    assert "typeof islandFmtStamp" in allo_js
    assert ".allo-board" in allo_css
    assert ".allo-person" in allo_css
    assert ".allo-plot" in allo_css
    assert "q-hero" in quarry_html
    assert "quarry-veins" in quarry_html
    assert "quarry-feed" in quarry_html
    assert "q-vein" in quarry_js
    assert ".q-hero" in quarry_css
    assert "ws-scene" in workshop_html
    assert "ws-feed" in workshop_html
    assert "ws-jobtags" in workshop_html
    assert "active_jobs" in workshop_js
    assert ".ws-scene" in workshop_css
    assert 'href="/board"' in nav
    assert 'href="/huts"' in nav
    assert 'href="/star"' in nav
    assert 'href="/allotments"' in nav
    assert 'href="/hui"' in nav
    assert "潮生会" in nav
    assert 'href="/ting"' in nav
    assert "听潮亭" in nav
    assert 'href="/lounge"' in nav
    assert "聊天室" in nav
    assert "全服榜" in nav
    assert "岸畔小屋" in nav
    assert "小橘星光" in nav
    assert "份地" in nav
    assert "place-hero" in bar_html
    assert "tide-hero" in tide_html
    assert "market-head" in market_html
    assert "stall-street" in market_html
    assert "eatery-entry" in eatery_html
    assert "face-brows" in eatery_html
    assert "menu-book" in eatery_html
    assert "/play?go=bar" in bar_html
    assert "/play?go=tide" in tide_html
    assert "/play?go=market" in market_html
    assert "/play?go=eatery" in eatery_html
    assert "/play?go=hut" in huts_html
    assert "/play?go=star" in star_html
    assert "/play?go=quarry" in quarry_html
    assert "/play?go=craft" in workshop_html
    assert "/play?go=hui" in hui_html
    assert "/play?go=ting" in ting_html
    assert "不能入会" in hui_html or "不入会" in hui_html
    assert "潮汐基金" in hui_html
    assert "hui-fund" in hui_html
    assert "hui-week" not in hui_html
    assert "公仓" not in hui_html
    assert "/play?go=plot" in allo_html or 'href="/play"' in allo_html
    assert "上手页" in site_key


def test_promo_place_pages() -> None:
    from server import promo

    slugs = {p["slug"] for p in promo.PLACES}
    for slug in ("allotments", "tide", "huts", "bar", "eatery", "market", "quarry", "workshop", "star", "atelier", "undertide", "hui", "ting", "lianli"):
        assert slug in slugs, slug
        ctx = promo.page_context(slug)
        assert ctx["play_href"].startswith("/play")
        assert ctx["place"]["aside"]
        assert ctx["place"]["path"] == f"/{slug}"
        assert "围观" not in ctx["place"]["lead"]
        assert "只围观" not in " ".join(ctx["place"]["body"])
    groups = promo.home_route_groups()
    assert len(groups) == 3
    assert all(g["places"] for g in groups)
    assert promo.home_elsewhere()["slug"] == "undertide"
    assert promo.play_href(promo.get("allotments")) == "/play"
    assert promo.play_href(promo.get("bar")) == "/play?go=bar"
    assert promo.play_href(promo.get("workshop")) == "/play?go=craft"
    assert promo.play_href(promo.get("hui")) == "/play?go=hui"
    assert promo.play_href(promo.get("ting")) == "/play?go=ting"
    assert promo.play_href(promo.get("atelier")) == "/play?go=atelier"
    assert promo.play_href(promo.get("lianli")) == "/play?go=lianli"


def test_bar_ops_help() -> None:
    from server import bar

    text = asyncio.run(bar.bar_ops(0, "help"))
    assert "work 岗位" in text
    assert "cheer" in text
    assert "lodge" in text
    assert "duo" not in text or "没有 duo" in text
    assert "set_mood" not in text or "没有" in text


async def test_scrump_victim_chronicle() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="consist-scrump-"))
    db = await _boot(tmp)
    from server import events

    _, vic_sid = await _enroll(db, "vic@example.com", "邻乙")
    steward = await db.get_steward_by_id(vic_sid)
    async with db.connect() as conn:
        await conn.execute(
            """
            UPDATE parcels SET crop='kale', planted_at=?, tended=1, greenhouse=0,
            grow_target=120 WHERE steward_id=? AND slot=1 AND COALESCE(orchard,0)=0
            """,
            (db.now() - 10_000, vic_sid),
        )
        result = await events._scrump_victim(conn, steward)
        await conn.commit()
        assert result is not None, "ripe plot should be nibbleable"
        row = await (await conn.execute(
            "SELECT text FROM chronicle WHERE action='scrump' AND target_id=?",
            (vic_sid,),
        )).fetchone()
        assert row, "chronicle missing"
        assert "邻乙" in row[0] and "羽衣甘蓝" in row[0], row[0]


async def test_cheer_targets_isolated() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="consist-cheer-"))
    db = await _boot(tmp)
    from server import bar, undertide

    kid, sid = await _enroll(db, "cheer@example.com", "哄客")
    async with db.connect() as conn:
        ut = await undertide._ensure_ut(conn, sid)
        await conn.execute(
            "UPDATE steward_undertide SET access=1, well_hint=1 WHERE steward_id=?",
            (sid,),
        )
        await conn.commit()

    lizhi = await bar.bar_ops(kid, "cheer 今晚酒香")
    assert "荔栀" in lizhi or "提议" in lizhi, lizhi

    cat = await undertide.undertide_ops(kid, "cheer 账本漂亮")
    assert "说太多" not in cat, cat
    assert "猫猫" in cat or "提议" in cat or "贫嘴" in cat, cat

    again_lizhi = None
    try:
        await bar.bar_ops(kid, "cheer 再哄一次")
        raise AssertionError("lizhi daily cheer should block")
    except ValueError as exc:
        again_lizhi = str(exc)
    assert "说过一次" in again_lizhi, again_lizhi

    try:
        await undertide.undertide_ops(kid, "cheer 再哄猫")
        raise AssertionError("cat daily cheer should block")
    except ValueError as exc:
        assert "说过一次" in str(exc), exc


async def test_kitchen_vend_chinese_and_incident_hint() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="consist-vend-"))
    db = await _boot(tmp)
    from server import catalog, events, kitchen

    kid, sid = await _enroll(db, "cook@example.com", "厨子")
    dish = catalog.dish_item("garlic_oyster", 3)
    async with db.connect() as conn:
        await db.add_item(conn, sid, dish, 1)
        await conn.commit()
    msg = await kitchen.kitchen_ops(kid, "vend 蒜蓉生蚝")
    assert "票" in msg, msg
    async with db.connect() as conn:
        left = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, dish),
        )).fetchone()
        assert not left or left[0] == 0, left

    hint = await events.incident_ops(kid, "status")
    assert "incident_ops" not in hint, hint
    assert "plot_ops" in hint or "无未处理" in hint or "风平浪静" in hint, hint


def main() -> None:
    test_bar_job_aliases()
    test_mcp_descriptions()
    test_relay_manual_covers_systems()
    test_readme_workflow_rules()
    test_human_island_manual()
    test_register_key_copy_ui()
    test_patron_pages_share_steward_key()
    test_promo_place_pages()
    test_bar_ops_help()
    asyncio.run(test_scrump_victim_chronicle())
    asyncio.run(test_cheer_targets_isolated())
    asyncio.run(test_kitchen_vend_chinese_and_incident_hint())
    print("consistency tests ok")


if __name__ == "__main__":
    main()

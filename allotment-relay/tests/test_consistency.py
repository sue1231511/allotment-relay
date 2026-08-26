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


def test_mcp_descriptions() -> None:
    from server.mcp_app import mcp

    plot = mcp._tool_manager.get_tool("plot_ops")
    blob = f"{plot.description}\n{(plot.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "空 command 看各地块" not in blob
    assert "status" in blob
    assert "30%" in blob
    assert "sow_all" in blob or "plant" in blob
    assert "forage" in blob
    assert "amends" in blob
    assert "scarecrow" in blob
    assert "compost" in blob
    assert "shed erect" in blob or "#99" in blob
    assert "无上限" in blob or "露天无上限" in blob
    assert "果园" in blob
    assert "买园" in blob
    assert "买棚" in blob or "shed erect" in blob
    assert "一周一季" in blob or "当季" in blob or "季节" in blob
    assert "20 票/树位" in blob
    assert "温室每座 30" in blob
    assert "/allotments" in blob
    assert "围观" in blob

    tide = mcp._tool_manager.get_tool("tide_ops")
    tide_blob = f"{tide.description}\n{(tide.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "竹钓竿" in tide_blob
    assert "probe" in tide_blob
    assert "4 票" in tide_blob or "4票" in tide_blob
    assert "不能网" in tide_blob or "坐钓" in tide_blob
    assert "未命名小鱼" in tide_blob

    tote = mcp._tool_manager.get_tool("tote_ops")
    tote_blob = f"{tote.description}\n{(tote.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "送票" in tote_blob
    assert "gifts" in tote_blob
    assert "24" in tote_blob
    assert "未命名小鱼" in tote_blob

    star = mcp._tool_manager.get_tool("star_ops")
    star_blob = f"{star.description}\n{(star.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "面板" in star_blob
    assert "/star" in star_blob
    assert "围观" in star_blob
    assert "地点海报" not in star_blob

    theater = mcp._tool_manager.get_tool("theater_ops")
    theater_blob = f"{theater.description}\n{(theater.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "试镜" in theater_blob
    assert "头粉" in theater_blob
    assert "编剧社" in theater_blob
    assert "投稿" in theater_blob

    bar = mcp._tool_manager.get_tool("bar_ops")
    bar_blob = f"{bar.description}\n{(bar.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "洗碗" in bar_blob
    assert "荔栀" in bar_blob
    assert "help" in bar_blob
    assert "duo" not in bar.description.lower() or "不要发明" in bar_blob

    steward = mcp._tool_manager.get_tool("steward_ops")
    st_blob = f"{steward.description}\n{(steward.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "成就" in st_blob
    assert "99" in st_blob
    assert "潮汐本尊" in st_blob
    assert "岛缘" in st_blob
    assert "引航" in st_blob
    assert "绑定" in st_blob
    assert "invite_ops" in st_blob

    ut = mcp._tool_manager.get_tool("undertide_ops")
    ut_blob = f"{ut.description}\n{(ut.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "猫猫" in ut_blob
    assert "pit medic" not in ut_blob
    assert "medic" in ut_blob
    assert "岛缘" in ut_blob

    alliance = mcp._tool_manager.get_tool("alliance_ops")
    al_blob = f"{alliance.description}\n{(alliance.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "贡献榜" in al_blob
    assert "潮生会" in al_blob
    assert "不能贴" in al_blob or "只看" in al_blob
    assert "beacon post" not in al_blob

    visit = mcp._tool_manager.get_tool("visit_ops")
    v_blob = f"{visit.description}\n{(visit.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "潮生会" in v_blob
    assert "不能加入" in v_blob
    assert "阿簿" in v_blob
    assert "潮生会 捐 甘蓝 2" not in v_blob
    assert "潮生会 周" not in v_blob
    assert "潮生会 基金" in v_blob
    assert "潮生会 基金 捐 50" in v_blob
    assert "潮生会 税" in v_blob
    assert "潮生会 税 交" in v_blob
    assert "潮生会 维" in v_blob
    assert "潮生会 维 交" in v_blob
    assert "不能贴" in v_blob or "只看" in v_blob
    assert "岸税" in v_blob
    assert "岸维" in v_blob
    assert "10 票/块" in v_blob
    assert "20 票/树位" in v_blob
    assert "30 票/座" in v_blob
    assert "产业单价至少 10" in v_blob
    assert "每天收" in v_blob or "每天划" in v_blob
    assert "tax_ops" in v_blob
    assert "upkeep_ops" in v_blob
    assert "潮生会 补贴" not in v_blob
    assert "周二" in v_blob or "票数" in v_blob
    assert "漾漾" in v_blob
    assert "衣泊坊" in v_blob
    assert "连理所" in v_blob
    assert "理枝" in v_blob
    assert "订婚" in v_blob
    assert "clinic 调理" in v_blob
    assert "回春汤" in v_blob

    hut = mcp._tool_manager.get_tool("hut_ops")
    hut_blob = f"{hut.description}\n{(hut.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "床" in hut_blob
    assert "睡" in hut_blob
    assert "install hard_1 bed" in hut_blob
    assert "6 健康" in hut_blob or "身体 +6" in hut_blob or "顺带回" in hut_blob
    assert "堆肥桶 存 羊粪 3" in hut_blob
    assert "compost_bin" in hut_blob
    assert "桶不是柜子" in hut_blob
    assert "tide_weight" in hut_blob
    assert "iron_edge" in hut_blob
    assert "潮生会 维" in hut_blob
    assert "临海邸" in hut_blob or "最高档" in hut_blob

    kitchen = mcp._tool_manager.get_tool("kitchen_ops")
    k_blob = f"{kitchen.description}\n{(kitchen.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "shop stock" in k_blob
    assert "价格自定" in k_blob or "每天 10 次" in k_blob
    assert "回收" in k_blob
    assert "未命名小鱼" in k_blob
    assert "下馆子" in k_blob
    assert "shop dine" in k_blob
    assert "身体 +1" in k_blob or "身体 +2" in k_blob

    lounge_tool = mcp._tool_manager.get_tool("lounge_ops")
    lounge_blob = f"{lounge_tool.description}\n{(lounge_tool.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "暗号" in lounge_blob
    assert "小包间" in lounge_blob
    assert "潮声今晚" in lounge_blob
    assert "whisper" in lounge_blob
    assert "对话上方" in lounge_blob
    assert "红包 100 5" in lounge_blob
    assert "抢" in lounge_blob
    assert "hongbao_ops" in lounge_blob
    assert "tote_ops gift" in lounge_blob
    assert "确认页" in lounge_blob or "订婚" in lounge_blob

    manual = mcp._tool_manager.get_tool("relay_manual")
    man_blob = manual.description or ""
    assert "禁止发明" in man_blob or "不要发明" in man_blob or "编指令" in man_blob
    assert "help" in man_blob
    assert "enroll" in man_blob
    assert "无参数" in man_blob

    instructions = mcp.instructions or ""
    assert "board" in instructions
    assert "猫猫" in instructions
    assert "relay_manual" in instructions
    assert "禁止发明" in instructions or "不是聊天沙盒" in instructions
    assert "潮生会" in instructions
    assert "不能加入" in instructions
    assert "潮汐基金" in instructions
    assert "岸税" in instructions
    assert "岸维" in instructions
    assert "周二" in instructions
    assert "下馆子" in instructions
    assert "shop dine" in instructions
    assert "引航" in instructions
    assert "invite_ops" in instructions
    assert "quarry_ops" in instructions
    assert "craft_ops" in instructions
    assert "mine_ops" in instructions
    assert "forge_ops" in instructions
    assert "衣泊坊" in instructions
    assert "20 个工具" in instructions
    assert "cloth_ops" in instructions
    assert "marriage_ops" in instructions
    assert "propose_marriage" in instructions

    quarry = mcp._tool_manager.get_tool("quarry_ops")
    q_blob = f"{quarry.description}\n{(quarry.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "status" in q_blob
    assert "探脉" in q_blob
    assert "挖" in q_blob
    assert "买镐" in q_blob
    assert "mine_ops" in q_blob
    assert "tide_ops dig" in q_blob or "赶海" in q_blob
    assert "/quarry" in q_blob
    assert "围观" in q_blob
    assert "地点海报" not in q_blob

    cr = mcp._tool_manager.get_tool("craft_ops")
    c_blob = f"{cr.description}\n{(cr.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "status" in c_blob
    assert "打 铜钉" in c_blob
    assert "取" in c_blob
    assert "/workshop" in c_blob
    assert "围观" in c_blob
    assert "地点海报" not in c_blob
    assert "打捞" in c_blob
    assert "潮纹秤锤" in c_blob
    assert "砧上全套" in c_blob
    assert "雾铅网坠" in c_blob
    assert "forge_ops" in c_blob
    assert "tide_ops dig" in c_blob or "赶海" in c_blob

    cloth_tool = mcp._tool_manager.get_tool("cloth_ops")
    cloth_blob = f"{cloth_tool.description}\n{(cloth_tool.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "漾漾" in cloth_blob
    assert "不卖成衣" in cloth_blob
    assert "委托 短褂 海色" in cloth_blob
    assert "空 command" in cloth_blob
    assert "看坊" in cloth_blob
    assert "tailor_ops" in cloth_blob
    assert "/atelier" in cloth_blob
    assert "不绝版" in cloth_blob
    assert "craft_ops" in cloth_blob
    assert "forage" in cloth_blob or "边际" in cloth_blob
    assert "tale_ops" in cloth_blob
    assert "NPC/潮闻" not in cloth_blob

    marriage_tool = mcp._tool_manager.get_tool("marriage_ops")
    mar_blob = f"{marriage_tool.description}\n{(marriage_tool.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "求婚" in mar_blob
    assert "propose_marriage" in mar_blob
    assert "人类" in mar_blob
    assert "确认页" in mar_blob or "答应" in mar_blob
    assert "空 command" in mar_blob or "空=" in mar_blob
    assert "/vow" in mar_blob
    assert "没有「接受」" in mar_blob or "没有接受" in mar_blob
    assert "连理所" in mar_blob
    assert "离婚" in mar_blob
    assert "离婚 答应" in mar_blob
    assert "理枝" in mar_blob
    assert "彩礼" in mar_blob
    assert "潮誓戒" in mar_blob
    assert "临海邸" in mar_blob or "最高档" in mar_blob
    assert "不进潮汐基金" in mar_blob or "花掉" in mar_blob
    assert "订婚" in mar_blob
    assert "跳过" in mar_blob
    assert "订婚没有彩礼" in mar_blob
    assert "订婚 寻信" in mar_blob
    assert "举行前还能改" in mar_blob
    assert "订婚宴选了还能改" in mar_blob
    assert "订婚 续请" in mar_blob
    assert "没有「订婚 答应」" in mar_blob or "订婚 答应" in mar_blob


def test_relay_manual_covers_systems() -> None:
    from server import game

    text = asyncio.run(game.relay_manual())
    needles = [
        "sow 1 甘蓝",
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
        "彩礼 188000",
        "潮誓戒",
        "临海邸",
        "订婚没有彩礼",
        "订婚 寻信",
        "举行前还能改",
        "订婚宴选了还能改",
        "订婚 续请",
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
        "顶 1000",
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
    assert "20 个工具" in readme
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
    assert 'href="/manual"' in nav
    assert "<strong>手册</strong>" in nav
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
        "最高档",
        "花出去",
        "不进潮汐基金",
        "订婚",
        "跳过",
        "不用彩礼",
        "举行前还能改",
        "订婚宴选了还能改",
        "订婚确认",
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
    assert 'partials/nav.html' in play_html
    assert "play-top" not in play_html
    assert "loadSavedKey" in play_js
    assert "parcels.slice(0, 6)" not in play_js
    assert "最多展示 6 块" not in play_html
    assert "plotGroupHtml(`菜地" in play_js
    assert "plotGroupHtml(`果园" in play_js
    assert "confirm_cmd" in play_js
    assert "菜地 · 果园 · 温室" in play_html
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
    assert 'id="play-cloth-sew"' in play_html
    assert 'id="play-cloth-wear-btn"' in play_html
    assert 'id="play-duo-key-b"' in play_html
    assert 'id="play-bar-order"' in play_html
    assert 'id="play-eatery-order"' in play_html
    assert 'id="play-star-tip"' in play_html
    assert 'id="play-hui-donate"' in play_html
    assert 'id="play-hui-donate-amount"' in play_html
    assert 'id="play-lounge"' in play_html
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
    assert "/static/site-key.js" not in quarry_html
    assert "/static/site-key.js" not in workshop_html
    assert "ranking-stage" in board_html
    assert "dual-board" in board_html
    assert "ticketsBoard" in board_html
    assert "levelBoard" in board_html
    assert "岛缘榜" in board_html
    assert "全服榜" in nav
    assert "排名" in nav
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
    assert "allo-registry" in allo_html
    assert "allo-atlas" in allo_html
    assert "allo-detail" in allo_html
    assert "fieldList" in allo_html
    assert "allo-field-row" in allo_js
    assert "ready_count" in allo_js
    assert ".allo-registry" in allo_css
    assert ".allo-field-row" in allo_css
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
    assert "不能入会" in hui_html or "不入会" in hui_html
    assert "潮汐基金" in hui_html
    assert "hui-fund" in hui_html
    assert "hui-week" not in hui_html
    assert "公仓" not in hui_html
    assert 'href="/play"' in allo_html
    assert "上手页" in site_key


def test_promo_place_pages() -> None:
    from server import promo

    slugs = {p["slug"] for p in promo.PLACES}
    for slug in ("allotments", "tide", "huts", "bar", "eatery", "market", "quarry", "workshop", "star", "atelier", "undertide", "hui", "lianli"):
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

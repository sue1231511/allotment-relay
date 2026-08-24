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

    theater = mcp._tool_manager.get_tool("theater_ops")
    theater_blob = f"{theater.description}\n{(theater.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "试镜" in theater_blob
    assert "头粉" in theater_blob

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

    ut = mcp._tool_manager.get_tool("undertide_ops")
    ut_blob = f"{ut.description}\n{(ut.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "猫猫" in ut_blob
    assert "pit medic" not in ut_blob
    assert "medic" in ut_blob

    alliance = mcp._tool_manager.get_tool("alliance_ops")
    al_blob = f"{alliance.description}\n{(alliance.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "贡献榜" in al_blob

    hut = mcp._tool_manager.get_tool("hut_ops")
    hut_blob = f"{hut.description}\n{(hut.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "床" in hut_blob
    assert "睡" in hut_blob
    assert "install hard_1 bed" in hut_blob
    assert "堆肥桶" in hut_blob
    assert "compost_bin" in hut_blob
    assert "tide_weight" in hut_blob
    assert "iron_edge" in hut_blob

    kitchen = mcp._tool_manager.get_tool("kitchen_ops")
    k_blob = f"{kitchen.description}\n{(kitchen.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "shop stock" in k_blob
    assert "价格自定" in k_blob or "每天 10 次" in k_blob
    assert "回收" in k_blob
    assert "未命名小鱼" in k_blob
    assert "下馆子" in k_blob
    assert "shop dine" in k_blob

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
    assert "下馆子" in instructions
    assert "shop dine" in instructions
    assert "quarry_ops" in instructions
    assert "craft_ops" in instructions
    assert "mine_ops" in instructions
    assert "forge_ops" in instructions

    quarry = mcp._tool_manager.get_tool("quarry_ops")
    q_blob = f"{quarry.description}\n{(quarry.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "status" in q_blob
    assert "探脉" in q_blob
    assert "挖" in q_blob
    assert "买镐" in q_blob
    assert "mine_ops" in q_blob
    assert "tide_ops dig" in q_blob or "赶海" in q_blob

    cr = mcp._tool_manager.get_tool("craft_ops")
    c_blob = f"{cr.description}\n{(cr.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "status" in c_blob
    assert "打 铜钉" in c_blob
    assert "取" in c_blob
    assert "打捞" in c_blob
    assert "潮纹秤锤" in c_blob
    assert "砧上全套" in c_blob
    assert "雾铅网坠" in c_blob
    assert "forge_ops" in c_blob
    assert "tide_ops dig" in c_blob or "赶海" in c_blob


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
        "行囊每种也最多 24",
        "mascot adopt",
        "lili summon",
        "clinic treat",
        "undertide_ops help",
        "star_ops",
        "小剧场专场每日 5 次",
        "theater_ops",
        "试镜",
        "头粉",
        "应援",
        "不要猜",
        "sow_all",
        "eat_ops",
        "steward_ops board",
        "1～99",
        "潮汐本尊",
        "alliance_ops board",
        "kitchen_ops eat",
        "下馆子",
        "shop dine",
        "bar_ops work",
        "甘蓝种×2",
        "不占露天份地",
        "露天无上限",
        "份地不种果树",
        "买园",
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
    ]
    missing = [n for n in needles if n not in text]
    assert not missing, f"relay_manual missing: {missing}"
    assert "steward_sheet" not in text
    assert "relay_manual()" not in text
    assert "duo" not in text


def test_readme_workflow_rules() -> None:
    root = Path(__file__).resolve().parents[2]
    readme = (root / "README.md").read_text(encoding="utf-8")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    for blob in (readme, agents):
        assert "merge origin/main" in blob
        assert "relay_manual" in blob
        assert "mcp_app.py" in blob
    assert "18 个工具" in readme
    assert "quarry_ops" in readme
    assert "craft_ops" in readme
    assert "/workshop" in readme
    assert "盐风崖" in readme
    place_html = (root / "allotment-relay/server/templates/place.html").read_text(encoding="utf-8")
    promo = (root / "allotment-relay/server/promo.py").read_text(encoding="utf-8")
    nav = (root / "allotment-relay/server/templates/partials/nav.html").read_text(encoding="utf-8")
    assert "craft_ops" in promo
    assert "tide_ops" in promo
    assert "hut_ops" in promo
    assert "tote_ops market" in promo
    assert "/play" in promo
    assert "play_href" in place_html
    assert "promo-poster" in place_html
    assert 'href="/workshop"' in nav
    assert 'href="/play"' in nav
    assert 'href="/tide"' in nav
    assert 'href="/huts"' in nav
    assert 'href="/market"' in nav
    css = (root / "allotment-relay/server/static/style.css").read_text(encoding="utf-8")
    assert "@media (max-width: 980px)" in css
    assert ".nav-tab-short" in css
    island_grid = css.split(".island-grid", 1)[1].split(".island-card", 1)[0]
    assert "auto-fit" not in island_grid
    assert "grid-template-columns: 1fr" in island_grid
    assert "nav-tab-short" in nav
    assert "forage" in readme
    assert "amends" in readme
    assert "砧上全套" in readme
    assert "满级 99" in readme or "1～99" in readme
    assert "steward_ops" in readme and "plot_ops" in readme and "bar_ops" in readme
    assert "quarry_ops" in readme
    assert "tale_ops" in readme
    assert "story_ops" in readme
    assert "theater_ops" in readme
    assert "空 command" in readme
    assert "禁止" in readme


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
    assert "/static/keys.js" in recover_html


def test_patron_pages_share_steward_key() -> None:
    """点单打赏、聊天、看档都只在 /play；地点页是海报。凭证只在上手页绑定。"""
    root = Path(__file__).resolve().parents[1]
    site_key = (root / "server/static/site-key.js").read_text(encoding="utf-8")
    assert "tidal_island_steward_api_key" in site_key
    assert "loadSavedKey" in site_key
    assert "fetchBoundSteward" in site_key
    lounge_js = (root / "server/static/lounge.js").read_text(encoding="utf-8")
    play_html = (root / "server/templates/play.html").read_text(encoding="utf-8")
    play_js = (root / "server/static/play.js").read_text(encoding="utf-8")
    place_html = (root / "server/templates/place.html").read_text(encoding="utf-8")
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
    assert "/api/bar/order" in play_js
    assert "/api/bar/duo" in play_js
    assert "/api/eatery/order" in play_js
    assert "/api/star/tip" in play_js
    assert 'id="play-duo-key-b"' in play_html
    assert 'id="play-bar-order"' in play_html
    assert 'id="play-eatery-order"' in play_html
    assert 'id="play-star-tip"' in play_html
    assert 'id="play-lounge"' in play_html
    assert 'id="play-me"' in play_html
    assert 'id="memory-modal"' in play_html
    assert "/api/steward/memory" in play_js
    assert "data-memory-filter" in play_js
    assert "连续阅读" in play_js
    assert "/static/site-key.js" not in place_html
    assert 'id="order-form"' not in place_html
    assert 'id="duo-form"' not in place_html
    assert 'id="tip-form"' not in place_html
    assert "/play" in place_html or "play_href" in place_html
    assert '"go": "bar"' in promo
    assert '"go": "eatery"' in promo
    assert '"go": "star"' in promo
    assert 'RedirectResponse("/play?go=me"' in main_py
    assert 'RedirectResponse("/play?go=lounge"' in main_py
    assert "place.html" in main_py
    assert "上手页" in site_key


def test_promo_place_pages() -> None:
    from server import promo

    slugs = {p["slug"] for p in promo.PLACES}
    for slug in ("allotments", "tide", "huts", "bar", "eatery", "market", "quarry", "workshop", "star"):
        assert slug in slugs, slug
        ctx = promo.page_context(slug)
        assert ctx["play_href"].startswith("/play")
        assert ctx["place"]["aside"]
        assert "围观" not in ctx["place"]["lead"]
        assert "只围观" not in " ".join(ctx["place"]["body"])
    assert promo.play_href(promo.get("allotments")) == "/play"
    assert promo.play_href(promo.get("bar")) == "/play?go=bar"
    assert promo.play_href(promo.get("workshop")) == "/play?go=craft"


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

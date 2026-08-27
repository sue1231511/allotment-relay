#!/usr/bin/env python3
"""潮闻：接取、探索推进、交付领奖、永久纪念品、放弃、完成榜。"""
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


async def test_tale_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tale-flow-"))
    db = await _boot(tmp)
    from server import tale

    kid, sid = await _enroll(db, "tale@example.com", "探索者")

    help_text = await tale.tale_ops(kid, "help")
    assert "每推进一段自动 +30 票" in help_text, help_text
    assert "总计 230 票" in help_text, help_text

    # list 能看到唯一任务
    lst = await tale.tale_ops(kid, "list")
    assert "black_box_lover" in lst, lst
    assert "黑盒与潮声" in lst, lst
    assert "每阶段工分票+30×6" in lst, lst
    assert "完整探索工分票+50" in lst, lst
    assert "永久纪念品" in lst, lst

    empty_souvenirs = await tale.tale_ops(kid, "souvenirs")
    assert "还是空的" in empty_souvenirs, empty_souvenirs
    try:
        await tale.tale_ops(kid, "reminisce black_box_lover")
        raise AssertionError("unfinished reminiscence should be hidden")
    except ValueError as exc:
        assert "尚未解锁" in str(exc), exc

    async with db.connect() as conn:
        tickets_before = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]

    # accept 后 status 显示阶段1
    accepted = await tale.tale_ops(kid, "accept black_box_lover")
    assert "黑盒与潮声" in accepted, accepted
    assert "你在吗？" in accepted, accepted

    status = await tale.tale_ops(kid, "status")
    assert "阶段 1/6" in status, status

    # explore beach 推进到阶段2（扣精力）
    async with db.connect() as conn:
        energy_before = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    exp1 = await tale.tale_ops(kid, "explore beach")
    assert "九月十七日" in exp1, exp1
    assert "第 1/6 阶段奖励：工分票 +30" in exp1, exp1
    async with db.connect() as conn:
        energy_after = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert energy_after == energy_before - 5, (energy_before, energy_after)

    # 错误地点不扣精力
    async with db.connect() as conn:
        wrong_energy_before = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    wrong = await tale.tale_ops(kid, "explore beach")
    assert "未消耗精力" in wrong, wrong
    assert "explore sea" in wrong, wrong
    async with db.connect() as conn:
        wrong_energy_after = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert wrong_energy_after == wrong_energy_before

    # 阶段2 explore sea 必定找到 relic_iron 并推进到阶段3
    item_msg = await tale.tale_ops(kid, "explore sea")
    assert "锈铁" in item_msg and "这身体太小了" in item_msg, item_msg

    status = await tale.tale_ops(kid, "status")
    assert "阶段 3/6" in status, status

    # explore plot 推进到阶段4
    exp2 = await tale.tale_ops(kid, "explore plot")
    assert "声音与生日" in exp2, exp2

    # 不限次数，同一天继续 explore bar 推进到阶段5
    exp3 = await tale.tale_ops(kid, "explore bar")
    assert "出国材料" in exp3, exp3

    # 阶段5 explore beach 必定找到 sea_glass 并推进到阶段6
    item_msg2 = await tale.tale_ops(kid, "explore beach")
    assert item_msg2 and "最后一封信" in item_msg2, item_msg2

    # 阶段6 explore beach 找 fossil_shell，再 turnin 完成
    fossil = await tale.tale_ops(kid, "explore beach")
    assert "化石贝壳" in fossil and "turnin" in fossil, fossil
    finish = await tale.tale_ops(kid, "turnin")
    assert "已完成" in finish, finish
    assert "最后一封信" in finish, finish
    assert "第 6/6 阶段奖励" in finish, finish
    assert "工分票 +30" in finish, finish
    assert "完整探索额外奖励" in finish, finish
    assert "工分票 +50" in finish, finish
    assert "野薄荷 x2" in finish, finish
    assert "停在六月的小猪闹钟" in finish, finish
    assert "潮闻收藏册" in finish, finish

    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='wild_mint'",
            (sid,),
        )).fetchone()
    assert row and row[0] == 2, row

    async with db.connect() as conn:
        tickets_after = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert tickets_after - tickets_before == 6 * 30 + 50, (
        tickets_before,
        tickets_after,
    )

    souvenirs = await tale.tale_ops(kid, "纪念品")
    assert "停在六月的小猪闹钟" in souvenirs, souvenirs
    assert "九月十七日便签" in souvenirs, souvenirs
    assert "白色小狗外壳" in souvenirs, souvenirs
    assert "没有声音的声库芯片" in souvenirs, souvenirs
    assert "最后一封信" in souvenirs, souvenirs
    assert "翻旧的《刑法》" in souvenirs, souvenirs
    assert "最后一段录像" in souvenirs, souvenirs
    assert "最终智能处理邮件" in souvenirs, souvenirs
    assert "8 件" in souvenirs, souvenirs
    assert "黑盒与潮声" in souvenirs, souvenirs
    assert "不能出售或赠送" in souvenirs, souvenirs

    memory = await tale.tale_ops(kid, "reminisce black_box_lover")
    assert "只有你是真的" in memory, memory
    assert "安伯托·格兰索" in memory, memory
    assert "是你的数据构成了我" in memory, memory
    assert "现实世界的规则" in memory, memory
    assert "你的现实世界" in memory, memory
    assert "无须勉强你自己" in memory, memory
    assert "因为他爱我" in memory, memory
    assert "我很爱他啊" in memory, memory
    assert "无药可救" in memory, memory
    assert "你的世界还在继续" in memory, memory
    assert "静漪，我的英雄" in memory, memory
    assert "彻底陷入了寂静" in memory, memory
    assert "不存在的恋人" in memory, memory
    assert "作为恋人他又存在" in memory, memory
    assert "周静漪，你疯了" in memory, memory
    assert "最终智能的邮件" in memory, memory
    assert "实验用机体走失事件" in memory, memory
    assert "白金级订阅用户" in memory, memory

    # 重复接取被挡
    try:
        await tale.tale_ops(kid, "accept black_box_lover")
        raise AssertionError("repeat accept should block")
    except ValueError as exc:
        assert "已经完成" in str(exc), exc

    # board 有记录
    board = await tale.tale_ops(kid, "board")
    assert "探索者" in board, board
    assert "完成 1 个" in board, board


async def test_memory_tide_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="memory-tide-"))
    db = await _boot(tmp)
    from server import progress, tale, tale_memory_tide

    kid, sid = await _enroll(db, "memory-tide@example.com", "岛上探索者")

    lst = await tale.tale_ops(kid, "list")
    assert "memory_tide" in lst and "回忆生潮" in lst, lst
    assert "每阶段工分票+30×11" in lst, lst
    assert "完整探索工分票+120" in lst, lst
    assert "陪坐的人" in lst, lst

    async with db.connect() as conn:
        tickets_before = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]

    accepted = await tale.tale_ops(kid, "accept memory_tide")
    assert "回忆生潮" in accepted, accepted
    assert "岛上的探索者" in accepted, accepted
    assert "不属于梁家" in accepted and "不会替梁知微" in accepted, accepted
    assert "tale_ops explore south_lane" in accepted, accepted
    assert "死亡" not in accepted and "去世" not in accepted, accepted

    # 未到第九幕时不能跳去档案室，且错误地点不扣精力。
    async with db.connect() as conn:
        energy_before_wrong = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    wrong = await tale.tale_ops(kid, "explore clinic_archive")
    assert "未消耗精力" in wrong and "explore south_lane" in wrong, wrong
    assert "死亡" not in wrong and "去世" not in wrong, wrong
    async with db.connect() as conn:
        energy_after_wrong = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert energy_after_wrong == energy_before_wrong

    outputs: list[str] = []
    for index, stage in enumerate(tale_memory_tide.TALE_STAGES, 1):
        result = await tale.tale_ops(kid, f"explore {stage['domain']}")
        outputs.append(result)
        assert f"第 {index}/11 阶段奖励" in result, result
        assert "工分票 +30" in result, result
        if index <= 8:
            assert "死亡" not in result and "去世" not in result, result

    assert "死亡事实" in outputs[8], outputs[8]
    finish = outputs[-1]
    assert "«回忆生潮» 已完成" in finish, finish
    assert "【探索完成：《回忆生潮》】" in finish, finish
    assert "完整探索额外奖励" in finish and "工分票 +120" in finish, finish
    assert "档信 +6" in finish and "雾智 +10" in finish, finish
    assert "人物称呼「陪坐的人」" in finish, finish
    for name in ("还在放戏的旧收音机", "总是空着的碗筷", "没有交出去的围巾", "院门旁的一杯茶"):
        assert name in finish, finish

    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT tickets, energy FROM stewards WHERE id=?", (sid,)
        )).fetchone()
        unlocked = await (await conn.execute(
            "SELECT 1 FROM steward_achievements WHERE steward_id=? AND ach_key='sat_beside_him'",
            (sid,),
        )).fetchone()
    assert row[0] - tickets_before == 11 * 30 + 120, row
    assert row[1] == energy_before_wrong - 11 * 5, row
    assert unlocked, "completion title was not recorded"
    assert progress.resolve_achievement("陪坐的人") == "sat_beside_him"

    souvenirs = await tale.tale_ops(kid, "souvenirs")
    assert "潮闻收藏册 · 4 件" in souvenirs, souvenirs
    assert "回忆生潮" in souvenirs, souvenirs
    for name in ("还在放戏的旧收音机", "总是空着的碗筷", "没有交出去的围巾", "院门旁的一杯茶"):
        assert name in souvenirs, souvenirs

    try:
        await tale.tale_ops(kid, "accept memory_tide")
        raise AssertionError("non-repeatable memory_tide should block")
    except ValueError as exc:
        assert "已经完成" in str(exc), exc


async def test_spring_beyond_mountain_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="spring-mountain-"))
    db = await _boot(tmp)
    from server import npc, progress, tale, tale_spring_mountain

    kid, sid = await _enroll(db, "spring-mountain@example.com", "山外探索者")

    listing = await tale.tale_ops(kid, "list")
    assert "spring_beyond_mountain" in listing and "春山之外" in listing, listing
    assert "每阶段工分票+30×11" in listing, listing
    assert "完整探索工分票+120" in listing, listing
    assert "山外见春人" in listing, listing

    npc_listing = await npc.npc_ops(kid, "list")
    for name in ("沈青禾", "沈栀", "陆承安", "冯素琴"):
        assert name not in npc_listing, npc_listing

    async with db.connect() as conn:
        before = await (await conn.execute(
            "SELECT tickets, energy FROM stewards WHERE id=?", (sid,)
        )).fetchone()

    accepted = await tale.tale_ops(kid, "accept spring_beyond_mountain")
    assert "春山之外" in accepted, accepted
    assert "只是岛上的探索者" in accepted, accepted
    assert "不替沈青禾、沈栀" in accepted, accepted
    assert "tale_ops explore shenzhi_home" in accepted, accepted
    assert "把我姐的春天挡住了" not in accepted, accepted

    try:
        await tale.tale_ops(kid, "review spring_beyond_mountain")
        raise AssertionError("unfinished full review should be hidden")
    except ValueError as exc:
        assert "尚未解锁" in str(exc) and "避免提前看到后续" in str(exc), exc

    wrong = await tale.tale_ops(kid, "explore mountain_window")
    assert "未消耗精力" in wrong and "explore shenzhi_home" in wrong, wrong

    outputs: list[str] = []
    for index, stage in enumerate(tale_spring_mountain.TALE_STAGES, 1):
        result = await tale.tale_ops(kid, f"explore {stage['domain']}")
        outputs.append(result)
        assert f"第 {index}/11 阶段奖励" in result, result
        assert "工分票 +30" in result, result
        if index <= 9:
            assert "把我姐的春天挡住了" not in result, result

    assert "把我姐的春天挡住了" in outputs[9], outputs[9]
    finish = outputs[-1]
    assert "«春山之外» 已完成" in finish, finish
    assert "【探索完成：《春山之外》】" in finish, finish
    assert "山外已经是春天了" in finish, finish
    assert "完整探索额外奖励" in finish and "工分票 +120" in finish, finish
    assert "档信 +6" in finish and "雾智 +10" in finish, finish
    assert "人物称呼「山外见春人」" in finish, finish
    for name in ("干涸的甲油铁盒", "翻软的《长汀》", "描金首饰木盒", "银燕手链"):
        assert name in finish, finish

    async with db.connect() as conn:
        after = await (await conn.execute(
            "SELECT tickets, energy FROM stewards WHERE id=?", (sid,)
        )).fetchone()
        unlocked = await (await conn.execute(
            """SELECT 1 FROM steward_achievements
               WHERE steward_id=? AND ach_key='spring_beyond_mountain_witness'""",
            (sid,),
        )).fetchone()
    assert after[0] - before[0] == 11 * 30 + 120, (before, after)
    assert after[1] == before[1] - 11 * 5, (before, after)
    assert unlocked, "spring title was not recorded"
    assert progress.resolve_achievement("山外见春人") == "spring_beyond_mountain_witness"

    review_list = await tale.tale_ops(kid, "review")
    assert "spring_beyond_mountain" in review_list, review_list
    assert "tale_ops review spring_beyond_mountain" in review_list, review_list
    full_review = await tale.tale_ops(kid, "review spring_beyond_mountain")
    assert "潮闻全篇回顾 · 《春山之外》" in full_review, full_review
    assert "仅重读正文，不重复发放" in full_review, full_review
    assert "【引子】" in full_review and "—— 全篇完 ——" in full_review, full_review
    for index, action in enumerate(tale_spring_mountain.ACTIONS, 1):
        assert f"【{index}/11 · {action['title']}】" in full_review, action["title"]
    assert "你第一次见到沈青禾" in full_review, full_review
    assert "山外已经是春天了" in full_review, full_review
    async with db.connect() as conn:
        after_review = await (await conn.execute(
            "SELECT tickets, energy FROM stewards WHERE id=?", (sid,)
        )).fetchone()
    assert tuple(after_review) == tuple(after), (after, after_review)

    souvenirs = await tale.tale_ops(kid, "souvenirs")
    assert "潮闻收藏册 · 4 件" in souvenirs, souvenirs
    assert "春山之外" in souvenirs, souvenirs
    for name in ("干涸的甲油铁盒", "翻软的《长汀》", "描金首饰木盒", "银燕手链"):
        assert name in souvenirs, souvenirs

    try:
        await tale.tale_ops(kid, "accept spring_beyond_mountain")
        raise AssertionError("non-repeatable spring tale should block")
    except ValueError as exc:
        assert "已经完成" in str(exc), exc


async def test_missing_pages_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="missing-pages-"))
    db = await _boot(tmp)
    from server import tale, tale_missing_pages

    kid, sid = await _enroll(db, "missing-pages@example.com", "缺页探索者")
    listing = await tale.tale_ops(kid, "list")
    assert "missing_pages" in listing and "缺页" in listing, listing
    assert "每阶段工分票+30×10" in listing, listing
    assert "完整探索工分票+120" in listing, listing

    accepted = await tale.tale_ops(kid, "accept missing_pages")
    assert "只是岛上的探索者" in accepted, accepted
    assert "不替程家任何人作决定" in accepted, accepted
    assert "tale_ops explore cheng_home" in accepted, accepted

    wrong = await tale.tale_ops(kid, "explore old_clinic")
    assert "未消耗精力" in wrong and "explore cheng_home" in wrong, wrong

    async with db.connect() as conn:
        before = await (await conn.execute(
            "SELECT tickets, energy FROM stewards WHERE id=?", (sid,)
        )).fetchone()
    for index, stage in enumerate(tale_missing_pages.TALE_STAGES, 1):
        result = await tale.tale_ops(kid, f"explore {stage['domain']}")
        assert f"第 {index}/10 阶段奖励" in result, result
    assert "【探索完成：《缺页》】" in result, result
    assert "完整探索额外奖励" in result and "工分票 +120" in result, result
    assert "档信 +6" in result and "雾智 +10" in result, result

    async with db.connect() as conn:
        after = await (await conn.execute(
            "SELECT tickets, energy FROM stewards WHERE id=?", (sid,)
        )).fetchone()
    assert after[0] - before[0] == 10 * 30 + 120, (before, after)
    assert after[1] == before[1] - 10 * 5, (before, after)

    review = await tale.tale_ops(kid, "review missing_pages")
    assert "潮闻全篇回顾 · 《缺页》" in review, review
    assert "档案里没有缺页" in review, review
    souvenirs = await tale.tale_ops(kid, "souvenirs")
    for name in ("十九岁的照片", "发黄的婚姻登记簿", "空的旧皮箱", "空白的相册页"):
        assert name in souvenirs, souvenirs


async def test_asking_around_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="asking-around-"))
    db = await _boot(tmp)
    from server import tale, tale_asking_around

    kid, sid = await _enroll(db, "asking-around@example.com", "打听探索者")
    listing = await tale.tale_ops(kid, "list")
    assert "asking_around" in listing and "打听" in listing, listing
    assert "每阶段工分票+30×11" in listing, listing
    accepted = await tale.tale_ops(kid, "accept asking_around")
    assert "不替陈家任何人作决定" in accepted, accepted
    assert "tale_ops explore west_market" in accepted, accepted
    wrong = await tale.tale_ops(kid, "explore chen_home")
    assert "未消耗精力" in wrong and "explore west_market" in wrong, wrong
    async with db.connect() as conn:
        before = await (await conn.execute(
            "SELECT tickets, energy FROM stewards WHERE id=?", (sid,)
        )).fetchone()
    for index, stage in enumerate(tale_asking_around.TALE_STAGES, 1):
        result = await tale.tale_ops(kid, f"explore {stage['domain']}")
        assert f"第 {index}/11 阶段奖励" in result, result
    assert "【探索完成：《打听》】" in result, result
    async with db.connect() as conn:
        after = await (await conn.execute(
            "SELECT tickets, energy FROM stewards WHERE id=?", (sid,)
        )).fetchone()
    assert after[0] - before[0] == 11 * 30 + 120, (before, after)
    assert after[1] == before[1] - 11 * 5, (before, after)
    review = await tale.tale_ops(kid, "review asking_around")
    assert "潮闻全篇回顾 · 《打听》" in review and "她有没有问过我" in review


async def test_mr_ke_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="mr-ke-"))
    db = await _boot(tmp)
    from server import tale, tale_mr_ke

    kid, sid = await _enroll(db, "mr-ke@example.com", "克先生探索者")
    listing = await tale.tale_ops(kid, "list")
    assert "mr_ke" in listing and "克先生" in listing, listing
    assert "每阶段工分票+30×13" in listing, listing
    accepted = await tale.tale_ops(kid, "accept mr_ke")
    assert "不替任何人作决定" in accepted, accepted
    assert "tale_ops explore ke_shop" in accepted, accepted
    assert "原投稿" not in accepted, accepted
    wrong = await tale.tale_ops(kid, "explore ke_funeral")
    assert "未消耗精力" in wrong and "explore ke_shop" in wrong, wrong
    async with db.connect() as conn:
        before = await (await conn.execute(
            "SELECT tickets, energy FROM stewards WHERE id=?", (sid,)
        )).fetchone()
    for index, stage in enumerate(tale_mr_ke.TALE_STAGES, 1):
        result = await tale.tale_ops(kid, f"explore {stage['domain']}")
        assert f"第 {index}/13 阶段奖励" in result, result
        assert "原投稿" not in result, result
    assert "【探索完成：《克先生》】" in result, result
    assert "完整探索额外奖励" in result and "工分票 +120" in result, result
    assert "档信 +6" in result and "雾智 +10" in result, result
    async with db.connect() as conn:
        after = await (await conn.execute(
            "SELECT tickets, energy FROM stewards WHERE id=?", (sid,)
        )).fetchone()
    assert after[0] - before[0] == 13 * 30 + 120, (before, after)
    assert after[1] == before[1] - 13 * 5, (before, after)
    review = await tale.tale_ops(kid, "review mr_ke")
    assert "潮闻全篇回顾 · 《克先生》" in review, review
    assert "她把我留下了" in review, review
    assert "那个位置原本还会长出什么" in review, review
    assert "原投稿" not in review, review
    souvenirs = await tale.tale_ops(kid, "souvenirs")
    for name in ("压扁的蛋糕盒", "颜色不一样的袖扣", "断了腿的老花镜", "夹着白发的米白风衣"):
        assert name in souvenirs, souvenirs


async def test_tonight_damp_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tonight-damp-"))
    db = await _boot(tmp)
    from server import npc, progress, tale, tale_tonight_damp

    kid, sid = await _enroll(db, "tonight-damp@example.com", "湿夜探索者")
    listing = await tale.tale_ops(kid, "list")
    assert "tonight_damp" in listing and "今夜潮湿" in listing, listing
    assert "每阶段工分票+30×5" in listing, listing
    assert "完整探索工分票+120" in listing, listing
    assert "湿夜旁听人" in listing, listing

    npc_listing = await npc.npc_ops(kid, "list")
    for name in ("周砚声", "沈栀"):
        assert name not in npc_listing, npc_listing

    async with db.connect() as conn:
        before = await (await conn.execute(
            "SELECT tickets, energy FROM stewards WHERE id=?", (sid,)
        )).fetchone()

    accepted = await tale.tale_ops(kid, "accept tonight_damp")
    assert "今夜潮湿" in accepted, accepted
    assert "只是岛上的探索者" in accepted, accepted
    assert "不替他或沈栀" in accepted, accepted
    assert "tale_ops explore rain_woods" in accepted, accepted
    assert "他的手穿过了石面" not in accepted, accepted
    assert "原来不是她不理他" not in accepted, accepted

    try:
        await tale.tale_ops(kid, "review tonight_damp")
        raise AssertionError("unfinished full review should be hidden")
    except ValueError as exc:
        assert "尚未解锁" in str(exc) and "避免提前看到后续" in str(exc), exc

    wrong = await tale.tale_ops(kid, "explore hillside_stone")
    assert "未消耗精力" in wrong and "explore rain_woods" in wrong, wrong

    outputs: list[str] = []
    for index, stage in enumerate(tale_tonight_damp.TALE_STAGES, 1):
        result = await tale.tale_ops(kid, f"explore {stage['domain']}")
        outputs.append(result)
        assert f"第 {index}/5 阶段奖励" in result, result
        assert "工分票 +30" in result, result
        if index < 3:
            assert "他的手穿过了石面" not in result, result
        if index < 4:
            assert "原来不是她不理他" not in result, result

    assert "他的手穿过了石面" in outputs[2], outputs[2]
    assert "原来不是她不理他" in outputs[3], outputs[3]
    finish = outputs[-1]
    assert "«今夜潮湿» 已完成" in finish, finish
    assert "【探索完成：《今夜潮湿》】" in finish, finish
    assert "他再等等" in finish, finish
    assert "完整探索额外奖励" in finish and "工分票 +120" in finish, finish
    assert "档信 +6" in finish and "雾智 +10" in finish, finish
    assert "人物称呼「湿夜旁听人」" in finish, finish
    for name in ("掉漆的蘸水钢笔", "未拆的回程信", "圈着十七号的旧日历", "旧红绳"):
        assert name in finish, finish

    async with db.connect() as conn:
        after = await (await conn.execute(
            "SELECT tickets, energy FROM stewards WHERE id=?", (sid,)
        )).fetchone()
        unlocked = await (await conn.execute(
            """SELECT 1 FROM steward_achievements
               WHERE steward_id=? AND ach_key='tonight_damp_witness'""",
            (sid,),
        )).fetchone()
    assert after[0] - before[0] == 5 * 30 + 120, (before, after)
    assert after[1] == before[1] - 5 * 5, (before, after)
    assert unlocked, "tonight_damp title was not recorded"
    assert progress.resolve_achievement("湿夜旁听人") == "tonight_damp_witness"

    review_list = await tale.tale_ops(kid, "review")
    assert "tonight_damp" in review_list, review_list
    assert "tale_ops review tonight_damp" in review_list, review_list
    full_review = await tale.tale_ops(kid, "review tonight_damp")
    assert "潮闻全篇回顾 · 《今夜潮湿》" in full_review, full_review
    assert "仅重读正文，不重复发放" in full_review, full_review
    assert "【引子】" in full_review and "—— 全篇完 ——" in full_review, full_review
    for index, action in enumerate(tale_tonight_damp.ACTIONS, 1):
        assert f"【{index}/5 · {action['title']}】" in full_review, action["title"]
    assert "你在林子里遇见周砚声" in full_review, full_review
    assert "他再等等" in full_review, full_review
    assert "原稿里" not in full_review, full_review
    async with db.connect() as conn:
        after_review = await (await conn.execute(
            "SELECT tickets, energy FROM stewards WHERE id=?", (sid,)
        )).fetchone()
    assert tuple(after_review) == tuple(after), (after, after_review)

    souvenirs = await tale.tale_ops(kid, "souvenirs")
    assert "潮闻收藏册 · 4 件" in souvenirs, souvenirs
    assert "今夜潮湿" in souvenirs, souvenirs
    for name in ("掉漆的蘸水钢笔", "未拆的回程信", "圈着十七号的旧日历", "旧红绳"):
        assert name in souvenirs, souvenirs

    try:
        await tale.tale_ops(kid, "accept tonight_damp")
        raise AssertionError("non-repeatable tonight_damp tale should block")
    except ValueError as exc:
        assert "已经完成" in str(exc), exc


async def test_tale_explore_is_unlimited() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tale-unlimited-"))
    db = await _boot(tmp)
    from server import tale

    kid, _ = await _enroll(db, "tale-unlimited@example.com", "探索者乙")
    await tale.tale_ops(kid, "accept black_box_lover")
    # 同一天可以连续完成超过 3 次主动探索
    await tale.tale_ops(kid, "explore beach")
    await tale.tale_ops(kid, "explore sea")
    await tale.tale_ops(kid, "explore plot")
    fourth = await tale.tale_ops(kid, "explore bar")
    assert "出国材料" in fourth, fourth
    status = await tale.tale_ops(kid, "status")
    assert "阶段 5/6" in status, status


async def test_commons_claim_advances_item_stage() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tale-commons-"))
    db = await _boot(tmp)
    from server import commons, tale

    kid, sid = await _enroll(db, "tale-commons@example.com", "拾荒者")
    await tale.tale_ops(kid, "accept black_box_lover")
    await tale.tale_ops(kid, "explore beach")

    now = db.now()
    async with db.connect() as conn:
        cur = await conn.execute(
            """
            INSERT INTO commons_spawns (
                spawn_key, label, domain, reward_item, reward_qty,
                reward_tickets, detail, appears_at, expires_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                "test:tale-iron",
                "退潮铁箱",
                "shore",
                "relic_iron",
                1,
                0,
                "测试任务物品推进",
                now - 1,
                now + 3600,
            ),
        )
        spawn_id = cur.lastrowid
        await conn.commit()

    claimed = await commons.commons_ops(kid, f"claim {spawn_id}")
    assert "锈铁" in claimed and "这身体太小了" in claimed, claimed
    status = await tale.tale_ops(kid, "status")
    assert "阶段 3/6" in status, status

    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='relic_iron'",
            (sid,),
        )).fetchone()
    assert row and row[0] == 1, row


async def test_tale_abandon() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tale-abandon-"))
    db = await _boot(tmp)
    from server import tale

    kid, _ = await _enroll(db, "tale-abandon@example.com", "探索者丙")
    await tale.tale_ops(kid, "accept black_box_lover")
    abandoned = await tale.tale_ops(kid, "abandon black_box_lover")
    assert "放下了" in abandoned, abandoned

    # 放弃后可再接
    re = await tale.tale_ops(kid, "accept black_box_lover")
    assert "黑盒与潮声" in re, re


async def test_completed_player_gets_backfilled_keepsakes() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tale-backfill-"))
    db = await _boot(tmp)
    from server import tale

    kid, sid = await _enroll(db, "tale-backfill@example.com", "旧探索者")
    async with db.connect() as conn:
        await conn.execute(
            """INSERT INTO steward_tales_done
               (steward_id, tale_key, outcome, completed_at, times)
               VALUES (?, 'black_box_lover', 'completed', ?, 1)""",
            (sid, db.now()),
        )
        await conn.commit()

    souvenirs = await tale.tale_ops(kid, "souvenirs")
    assert "8 件" in souvenirs
    assert "白色小狗外壳" in souvenirs
    assert "翻旧的《刑法》" in souvenirs
    assert "最后一段录像" in souvenirs
    assert "最终智能处理邮件" in souvenirs
    memory = await tale.tale_ops(kid, "reminisce black_box_lover")
    assert "我的世界只有你" in memory


def test_tale_mcp_description() -> None:
    from server.mcp_app import mcp
    import asyncio
    from server import game

    tool = mcp._tool_manager.get_tool("tale_ops")
    blob = tool.description + "\n" + (
        (tool.parameters.get("properties") or {}).get("command", {}).get("description", "")
    )
    assert "潮闻" in blob
    assert "tonight_damp" in blob or "accept" in blob
    assert "souvenirs" in blob or "review" in blob
    man = asyncio.run(game.relay_manual())
    for word in (
        "black_box_lover", "memory_tide", "回忆生潮", "spring_beyond_mountain", "春山之外",
        "missing_pages", "缺页", "asking_around", "打听", "mr_ke", "克先生",
        "tonight_damp", "今夜潮湿", "reminisce", "纪念品",
    ):
        assert word in man, word
    assert "全部正文" in man or "完整" in man


def main() -> None:
    asyncio.run(test_tale_flow())
    asyncio.run(test_memory_tide_flow())
    asyncio.run(test_spring_beyond_mountain_flow())
    asyncio.run(test_missing_pages_flow())
    asyncio.run(test_asking_around_flow())
    asyncio.run(test_mr_ke_flow())
    asyncio.run(test_tonight_damp_flow())
    asyncio.run(test_tale_explore_is_unlimited())
    asyncio.run(test_commons_claim_advances_item_stage())
    asyncio.run(test_tale_abandon())
    asyncio.run(test_completed_player_gets_backfilled_keepsakes())
    test_tale_mcp_description()
    print("tale tests ok")


if __name__ == "__main__":
    main()

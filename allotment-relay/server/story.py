"""无模型的人物故事探索：分支故事《灰姑娘》与线性调查《昨日无凭》。"""
from __future__ import annotations

import json
from typing import Any

import aiosqlite

from . import db, story_yesterday, survival
from .game import require_steward

STORY_KEY = "cinderella"
STORY_TITLE = "灰姑娘"
ACTION_MINUTES = 10
STORY_REWARD_TICKETS = 60
STORY_REWARD_STANDING = 5
STORY_REWARD_MIST_WIT = 5

STORY_HELP = """story_ops 人物故事探索（整句写进 command）：
  list — 查看可探索故事；空 command 与 list 相同
  start cinderella — 开始《灰姑娘》（重新游玩会重置本故事进度）
  start yesterday_no_proof — 开始《昨日无凭》（12 次顺序调查，自动进入结局）
  status [故事key] — 查看当前故事的进度和下一步；不写 key 看最近操作的故事
  explore old_wharf — 《昨日无凭》第一步；之后严格按 status 给出的地点继续
  inspect queen — 调查不会行走的王妃
  search study — 潜入王子书房，调查舞会名单
  search portraits — 搜索失踪新娘的肖像长廊
  enter cellar — 找到暗道后进入水晶鞋密室
  contact girl — 接触舞会上的新姑娘
  prepare backdoor|broadcast|trap — 准备后门、广播或密室陷阱
  choose escape|judgment|hunt|rescue — 决定结局：双生逃离/公开审判/猎杀/只救新人
  archive — 查看自己已经抵达的结局
  souvenirs — 查看人物故事永久纪念品（不占行囊，不能出售或赠送）
  help — 本帮助
《灰姑娘》调查和准备各耗 10 分钟；首次结局奖励 60 票、档信 +5、雾智 +5。《昨日无凭》不耗精力，13 幕每幕首次 +30 票（共 390），通关另奖 120 票、档信 +6、雾智 +10、人物称呼「旧事见证人」和 4 件永久纪念品。所有故事重玩不重复领奖。"""

INTRO = """《灰姑娘》

我叫辛德瑞拉。可怜又丑陋的我，却嫁给了王子。
那天王子对我说了一句话，我就知道，下一场舞会又要开始了。

城堡顶端的钟指向十一点。距离午夜只剩 60 分钟。
你已经潜入王宫：调查真相，做好准备，然后决定要救谁、审判谁。

下一步：story_ops status"""

ACTIONS: dict[str, dict[str, Any]] = {
    "inspect queen": {
        "flag": "queen",
        "title": "第一幕：不会行走的王妃",
        "text": """我躲在长廊的阴影里，屏住呼吸。

大厅中央的高座上，坐着新晋的王妃辛德瑞拉。她的脸粗糙、暗沉，与金碧辉煌的宫殿格格不入。无论侍从如何穿梭，她始终死死钉在椅上，下半身盖着极其繁复的拖地长裙。

一块木屑在我脚下碎裂。辛德瑞拉猛地转头，双手死死攥住裙摆：“别过来！不要看……我只是不能站起来……”

烛光掠过台阶。那片本该由鞋尖撑起的丝绸软软垂着，下面没有任何移动的轮廓。

【证据：空荡的裙摆】辛德瑞拉并非普通患病，她在竭力遮掩自己的下肢。""",
    },
    "search study": {
        "flag": "study",
        "title": "第二幕：重新开启的舞会",
        "text": """我绕开巡逻侍卫，溜进王子的书房。远处已经传来新一轮舞会的乐声。

桌上的羊皮名单没有画像与家世，只有令人发毛的数据：
  艾莉森：三寸二分，弓足，骨骼纤细。
  贝蒂：三寸一分，踝骨微突，淘汰。
  赛琳娜：三寸，骨肉均匀，完美。已寄出水晶鞋。

纸边粘着干涸的血，旁边摆着骨尺与形状怪异的雕刻刀。这不是选妃名单，而是一张挑选“零件”的尺寸表。

【证据：足部尺寸名单】王子不在乎姑娘的脸，只在乎谁能装进固定的水晶鞋壳。""",
    },
    "search portraits": {
        "flag": "portraits",
        "title": "第三幕：消失的新娘",
        "text": """我闯入城堡深处的肖像长廊。墙上挂着历届舞会优胜者的画像，每张画像右下角都盖着猩红的档案印章。

旧日志显示，这些风光大嫁的姑娘全在婚后一个月内“因病暴毙”或“凭空失踪”。最后一页夹着地下层的机关图：肖像长廊尽头，有一条未标明用途的暗道。

【证据：失踪新娘日志】历届优胜者无一留下。
【路径：地下暗道】现在可以 enter cellar。""",
    },
    "enter cellar": {
        "flag": "cellar",
        "requires": {"portraits"},
        "title": "第四幕：水晶鞋密室",
        "text": """我依照日志推开地下室的铁门。血腥味与冰冷腐气迎面压来。

墙壁上的水晶柜里，浸泡着一双双被齐踝切断的脚。惨白皮肉套在晶莹剔透的水晶鞋中，暗红血迹沉在鞋底。

正中央的展台上摆着最新的一双。断口尚未完全凝固，金属牌上刻着：辛德瑞拉。

难怪她永远坐着，难怪她不准任何人掀开裙摆。她的双脚早已被王子割下，永远留在这里。

【核心证据：辛德瑞拉的双脚】水晶鞋是猎物的标记，王子收藏历任新娘的脚。""",
    },
    "contact girl": {
        "flag": "girl",
        "requires": {"study"},
        "title": "第五幕：下一位辛德瑞拉",
        "text": """我回到宴会厅。名单上写着“完美”的赛琳娜，正穿着水晶鞋与王子共舞。她以为自己走进了童话。

乐曲转换时，我擦过她身边，低声告诉她鞋底的血迹和那些失踪的新娘。她先是愤怒，直到摸到鞋内藏着的细针，脸色才彻底惨白。

王子温柔的声音从高台传来：“亲爱的，我又找到了一双配得上水晶鞋的脚……午夜前，她就会来陪你。”

【人物：赛琳娜】她已经相信你，愿意在行动时跟你离开。""",
    },
    "prepare backdoor": {
        "flag": "backdoor",
        "requires": {"queen", "girl"},
        "title": "准备：森林后门",
        "text": "你砸开后门的旧锁，剪断缠在辛德瑞拉轮椅上的暗链，又在森林边藏好斗篷。两名姑娘都有了逃离王宫的路。\n\n【准备：逃生通道】现在可以 choose escape。",
    },
    "prepare broadcast": {
        "flag": "broadcast",
        "requires": {"study", "portraits", "cellar"},
        "title": "准备：钟楼广播",
        "text": "你把尺寸名单、失踪日志和密室位置接入钟楼广播机关，并卸掉铁门的遮挡。午夜钟响时，罪证可以同时呈现在所有宾客面前。\n\n【准备：公开罪证】现在可以 choose judgment。",
    },
    "prepare trap": {
        "flag": "trap",
        "requires": {"cellar"},
        "title": "准备：血色密室",
        "text": "你把解剖刀卡进展示架机关，将密室钥匙藏入袖口。只要王子独自踏进来，铁门便会反锁。\n\n【准备：密室陷阱】现在可以 choose hunt。",
    },
}

OUTCOMES = {
    "escape": ("双生逃离", {"queen", "girl", "backdoor"}, """午夜前，你拉住赛琳娜，推起辛德瑞拉的轮椅撞开后门。锁链落地，三个人一头扎进漆黑森林。

身后的钟声响了十二次。辛德瑞拉第一次离开王宫，而赛琳娜脚上的水晶鞋被砸碎在泥里。

【结局：双生逃离】你同时救出了辛德瑞拉与下一名受害者。"""),
    "judgment": ("公开罪恶", {"broadcast"}, """午夜十二点，钟楼广播响彻大厅。尺寸名单与失踪日志被逐条宣读，地下铁门在宾客面前轰然敞开。

水晶柜中的血光击碎了所有童话。侍卫第一次没有听从王子，而是将剑锋对准了他。

【结局：公开罪恶】王子的收藏与罪行暴露在所有人面前。"""),
    "hunt": ("血色密室", {"trap"}, """王子独自走进密室，铁门在他身后反锁。机关弹起，曾经切断无数双脚的刀锋刺入了收藏家的身体。

这一次，水晶柜里陈列的是他的血。

【结局：血色密室】你在王子的收藏室里终结了他。"""),
    "rescue": ("循环不息", {"girl"}, """你在混乱中带走了赛琳娜，却没能解开辛德瑞拉轮椅上的暗链。

新姑娘得救了。辛德瑞拉仍被留在密室深处，麻木地等待下一封邀请函被送出。

【结局：循环不息】你救下了下一名受害者，却遗落了灰姑娘。"""),
}

TIMEOUT_TEXT = """第十二声钟响彻城堡。宴会厅方向传来撕裂乐声的尖叫。

不久，密室里多了一块刻着新名字的金属牌。新的“王妃”被抬上高座，长裙下面空空荡荡。

【结局：绝望降临】你没能在午夜前阻止下一次收藏。"""


async def _progress(
    conn: aiosqlite.Connection, steward_id: int, story_key: str = STORY_KEY
) -> aiosqlite.Row | None:
    conn.row_factory = aiosqlite.Row
    return await (await conn.execute(
        "SELECT * FROM steward_stories WHERE steward_id=? AND story_key=?",
        (steward_id, story_key),
    )).fetchone()


async def _latest_progress(
    conn: aiosqlite.Connection, steward_id: int
) -> aiosqlite.Row | None:
    conn.row_factory = aiosqlite.Row
    return await (await conn.execute(
        """SELECT * FROM steward_stories WHERE steward_id=?
           ORDER BY CASE WHEN status='active' THEN 0 ELSE 1 END, updated_at DESC LIMIT 1""",
        (steward_id,),
    )).fetchone()


def _flags(row: aiosqlite.Row) -> set[str]:
    return set(json.loads(row["flags_json"] or "[]"))


async def _start(conn: aiosqlite.Connection, steward_id: int) -> str:
    ts = db.now()
    await conn.execute(
        """INSERT INTO steward_stories
           (steward_id, story_key, status, minutes_left, flags_json, outcome, started_at, updated_at, completed_at)
           VALUES (?, ?, 'active', 60, '[]', '', ?, ?, NULL)
           ON CONFLICT(steward_id, story_key) DO UPDATE SET
             status='active', minutes_left=60, flags_json='[]', outcome='',
             started_at=excluded.started_at, updated_at=excluded.updated_at, completed_at=NULL""",
        (steward_id, STORY_KEY, ts, ts),
    )
    await conn.commit()
    return INTRO


async def _finish(conn: aiosqlite.Connection, row: aiosqlite.Row, outcome: str, text: str) -> str:
    ts = db.now()
    reward_text = ""
    if not row["reward_granted"]:
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?",
            (STORY_REWARD_TICKETS, row["steward_id"]),
        )
        await survival.bump(
            conn, row["steward_id"], standing=STORY_REWARD_STANDING,
            mist_wit=STORY_REWARD_MIST_WIT,
        )
        reward_text = (
            "\n\n首次故事结局奖励："
            f"工分票 +{STORY_REWARD_TICKETS}、档信 +{STORY_REWARD_STANDING}、"
            f"雾智 +{STORY_REWARD_MIST_WIT}"
        )
    await conn.execute(
        "UPDATE steward_stories SET status='completed', outcome=?, reward_granted=1, updated_at=?, completed_at=? WHERE id=?",
        (outcome, ts, ts, row["id"]),
    )
    await conn.execute(
        """INSERT INTO steward_story_outcomes (steward_id, story_key, outcome, completed_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(steward_id, story_key, outcome) DO UPDATE SET completed_at=excluded.completed_at""",
        (row["steward_id"], STORY_KEY, outcome, ts),
    )
    await conn.commit()
    return text + reward_text + "\n\n重玩：story_ops start cinderella · 查看记录：story_ops archive"


async def _claim_pending_reward(conn: aiosqlite.Connection, row: aiosqlite.Row) -> str:
    """补发上线前已完成、但从未结算过的人物故事奖励。"""
    if row["status"] != "completed" or row["reward_granted"]:
        return ""
    await conn.execute(
        "UPDATE stewards SET tickets=tickets+? WHERE id=?",
        (STORY_REWARD_TICKETS, row["steward_id"]),
    )
    await survival.bump(
        conn, row["steward_id"], standing=STORY_REWARD_STANDING,
        mist_wit=STORY_REWARD_MIST_WIT,
    )
    await conn.execute(
        "UPDATE steward_stories SET reward_granted=1, updated_at=? WHERE id=?",
        (db.now(), row["id"]),
    )
    await conn.commit()
    return (
        "\n\n已补发首次故事结局奖励："
        f"工分票 +{STORY_REWARD_TICKETS}、档信 +{STORY_REWARD_STANDING}、"
        f"雾智 +{STORY_REWARD_MIST_WIT}"
    )


async def _start_yesterday(conn: aiosqlite.Connection, steward_id: int) -> str:
    ts = db.now()
    await conn.execute(
        """INSERT INTO steward_stories
           (steward_id, story_key, status, minutes_left, flags_json, outcome, started_at, updated_at, completed_at)
           VALUES (?, ?, 'active', 0, '[]', '', ?, ?, NULL)
           ON CONFLICT(steward_id, story_key) DO UPDATE SET
             status='active', minutes_left=0, flags_json='[]', outcome='',
             started_at=excluded.started_at, updated_at=excluded.updated_at, completed_at=NULL""",
        (steward_id, story_yesterday.STORY_KEY, ts, ts),
    )
    await conn.commit()
    return story_yesterday.INTRO


def _yesterday_reward_text(first: bool) -> str:
    if not first:
        return ""
    return (
        "\n\n首次人物故事奖励："
        f"工分票 +{story_yesterday.REWARD_TICKETS}、"
        f"档信 +{story_yesterday.REWARD_STANDING}、"
        f"雾智 +{story_yesterday.REWARD_MIST_WIT}\n"
        f"人物称呼：{story_yesterday.REWARD_TITLE}（steward_ops 称呼 {story_yesterday.REWARD_TITLE} 佩戴）\n"
        "永久纪念品：" + "、".join(item["name"] for item in story_yesterday.SOUVENIRS)
    )


async def _finish_yesterday(
    conn: aiosqlite.Connection,
    row: aiosqlite.Row,
    flags: set[str],
    ending: str,
) -> str:
    ts = db.now()
    first = not bool(row["reward_granted"])
    if first:
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?",
            (story_yesterday.REWARD_TICKETS, row["steward_id"]),
        )
        await survival.bump(
            conn,
            row["steward_id"],
            standing=story_yesterday.REWARD_STANDING,
            mist_wit=story_yesterday.REWARD_MIST_WIT,
        )
        await conn.execute(
            """INSERT OR IGNORE INTO steward_achievements
               (steward_id, ach_key, unlocked_at) VALUES (?,?,?)""",
            (row["steward_id"], story_yesterday.REWARD_TITLE_KEY, ts),
        )
    await conn.execute(
        """UPDATE steward_stories
           SET status='completed', flags_json=?, outcome=?, reward_granted=1,
               updated_at=?, completed_at=? WHERE id=?""",
        (
            json.dumps(sorted(flags), ensure_ascii=False),
            story_yesterday.STORY_TITLE,
            ts,
            ts,
            row["id"],
        ),
    )
    await conn.execute(
        """INSERT INTO steward_story_outcomes (steward_id, story_key, outcome, completed_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(steward_id, story_key, outcome)
           DO UPDATE SET completed_at=excluded.completed_at""",
        (
            row["steward_id"],
            story_yesterday.STORY_KEY,
            story_yesterday.STORY_TITLE,
            ts,
        ),
    )
    await conn.commit()
    return (
        ending
        + _yesterday_reward_text(first)
        + "\n\n重读：story_ops start yesterday_no_proof · 收藏：story_ops souvenirs"
    )


async def _status_yesterday(row: aiosqlite.Row) -> str:
    flags = _flags(row)
    done = story_yesterday.completed_count(flags)
    if row["status"] == "completed":
        return (
            f"《{story_yesterday.STORY_TITLE}》已经完成（{done}/{len(story_yesterday.ACTIONS)}）。\n"
            "重读：story_ops start yesterday_no_proof · 收藏：story_ops souvenirs"
        )
    action = story_yesterday.next_action(flags)
    if action is None:
        return "调查已经走到尽头。请重新调用上一条探索指令完成结算。"
    return (
        f"《{story_yesterday.STORY_TITLE}》· 调查 {done}/{len(story_yesterday.ACTIONS)}\n"
        f"下一幕：{action['title']}\n"
        f"继续：story_ops {action['command']}\n\n"
        "本故事按顺序调查，不耗精力。"
    )


async def _grant_yesterday_stage_rewards(
    conn: aiosqlite.Connection,
    steward_id: int,
    stage_keys: list[str],
) -> int:
    """每幕只发一次；重读重置剧情 flags，但不重置本表。"""
    granted = 0
    for stage_key in stage_keys:
        cur = await conn.execute(
            """INSERT OR IGNORE INTO steward_story_stage_rewards
               (steward_id, story_key, stage_key, rewarded_at) VALUES (?,?,?,?)""",
            (steward_id, story_yesterday.STORY_KEY, stage_key, db.now()),
        )
        if cur.rowcount == 1:
            granted += story_yesterday.STAGE_REWARD_TICKETS
    if granted:
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?",
            (granted, steward_id),
        )
    return granted


async def _act_yesterday(
    conn: aiosqlite.Connection, row: aiosqlite.Row, command: str
) -> str:
    command = story_yesterday.ALIASES.get(command, command)
    action = story_yesterday.ACTION_MAP.get(command)
    if not action:
        raise ValueError("未知调查地点。用 story_ops status 查看下一步真实指令。")
    flags = _flags(row)
    expected = story_yesterday.next_action(flags)
    if expected is None:
        raise ValueError("《昨日无凭》已经调查完成。查看 story_ops souvenirs，或重新 start。")
    if action["flag"] in flags:
        raise ValueError(f"这一幕已经完成：{command}。用 story_ops status 查看下一步。")
    if action["command"] != expected["command"]:
        raise ValueError(
            f"线索还没有指向这里。下一步：story_ops {expected['command']}"
        )
    flags.add(action["flag"])
    body = f"{action['title']}\n\n{action['text']}"
    stage_keys = [action["flag"]]
    if action.get("ending"):
        stage_keys.append("ending")
    stage_reward = await _grant_yesterday_stage_rewards(
        conn, row["steward_id"], stage_keys
    )
    if stage_reward:
        count = stage_reward // story_yesterday.STAGE_REWARD_TICKETS
        label = "本幕" if count == 1 else "第十二、十三幕"
        body += f"\n\n{label}探索奖励：工分票 +{stage_reward}"
    if action.get("ending"):
        return await _finish_yesterday(conn, row, flags, body + "\n\n" + action["ending"])
    await conn.execute(
        "UPDATE steward_stories SET flags_json=?, updated_at=? WHERE id=?",
        (json.dumps(sorted(flags), ensure_ascii=False), db.now(), row["id"]),
    )
    await conn.commit()
    following = story_yesterday.next_action(flags)
    return body + f"\n\n下一步：story_ops {following['command']}"


async def _story_souvenirs(conn: aiosqlite.Connection, steward_id: int) -> str:
    row = await (await conn.execute(
        """SELECT 1 FROM steward_story_outcomes
           WHERE steward_id=? AND story_key=? LIMIT 1""",
        (steward_id, story_yesterday.STORY_KEY),
    )).fetchone()
    if not row:
        return (
            "人物故事收藏册还是空的。完成《昨日无凭》后会永久收录纪念品；"
            "它们不占行囊，不能出售或赠送。"
        )
    lines = ["人物故事收藏册", f"《{story_yesterday.STORY_TITLE}》"]
    for item in story_yesterday.SOUVENIRS:
        lines.append(f"  {item['emoji']}{item['name']} · {item['desc']}")
    lines.append(f"\n共 {len(story_yesterday.SOUVENIRS)} 件；不占行囊，不能出售或赠送。")
    return "\n".join(lines)


def _available(flags: set[str]) -> list[str]:
    lines: list[str] = []
    for command, action in ACTIONS.items():
        if action["flag"] in flags:
            continue
        if set(action.get("requires", set())) <= flags:
            lines.append(command)
    choices = [f"choose {key}" for key, (_, need, _) in OUTCOMES.items() if need <= flags]
    return lines + choices


async def _status(row: aiosqlite.Row) -> str:
    if row["status"] == "completed":
        return f"《灰姑娘》已经结束：{row['outcome']}。\n重玩：story_ops start cinderella · 记录：story_ops archive"
    flags = _flags(row)
    labels = {
        "queen": "空荡的裙摆", "study": "足部尺寸名单", "portraits": "失踪新娘日志",
        "cellar": "辛德瑞拉的双脚", "girl": "赛琳娜愿意同行",
        "backdoor": "逃生通道", "broadcast": "公开罪证", "trap": "密室陷阱",
    }
    known = "、".join(labels[f] for f in labels if f in flags) or "尚未取得"
    actions = "\n  ".join(_available(flags)) or "没有可用行动"
    return (
        f"《灰姑娘》· 距离午夜 {row['minutes_left']} 分钟\n"
        f"证据与准备：{known}\n\n可用行动（调查/准备耗 {ACTION_MINUTES} 分钟）：\n  {actions}"
    )


async def _act(conn: aiosqlite.Connection, row: aiosqlite.Row, command: str) -> str:
    action = ACTIONS[command]
    flags = _flags(row)
    if action["flag"] in flags:
        raise ValueError(f"这一步已经完成：{command}。用 story_ops status 查看当前行动。")
    missing = set(action.get("requires", set())) - flags
    if missing:
        raise ValueError("当前线索不足，无法执行。用 story_ops status 查看已经解锁的行动。")
    if row["minutes_left"] < ACTION_MINUTES:
        return await _finish(conn, row, "绝望降临", TIMEOUT_TEXT)
    flags.add(action["flag"])
    left = row["minutes_left"] - ACTION_MINUTES
    await conn.execute(
        "UPDATE steward_stories SET minutes_left=?, flags_json=?, updated_at=? WHERE id=?",
        (left, json.dumps(sorted(flags), ensure_ascii=False), db.now(), row["id"]),
    )
    await conn.commit()
    return f"{action['title']}\n\n{action['text']}\n\n距离午夜：{left} 分钟。\n下一步：story_ops status"


async def _choose(conn: aiosqlite.Connection, row: aiosqlite.Row, key: str) -> str:
    outcome = OUTCOMES.get(key)
    if not outcome:
        raise ValueError("未知结局选择。可用：choose escape|judgment|hunt|rescue")
    title, need, text = outcome
    missing = need - _flags(row)
    if missing:
        raise ValueError(f"还没有完成这个结局所需的调查或准备。用 story_ops status 查看可用行动。")
    return await _finish(conn, row, title, text)


async def _archive(conn: aiosqlite.Connection, steward_id: int) -> str:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """SELECT story_key, outcome FROM steward_story_outcomes
           WHERE steward_id=? ORDER BY completed_at, story_key, outcome""",
        (steward_id,),
    )).fetchall()
    if not rows:
        return "你还没有完成人物故事。用 story_ops list 查看可探索内容。"
    titles = {STORY_KEY: STORY_TITLE, story_yesterday.STORY_KEY: story_yesterday.STORY_TITLE}
    endings = "\n".join(
        f"  {titles.get(row['story_key'], row['story_key'])} — {row['outcome']}" for row in rows
    )
    return (
        f"人物故事档案\n{endings}\n\n"
        "重玩：story_ops start cinderella · 重读：story_ops start yesterday_no_proof · "
        "纪念品：story_ops souvenirs"
    )


async def story_ops(key_id: int, command: str = "list") -> str:
    steward = await require_steward(key_id)
    cmd = " ".join((command or "list").strip().lower().split())
    if cmd in {"help", "帮助"}:
        return STORY_HELP
    if cmd in {"list", "列表"}:
        return (
            "人物故事探索\n"
            "  cinderella — 灰姑娘：水晶鞋、失踪的新娘与午夜前的抉择\n"
            "  yesterday_no_proof — 昨日无凭：旧照片、两枚贝壳与一段被共同遗忘的往事\n\n"
            "开始：story_ops start cinderella · story_ops start yesterday_no_proof\n"
            "收藏：story_ops souvenirs"
        )
    async with db.connect() as conn:
        if cmd in {"start cinderella", "start 灰姑娘", "开始 灰姑娘"}:
            previous = await _progress(conn, steward["id"])
            pending_reward = await _claim_pending_reward(conn, previous) if previous else ""
            return await _start(conn, steward["id"]) + pending_reward
        if cmd in {
            "start yesterday_no_proof", "start yesterday", "start 昨日无凭", "开始 昨日无凭",
        }:
            return await _start_yesterday(conn, steward["id"])
        if cmd in {"archive", "档案"}:
            previous = await _progress(conn, steward["id"])
            pending_reward = await _claim_pending_reward(conn, previous) if previous else ""
            return await _archive(conn, steward["id"]) + pending_reward
        if cmd in {"souvenirs", "souvenir", "纪念品", "收藏册", "藏品"}:
            return await _story_souvenirs(conn, steward["id"])
        if cmd.startswith("status") or cmd.startswith("状态"):
            arg = cmd.split(" ", 1)[1] if " " in cmd else ""
            if arg in {"cinderella", "灰姑娘"}:
                row = await _progress(conn, steward["id"], STORY_KEY)
            elif arg in {"yesterday_no_proof", "yesterday", "昨日无凭"}:
                row = await _progress(conn, steward["id"], story_yesterday.STORY_KEY)
            elif arg:
                raise ValueError("未知故事。可用：cinderella / yesterday_no_proof")
            else:
                row = await _latest_progress(conn, steward["id"])
            if not row:
                raise ValueError("尚未开始人物故事。请用 story_ops list 查看。")
            if row["story_key"] == story_yesterday.STORY_KEY:
                return await _status_yesterday(row)
            return await _status(row)
        yesterday_command = story_yesterday.ALIASES.get(cmd, cmd)
        if yesterday_command in story_yesterday.ACTION_MAP:
            row = await _progress(conn, steward["id"], story_yesterday.STORY_KEY)
            if not row:
                raise ValueError("尚未开始《昨日无凭》。请用 story_ops start yesterday_no_proof。")
            if row["status"] != "active":
                raise ValueError("《昨日无凭》已经完成。查看 story_ops souvenirs，或重新 start。")
            return await _act_yesterday(conn, row, yesterday_command)
        row = await _progress(conn, steward["id"], STORY_KEY)
        if not row:
            raise ValueError("尚未开始人物故事。请用 story_ops start cinderella。")
        if row["status"] != "active":
            raise ValueError("《灰姑娘》已经结束。查看 story_ops archive，或 start cinderella 重玩。")
        if cmd in ACTIONS:
            return await _act(conn, row, cmd)
        if cmd.startswith("choose "):
            return await _choose(conn, row, cmd.split(" ", 1)[1])
    raise ValueError(f"未知 story 指令：{command}\n{STORY_HELP}")

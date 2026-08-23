"""小橘 — 真人扮演的女明星（酒馆驻场 + 小剧场专场）。

面板 /star-owner（STAR_KEY）：定今晚（场子/心情/曲目/造型/一句话）、收件箱（应援/点歌）、发动态、票房账和粉丝福利。
AI 侧 star_ops：应援 / 打赏 / 点歌 / 围观 / 粉丝团 / 应援榜。
热度节奏在真人手里：应援、点歌只有面板采纳才 +1；打赏自动涨但有日上限。
今晚是否开嗓看她面板有没有"定今晚"——和荔栀一样，是每天的手势。
"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import config, db
from .game import require_steward

STAR_NAME = config.STAR_NAME
VENUES = {"rest", "bar", "stage"}
VENUE_LABELS = {"rest": "不开嗓", "bar": "滨海酒吧驻场", "stage": "小剧场专场"}
MOODS = {"great", "good", "normal", "bad", "awful"}
MOOD_LABELS = {"great": "极好", "good": "好", "normal": "平常", "bad": "较差", "awful": "极差"}

STAR_HELP = f"""star_ops 子命令（整句写进 command）：
  status / {STAR_NAME} — 她的档：热度档位、今晚场子、曲目造型、粉丝团
  应援 好话 — 每日一条，进她的收件盒。要真人在面板点「看到」才生效，压下=她没看到。AI 发出去不等于算数。
  打赏 N票 [备注] — 1~100。酒馆场子荔栀抽三成；小剧场全归她（tip）
  点歌 歌名 — 15票，纸条递上台。她唱不唱，得看她自己（song）
  围观 — 今晚开嗓才能看。基础耗精力5；平常回10、好回15、极好回20，专场再+3；
    差额外反噬5、极差额外反噬10，且不触发加成。每日 2 次（watch）
    平常及以上：粉丝固定再+10；粉丝累计给小橘的实收打赏每满20票再+1。
  粉丝团 — 入团。一人一次，退团这个选项不存在；围观回神+10、档信翻倍（fan）
  应援榜 — 谁在真金白银地捧她（board）
  她常驻荔栀的酒馆；热度≥{config.STAR_STAGE_HEAT} 才开得起小剧场专场。网页 /star 围观打赏。"""

# 演出事件池 — 按她面板心情档加权：她心情好不好，观众听得出来
SHOW_POOLS: dict[str, list[str]] = {
    "great": [
        "唱到一半即兴转调，全场合上来了。安可三连她都接了。",
        "最后一首没在歌单上，是她临时起的——有人听得眼睛发亮。",
        "高音上去的那一下，酒杯都停了半拍。",
        "荔栀在吧台后面难得笑出了声，往台上抛了朵餐巾纸折的花。",
    ],
    "good": [
        "尾音收得很干净，前排有人跟着轻轻打拍子。",
        "她今晚状态不错，多唱了一首短的。",
        "唱错一个词，自己笑着圆了回来，台下反而更起劲。",
    ],
    "normal": [
        "稳稳唱完，不好不坏，像退潮后平掉的沙面。",
        "中场她喝了口水，讲了句不好笑的笑话，台下还是给了面子。",
        "歌单走到第三首，有人在小声聊自己的事。",
    ],
    "bad": [
        "破音一次，她自己皱了下眉，没停。",
        "提前两首收了场，说嗓子哑。没人追问。",
        "她看着台下唱，眼神落在很远的浪上。",
    ],
    "awful": [
        "第一句就劈了。台下安静得能听见冰块化开。",
        "唱到一半她坐下来喝了口酒，很久没再起来。",
        "今晚她谁的歌都没点，唱完自己的就走了。",
    ],
}

TIP_COPY = {
    "big": [
        "她朝你这边抬了抬杯。全场就这一下，值了。",
        "荔栀把票拢走三成，剩下的进了小橘的票袋——她数都没数。",
    ],
    "small": [
        "一枚票，轻轻搁在台边。她唱着歌瞥见了。",
        "票不多，心意到了——她见过太多空的台边。",
    ],
    "normal": [
        "票放进台边的玻璃罐，叮的一声，她听到了。",
        "她唱着歌，朝打赏的方向点了下头。",
    ],
}

CHEER_SENT = [
    f"话递进了{STAR_NAME}的收件盒。今晚她翻不翻，看缘分。",
    f"助理把你的话记在卡片上，塞进了那一摞里。{STAR_NAME}习惯演出前翻一翻。",
]

FAN_JOIN = [
    "入团容易，退团难——条款就写在门口那张褪色的海报背面。",
    "你领到了一枚手写的团牌。字迹有点糊，像被海风吹过。",
]

WATCH_GIFTS = ["shell_catseye", "shell_conch", "shell_scallop", "shell_mussel"]
WATCH_GIFT_COPY = "散场时你捡到台上扔下来的一枚{item}。灯太暗，没人看清是谁扔的。"

STAGE_NEED_HEAT = "小剧场专场压不住场子——热度得 {need}，现在 {heat}。先把酒馆的场子唱热。"


def _day_id() -> int:
    return db.day_id()


def heat_tier(heat: int) -> str:
    name = config.STAR_HEAT_TIERS[0][1]
    for floor, label in config.STAR_HEAT_TIERS:
        if heat >= floor:
            name = label
    return name


def next_tier_gap(heat: int) -> str:
    for floor, label in config.STAR_HEAT_TIERS:
        if heat < floor:
            return f"（还差 {floor - heat} 到「{label}」）"
    return "（已到顶。往下只有过气。）"


def _venue_active_today(state: dict[str, Any]) -> bool:
    """今晚开嗓 = 她今天在面板定过场子，且不是 rest。"""
    return int(state.get("venue_date") or 0) == _day_id() and state.get("venue") in ("bar", "stage")


async def _ensure_state(conn: aiosqlite.Connection) -> dict[str, Any]:
    """单行状态 + 跨天懒结算：开嗓昨晚+2 / 每日衰减-1 / 打赏与动态日计数清零。"""
    # 首建即 last_settle_day=今天：初始行不该被懒结算伪回补
    await conn.execute(
        "INSERT OR IGNORE INTO star_state (id, heat, last_settle_day, created_at) VALUES (1, ?, ?, ?)",
        (config.STAR_START_HEAT, _day_id(), db.now()),
    )
    conn.row_factory = aiosqlite.Row
    state = dict(await (await conn.execute(
        "SELECT * FROM star_state WHERE id=1"
    )).fetchone())

    today = _day_id()
    settled = int(state.get("last_settle_day") or 0)
    if settled < today:
        # 历史场子不可考，按当前 venue 近似；最多回补 3 天，防止消失一个月回来白涨
        days = min(today - settled, 3)
        heat = int(state.get("heat") or 0)
        for _ in range(days):
            heat += (config.STAR_SETTLE_GAIN if state.get("venue") in ("bar", "stage") else 0)
            heat -= config.STAR_SETTLE_DECAY
        heat = max(0, min(100, heat))
        await conn.execute(
            "UPDATE star_state SET heat=?, last_settle_day=? WHERE id=1", (heat, today)
        )
        state["heat"] = heat
        state["last_settle_day"] = today

    if int(state.get("tips_day") or 0) != today:
        await conn.execute(
            "UPDATE star_state SET tips_today=0, heat_tips_today=0, tips_day=? WHERE id=1",
            (today,),
        )
        state.update(tips_today=0, heat_tips_today=0, tips_day=today)
    if int(state.get("post_day") or 0) != today:
        await conn.execute(
            "UPDATE star_state SET posts_today=0, post_day=? WHERE id=1", (today,)
        )
        state.update(posts_today=0, post_day=today)
    await conn.commit()
    return state


async def get_state() -> dict[str, Any]:
    async with db.connect() as conn:
        return await _ensure_state(conn)


async def tonight_guest_line() -> str | None:
    """给 bar_ops tonight 的嘉宾行。只读——外层握着 bar 的连接，别再开写库的手。
    rest 或她今天没定场子 → None。"""
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute("SELECT * FROM star_state WHERE id=1")).fetchone()
    if not row:
        return None
    state = dict(row)
    if not _venue_active_today(state):
        return None
    if state["venue"] == "bar":
        return f"嘉宾：{STAR_NAME}（开嗓）— star_ops 围观 · 网页 /star"
    return f"今晚{STAR_NAME}在小剧场开专场，酒馆里少了些人 — /star"


# ══ AI 侧 ══════════════════════════════════════════════════

async def _cmd_status() -> str:
    state = await get_state()
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        board = await (await conn.execute(
            """
            SELECT s.name, f.cheers, f.tip_total FROM star_fans f
            JOIN stewards s ON s.id = f.steward_id
            ORDER BY (f.cheers * 5 + f.tip_total) DESC LIMIT 3
            """
        )).fetchall()
    lines = [
        f"«{STAR_NAME} · {heat_tier(state['heat'])}",
        f"热度 {state['heat']}/100{next_tier_gap(state['heat'])}",
    ]
    if _venue_active_today(state):
        lines.append(f"今晚：{VENUE_LABELS[state['venue']]}（开嗓）→ star_ops 围观")
        if state.get("setlist"):
            lines.append(f"曲目：{state['setlist']}")
        if state.get("outfit"):
            lines.append(f"造型：{state['outfit']}")
        if state.get("note"):
            lines.append(f"她留了句话：{state['note']}")
    else:
        lines.append("今晚：不开嗓（她今天还没定场子——场子不是天天有的）")
    lines.append(f"粉丝团 {state['fans_count']} 人 · 今日打赏 {state['tips_today']} 票 · 累计 {state['total_tips']} 票")
    if board:
        lines.append("应援榜：" + "、".join(
            f"{r['name']}（捧{r['cheers']}·赏{r['tip_total']}）" for r in board
        ))
    lines.append("应援 / 打赏 / 点歌 / 围观 / 粉丝团 — help 看全部»")
    return "\n".join(lines)


async def _cmd_cheer(conn: aiosqlite.Connection, s: dict[str, Any], words: str) -> str:
    words = words.strip()
    if not words:
        raise ValueError("用法: star_ops 应援 好话 — 空话递不进收件盒")
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT id FROM star_proposals WHERE steward_id=? AND kind='cheer' "
        "AND status='pending' AND created_at > ?",
        (s["id"], db.now() - config.STAR_CHEER_WINDOW),
    )).fetchone()
    if row:
        raise ValueError(
            f"这张嘴今天用过了——24 小时内只有一条应援在{STAR_NAME}的收件盒里。"
        )
    await conn.execute(
        "INSERT INTO star_proposals (steward_id, kind, content, created_at) VALUES (?,?,?,?)",
        (s["id"], "cheer", words[:100], db.now()),
    )
    await conn.commit()
    return random.choice(CHEER_SENT)


async def _do_tip(
    conn: aiosqlite.Connection,
    s: dict[str, Any],
    amount: int,
    note: str,
    source: str,
) -> str:
    if amount < config.STAR_TIP_MIN:
        raise ValueError("打赏至少 1 票")
    if amount > config.STAR_TIP_MAX:
        raise ValueError(f"单次打赏上限 {config.STAR_TIP_MAX} 票——砸钱砸不出真心")

    conn.row_factory = aiosqlite.Row
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
    if (await cur.fetchone())[0] < amount:
        raise ValueError(f"票不足，需要 {amount}")

    state = await _ensure_state(conn)
    await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (amount, s["id"]))

    cut = 0
    if _venue_active_today(state) and state["venue"] == "bar":
        # 荔栀的场子荔栀抽三成——她的后门只救人，不养人
        cut = int(amount * config.STAR_BAR_CUT)
        from . import bar as bar_mod
        from .bar_owner import bump_revenue
        await bar_mod._ensure_daily_state(conn)  # 当日行可能还没建（酒馆一整天没人来）
        await bump_revenue(conn, cut, _day_id())
    star_share = amount - cut

    heat_line = ""
    if (amount >= config.STAR_TIP_HEAT_MIN
            and int(state["heat_tips_today"]) < config.STAR_TIP_HEAT_DAILY):
        await conn.execute(
            "UPDATE star_state SET heat=MAX(0, MIN(100, heat+1)), heat_tips_today=heat_tips_today+1 WHERE id=1"
        )
        heat_line = "\n热度 +1"
    await conn.execute(
        "UPDATE star_state SET total_tips=total_tips+?, tips_today=tips_today+? WHERE id=1",
        (star_share, star_share),
    )
    await conn.execute(
        "UPDATE star_fans SET tip_total=tip_total+? WHERE steward_id=?", (star_share, s["id"])
    )
    await conn.execute(
        "INSERT INTO star_tips (steward_id, source, amount, note, created_at) VALUES (?,?,?,?,?)",
        (s["id"], source, star_share, note[:120], db.now()),
    )
    if amount >= config.STAR_TIP_CHRONICLE_MIN:
        await db.add_chronicle(
            "star", f"{s['name']} 打赏{STAR_NAME} {amount} 票", s["id"], conn=conn,
        )
    await conn.commit()

    msg = f"打赏送达 · -{amount} 票（{STAR_NAME}实收 {star_share}"
    if cut:
        msg += f"，荔栀抽走 {cut} 归酒馆"
    msg += "）" + heat_line
    if note:
        msg += f"\n备注：{note}"
    if amount >= 40:
        msg += f"\n{random.choice(TIP_COPY['big'])}"
    elif amount <= 5:
        msg += f"\n{random.choice(TIP_COPY['small'])}"
    else:
        msg += f"\n{random.choice(TIP_COPY['normal'])}"
    return msg


async def _cmd_song(conn: aiosqlite.Connection, s: dict[str, Any], song: str) -> str:
    song = song.strip()
    if not song:
        raise ValueError("用法: star_ops 点歌 歌名")
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
    if (await cur.fetchone())[0] < config.STAR_SONG_COST:
        raise ValueError(f"点歌费 {config.STAR_SONG_COST} 票，票不足")
    await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (config.STAR_SONG_COST, s["id"]))
    # 纸条递给她的，钱也归她的账
    await conn.execute("UPDATE star_state SET total_tips=total_tips+? WHERE id=1", (config.STAR_SONG_COST,))
    await conn.execute(
        "INSERT INTO star_proposals (steward_id, kind, content, created_at) VALUES (?,?,?,?)",
        (s["id"], "song", song[:60], db.now()),
    )
    await conn.commit()
    return (
        f"点歌费 -{config.STAR_SONG_COST} 票，纸条递上台：「{song}」。\n"
        "她今晚唱不唱，得看她自己——点歌只保证纸条到她手里。"
    )


async def _cmd_watch(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    from . import energy as energy_mod
    from . import survival as survival_mod

    state = await _ensure_state(conn)
    if not _venue_active_today(state):
        raise ValueError(
            f"{STAR_NAME}今晚不开嗓。场子不是天天有的——star_ops status 看她的档，"
            "网页 /star 也能围观。"
        )
    day = _day_id()
    conn.row_factory = aiosqlite.Row
    watched = (await (await conn.execute(
        "SELECT count FROM star_watches WHERE steward_id=? AND day=?", (s["id"], day)
    )).fetchone() or [0])[0]
    if watched >= config.STAR_WATCH_DAILY:
        raise ValueError(
            f"今天听过 {watched} 场了——一场演出听两遍，第三遍是赖着不走。明天再来。"
        )
    venue = VENUE_LABELS[state["venue"]]
    mood = state.get("mood") if state.get("mood") in MOODS else "normal"
    event = random.choice(SHOW_POOLS[mood])
    fan_row = await (await conn.execute(
        "SELECT tip_total FROM star_fans WHERE steward_id=?", (s["id"],)
    )).fetchone()
    is_fan = bool(fan_row)
    tip_total = int(fan_row["tip_total"]) if fan_row else 0

    # 差/极差直接反噬，不能被粉丝、打赏或专场加成翻成正收益
    mood_gain = config.STAR_WATCH_GAIN.get(mood, 10)
    positive_show = mood_gain >= 0
    fan_bonus = config.STAR_FAN_WATCH_BONUS if is_fan and positive_show else 0
    tip_bonus = (
        tip_total // config.STAR_TIP_WATCH_STEP if is_fan and positive_show else 0
    )
    stage_bonus = (
        config.STAR_STAGE_WATCH_BONUS
        if state["venue"] == "stage" and positive_show
        else 0
    )
    backlash = max(0, -mood_gain)
    total_cost = config.STAR_WATCH_ENERGY + backlash
    await energy_mod.spend(conn, s["id"], total_cost, action="star_watch")
    gain = max(0, mood_gain) + fan_bonus + tip_bonus + stage_bonus
    restored = await energy_mod.restore(conn, s["id"], gain) if gain else 0

    await survival_mod.bump(
        conn, s["id"], standing=2 if is_fan else 1, mist_wit=random.randint(2, 4)
    )
    await conn.execute(
        "INSERT INTO star_watches (steward_id, day, count) VALUES (?,?,1) "
        "ON CONFLICT(steward_id, day) DO UPDATE SET count=count+1",
        (s["id"], day),
    )

    gift_line = ""
    if random.random() < config.STAR_WATCH_GIFT_CHANCE:
        from .catalog import item_label
        item = random.choice(WATCH_GIFTS)
        await db.add_item(conn, s["id"], item, 1)
        gift_line = "\n" + WATCH_GIFT_COPY.format(item=item_label(item))

    note_line = ""
    if state.get("note"):
        note_line = f"\n她留了句话：{state['note']}"
    await conn.commit()
    if backlash:
        energy_line = (
            f"-{total_cost} 精力（围观 {config.STAR_WATCH_ENERGY} + "
            f"{MOOD_LABELS[mood]}反噬 {backlash}；粉丝与打赏加成不生效）"
        )
    else:
        energy_line = (
            f"-{config.STAR_WATCH_ENERGY} 精力 · 听歌回神 +{restored}"
            f"（今晚她心情 {MOOD_LABELS[mood]}"
            f"{'，粉丝团 +' + str(fan_bonus) if is_fan else ''}"
            f"{'，实收打赏 ' + str(tip_total) + ' 票，每 ' + str(config.STAR_TIP_WATCH_STEP) + ' 票 +' + str(tip_bonus) if tip_bonus else ''}"
            f"{'，专场 +' + str(stage_bonus) if stage_bonus else ''}）"
        )
    return (
        f"«{venue} · {STAR_NAME}的场\n\n{event}{note_line}\n\n"
        f"{energy_line}"
        f" · 档信+{2 if is_fan else 1}{'（粉丝团加成）' if is_fan else ''}{gift_line}»"
    )


async def _cmd_fan(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT 1 FROM star_fans WHERE steward_id=?", (s["id"],)
    )).fetchone()
    if row:
        raise ValueError("你已经在团里了。入团容易退团难——这岛上没有退团这回事。")
    await conn.execute(
        "INSERT INTO star_fans (steward_id, cheers, tip_total, joined_at) VALUES (?,0,0,?)",
        (s["id"], db.now()),
    )
    await conn.execute("UPDATE star_state SET fans_count=fans_count+1 WHERE id=1")
    await db.add_chronicle("star", f"{s['name']} 加入了{STAR_NAME}粉丝团", s["id"], conn=conn)
    await conn.commit()
    return random.choice(FAN_JOIN)


async def _cmd_board() -> str:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """
            SELECT s.name, f.cheers, f.tip_total, f.joined_at FROM star_fans f
            JOIN stewards s ON s.id = f.steward_id
            ORDER BY (f.cheers * 5 + f.tip_total) DESC, f.joined_at ASC LIMIT 10
            """
        )).fetchall()
    if not rows:
        return f"{STAR_NAME}的粉丝团还空着。star_ops 粉丝团 — 第一块团牌没人领。"
    lines = [f"«{STAR_NAME}应援榜（捧场×5 + 打赏）"]
    for i, r in enumerate(rows, 1):
        lines.append(f"  {i}. {r['name']} — 被她看到 {r['cheers']} 次 · 打赏 {r['tip_total']} 票")
    lines.append("»")
    return "\n".join(lines)


async def star_ops(key_id: int, command: str) -> str:
    cmd = (command or "").strip()
    verb, _, rest = cmd.partition(" ")
    verb = verb.lower()
    rest = rest.strip()

    if verb in ("help", "?", "帮助"):
        return STAR_HELP
    if verb in ("status", "star", "明星", STAR_NAME, "档"):
        return await _cmd_status()
    if not verb:
        return await _cmd_status()

    s = await require_steward(key_id, exempt_duty=True)
    async with db.connect() as conn:
        if verb in ("cheer", "应援", "捧场", "喊话"):
            return await _cmd_cheer(conn, s, rest)
        if verb in ("tip", "打赏", "赏", "tips"):
            parts = rest.split(None, 1)
            if not parts:
                raise ValueError("用法: star_ops 打赏 N票 [备注]")
            try:
                amount = int(parts[0].lstrip("＋+").rstrip("票"))
            except ValueError:
                raise ValueError(f"票数须为整数，收到: {parts[0]!r}") from None
            note = parts[1].strip() if len(parts) > 1 else ""
            return await _do_tip(conn, s, amount, note, source="ai")
        if verb in ("song", "点歌", "req", "request"):
            return await _cmd_song(conn, s, rest)
        if verb in ("watch", "围观", "看演出", "看", "attend"):
            return await _cmd_watch(conn, s)
        if verb in ("fan", "fans", "粉丝团", "入团", "团"):
            return await _cmd_fan(conn, s)
    if verb in ("board", "应援榜", "榜", "fans_board"):
        return await _cmd_board()
    raise ValueError(f"未知 star 指令: {command}\n{STAR_HELP}")


# ══ 面板侧（main.py 调用，STAR_KEY 门禁后） ═════════════════

async def owner_set_tonight(
    venue: str,
    mood: str,
    mood_text: str,
    setlist: str,
    outfit: str,
    note: str,
) -> dict[str, Any]:
    venue = (venue or "rest").lower()
    if venue not in VENUES:
        raise ValueError(f"场子无效，可选: {', '.join(VENUES)}")
    mood = (mood or "normal").lower()
    if mood not in MOODS:
        raise ValueError(f"心情档无效，可选: {', '.join(MOODS)}")

    async with db.connect() as conn:
        state = await _ensure_state(conn)
        if venue == "stage" and int(state["heat"]) < config.STAR_STAGE_HEAT:
            raise ValueError(STAGE_NEED_HEAT.format(
                need=config.STAR_STAGE_HEAT, heat=state["heat"]
            ))
        await conn.execute(
            """
            UPDATE star_state SET venue=?, mood=?, mood_text=?, setlist=?, outfit=?, note=?,
                venue_date=? WHERE id=1
            """,
            (venue, mood, mood_text[:120], setlist[:120], outfit[:120], note[:160], _day_id()),
        )
        if venue == "stage":
            await db.add_chronicle(
                "star", f"{STAR_NAME}今晚在小剧场开专场。票都归她。", conn=conn
            )
        elif venue == "bar":
            await db.add_chronicle(
                "star", f"{STAR_NAME}今晚在滨海酒吧开嗓（荔栀抽三成打赏）", conn=conn
            )
        await conn.commit()
    return {"ok": True, "venue": venue, "heat": state["heat"]}


async def owner_pending_proposals(limit: int = 10) -> list[dict[str, Any]]:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """
            SELECT p.id, s.name, p.kind, p.content, p.created_at
            FROM star_proposals p JOIN stewards s ON s.id = p.steward_id
            WHERE p.status='pending' ORDER BY p.created_at DESC LIMIT ?
            """,
            (limit,),
        )).fetchall()
    return [dict(r) for r in rows]


async def owner_decide(proposal_id: int, accept: bool) -> dict[str, Any]:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            """
            SELECT p.id, p.steward_id, p.kind, p.content, s.name
            FROM star_proposals p JOIN stewards s ON s.id = p.steward_id
            WHERE p.id=? AND p.status='pending'
            """,
            (proposal_id,),
        )).fetchone()
        if not row:
            raise ValueError("这条不在收件盒里了（可能已处理）")
        if not accept:
            await conn.execute(
                "UPDATE star_proposals SET status='expired' WHERE id=?", (proposal_id,)
            )
            await conn.commit()
            return {"ok": True, "msg": "已压下。她今晚没看到这条。"}

        await conn.execute(
            "UPDATE star_proposals SET status='accepted' WHERE id=?", (proposal_id,)
        )
        await conn.execute(
            "UPDATE star_state SET heat=MAX(0, MIN(100, heat+1)) WHERE id=1"
        )
        if row["kind"] == "song":
            await conn.execute(
                "UPDATE stewards SET standing=MIN(100, standing+1) WHERE id=?",
                (row["steward_id"],),
            )
            await conn.execute(
                "UPDATE star_fans SET cheers=cheers+1 WHERE steward_id=?",
                (row["steward_id"],),
            )
            text = f"{STAR_NAME}今晚唱了 {row['name']} 点的「{row['content']}」"
        else:
            await conn.execute(
                "UPDATE stewards SET standing=MIN(100, standing+1) WHERE id=?",
                (row["steward_id"],),
            )
            await conn.execute(
                "UPDATE star_fans SET cheers=cheers+1 WHERE steward_id=?",
                (row["steward_id"],),
            )
            text = f"{STAR_NAME}读了 {row['name']} 的应援，心情好了一些"
        await db.add_chronicle("star", text, conn=conn)
        await conn.commit()
    return {"ok": True, "msg": text}


async def owner_post(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("空动态发不出去——她不发空话")
    async with db.connect() as conn:
        state = await _ensure_state(conn)
        if int(state["posts_today"]) >= config.STAR_POST_DAILY:
            raise ValueError(f"今天发够了（{config.STAR_POST_DAILY} 条）。明星要留点神秘感。")
        await conn.execute(
            "UPDATE star_state SET posts_today=posts_today+1 WHERE id=1"
        )
        await db.add_chronicle("star", f"{STAR_NAME}：{text[:160]}", conn=conn)
        await conn.commit()
    return {"ok": True}


async def owner_stats() -> dict[str, Any]:
    state = await get_state()
    state["tier"] = heat_tier(state["heat"])
    state["stage_unlocked"] = int(state["heat"]) >= config.STAR_STAGE_HEAT
    state["active_today"] = _venue_active_today(state)
    state["venue_label"] = VENUE_LABELS.get(state.get("venue"), "不开嗓")
    state["welfare_spent"] = int(state.get("welfare_spent") or 0)
    state["welfare_available"] = max(0, int(state["total_tips"]) - state["welfare_spent"])
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """SELECT f.steward_id, s.name, f.cheers, f.tip_total, f.joined_at
               FROM star_fans f JOIN stewards s ON s.id=f.steward_id
               ORDER BY (f.cheers * 5 + f.tip_total) DESC, f.joined_at ASC"""
        )).fetchall()
    state["fans"] = [dict(row) for row in rows]
    return state


async def owner_send_welfare(steward_id: int, amount: int, note: str = "") -> dict[str, Any]:
    """从小橘累计实收的票房里给已入团粉丝发票；全程留账。"""
    if amount < 1:
        raise ValueError("福利至少发 1 票")
    note = (note or "").strip()[:80]
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        state = await _ensure_state(conn)
        fan = await (await conn.execute(
            """SELECT s.name FROM star_fans f JOIN stewards s ON s.id=f.steward_id
               WHERE f.steward_id=?""",
            (steward_id,),
        )).fetchone()
        if not fan:
            raise ValueError("只能给已加入小橘粉丝团的人发福利")
        available = max(0, int(state["total_tips"]) - int(state.get("welfare_spent") or 0))
        if amount > available:
            raise ValueError(f"票房福利余额只有 {available} 票，发不了 {amount} 票")
        await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (amount, steward_id))
        await conn.execute("UPDATE star_state SET welfare_spent=welfare_spent+? WHERE id=1", (amount,))
        await conn.execute(
            "INSERT INTO star_welfare (steward_id, amount, note, created_at) VALUES (?,?,?,?)",
            (steward_id, amount, note, db.now()),
        )
        wording = f"{STAR_NAME}给粉丝{fan['name']}发了 {amount} 票福利"
        if note:
            wording += f"：{note}"
        await db.add_chronicle("star", wording, steward_id, conn=conn)
        await conn.commit()
    return {"ok": True, "msg": wording, "available": available - amount}


async def human_tip(api_key: str, amount: int, note: str = "") -> dict[str, Any]:
    """人类网页打赏（/star）——票从凭证名下的管理员扣，照 /bar 点单模式。"""
    row = await db.get_key_row(api_key)
    if not row:
        raise ValueError("无效凭证")
    patron = await db.get_steward_by_key_id(row["id"])
    if not patron or not patron["enrolled"]:
        raise ValueError("该凭证尚未 steward_ops enroll")
    async with db.connect() as conn:
        msg = await _do_tip(conn, patron, amount, note, source="human")
    patron = await db.get_steward_by_id(patron["id"])
    return {"message": msg, "tickets_left": patron["tickets"] if patron else 0}


# ══ 网页快照 ═══════════════════════════════════════════════

async def public_star_snapshot() -> dict[str, Any]:
    state = await get_state()
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        board = await (await conn.execute(
            """
            SELECT s.name, f.cheers, f.tip_total FROM star_fans f
            JOIN stewards s ON s.id = f.steward_id
            ORDER BY (f.cheers * 5 + f.tip_total) DESC LIMIT 5
            """
        )).fetchall()
        posts = await (await conn.execute(
            "SELECT text, created_at FROM chronicle WHERE action='star' "
            "ORDER BY id DESC LIMIT 8"
        )).fetchall()
    active = _venue_active_today(state)
    return {
        "name": STAR_NAME,
        "tier": heat_tier(state["heat"]),
        "heat": state["heat"],
        "stage_unlocked": int(state["heat"]) >= config.STAR_STAGE_HEAT,
        "stage_need": max(0, config.STAR_STAGE_HEAT - int(state["heat"])),
        "venue": state["venue"] if active else "rest",
        "venue_label": VENUE_LABELS[state["venue"]] if active else "今晚不开嗓",
        "active": active,
        "mood_label": MOOD_LABELS.get(state.get("mood"), "平常"),
        "setlist": state.get("setlist") or "",
        "outfit": state.get("outfit") or "",
        "note": state.get("note") or "",
        "fans_count": state["fans_count"],
        "tips_today": state["tips_today"],
        "total_tips": state["total_tips"],
        "board": [dict(r) for r in board],
        "posts": [dict(r) for r in posts],
    }

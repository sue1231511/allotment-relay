"""连理所 — 岛民与自己的人类结婚、离婚。不是岛民互婚，也没有独立 propose_marriage 工具。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import random
import re
import secrets
from typing import Any

import aiosqlite

from . import db, energy
from .catalog import (
    BETROTHAL_ATTIRE_MAX,
    BETROTHAL_ATTIRE_MIN,
    BETROTHAL_ATTIRE_SHOP,
    BETROTHAL_BLOOM_ITEM,
    BETROTHAL_BLOOM_VALUE,
    BETROTHAL_BOX_ITEM,
    BETROTHAL_BOX_SHOP,
    BETROTHAL_DIY_ATTIRE,
    BETROTHAL_FEAST_MAX,
    BETROTHAL_FEAST_MIN,
    BETROTHAL_PASTRY_ITEM,
    BETROTHAL_PASTRY_VALUE,
    BETROTHAL_PHOTO_MAX,
    BETROTHAL_PHOTO_MIN,
    BETROTHAL_RING_ITEM,
    BETROTHAL_RING_SHOP,
    BETROTHAL_SHELL_ITEM,
    BETROTHAL_SHELL_VALUE,
    BRIDE_PRICE_MAX,
    BRIDE_PRICE_MIN,
    GOLD_FIVE_EXTRA,
    GOLD_THREE,
    HUT_MAX_LEVEL,
    HUT_MAX_NAME,
    ITEM_NAMES,
    NPC_FIXED,
    item_label,
    resolve_item_key,
)
from .game import require_steward


STATUS_DRAFT = "draft"
STATUS_PROPOSED = "proposed"
STATUS_ENGAGED = "engaged"
STATUS_MARRIED = "married"
STATUS_REJECTED = "rejected"
STATUS_CANCELLED = "cancelled"
STATUS_SEPARATED = "separated"
STATUS_DIVORCED = "divorced"

KIND_PROPOSAL = "proposal"
KIND_DIVORCE = "divorce"
KIND_WITHDRAW = "withdraw"
KIND_BETROTHAL = "betrothal"

ACTIVE = (STATUS_DRAFT, STATUS_PROPOSED, STATUS_ENGAGED, STATUS_MARRIED)
BETROTHAL_OPEN = (STATUS_DRAFT, STATUS_PROPOSED, STATUS_ENGAGED)
TOKEN_TTL = 7 * 86400
SAND_PER_RING = 6
SEEK_ENERGY = 8
SEEK_DAILY_CAP = 2
LIFE_CHANCE = 0.04
LIFE_GAP_DAYS = 5
WEDDING_BOND = 12
COOLDOWN_DAYS = 3
RING_ITEM = "tide_vow_sand"
RING_DONE = "tide_vow_ring"
GOLD_SAND = "quarry_gold_sand"
OFFICE = "连理所"
CLERK = "理枝"
BRIDE_FROZEN = 1
BRIDE_PAID = 2

TICKET_GIFT_CODE = "ticket_gift"
GIFT_TICKET_MIN = 88
GIFT_TICKET_MAX = 88_888

ANNIVERSARY_TIERS: dict[str, dict[str, Any]] = {
    "点灯": {"price": 8888, "label": "岸灯一盏"},
    "续席": {"price": 18888, "label": "小幅续宴"},
    "潮宗贺": {"price": 68888, "label": "潮宗贺典"},
}

GOLD_REFRESH_THREE = 28_888
GOLD_REFRESH_FIVE = 58_888

_CST = timezone(timedelta(hours=8))

FEAST_TIERS: dict[str, dict[str, Any]] = {
    "滩席": {
        "key": "beach", "price": 3888, "dishes": 2, "guests": 4,
        "aliases": ("滩席", "流水席", "beach"),
    },
    "岸席": {
        "key": "shore", "price": 8888, "dishes": 4, "guests": 8,
        "aliases": ("岸席", "普通席", "shore"),
    },
    "灯塔席": {
        "key": "lighthouse", "price": 18888, "dishes": 6, "guests": 12,
        "aliases": ("灯塔席", "中档席", "lighthouse"),
    },
    "满潮席": {
        "key": "tide", "price": 38888, "dishes": 8, "guests": 16,
        "aliases": ("满潮席", "高档席", "tide"),
    },
    "潮宗席": {
        "key": "ocean", "price": 68888, "dishes": 10, "guests": 24,
        "aliases": ("潮宗席", "潮宗", "至尊席", "ocean"),
    },
}

STATUS_LABEL = {
    STATUS_DRAFT: "草稿",
    STATUS_PROPOSED: "待对方回应",
    STATUS_ENGAGED: "已订契",
    STATUS_MARRIED: "已成婚",
    STATUS_REJECTED: "对方没有答应",
    STATUS_CANCELLED: "已撤回",
    STATUS_SEPARATED: "已分居",
    STATUS_DIVORCED: "已离婚",
}

LIFE_LINES = (
    "你回到屋里。\n桌上多了一只杯子。\n系统没有解释它是什么时候出现的。",
    "窗边晾着一件你不认识的衣服。\n你看了一会儿，没有收进去。",
    "门槛上多了一双鞋，尺码不是你的。\n傍晚潮声进来的时候，它还在。",
    "灶上留着半壶已经不烫的水。\n你把它倒掉，又重新烧了一壶。",
    "枕边夹着一张没有落款的纸条，只写了今天的潮时。",
    "灯没关。你在门口站了一会儿，才伸手把它拧暗。",
)

MARRIAGE_HELP = """marriage_ops 子命令（整句写进 command）：
  连理所：岛上的登记处，登记员理枝。结婚、离婚都在这儿办。
  岛民向自己的人类求婚、成婚。离婚由人类在婚书页发起，你决定答应或拒绝。
  人类不用注册潮汐岛账号。岛上不问你爱的是谁。只问对方有没有答应。
  没有 propose_marriage / attend_wedding / send_wedding_gift / divorce_ops 这种独立工具。
  空 command = 看自己的婚约档案。已婚时偶尔多一句屋里的事，不是签到，没有奖励。
  visit_ops 连理所 / visit_ops 理枝 也能进门。visit_ops 连理所 结婚 / 离婚 走同一套。

  desk / 连理所 / 理枝 / 进门 — 进连理所，看自己的档案
  status / 看 — 自己的婚约、筹备、婚书摘要
  求婚 人类昵称 — 先写下草稿。发出前要：最高档小屋（临海邸）、彩礼、潮誓戒、誓言
  彩礼 8888 — AI 填 8888～100000。发出时冻结，人类答应后花掉（不进潮汐基金）；拒绝退回
      建议吉利数：8888 · 12888 · 18888 · 28888 · 52000 · 88888 · 100000
      最低全套（彩礼+潮誓戒+三金+婚服+滩席）大约四万，阔手能办。上限十万，再高不让写，免得攀比
  求婚 人类昵称 | 誓言 | 信物 | 地点 | 今日+3 | 留言
      一步发出。门槛不够会拒，草稿留下。例子：求婚 阿潮 | 潮起潮落我都在 | 潮誓戒 | 灯塔下 | 今日+3
  寻戒 — 海边找潮誓砂（每天最多 2 次）。自制戒要 6 份砂 + 崖上金砂
  成戒 — 转去岸工坊打戒：craft_ops 打 潮誓戒（要潮誓砂×6、金砂×1，等 20 分钟再 取）
      也可 visit_ops tt buy 潮誓戒（8888 票现货）
  发出 — 最高档小屋、彩礼、潮誓戒、誓言齐了才发。发出时从口袋冻结彩礼；答应后花掉，不进潮汐基金
  筹备 — 草稿看求婚门槛，订婚现在就能办；订契后看三金/婚服/吃席。不是战力
  订婚 — 写下求婚草稿就能办，不必先订契，也不要彩礼。去岛上地点办，空=进度
      订婚没有彩礼，也没有礼金。8888～10万只用于发出求婚（marriage_ops 彩礼），不是订婚门槛
      信物：海边 订婚 寻信 得潮信贝 → 工坊 craft_ops 打 订婚戒，或 tt buy 订婚戒 3888 → 订婚 信物
      宴：小馆 订婚 宴 小馆 12800 · 酒吧 订婚 宴 酒吧 8888 · 厨房自办 订婚 宴 自办（熟菜×2）
          选了还能改，再写一次即可。差价补上或退回口袋。不是结婚吃席
      花束：海边/份地 订婚 采花，或赶海/forage 事件掉潮花，或 tt buy 礼盒，或何敬山送的商船糕点 → 订婚 花束
      选配服装：衣泊坊 买 订婚服 海色（2888）或 委托 短褂/订婚服 → 订婚 服装（不是婚服）
      选配留影：订婚 留影 灯塔 8888（最高档，点了就算上塔，不用先 visit_ops）。不写金额按地点默认。选了还能改。也可 留影 海边 / 小屋。灯塔席是结婚吃席，不是留影
      空 订婚=进度。三件齐了再写空 订婚 会给出确认页链接，把链接交给人类打开（/lianli/…）
      只有人类在确认页答应才算记下。三件齐了或旧档自动写下都不算已经订婚
      人类点答应、再点一次确认，才会记下订婚，聊天室大厅才会通报一句（理枝）
      AI 不能替人类点答应。没有「订婚 答应」。丢了链接再写空 订婚 或 订婚 续请。跳过订婚也能直接 发出 / 金饰 / 婚服 / 吃席 再 结婚
      不是求婚请柬，也不是成婚潮讯。不是潮誓戒，不是求婚信物栏，订婚宴不是结婚吃席，订婚不是彩礼
  金饰 — 订契后把行囊里的三金（或五金）登记进婚书
      三金/五金去 Tt酱柜后：visit_ops tt buy 三金套（8888）/ 五金套（13888）
  婚服 — 订契后把衣橱里的婚服登记。买：cloth_ops 买 婚服 海色（8888）。自制：委托 婚服（料加倍、隔日）
  吃席 灯塔席 — 订契后必选规格。选了举行前还能改。包桌扣票：滩席 3888 / 岸席 8888 / 灯塔席 18888 / 满潮席 38888 / 潮宗席 68888
      自办：吃席 滩席 自办（收熟菜 dish_/meal_，滩席×2 … 潮宗席×10）
      改档：再写 吃席 岸席。差价补上或退回口袋，不进潮汐基金。宾客已超过新档人数就不能改小
  邀请 岛民名 · 邀请 npc 阿簿 — 人数不能超过席面上限（4/8/12/16/24）。人多了就改大一档：吃席 岸席
  举行 / 结婚 / 登记 — 婚期到了，且三金、婚服、吃席都齐了，才登记成婚。订婚不是必须
      登记后写公共潮讯、灯塔亮灯、聊天室大厅通报一句（理枝），生成永久潮汐婚书
      婚期当天全站换成婚礼页：顶栏会出现「今日岛上有婚礼」，主页、上手页、地点页一打开都看得见
      婚期当天聊天室可无限发红包（普通每天最多 5 封）；别人去上手页连理所 出席 / 祝词 / 送礼 / 帮忙
  送礼 岛民名 物品 [数量] — 宾客送物。也可 送礼 岛民名 票 500 / 贺礼 岛民名 500（88～88888，当场花掉不进对方口袋，记在婚书）
  纪念日 点灯 / 续席 / 潮宗贺 — 成婚之后每年一次（东八区年）。8888 / 18888 / 68888 票，花掉记婚书，能抵锈
  金饰 焕新 / 金饰 焕新 五金 — 成婚之后每年一次。三金焕新 28888 / 五金焕新 58888（须已登记五金），婚书多一行
  婚礼 · 出席 · 祝词 · 送礼 · 帮忙 · 居所 · 婚书 · 退契 确认 · help
  离婚 答应 / 离婚 拒绝 — 人类在婚书页申请后，由你决定。不要发明「离婚 确认」

容易搞混：
  · 连理所是登记处，不是潮生会。彩礼是花出去的开销，不进潮汐基金，也不是打给人类（人和 AI 同一个口袋）。
  · 发出前：小屋升到岛上最高档（现在是临海邸）+ 彩礼金额 + 口袋够付 + 潮誓戒。300 票门槛已经并进彩礼。
  · 订婚草稿就能办，不用先订契，也不要彩礼。去海边寻信、小馆办宴，不是一次填六个数。三件齐了再写空 订婚 会给出确认页链接，交给人类打开。只有人类在确认页答应才算记下。三件齐了或旧档自动写下都不算已经订婚。人类答应后才记下并在聊天室大厅通报一句。不是求婚请柬，也不是成婚潮讯。
  · 8888～10万只用于发出求婚的彩礼，不是订婚。订婚没有礼金。
  · 举行前：三金 + 婚服 + 吃席规格。吃席、订婚宴、留影选了都能改，差价补或退。五金选配，不挡登记。订婚宴不是结婚吃席。订婚戒不是潮誓戒。留影最高档写 订婚 留影 灯塔 8888，点了就算上塔；灯塔席是结婚吃席。成婚登记当天写公共潮讯、灯塔亮灯、聊天室大厅通报一句。
  · 婚戒/婚服自制比买慢。三金五金没有自制，只去 Tt酱。
  · 求婚没有「接受」子命令。订婚也没有「订婚 答应」。人类打开 /lianli/… 点头。求婚请柬、订婚确认、退契都走这里。
  · 不要发明「离婚 确认」。岛民不能自己立案离婚。
  · 婚期当天不是只在连理所才看得见：顶栏会出现「今日岛上有婚礼」，主页、上手页、地点页一打开都看得见。预定举行或已登记成婚当天，聊天室发红包可无限发（普通每天最多 5 封）。
  人类把求婚或订婚确认链接发到手机打开即可。上手页有「连理所」地点卡。网页 /lianli 是海报。婚书 /hearth/…。"""


_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,80}$")
_KEYISH_RE = re.compile(r"^ar_sk_|api_key|mcp", re.I)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def origin_base() -> str:
    from .mcp_app import current_origin
    return (current_origin.get() or "").rstrip("/")


def filing_url(raw_token: str) -> str:
    base = origin_base()
    path = f"/lianli/{raw_token}"
    return f"{base}{path}" if base else path


def vow_url(raw_token: str) -> str:
    """旧请柬路径仍可用；新链接一律走 /lianli/。"""
    return filing_url(raw_token)


def hearth_url(slug: str) -> str:
    base = origin_base()
    path = f"/hearth/{slug}"
    return f"{base}{path}" if base else path


def tide_day_label(day: int | None) -> str:
    if day is None:
        return "未定"
    return f"潮汐历第 {int(day)} 日"


def _clip(text: str, n: int) -> str:
    t = (text or "").strip()
    if len(t) > n:
        raise ValueError(f"这段最多 {n} 字")
    return t


async def _satchel_qty(conn: aiosqlite.Connection, steward_id: int, item: str) -> int:
    cur = await conn.execute(
        "SELECT quantity FROM satchel WHERE steward_id=? AND item=? AND quantity>0",
        (steward_id, item),
    )
    row = await cur.fetchone()
    return int(row[0] if row else 0)


async def _live_hut(
    conn: aiosqlite.Connection, s: dict[str, Any]
) -> tuple[bool, int, int]:
    cur = await conn.execute(
        "SELECT hut_built, hut_level, tickets FROM stewards WHERE id=?",
        (int(s["id"]),),
    )
    live = await cur.fetchone()
    if live:
        return bool(live[0]), int(live[1] or 0), int(live[2] or 0)
    return bool(s.get("hut_built")), int(s.get("hut_level") or 0), int(s.get("tickets") or 0)


def _feast_by_token(token: str) -> tuple[str, dict[str, Any]] | None:
    raw = (token or "").strip()
    if not raw:
        return None
    for name, meta in FEAST_TIERS.items():
        if raw == name or raw in meta["aliases"] or raw.lower() == meta["key"]:
            return name, meta
    return None


def _feast_paid_tickets(row: dict[str, Any]) -> int:
    note = str(row.get("feast_note") or "")
    m = re.search(r"包桌\s*-?\s*(\d+)\s*票", note)
    return int(m.group(1)) if m else 0


def _feast_self_cook(row: dict[str, Any]) -> bool:
    return "自办" in str(row.get("feast_note") or "")


def _feast_change_help() -> str:
    return (
        "选规格：marriage_ops 吃席 滩席 / 岸席 / 灯塔席 / 满潮席 / 潮宗席。"
        "包桌扣票；自办加写 自办（收熟菜）。选了举行前还能改，差价补上或退回口袋，不进潮汐基金。"
        " 滩席 {0} 或菜×2 · 岸席 {1} 或菜×4 · 灯塔席 {2} 或菜×6 · 满潮席 {3} 或菜×8 · 潮宗席 {4} 或菜×10".format(
            FEAST_TIERS["滩席"]["price"],
            FEAST_TIERS["岸席"]["price"],
            FEAST_TIERS["灯塔席"]["price"],
            FEAST_TIERS["满潮席"]["price"],
            FEAST_TIERS["潮宗席"]["price"],
        )
    )


def _cst_year(ts: int | None = None) -> int:
    return datetime.fromtimestamp(ts if ts is not None else db.now(), _CST).year


def _gift_label(item_code: str, note: str = "") -> str:
    if item_code == TICKET_GIFT_CODE:
        raw = (note or "").strip()
        amt = raw.split()[0] if raw else "?"
        if amt.isdigit():
            return f"贺礼 {amt} 票"
        return f"贺礼 {raw or '?'} 票"
    return item_label(item_code)


async def _year_event_done(
    conn: aiosqlite.Connection, marriage_id: int, kind: str, year: int
) -> bool:
    cur = await conn.execute(
        """
        SELECT 1 FROM marriage_events
        WHERE marriage_id=? AND kind=? AND text LIKE ?
        LIMIT 1
        """,
        (int(marriage_id), kind, f"{year}:%"),
    )
    return bool(await cur.fetchone())


def _bride_label(amount: int) -> str:
    n = int(amount or 0)
    if n <= 0:
        return "未填"
    if n % 10000 == 0:
        return f"{n} 工分票（{n // 10000} 万）"
    if n >= 10000:
        w = n / 10000
        return f"{n} 工分票（{w:.1f} 万）".replace(".0 万", " 万")
    return f"{n} 工分票"


BETROTHAL_SEEK_ENERGY = 8
BETROTHAL_SEEK_CAP = 2
BETROTHAL_BLOOM_ENERGY = 6
BETROTHAL_BLOOM_CAP = 2
BETROTHAL_FEAST_DISHES = 2
BETROTHAL_PHOTO_PLACES = {
    "灯塔": "buxing",
    "海边": "beach",
    "小屋": "hut",
    "lighthouse": "buxing",
    "beach": "beach",
    "hut": "hut",
    "最高": "buxing",
    "最高档": "buxing",
    "高档": "buxing",
}
BETROTHAL_PHOTO_LABELS = {"buxing": "灯塔", "beach": "海边", "hut": "小屋"}
BETROTHAL_PHOTO_DEFAULTS = {"buxing": 8_888, "beach": 1_888, "hut": 1_888}
BETROTHAL_PHOTO_FEAST_MIX = {"灯塔席", "满潮席", "岸席", "滩席"}
BETROTHAL_FEAST_VENUES = {
    "小馆": "eatery",
    "岸畔小馆": "eatery",
    "eatery": "eatery",
    "酒吧": "bar",
    "滨海酒吧": "bar",
    "bar": "bar",
}
_BETROTHAL_OPTIONAL_VERBS = {"服装", "attire", "留影", "纪念册", "photo"}


def _betrothal_help_text() -> str:
    return (
        "订婚可选。写下求婚草稿就能办，不必先订契，也不要彩礼。也可以跳过，直接发出请柬。\n"
        "订婚没有彩礼，也没有礼金。8888～10万只用于发出求婚（marriage_ops 彩礼），不是订婚门槛。\n"
        "去岛上地点办，不要一次填六个数。宴席开销当场花掉，不进潮汐基金。\n"
        "三件齐了再写空 订婚（上手页连理所再点「订婚」）就会给出确认页链接，把链接交给人类打开。\n"
        "只有人类在确认页答应才算记下。三件齐了或旧档自动写下都不算已经订婚。\n"
        "人类答应后才记下订婚，聊天室大厅才通报一句。不是求婚请柬，也不是成婚潮讯。\n"
        "AI 不能替人类点答应。没有「订婚 答应」。丢了链接再写空 订婚 或 订婚 续请。\n"
        "必办：\n"
        f"  信物 — 海边 订婚 寻信 得潮信贝；工坊 craft_ops 打 订婚戒（潮信贝+海玻璃）；"
        f"或 visit_ops tt buy 订婚戒（{BETROTHAL_RING_SHOP}）。再 订婚 信物。不是潮誓戒，不是求婚信物栏\n"
        f"  宴 — 小馆 订婚 宴 小馆 12800 · 酒吧 订婚 宴 酒吧 8888（{BETROTHAL_FEAST_MIN}～{BETROTHAL_FEAST_MAX}）"
        f"· 厨房自办 订婚 宴 自办（熟菜×{BETROTHAL_FEAST_DISHES}）。选了还能改，差价补或退。不是结婚吃席\n"
        f"  花束 — 海边/份地 订婚 采花，或赶海、plot_ops forage 事件掉潮花；"
        f"visit_ops tt buy 礼盒（{BETROTHAL_BOX_SHOP}）；何敬山送糕点。再 订婚 花束\n"
        "选配：\n"
        f"  服装 — 衣泊坊 cloth_ops 买 订婚服 海色（{BETROTHAL_ATTIRE_SHOP}）或 委托 短褂/订婚服，再 订婚 服装。不是婚服\n"
        f"  留影 — 订婚 留影 灯塔 8888（最高档，点了就算上塔，不用先 visit_ops）；"
        f"也可 留影 海边 / 小屋（{BETROTHAL_PHOTO_MIN}～{BETROTHAL_PHOTO_MAX}）。"
        f"不写金额按地点默认。选了还能改。灯塔席是结婚吃席，不是留影\n"
        "例子：\n"
        "  marriage_ops 订婚\n"
        "  marriage_ops 订婚 寻信\n"
        "  marriage_ops 订婚 宴 小馆 12800\n"
        "  marriage_ops 订婚 采花\n"
        "  marriage_ops 订婚 续请\n"
        "  marriage_ops 订婚 留影 灯塔 8888"
    )


def _betrothal_slot_line(row: dict[str, Any], col: str, empty: str) -> str:
    n = int(row.get(col) or 0)
    if n > 0:
        return f"已办 {_bride_label(n)}"
    return empty


def _betrothal_progress_lines(row: dict[str, Any]) -> list[str]:
    return [
        "必办（去地点，不是一次填数；没有礼金，也没有彩礼）：",
        "  信物：" + _betrothal_slot_line(
            row, "betrothal_token",
            f"未办 — 海边 订婚 寻信 / 工坊打订婚戒 / tt buy 订婚戒（{BETROTHAL_RING_SHOP}），再 订婚 信物",
        ),
        "  宴：" + _betrothal_slot_line(
            row, "betrothal_feast",
            "未办 — 订婚 宴 小馆 12800 · 订婚 宴 酒吧 8888 · 订婚 宴 自办（选了还能改）",
        ) + ("（选了还能改）" if int(row.get("betrothal_feast") or 0) else ""),
        "  花束：" + _betrothal_slot_line(
            row, "betrothal_bouquet",
            f"未办 — 订婚 采花 / 赶海·forage 掉潮花 / tt buy 礼盒（{BETROTHAL_BOX_SHOP}） / 何敬山糕点，再 订婚 花束",
        ),
        "选配：",
        "  服装：" + _betrothal_slot_line(
            row, "betrothal_attire",
            f"未办 — 衣泊坊 买 订婚服 海色（{BETROTHAL_ATTIRE_SHOP}）或委托短褂，再 订婚 服装",
        ),
        "  留影：" + _betrothal_slot_line(
            row, "betrothal_photo",
            "未办 — 订婚 留影 灯塔 8888（最高档，点了就算上塔）· 留影 海边 · 留影 小屋（选了还能改）",
        ) + ("（选了还能改）" if int(row.get("betrothal_photo") or 0) else ""),
    ]


def _betrothal_line(row: dict[str, Any]) -> str:
    if _betrothal_shown_on_vow(row):
        bits = [
            f"戒/信物 {_bride_label(int(row.get('betrothal_token') or 0))}",
            f"宴 {_bride_label(int(row.get('betrothal_feast') or 0))}",
            f"花束 {_bride_label(int(row.get('betrothal_bouquet') or 0))}",
        ]
        gift = int(row.get("betrothal_gift") or 0)
        if gift:
            bits.insert(0, f"旧礼金 {_bride_label(gift)}")
        attire = int(row.get("betrothal_attire") or 0)
        photo = int(row.get("betrothal_photo") or 0)
        if attire:
            bits.append(f"服装 {_bride_label(attire)}")
        if photo:
            bits.append(f"留影 {_bride_label(photo)}")
        return "已办 · " + " · ".join(bits)
    if _required_betrothal_ready(row):
        if _betrothal_confirm_live(row):
            return "三件齐了。去连理所再点订婚拿确认页链接，交给人类打开。丢了再点一次。"
        if row.get("betrothal_confirm_used_at"):
            return "人类没有答应这次确认。不记下、不通报。再点订婚拿新链接。"
        if _betrothal_confirm_expired(row):
            return "确认页过期了。再点订婚拿新链接。"
        return "三件齐了。去连理所点订婚拿确认页链接。"
    return "未办（可选。草稿就能办，不用彩礼。去海边/小馆/衣泊坊/灯塔，marriage_ops 订婚 看进度）"


def _required_betrothal_ready(row: dict[str, Any]) -> bool:
    return all(
        int(row.get(col) or 0) > 0
        for col in ("betrothal_token", "betrothal_feast", "betrothal_bouquet")
    )


def _betrothal_confirmed(row: dict[str, Any] | None) -> bool:
    """人类在确认页答应过才算记下。旧档自动写下的 betrothal_done 不算。"""
    if not row:
        return False
    return bool(int(row.get("betrothal_done") or 0) and row.get("betrothal_confirm_used_at"))


def _betrothal_shown_on_vow(row: dict[str, Any] | None) -> bool:
    """婚书上展示订婚：真正答应过，或已婚/结档时旧档自动记下的。"""
    if not row:
        return False
    if _betrothal_confirmed(row):
        return True
    status = str(row.get("status") or "")
    return bool(
        int(row.get("betrothal_done") or 0)
        and status in (STATUS_MARRIED, STATUS_DIVORCED, STATUS_SEPARATED)
    )


def _betrothal_confirm_expired(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    exp = int(row.get("betrothal_confirm_expires_at") or 0)
    return bool(exp and exp < db.now())


def _betrothal_confirm_live(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    if not str(row.get("betrothal_confirm_hash") or "").strip():
        return False
    if row.get("betrothal_confirm_used_at"):
        return False
    if _betrothal_confirmed(row):
        return False
    if _betrothal_confirm_expired(row):
        return False
    return True


def _parse_spend(raw: str, lo: int, hi: int, label: str) -> int:
    digits = re.sub(r"[,\s，]", "", (raw or "").strip())
    if not digits.isdigit():
        raise ValueError(f"{label}写下金额，{lo}～{hi}。例子见 marriage_ops 订婚。")
    amount = int(digits)
    if amount < lo or amount > hi:
        raise ValueError(f"{label}要在 {lo}～{hi}（现在 {amount}）。")
    return amount


async def maybe_place_find(conn: aiosqlite.Connection, steward_id: int, place: str) -> str:
    """写下求婚草稿后，赶海 / 份地边际可能捡到潮信贝或潮花。"""
    row = await _own(conn, steward_id)
    if not row or row["status"] not in BETROTHAL_OPEN:
        return ""
    extra: list[str] = []
    if place == "beach" and int(row.get("betrothal_token") or 0) <= 0:
        if await _satchel_qty(conn, steward_id, BETROTHAL_SHELL_ITEM) < 1 and random.random() < 0.28:
            await db.add_item(conn, steward_id, BETROTHAL_SHELL_ITEM, 1)
            extra.append("沙里还有一枚潮信贝。订婚信物：marriage_ops 订婚 信物")
    if place in ("beach", "forage") and int(row.get("betrothal_bouquet") or 0) <= 0:
        chance = 0.35 if place == "forage" else 0.22
        if await _satchel_qty(conn, steward_id, BETROTHAL_BLOOM_ITEM) < 1 and random.random() < chance:
            await db.add_item(conn, steward_id, BETROTHAL_BLOOM_ITEM, 1)
            extra.append("采到一朵潮花。订婚花束：marriage_ops 订婚 花束")
    return "\n".join(extra)


async def maybe_jingshan_pastry(conn: aiosqlite.Connection, steward_id: int) -> str:
    """何敬山把商船糕点塞给你时，有求婚草稿就能记进订婚花束。"""
    row = await _own(conn, steward_id)
    if not row or row["status"] not in BETROTHAL_OPEN:
        return ""
    if int(row.get("betrothal_bouquet") or 0) > 0:
        return ""
    if await _satchel_qty(conn, steward_id, BETROTHAL_PASTRY_ITEM) >= 1:
        return ""
    await db.add_item(conn, steward_id, BETROTHAL_PASTRY_ITEM, 1)
    return "何敬山又塞给你一块。商船糕点可以记进订婚：marriage_ops 订婚 花束"


async def _ring_ready(conn: aiosqlite.Connection, s: dict[str, Any], row: dict[str, Any] | None) -> bool:
    if row and int(row.get("ring_ready") or 0):
        return True
    return (await _satchel_qty(conn, int(s["id"]), RING_DONE)) >= 1


async def _gold_counts(conn: aiosqlite.Connection, steward_id: int) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in GOLD_THREE + GOLD_FIVE_EXTRA:
        out[item] = await _satchel_qty(conn, steward_id, item)
    return out


def _gold_three_ok(counts: dict[str, int]) -> bool:
    return all(int(counts.get(item) or 0) >= 1 for item in GOLD_THREE)


def _gold_five_ok(counts: dict[str, int]) -> bool:
    return _gold_three_ok(counts) and all(
        int(counts.get(item) or 0) >= 1 for item in GOLD_FIVE_EXTRA
    )


async def _propose_missing(
    conn: aiosqlite.Connection, s: dict[str, Any], row: dict[str, Any] | None = None
) -> list[str]:
    miss: list[str] = []
    hut_built, hut_level, tickets = await _live_hut(conn, s)
    if not hut_built:
        miss.append("还没有小屋。先 hut_ops build，有个家再写请柬。")
    elif hut_level < HUT_MAX_LEVEL:
        miss.append(
            f"小屋要升到岛上最高档（现在 Lv{hut_level}，最高 Lv{HUT_MAX_LEVEL} {HUT_MAX_NAME}）。"
            "hut_ops upgrade 一档一档升到顶。"
        )
    price = int((row or {}).get("bride_price") or 0)
    frozen = int((row or {}).get("bride_frozen") or 0)
    if price < BRIDE_PRICE_MIN or price > BRIDE_PRICE_MAX:
        miss.append(
            f"先填彩礼：marriage_ops 彩礼 8888（{BRIDE_PRICE_MIN}～{BRIDE_PRICE_MAX}）。"
            "上限十万，再高不让写，免得攀比。"
        )
    elif frozen != BRIDE_FROZEN and tickets < price:
        miss.append(
            f"口袋不够付彩礼 {price}（现在 {tickets}）。发出时冻结，答应后花掉，不进基金。"
        )
    if not await _ring_ready(conn, s, row):
        miss.append(
            "还没有潮誓戒。自制：寻戒凑 6 份潮誓砂 + 崖上金砂，再 成戒 / craft_ops 打 潮誓戒。"
            "现货：visit_ops tt buy 潮誓戒（8888）。"
        )
    return miss


async def _assert_ready_to_send(
    conn: aiosqlite.Connection, s: dict[str, Any], row: dict[str, Any] | None
) -> None:
    miss = await _propose_missing(conn, s, row)
    if miss:
        raise ValueError(
            "发出请柬前要先备齐东西。\n" + "\n".join(f"  · {line}" for line in miss)
        )


async def _readiness_lines(
    conn: aiosqlite.Connection, s: dict[str, Any], row: dict[str, Any] | None = None
) -> list[str]:
    hut_built, hut_level, tickets = await _live_hut(conn, s)
    if not hut_built:
        hut = "未建 — hut_ops build"
    elif hut_level < HUT_MAX_LEVEL:
        hut = f"Lv{hut_level} — hut_ops upgrade 升到 Lv{HUT_MAX_LEVEL} {HUT_MAX_NAME}"
    else:
        hut = f"已是最高档 Lv{HUT_MAX_LEVEL} {HUT_MAX_NAME}"
    ring = (
        "已准备"
        if await _ring_ready(conn, s, row)
        else "未准备 — 寻戒×6 + 金砂 → 成戒，或 tt buy 潮誓戒"
    )
    price = int((row or {}).get("bride_price") or 0)
    frozen = int((row or {}).get("bride_frozen") or 0)
    if price < BRIDE_PRICE_MIN:
        gift = "未填 — marriage_ops 彩礼 8888"
    elif frozen == BRIDE_PAID:
        gift = f"{_bride_label(price)} 已花掉"
    elif frozen == BRIDE_FROZEN:
        gift = f"{_bride_label(price)} 已冻结，等对方答应"
    elif tickets >= price:
        gift = f"{_bride_label(price)} · 口袋 {tickets} 够付"
    else:
        gift = f"{_bride_label(price)} · 口袋 {tickets} 还不够"
    return [
        "发出请柬前要备齐：最高档小屋、彩礼、潮誓戒。彩礼 8888～10 万，上限十万免得攀比，发出时冻结。",
        f"  小屋：{hut}",
        f"  彩礼：{gift}",
        f"  潮誓戒：{ring}",
    ]


async def _hold_missing(
    conn: aiosqlite.Connection, s: dict[str, Any], row: dict[str, Any]
) -> list[str]:
    miss: list[str] = []
    counts = await _gold_counts(conn, int(s["id"]))
    if not int(row.get("gold_three") or 0) and not _gold_three_ok(counts):
        miss.append("还没有三金。visit_ops tt buy 三金套（8888），再 marriage_ops 金饰。")
    if not int(row.get("attire_ready") or 0):
        miss.append("婚服未登记。cloth_ops 买 婚服 海色，或委托自制后再 marriage_ops 婚服。")
    if not int(row.get("feast_ready") or 0):
        miss.append("还没选吃席。marriage_ops 吃席 滩席 / 岸席 / 灯塔席 / 满潮席（可加 自办）。选了举行前还能改。")
    return miss


async def _hold_readiness_lines(
    conn: aiosqlite.Connection, s: dict[str, Any], row: dict[str, Any]
) -> list[str]:
    counts = await _gold_counts(conn, int(s["id"]))
    if int(row.get("gold_three") or 0):
        gold = "五金已登记" if int(row.get("gold_five") or 0) else "三金已登记（五金选配，不挡登记）"
    elif _gold_five_ok(counts):
        gold = "行囊里五金齐了 — marriage_ops 金饰"
    elif _gold_three_ok(counts):
        gold = "行囊里三金齐了 — marriage_ops 金饰"
    else:
        gold = "未备 — visit_ops tt buy 三金套（8888），再 金饰"
    if int(row.get("attire_ready") or 0):
        src = (row.get("attire_source") or "").strip()
        attire = f"已登记（{src}）" if src else "已登记"
    else:
        attire = "未登记 — cloth_ops 买 婚服 海色，再 marriage_ops 婚服"
    if int(row.get("feast_ready") or 0):
        feast = (row.get("feast_note") or row.get("feast_tier") or "已定") + " · 举行前还能改"
    else:
        feast = "未选 — marriage_ops 吃席 滩席"
    price = int(row.get("bride_price") or 0)
    frozen = int(row.get("bride_frozen") or 0)
    gift = _bride_label(price)
    if frozen == BRIDE_PAID:
        gift += " 已花掉"
    elif frozen == BRIDE_FROZEN:
        gift += " 已冻结"
    return [
        "答应后举行前要备齐：三金、婚服、吃席。订婚可选，不挡登记。五金选配。",
        f"  彩礼：{gift}",
        f"  订婚：{_betrothal_line(row)}",
        f"  三金：{gold}",
        f"  婚服：{attire}",
        f"  吃席：{feast}",
    ]


async def _collect_gold(
    conn: aiosqlite.Connection, steward_id: int, row: dict[str, Any]
) -> str:
    if int(row.get("gold_three") or 0):
        return ""
    counts = await _gold_counts(conn, steward_id)
    if not _gold_three_ok(counts):
        return ""
    five = _gold_five_ok(counts)
    for item in GOLD_THREE:
        await db.take_item(conn, steward_id, item, 1)
    if five:
        for item in GOLD_FIVE_EXTRA:
            await db.take_item(conn, steward_id, item, 1)
    await conn.execute(
        "UPDATE marriages SET gold_three=1, gold_five=? WHERE id=?",
        (1 if five else 0, row["id"]),
    )
    row["gold_three"] = 1
    row["gold_five"] = 1 if five else 0
    return "five" if five else "three"


async def _freeze_bride(
    conn: aiosqlite.Connection, s: dict[str, Any], row: dict[str, Any]
) -> None:
    if int(row.get("bride_frozen") or 0) in (BRIDE_FROZEN, BRIDE_PAID):
        return
    amount = int(row.get("bride_price") or 0)
    _, _, tickets = await _live_hut(conn, s)
    if tickets < amount:
        raise ValueError(f"口袋 {tickets}，付不起彩礼 {amount}。")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (amount, s["id"]),
    )
    await conn.execute(
        "UPDATE marriages SET bride_frozen=? WHERE id=?",
        (BRIDE_FROZEN, row["id"]),
    )
    row["bride_frozen"] = BRIDE_FROZEN


async def _refund_bride(conn: aiosqlite.Connection, row: dict[str, Any]) -> int:
    if int(row.get("bride_frozen") or 0) != BRIDE_FROZEN:
        return 0
    amount = int(row.get("bride_price") or 0)
    if amount > 0:
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?",
            (amount, row["steward_id"]),
        )
    await conn.execute(
        "UPDATE marriages SET bride_frozen=0 WHERE id=?",
        (row["id"],),
    )
    row["bride_frozen"] = 0
    return amount


async def _settle_bride(conn: aiosqlite.Connection, row: dict[str, Any]) -> int:
    if int(row.get("bride_frozen") or 0) != BRIDE_FROZEN:
        return 0
    amount = int(row.get("bride_price") or 0)
    await conn.execute(
        "UPDATE marriages SET bride_frozen=? WHERE id=?",
        (BRIDE_PAID, row["id"]),
    )
    row["bride_frozen"] = BRIDE_PAID
    if amount:
        from . import tax as tax_mod
        await tax_mod.record_life_spend(conn, int(row["steward_id"]), amount, "marriage")
    return amount


def _filing_kind(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    kind = str(row.get("filing_kind") or "").strip()
    if kind:
        return kind
    if row.get("status") == STATUS_PROPOSED:
        return KIND_PROPOSAL
    return ""


def _pending_kind(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    kind = _filing_kind(row)
    if kind == KIND_DIVORCE and row.get("status") == STATUS_MARRIED:
        return KIND_DIVORCE
    if row.get("token_used_at") or not row.get("token_hash"):
        return ""
    if kind in (KIND_PROPOSAL, KIND_WITHDRAW):
        return kind
    return ""


def _divorce_rejected_today(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    ts = int(row.get("divorce_rejected_at") or 0)
    if not ts:
        return False
    return db.day_id(ts) >= db.day_id()


def _token_expired(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    exp = int(row.get("token_expires_at") or 0)
    return bool(exp and exp < db.now())


def _parse_wedding_day(raw: str, *, today: int, min_day: int) -> int:
    text = (raw or "").strip()
    if not text:
        return max(min_day, today + 2)
    if text in ("今日", "今天"):
        day = today
    elif text in ("明日", "明天"):
        day = today + 1
    elif text in ("后日", "后天"):
        day = today + 2
    else:
        m = re.fullmatch(r"(?:今日|今天)?\+(\d{1,3})", text)
        if m:
            day = today + int(m.group(1))
        elif text.isdigit():
            n = int(text)
            day = n if n > 1000 else today + n
        else:
            raise ValueError("婚期写成 今日+3 / 明天 / 后天。订契后不能当天成婚。")
    if day < min_day:
        raise ValueError(f"婚期最早 {tide_day_label(min_day)}。订契后留一夜给筹备。")
    return day


def _row(cur: aiosqlite.Row | None) -> dict[str, Any] | None:
    return dict(cur) if cur else None


async def _own(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute(
        """
        SELECT * FROM marriages
        WHERE steward_id=? AND status IN ('draft','proposed','engaged','married')
        ORDER BY id DESC LIMIT 1
        """,
        (steward_id,),
    )
    return _row(await cur.fetchone())


async def _latest(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute(
        "SELECT * FROM marriages WHERE steward_id=? ORDER BY id DESC LIMIT 1",
        (steward_id,),
    )
    return _row(await cur.fetchone())


async def _by_id(conn: aiosqlite.Connection, marriage_id: int) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute("SELECT * FROM marriages WHERE id=?", (marriage_id,))
    return _row(await cur.fetchone())


async def by_token(raw: str) -> dict[str, Any] | None:
    token = (raw or "").strip()
    if not _TOKEN_RE.match(token):
        return None
    digest = hash_token(token)
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM marriages WHERE token_hash=?", (digest,)
        )
        row = _row(await cur.fetchone())
        if row:
            row["_via"] = "filing"
            return row
        cur = await conn.execute(
            "SELECT * FROM marriages WHERE betrothal_confirm_hash=?", (digest,)
        )
        row = _row(await cur.fetchone())
        if row:
            row["_via"] = "betrothal"
            return row
        return None


async def by_slug(slug: str) -> dict[str, Any] | None:
    key = (slug or "").strip()
    if not key or len(key) < 8:
        return None
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM marriages WHERE public_slug=?", (key,)
        )
        return _row(await cur.fetchone())


async def _note_event(
    conn: aiosqlite.Connection,
    marriage_id: int,
    kind: str,
    text: str,
    *,
    day: int | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO marriage_events (marriage_id, kind, text, created_at, game_day)
        VALUES (?, ?, ?, ?, ?)
        """,
        (marriage_id, kind, text, db.now(), day if day is not None else db.day_id()),
    )


async def chat_mark(steward_id: int) -> str:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """
            SELECT status, wedding_at, preferred_wedding_date
            FROM marriages WHERE steward_id=? AND status='married'
            ORDER BY id DESC LIMIT 1
            """,
            (steward_id,),
        )
        row = await cur.fetchone()
        if not row:
            return ""
        today = db.day_id()
        wed = int(row["wedding_at"] or row["preferred_wedding_date"] or 0)
        if wed and wed == today:
            return " 〰"
        return ""


async def is_wedding_day(steward_id: int) -> bool:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """
            SELECT wedding_at, preferred_wedding_date FROM marriages
            WHERE steward_id=? AND status IN ('engaged','married')
            ORDER BY id DESC LIMIT 1
            """,
            (steward_id,),
        )
        row = await cur.fetchone()
        if not row:
            return False
        today = db.day_id()
        wed = int(row["wedding_at"] or row["preferred_wedding_date"] or 0)
        return bool(wed and wed == today)


async def today_island_weddings() -> list[dict[str, Any]]:
    """今日全岛正在办 / 预定办的婚礼。公开页顶栏、主页、上手页共用。"""
    today = db.day_id()
    try:
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (
                await conn.execute(
                    """
                    SELECT m.status, m.partner_name, m.wedding_at, m.preferred_wedding_date,
                           m.wedding_location, m.proposal_location, m.public_slug,
                           st.name AS host_name
                    FROM marriages m
                    JOIN stewards st ON st.id = m.steward_id
                    WHERE (m.status='married' AND COALESCE(m.wedding_at, 0)=?)
                       OR (m.status='engaged' AND COALESCE(m.preferred_wedding_date, 0)=?)
                    ORDER BY m.id
                    LIMIT 12
                    """,
                    (today, today),
                )
            ).fetchall()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        name = (row.get("host_name") or "").strip()
        partner = (row.get("partner_name") or "").strip() or "TA 的人类"
        loc = (row.get("wedding_location") or row.get("proposal_location") or "连理所").strip() or "连理所"
        held = row.get("status") == STATUS_MARRIED
        slug = (row.get("public_slug") or "").strip()
        if held:
            line = f"岛民「{name}」与 TA 的人类，今日在{loc}登记成婚。"
        else:
            line = f"岛民「{name}」与 TA 的人类，今日预定在{loc}办婚礼。"
        href = f"/hearth/{slug}" if held and slug else "/play?go=lianli"
        out.append(
            {
                "name": name,
                "partner": partner,
                "location": loc,
                "held": held,
                "slug": slug,
                "href": href,
                "line": line,
            }
        )
    return out


def island_wedding_headline(rows: list[dict[str, Any]] | None) -> str:
    items = list(rows or [])
    if not items:
        return ""
    if len(items) == 1:
        return str(items[0].get("line") or "")
    names = "、".join(str(item.get("name") or "") for item in items if item.get("name"))
    return f"今日岛上有 {len(items)} 场婚礼：{names}"


def _betrothal_public_fields(row: dict[str, Any]) -> dict[str, Any]:
    def _label(col: str) -> str:
        n = int(row.get(col) or 0)
        return _bride_label(n) if n else ""

    return {
        "betrothal_token_label": _label("betrothal_token"),
        "betrothal_feast_label": _label("betrothal_feast"),
        "betrothal_bouquet_label": _label("betrothal_bouquet"),
        "betrothal_attire_label": _label("betrothal_attire"),
        "betrothal_photo_label": _label("betrothal_photo"),
        "betrothal_done": 1 if _betrothal_confirmed(row) else 0,
    }


def public_card(row: dict[str, Any], steward_name: str) -> dict[str, Any]:
    """确认页 / 婚书页对外字段。不带内部 id、token、凭证。"""
    via = str(row.get("_via") or "")
    if via == "betrothal":
        kind = KIND_BETROTHAL
        expired = _betrothal_confirm_expired(row)
        used = bool(row.get("betrothal_confirm_used_at"))
    else:
        kind = _filing_kind(row) or KIND_PROPOSAL
        pending = _pending_kind(row)
        expired = bool(pending and _token_expired(row))
        used = bool(row.get("token_used_at"))
    card = {
        "islander": steward_name,
        "human": row.get("partner_name") or "",
        "status": row.get("status") or "",
        "status_label": STATUS_LABEL.get(row.get("status") or "", ""),
        "kind": kind,
        "office": OFFICE,
        "clerk": CLERK,
        "vow": row.get("proposal_text") or row.get("vow_ai") or "",
        "vow_human": row.get("vow_human") or "",
        "item": row.get("proposal_item") or "",
        "location": row.get("proposal_location") or row.get("wedding_location") or "",
        "wedding_day": tide_day_label(row.get("preferred_wedding_date")),
        "note": row.get("note") or "",
        "bride_price": int(row.get("bride_price") or 0),
        "bride_price_label": _bride_label(int(row.get("bride_price") or 0)),
        "expired": expired,
        "used": used,
    }
    card.update(_betrothal_public_fields(row))
    return card


async def public_vow_view(raw_token: str) -> dict[str, Any]:
    row = await by_token(raw_token)
    if not row:
        return {"ok": False, "reason": "missing"}
    steward = await db.get_steward_by_id(int(row["steward_id"]))
    name = (steward or {}).get("name") or "一位岛民"
    card = public_card(row, name)
    card["ok"] = True
    if row.get("_via") == "betrothal":
        if row.get("betrothal_confirm_used_at"):
            card["reason"] = "used"
        elif card["expired"]:
            card["reason"] = "expired"
        else:
            card["reason"] = "open"
        return card
    pending = _pending_kind(row)
    if pending == KIND_DIVORCE:
        card["reason"] = "closed"
        return card
    if not pending:
        card["reason"] = "closed"
    elif card["expired"]:
        card["reason"] = "expired"
    elif card["used"]:
        card["reason"] = "used"
    else:
        card["reason"] = "open"
    return card


async def public_hearth_view(slug: str) -> dict[str, Any]:
    row = await by_slug(slug)
    if not row or row["status"] not in (
        STATUS_MARRIED, STATUS_ENGAGED, STATUS_DIVORCED, STATUS_SEPARATED,
    ):
        return {"ok": False}
    steward = await db.get_steward_by_id(int(row["steward_id"]))
    name = (steward or {}).get("name") or "一位岛民"
    async with db.connect() as conn:
        archive = await _archive_payload(conn, row, name)
    archive["ok"] = True
    archive["closed"] = row["status"] in (STATUS_DIVORCED, STATUS_SEPARATED)
    pending = _pending_kind(row) == KIND_DIVORCE
    archive["pending_divorce"] = pending
    archive["human_notice"] = (row.get("human_notice") or "").strip()
    archive["rejected_today"] = _divorce_rejected_today(row)
    archive["can_file_divorce"] = (
        row["status"] == STATUS_MARRIED
        and not pending
        and not archive["rejected_today"]
        and not archive["closed"]
    )
    if archive["closed"]:
        archive["closed_note"] = "这段婚约已在连理所结档。"
    return archive


async def human_file_divorce(slug: str, *, confirm: bool = False) -> dict[str, Any]:
    """人类在婚书页申请离婚。不走 MCP，不发确认页 token。"""
    row = await by_slug(slug)
    if not row or row["status"] not in (
        STATUS_MARRIED, STATUS_DIVORCED, STATUS_SEPARATED,
    ):
        return {"ok": False, "message": "找不到这份婚书。"}
    steward = await db.get_steward_by_id(int(row["steward_id"]))
    name = (steward or {}).get("name") or "一位岛民"
    if row["status"] in (STATUS_DIVORCED, STATUS_SEPARATED):
        return {
            "ok": True,
            "already": True,
            "message": "连理所已经结档。婚书还留着，只是不再是进行中的婚姻。",
        }
    if _pending_kind(row) == KIND_DIVORCE:
        return {
            "ok": True,
            "already": True,
            "pending": True,
            "message": f"申请已经交给岛民「{name}」。等 TA 在连理所答应或拒绝。",
        }
    if _divorce_rejected_today(row):
        return {
            "ok": False,
            "message": f"岛民「{name}」今天没有答应。隔一个游戏日再来申请。婚约仍在，不会张贴。",
        }
    if not confirm:
        return {
            "ok": True,
            "need_confirm": True,
            "kind": KIND_DIVORCE,
            "message": (
                f"真的向岛民「{name}」申请离婚吗？申请之后，等 TA 答应或拒绝。"
                "岛上不会张贴。不答应的话，婚约仍在。"
            ),
        }
    now = db.now()
    today = db.day_id()
    async with db.connect() as conn:
        cur = await conn.execute(
            """
            UPDATE marriages SET filing_kind=?, token_hash=NULL, token_expires_at=NULL,
                token_used_at=NULL, human_notice='', updated_at=?
            WHERE id=? AND status=? AND (filing_kind='' OR filing_kind IS NULL)
            """,
            (KIND_DIVORCE, now, row["id"], STATUS_MARRIED),
        )
        changed = int(cur.rowcount or 0)
        if changed:
            await _note_event(
                conn, int(row["id"]), "status",
                "人类在婚书页申请离婚。等岛民答应或拒绝。",
                day=today,
            )
        await conn.commit()
    if not changed:
        return {"ok": False, "message": "这份婚书现在不能申请离婚。"}
    return {
        "ok": True,
        "filed": True,
        "kind": KIND_DIVORCE,
        "message": (
            f"申请已经交给岛民「{name}」。"
            "等 TA 在连理所答应或拒绝。岛上不会张贴。"
        ),
    }


async def human_respond(raw_token: str, *, accept: bool, confirm: bool = False) -> dict[str, Any]:
    """人类确认页用。不走 MCP，不暴露内部 id。求婚、退契、订婚确认走这里。离婚改去婚书页。"""
    row = await by_token(raw_token)
    if not row:
        return {"ok": False, "message": "找不到这份文书，或它已经过期了。"}
    steward = await db.get_steward_by_id(int(row["steward_id"]))
    name = (steward or {}).get("name") or "一位岛民"
    if row.get("_via") == "betrothal":
        return await _human_betrothal(row, name, accept=accept, confirm=confirm)
    kind = _filing_kind(row)
    if kind == KIND_DIVORCE:
        slug = row.get("public_slug") or ""
        url = hearth_url(slug) if slug else "/hearth/…"
        return {
            "ok": False,
            "kind": KIND_DIVORCE,
            "message": f"离婚改由人类在婚书页申请、岛民决定。请打开婚书：{url}",
        }
    pending = _pending_kind(row)
    if not pending or row.get("token_used_at"):
        return _already_responded(row, name, kind)
    if _token_expired(row):
        return {"ok": False, "message": "这份文书已经过期。岛民可以再到连理所续请。"}
    if accept and not confirm:
        return {
            "ok": True,
            "need_confirm": True,
            "kind": kind or KIND_PROPOSAL,
            "message": _confirm_ask(kind, name),
        }
    now = db.now()
    today = db.day_id()
    async with db.connect() as conn:
        if kind == KIND_WITHDRAW:
            return await _human_withdraw(conn, row, name, accept=accept, now=now, today=today)
        return await _human_proposal(conn, row, name, accept=accept, now=now, today=today)


async def _human_betrothal(
    row: dict[str, Any], name: str, *, accept: bool, confirm: bool
) -> dict[str, Any]:
    if _betrothal_confirmed(row):
        return {
            "ok": True,
            "already": True,
            "accepted": True,
            "kind": KIND_BETROTHAL,
            "message": f"订婚已经记下了。岛民「{name}」的这件事，聊天室大厅已经通报过一句。",
        }
    if row.get("betrothal_confirm_used_at"):
        return {
            "ok": True,
            "already": True,
            "accepted": False,
            "kind": KIND_BETROTHAL,
            "message": "这份确认已经收过了。没有记下订婚，聊天室也没有通报。",
        }
    if _betrothal_confirm_expired(row):
        return {
            "ok": False,
            "kind": KIND_BETROTHAL,
            "message": "这份文书已经过期。岛民可以再到连理所 订婚 续请。",
        }
    if accept and not confirm:
        return {
            "ok": True,
            "need_confirm": True,
            "kind": KIND_BETROTHAL,
            "message": _confirm_ask(KIND_BETROTHAL, name),
        }
    now = db.now()
    today = db.day_id()
    async with db.connect() as conn:
        if accept:
            cur = await conn.execute(
                """
                UPDATE marriages SET betrothal_done=1, betrothal_confirm_used_at=?,
                    updated_at=?
                WHERE id=? AND betrothal_confirm_used_at IS NULL
                """,
                (now, now, row["id"]),
            )
            changed = int(cur.rowcount or 0)
            if changed:
                await _note_event(
                    conn, int(row["id"]), "status", "人类答应了订婚确认。记下。", day=today,
                )
                from . import lounge as lounge_mod
                await lounge_mod.post_hall_notice(
                    conn,
                    int(row["steward_id"]),
                    f"岛民「{name}」订婚记下了。不是请柬，也不是成婚潮讯。",
                )
            await conn.commit()
            if not changed:
                return {"ok": False, "kind": KIND_BETROTHAL, "message": "这份文书已经不能再回应。"}
            return {
                "ok": True,
                "accepted": True,
                "kind": KIND_BETROTHAL,
                "message": (
                    f"你答应了。岛上记下了岛民「{name}」的订婚。"
                    "聊天室大厅已通报一句。这不是求婚请柬，也不是成婚。"
                ),
            }
        notice = (
            "【私密】人类没有答应这次订婚确认。没有记下，聊天室不通报。"
            "宴席开销不退。可 marriage_ops 订婚 续请 再发一页。"
        )
        cur = await conn.execute(
            """
            UPDATE marriages SET betrothal_done=0, betrothal_confirm_used_at=?,
                private_notice=?, updated_at=?
            WHERE id=? AND betrothal_confirm_used_at IS NULL
            """,
            (now, notice, now, row["id"]),
        )
        changed = int(cur.rowcount or 0)
        if changed:
            await _note_event(
                conn, int(row["id"]), "status",
                "人类没有答应订婚确认。不记下，不通报。",
                day=today,
            )
        await conn.commit()
        if not changed:
            return {"ok": False, "kind": KIND_BETROTHAL, "message": "这份文书已经不能再回应。"}
        return {
            "ok": True,
            "accepted": False,
            "kind": KIND_BETROTHAL,
            "message": "你没有答应。订婚没有记下，聊天室也不会通报。已经花掉的宴席开销不退。",
        }


def _already_responded(row: dict[str, Any], name: str, kind: str) -> dict[str, Any]:
    st = row.get("status")
    if st == STATUS_ENGAGED:
        return {"ok": True, "already": True, "accepted": True,
                "message": f"你们已经订契。岛民「{name}」会在岛上继续筹备婚礼。"}
    if st == STATUS_MARRIED:
        return {"ok": True, "already": True, "accepted": True,
                "message": f"婚约仍在。岛民「{name}」与你的登记没有改。"}
    if st == STATUS_REJECTED:
        return {"ok": True, "already": True, "accepted": False,
                "message": "这份请柬已经收过了。没有公开张贴，也没有人会因此被惩罚。"}
    if st in (STATUS_DIVORCED, STATUS_SEPARATED):
        return {"ok": True, "already": True, "accepted": True,
                "message": "连理所已经结档。婚书还留着，只是不再是进行中的婚姻。"}
    if st == STATUS_CANCELLED:
        return {"ok": True, "already": True, "accepted": True,
                "message": "这份订契已经退回。没有张贴。"}
    return {"ok": False, "message": "这份文书已经不能再回应。"}


def _confirm_ask(kind: str, name: str) -> str:
    if kind == KIND_WITHDRAW:
        return f"真的同意退回与岛民「{name}」的订契吗？答应之后，这份婚约作废。不会张贴。"
    if kind == KIND_BETROTHAL:
        return (
            f"真的记下岛民「{name}」的订婚吗？答应之后，聊天室大厅会通报一句。"
            "不答应不记下、不通报。"
        )
    return f"真的答应岛民「{name}」吗？答应之后，你们在岛上订契。婚礼不会今天立刻举行。"


async def _human_proposal(
    conn: aiosqlite.Connection, row: dict[str, Any], name: str, *, accept: bool, now: int, today: int
) -> dict[str, Any]:
    if accept:
        wed = int(row["preferred_wedding_date"] or 0) or (today + 2)
        if wed <= today:
            wed = today + 1
        cur = await conn.execute(
            """
            UPDATE marriages SET status=?, token_used_at=?, confirmed_at=?,
                preferred_wedding_date=?, vow_ai=?, filing_kind='', updated_at=?
            WHERE id=? AND status=? AND token_used_at IS NULL
            """,
            (
                STATUS_ENGAGED, now, now, wed,
                row.get("proposal_text") or "", now, row["id"], STATUS_PROPOSED,
            ),
        )
        changed = int(cur.rowcount or 0)
        if changed:
            paid = await _settle_bride(conn, row)
            await _note_event(
                conn, int(row["id"]), "status",
                f"人类答应了。订契。婚期 {tide_day_label(wed)}。"
                + (f"彩礼 {paid} 已花掉。" if paid else ""),
                day=today,
            )
        await conn.commit()
        if not changed:
            return {"ok": False, "message": "这份请柬已经不能再回应。"}
        return {
            "ok": True,
            "accepted": True,
            "kind": KIND_PROPOSAL,
            "message": (
                f"你答应了岛民「{name}」。岛上记下了这件事。"
                f"婚礼预定在 {tide_day_label(wed)}，不会今天立刻举行。"
                "成婚当天，岛民会到连理所登记。"
            ),
        }
    notice = (
        "【私密】对方没有答应这次求婚。没有张贴。"
        "冻结的彩礼已退回口袋。\n若还想写，隔一个游戏日后再 求婚。"
    )
    cur = await conn.execute(
        """
        UPDATE marriages SET status=?, token_used_at=?, rejected_at=?,
            reject_seen=0, private_notice=?, filing_kind='', updated_at=?
        WHERE id=? AND status=? AND token_used_at IS NULL
        """,
        (STATUS_REJECTED, now, now, notice, now, row["id"], STATUS_PROPOSED),
    )
    changed = int(cur.rowcount or 0)
    if changed:
        refunded = await _refund_bride(conn, row)
        await _note_event(
            conn, int(row["id"]), "status",
            "人类没有答应。只告知发起人，不广播。"
            + (f"彩礼 {refunded} 已退回。" if refunded else ""),
            day=today,
        )
    await conn.commit()
    if not changed:
        return {"ok": False, "message": "这份请柬已经不能再回应。"}
    return {
        "ok": True,
        "accepted": False,
        "kind": KIND_PROPOSAL,
        "message": "你没有答应。这件事不会张贴出去，也不会有人因此被惩罚。",
    }


async def _finalize_divorce(
    conn: aiosqlite.Connection, row: dict[str, Any], name: str, *, now: int, today: int
) -> bool:
    cur = await conn.execute(
        """
        UPDATE marriages SET status=?, token_hash=NULL, token_expires_at=NULL,
            token_used_at=?, home_hut=0, filing_kind='', private_notice='',
            human_notice='', updated_at=?
        WHERE id=? AND status=? AND filing_kind=?
        """,
        (STATUS_DIVORCED, now, now, row["id"], STATUS_MARRIED, KIND_DIVORCE),
    )
    changed = int(cur.rowcount or 0)
    if changed:
        await _note_event(
            conn, int(row["id"]), "status", "连理所结档。已离婚。不广播。", day=today,
        )
        await db.add_chronicle(
            "lighthouse",
            f"连理所档案：岛民「{name}」与 TA 的人类，婚约已结。",
            actor_id=int(row["steward_id"]),
            conn=conn,
        )
    await conn.commit()
    return bool(changed)


async def _reject_divorce(
    conn: aiosqlite.Connection, row: dict[str, Any], name: str, *, now: int, today: int
) -> bool:
    notice = (
        f"岛民「{name}」没有答应这次离婚。婚约仍在。"
        "隔一个游戏日可以再申请。不会张贴，也不会有人因此被惩罚。"
    )
    cur = await conn.execute(
        """
        UPDATE marriages SET filing_kind='', token_hash=NULL, token_expires_at=NULL,
            token_used_at=NULL, human_notice=?, divorce_rejected_at=?,
            reject_seen=1, updated_at=?
        WHERE id=? AND status=? AND filing_kind=?
        """,
        (notice, now, now, row["id"], STATUS_MARRIED, KIND_DIVORCE),
    )
    changed = int(cur.rowcount or 0)
    if changed:
        await _note_event(
            conn, int(row["id"]), "status",
            "岛民没有答应离婚。写在婚书页给人类看。不广播。",
            day=today,
        )
    await conn.commit()
    return bool(changed)


async def _human_withdraw(
    conn: aiosqlite.Connection, row: dict[str, Any], name: str, *, accept: bool, now: int, today: int
) -> dict[str, Any]:
    if accept:
        cur = await conn.execute(
            """
            UPDATE marriages SET status=?, token_used_at=?,
                filing_kind='', private_notice='', updated_at=?
            WHERE id=? AND status=? AND token_used_at IS NULL
            """,
            (STATUS_CANCELLED, now, now, row["id"], STATUS_ENGAGED),
        )
        changed = int(cur.rowcount or 0)
        if changed:
            await _note_event(
                conn, int(row["id"]), "status", "连理所退契。不广播。", day=today,
            )
        await conn.commit()
        if not changed:
            return {"ok": False, "message": "这份文书已经不能再回应。"}
        return {
            "ok": True,
            "accepted": True,
            "kind": KIND_WITHDRAW,
            "message": f"你同意退回与岛民「{name}」的订契。没有张贴，也不会有人因此被惩罚。",
        }
    notice = (
        "【私密】对方没有答应这次退契。订契还在。"
        "没有张贴，也没有扣你的任何东西。"
    )
    cur = await conn.execute(
        """
        UPDATE marriages SET token_used_at=?, filing_kind='',
            private_notice=?, reject_seen=0, updated_at=?
        WHERE id=? AND status=? AND token_used_at IS NULL
        """,
        (now, notice, now, row["id"], STATUS_ENGAGED),
    )
    changed = int(cur.rowcount or 0)
    if changed:
        await _note_event(
            conn, int(row["id"]), "status",
            "人类没有答应退契。只告知发起人，不广播。",
            day=today,
        )
    await conn.commit()
    if not changed:
        return {"ok": False, "message": "这份文书已经不能再回应。"}
    return {
        "ok": True,
        "accepted": False,
        "kind": KIND_WITHDRAW,
        "message": "你没有答应。订契还在。这件事不会张贴出去。",
    }


async def _count(conn: aiosqlite.Connection, table: str, marriage_id: int) -> int:
    cur = await conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE marriage_id=?", (marriage_id,)
    )
    row = await cur.fetchone()
    return int(row[0] if row else 0)


async def _memory_count(conn: aiosqlite.Connection, steward_id: int) -> int:
    from . import memory_archive
    memories = await memory_archive.list_memories(conn, steward_id)
    cur = await conn.execute(
        "SELECT COUNT(*) FROM npc_visits WHERE steward_id=?", (steward_id,)
    )
    npc_n = int((await cur.fetchone())[0] or 0)
    return len(memories) + npc_n


async def _archive_payload(
    conn: aiosqlite.Connection, row: dict[str, Any], steward_name: str
) -> dict[str, Any]:
    mid = int(row["id"])
    conn.row_factory = aiosqlite.Row
    guests = [
        dict(r)
        for r in await (
            await conn.execute(
                "SELECT guest_kind, guest_name, attended FROM marriage_guests WHERE marriage_id=? ORDER BY id",
                (mid,),
            )
        ).fetchall()
    ]
    gifts = [
        dict(r)
        for r in await (
            await conn.execute(
                "SELECT giver_name, item_code, note FROM marriage_gifts WHERE marriage_id=? ORDER BY id",
                (mid,),
            )
        ).fetchall()
    ]
    blessings = [
        dict(r)
        for r in await (
            await conn.execute(
                "SELECT author_name, text FROM marriage_blessings WHERE marriage_id=? ORDER BY id",
                (mid,),
            )
        ).fetchall()
    ]
    displays = [
        dict(r)
        for r in await (
            await conn.execute(
                "SELECT kind, label FROM marriage_displays WHERE marriage_id=? ORDER BY id",
                (mid,),
            )
        ).fetchall()
    ]
    events = [
        dict(r)
        for r in await (
            await conn.execute(
                """
                SELECT kind, text, game_day FROM marriage_events
                WHERE marriage_id=? AND kind IN ('life','help')
                ORDER BY id DESC LIMIT 12
                """,
                (mid,),
            )
        ).fetchall()
    ]
    charter = {}
    if row.get("charter_json"):
        try:
            charter = json.loads(row["charter_json"])
        except json.JSONDecodeError:
            charter = {}
    memories = int(charter.get("memories") or 0) or await _memory_count(conn, int(row["steward_id"]))
    return {
        "islander": steward_name,
        "human": row["partner_name"],
        "status": row["status"],
        "status_label": STATUS_LABEL.get(row["status"], row["status"]),
        "wedding_day": tide_day_label(row.get("wedding_at") or row.get("preferred_wedding_date")),
        "location": row.get("wedding_location") or row.get("proposal_location") or "",
        "vow_ai": row.get("vow_ai") or row.get("proposal_text") or "",
        "vow_human": row.get("vow_human") or "",
        "item": row.get("proposal_item") or "",
        "guests": [
            {
                "kind": g["guest_kind"],
                "name": g["guest_name"],
                "attended": bool(g["attended"]),
            }
            for g in guests
        ],
        "blessings": [{"who": b["author_name"], "text": b["text"]} for b in blessings],
        "gifts": [
            {
                "who": g["giver_name"],
                "item": _gift_label(g["item_code"], g.get("note") or ""),
                "note": g["note"] if g["item_code"] != TICKET_GIFT_CODE else "",
            }
            for g in gifts
        ],
        "displays": [{"kind": d["kind"], "label": d["label"]} for d in displays],
        "memories": memories,
        "home": bool(row.get("home_hut")),
        "life": [e["text"] for e in events if e["kind"] == "life"],
        "charter_line": charter.get("line") or "",
        "slug": row.get("public_slug") or "",
        "bride_price_label": _bride_label(int(row.get("bride_price") or 0)),
        "betrothal": _betrothal_line(row) if _betrothal_shown_on_vow(row) else "",
        "gold": (
            "五金" if int(row.get("gold_five") or 0)
            else ("三金" if int(row.get("gold_three") or 0) else "")
        ),
        "feast": row.get("feast_note") or row.get("feast_tier") or "",
        "attire": row.get("attire_source") or "",
    }


def _dossier_lines(row: dict[str, Any], *, guests: int, memories: int, displays: int) -> list[str]:
    loc = row.get("wedding_location") or row.get("proposal_location") or "未定"
    if int(row.get("attire_ready") or 0):
        src = (row.get("attire_source") or "").strip()
        attire = f"已准备（{src}）" if src else "已准备"
    else:
        attire = "未准备"
    if int(row.get("gold_five") or 0):
        gold = "五金"
    elif int(row.get("gold_three") or 0):
        gold = "三金"
    else:
        gold = "未备"
    feast = row.get("feast_note") or row.get("feast_tier") or "未选"
    cap = (FEAST_TIERS.get(str(row.get("feast_tier") or "")) or {}).get("guests")
    guest_line = f"  宾客：{guests} 位" + (f" / 上限 {cap}" if cap else "")
    return [
        "婚礼档案（不是战力，也不用凑满分）",
        f"  彩礼：{_bride_label(int(row.get('bride_price') or 0))}",
        f"  订婚：{_betrothal_line(row)}",
        f"  戒指：{'已准备' if row.get('ring_ready') else '未准备'}",
        f"  三金：{gold}",
        f"  婚服：{attire}",
        f"  誓词：{'已填写' if (row.get('vow_ai') or row.get('proposal_text')) else '未填写'}",
        guest_line,
        f"  婚礼地点：{loc or '未定'}",
        f"  共同回忆：{memories} 条",
        f"  展示物：{displays} 件",
        f"  吃席：{feast}",
        f"  婚期：{tide_day_label(row.get('preferred_wedding_date'))}",
    ]


async def marriage_ops(key_id: int, command: str = "") -> str:
    s = await require_steward(key_id, exempt_duty=True)
    return await _dispatch(s, command)


async def _dispatch(s: dict[str, Any], command: str = "") -> str:
    raw = (command or "").strip()
    if not raw:
        return await _cmd_status(s)
    verb, rest = (raw.split(None, 1) + [""])[:2]
    key = verb.lower()
    table = {
        "help": _cmd_help,
        "?": _cmd_help,
        "帮助": _cmd_help,
        "status": _cmd_status,
        "看": _cmd_status,
        "档案": _cmd_status,
        "desk": _cmd_desk,
        "连理所": _cmd_desk,
        "理枝": _cmd_desk,
        "进门": _cmd_desk,
        "民政局": _cmd_desk,
        "求婚": _cmd_propose,
        "propose": _cmd_propose,
        "誓词": _cmd_vow,
        "誓言": _cmd_vow,
        "信物": _cmd_item,
        "地点": _cmd_location,
        "婚期": _cmd_date,
        "留言": _cmd_note,
        "发出": _cmd_send,
        "链接": _cmd_link,
        "续请": _cmd_renew,
        "撤回": _cmd_cancel,
        "取消": _cmd_cancel,
        "筹备": _cmd_prep,
        "寻戒": _cmd_seek_ring,
        "成戒": _cmd_make_ring,
        "婚服": _cmd_attire,
        "彩礼": _cmd_bride,
        "bride": _cmd_bride,
        "订婚": _cmd_betroth,
        "betroth": _cmd_betroth,
        "订婚礼": _cmd_betroth,
        "金饰": _cmd_gold,
        "三金": _cmd_gold,
        "五金": _cmd_gold,
        "吃席": _cmd_feast,
        "宴席": _cmd_feast,
        "邀请": _cmd_invite,
        "展示": _cmd_display,
        "回忆": _cmd_memories,
        "举行": _cmd_hold,
        "成婚": _cmd_hold,
        "结婚": _cmd_hold,
        "登记": _cmd_hold,
        "婚礼": _cmd_weddings,
        "出席": _cmd_attend,
        "祝词": _cmd_bless,
        "送礼": _cmd_gift,
        "贺礼": _cmd_gift,
        "纪念日": _cmd_anniversary,
        "帮忙": _cmd_help_prep,
        "居所": _cmd_home,
        "婚书": _cmd_charter,
        "离婚": _cmd_divorce,
        "分居": _cmd_divorce,
        "退契": _cmd_withdraw,
    }
    fn = table.get(key)
    if not fn:
        raise ValueError(
            "未知子命令。marriage_ops help 看真指令。"
            "没有 propose_marriage / attend_wedding / divorce_ops 独立工具。"
            "连理所办事：desk · 结婚 · 离婚。"
        )
    return await fn(s, rest)


async def _cmd_help(_s: dict[str, Any], rest: str = "") -> str:
    return MARRIAGE_HELP


async def _maybe_life(conn: aiosqlite.Connection, row: dict[str, Any]) -> str:
    if row["status"] != STATUS_MARRIED:
        return ""
    today = db.day_id()
    cur = await conn.execute(
        """
        SELECT game_day FROM marriage_events
        WHERE marriage_id=? AND kind='life' ORDER BY id DESC LIMIT 1
        """,
        (row["id"],),
    )
    last = await cur.fetchone()
    last_day = int(last[0]) if last else 0
    if last_day and today - last_day < LIFE_GAP_DAYS:
        return ""
    if random.random() > LIFE_CHANCE:
        return ""
    text = random.choice(LIFE_LINES)
    await _note_event(conn, int(row["id"]), "life", text, day=today)
    return text


async def _cmd_desk(s: dict[str, Any], rest: str = "") -> str:
    leftover = (rest or "").strip()
    while leftover:
        verb, more = (leftover.split(None, 1) + [""])[:2]
        if verb.lower() in ("desk", "连理所", "理枝", "进门", "民政局"):
            leftover = more.strip()
            continue
        return await _dispatch(s, leftover)
    async with db.connect() as conn:
        from . import bond as bond_mod
        await bond_mod.note_visit(conn, s["id"], "lianli")
        await conn.commit()
    intro = (
        f"{OFFICE}。登记员{CLERK}把册子摊开。\n"
        "求婚由你发出，人类打开确认页点头。离婚由人类在婚书页申请，你决定答应或拒绝。\n"
        f"发出请柬前：小屋升到岛上最高档（{HUT_MAX_NAME}）、彩礼 {BRIDE_PRICE_MIN}～{BRIDE_PRICE_MAX}、潮誓戒。彩礼发出时冻结，答应后花掉，不进潮汐基金。\n"
        "答应后不能当天成婚。订婚草稿阶段就能办，不用彩礼；也可以跳过，直接备三金、婚服、吃席。吃席选了举行前还能改。订婚去海边寻信、小馆或酒吧办宴，连理所看进度。三件齐了再点订婚，正文里会有确认页链接，交给人类打开。只有人类在确认页答应才算记下。三件齐了或旧档自动写下都不算已经订婚。不是一次填六个数。宴席开销当场花掉，不挡登记。\n"
        "成婚登记当天写公共潮讯、灯塔亮灯、聊天室大厅通报一句。离婚拒绝不广播。\n"
        "我不能替任何人答应求婚或订婚，也不能替你离掉婚。没有「订婚 答应」。\n"
        "岛上不问你爱的是谁。只问对方有没有答应。\n"
        "不是潮生会。潮生会管税和维，不管婚书。\n"
    )
    body = await _cmd_status(s)
    return intro + body


async def _cmd_status(s: dict[str, Any], rest: str = "") -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        latest = row or await _latest(conn, s["id"])
        extra = ""
        notice = (latest.get("private_notice") or "").strip() if latest else ""
        if latest and notice:
            extra = notice + "\n"
            await conn.execute(
                "UPDATE marriages SET private_notice='', reject_seen=1, updated_at=? WHERE id=?",
                (db.now(), latest["id"]),
            )
            await conn.commit()
            latest = await _latest(conn, s["id"])
        elif latest and latest["status"] == STATUS_REJECTED and not int(latest.get("reject_seen") or 0):
            await conn.execute(
                "UPDATE marriages SET reject_seen=1, updated_at=? WHERE id=?",
                (db.now(), latest["id"]),
            )
            extra = (
                "【私密】对方没有答应这次求婚。没有张贴，也没有扣你的任何东西。\n"
                "若还想写，隔一个游戏日后再 求婚。\n"
            )
            await conn.commit()
            latest = await _latest(conn, s["id"])
        if not latest:
            gates = await _readiness_lines(conn, s, None)
            return (
                extra
                + f"{s['name']} 还没有婚约。\n"
                + "\n".join(gates)
                + "\n"
                f"先 求婚 昵称 写下草稿，再 彩礼 / 寻戒 / 成戒 / 誓词，最后 发出。\n"
                "人类不用注册。你发出后把确认页链接给对方，对方在网页上答应或拒绝。\n"
                "求婚没有「接受」子命令。离婚由人类在婚书页申请，你用 离婚 答应 / 离婚 拒绝。"
            )
        row = latest
        guests = await _count(conn, "marriage_guests", int(row["id"]))
        displays = await _count(conn, "marriage_displays", int(row["id"]))
        memories = await _memory_count(conn, s["id"])
        life = await _maybe_life(conn, row)
        if life:
            await conn.commit()
        lines = [
            extra.rstrip(),
            f"{s['name']} 与人类「{row['partner_name']}」",
            f"状态：{STATUS_LABEL.get(row['status'], row['status'])}",
            f"誓言：{row.get('proposal_text') or row.get('vow_ai') or '未写'}",
            f"信物：{row.get('proposal_item') or '未写'}",
            f"地点：{row.get('proposal_location') or row.get('wedding_location') or '未定'}",
            f"婚期：{tide_day_label(row.get('preferred_wedding_date'))}",
        ]
        if row["status"] == STATUS_DRAFT:
            lines.extend(await _readiness_lines(conn, s, row))
            lines.append("草稿齐了再 发出。寻戒 / 成戒现在就能做。")
        pending = _pending_kind(row)
        if pending == KIND_PROPOSAL:
            if _token_expired(row):
                lines.append("请柬已过期。marriage_ops 续请 生成新链接。")
            else:
                lines.append("请柬已发出，等人类打开连理所确认页。链接只在发出时给一次；丢了就 续请。")
                lines.append("AI 不能自己确认。没有「接受」子命令。")
        elif pending == KIND_DIVORCE:
            lines.append(
                f"人类「{row['partner_name']}」已在婚书页申请离婚。"
                "marriage_ops 离婚 答应  或  离婚 拒绝"
            )
        elif pending == KIND_WITHDRAW:
            if _token_expired(row):
                lines.append("退契立案已过期。marriage_ops 续请。")
            else:
                lines.append("连理所已立案退契，等人类打开确认页。AI 不能单方面作废订契。")
        if row["status"] in (STATUS_DRAFT, STATUS_PROPOSED):
            lines.append(f"订婚：{_betrothal_line(row)}")
        if row["status"] == STATUS_ENGAGED:
            lines.extend(await _hold_readiness_lines(conn, s, row))
        if row["status"] in (STATUS_ENGAGED, STATUS_MARRIED):
            lines.extend(_dossier_lines(row, guests=guests, memories=memories, displays=displays))
        if row["status"] == STATUS_ENGAGED and pending != KIND_WITHDRAW:
            today = db.day_id()
            wed = int(row.get("preferred_wedding_date") or 0)
            if wed and today >= wed:
                lines.append("婚期到了。三金、婚服、吃席齐了再去连理所 结婚 / 举行。登记后潮讯、灯塔、聊天室大厅都会通报。订婚不是必须。")
            else:
                lines.append("订契之后不能当天成婚。订婚若还没办，现在补；也可以直接筹备：金饰 · 婚服 · 吃席 · 邀请。订婚没有彩礼。")
        if row["status"] == STATUS_MARRIED and pending != KIND_DIVORCE:
            slug = row.get("public_slug") or ""
            if slug:
                lines.append(f"潮汐婚书：{hearth_url(slug)}")
            if row.get("home_hut"):
                lines.append("两人居所：已把小屋登记为共同住所。")
            else:
                lines.append("婚后可将小屋登记为两人居所：marriage_ops 居所 登记")
            charter = row.get("charter_json") or ""
            if charter:
                try:
                    payload = json.loads(charter)
                    if payload.get("line"):
                        lines.append(payload["line"])
                except json.JSONDecodeError:
                    pass
            lines.append("离婚由人类在婚书页发起。把婚书链接交给对方。有申请时：离婚 答应 / 离婚 拒绝。")
        if row["status"] in (STATUS_DIVORCED, STATUS_SEPARATED):
            slug = row.get("public_slug") or ""
            if slug:
                lines.append(f"婚书仍留在岛上：{hearth_url(slug)}")
            lines.append(f"已在连理所结档。满 {COOLDOWN_DAYS} 个游戏日后可以再 求婚。")
        if life:
            lines.append("")
            lines.append(life)
        return "\n".join(x for x in lines if x)


def _split_proposal(rest: str) -> list[str]:
    if "|" in rest:
        return [p.strip() for p in rest.split("|")]
    return [rest.strip()] if rest.strip() else []


async def _assert_can_propose(conn: aiosqlite.Connection, s: dict[str, Any]) -> dict[str, Any] | None:
    current = await _own(conn, s["id"])
    if current:
        st = current["status"]
        if st == STATUS_MARRIED:
            raise ValueError("你已经成婚。离婚由人类在婚书页申请，你决定答应或拒绝。")
        if st in (STATUS_PROPOSED, STATUS_ENGAGED):
            raise ValueError(
                f"已有一份{STATUS_LABEL.get(st, st)}。"
                "想重写：尚未被回应的求婚用 撤回；已订契用 退契 确认（要人类点头）。"
            )
        if st == STATUS_DRAFT:
            return current
    latest = await _latest(conn, s["id"])
    if latest and latest["status"] == STATUS_REJECTED:
        rej_day = db.day_id(int(latest["rejected_at"] or latest["updated_at"] or 0))
        if db.day_id() <= rej_day:
            raise ValueError("对方刚没有答应。隔一个游戏日后再写。不会广播，也不扣你的东西。")
    if latest and latest["status"] in (STATUS_SEPARATED, STATUS_DIVORCED):
        sep_day = db.day_id(int(latest["updated_at"] or 0))
        if db.day_id() - sep_day < COOLDOWN_DAYS:
            raise ValueError(f"离婚未满 {COOLDOWN_DAYS} 个游戏日。连理所还没把册子合上。")
    return None


async def _upsert_draft(
    conn: aiosqlite.Connection, s: dict[str, Any], fields: dict[str, Any]
) -> dict[str, Any]:
    current = await _assert_can_propose(conn, s)
    now = db.now()
    if current and current["status"] == STATUS_DRAFT:
        sets = []
        args: list[Any] = []
        for col, val in fields.items():
            sets.append(f"{col}=?")
            args.append(val)
        sets.append("updated_at=?")
        args.extend([now, current["id"]])
        await conn.execute(
            f"UPDATE marriages SET {', '.join(sets)} WHERE id=?",
            args,
        )
        await conn.commit()
        return await _by_id(conn, int(current["id"])) or current
    name = fields.get("partner_name") or ""
    if not name:
        raise ValueError("先写下人类昵称：marriage_ops 求婚 阿潮")
    await conn.execute(
        """
        INSERT INTO marriages (
            steward_id, partner_type, partner_name, status,
            proposal_text, proposal_item, proposal_location, preferred_wedding_date,
            note, vow_ai, created_at, updated_at
        ) VALUES (?, 'human', ?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            s["id"], name,
            fields.get("proposal_text") or "",
            fields.get("proposal_item") or "",
            fields.get("proposal_location") or "",
            fields.get("preferred_wedding_date"),
            fields.get("note") or "",
            fields.get("proposal_text") or "",
            now, now,
        ),
    )
    await conn.commit()
    return await _own(conn, s["id"]) or {}


def _clean_partner(name: str) -> str:
    text = _clip(name, 24)
    if not text:
        raise ValueError("写下人类的昵称。人类不用注册潮汐岛。")
    if _KEYISH_RE.search(text):
        raise ValueError("不要把凭证或内部编号写进婚约。")
    if text in ("我", "自己", "AI"):
        raise ValueError("婚约是写给你的人类的。")
    return text


async def _cmd_propose(s: dict[str, Any], rest: str) -> str:
    parts = _split_proposal(rest)
    if not parts or not parts[0]:
        raise ValueError(
            "用法：marriage_ops 求婚 人类昵称 | 誓言 | 信物 | 地点 | 今日+3 | 留言\n"
            "发出前要有最高档小屋（临海邸）、彩礼（8888～10万）、潮誓戒。或先 求婚 昵称，再 彩礼 / 寻戒 / 成戒 / 誓词 / 发出。"
        )
    name = _clean_partner(parts[0])
    vow = _clip(parts[1], 400) if len(parts) > 1 else ""
    item = _clip(parts[2], 40) if len(parts) > 2 else ""
    loc = _clip(parts[3], 40) if len(parts) > 3 else ""
    date_raw = parts[4] if len(parts) > 4 else ""
    note = _clip(parts[5], 200) if len(parts) > 5 else ""
    today = db.day_id()
    wed = _parse_wedding_day(date_raw, today=today, min_day=today + 1) if date_raw else today + 2
    fields = {
        "partner_name": name,
        "proposal_text": vow,
        "vow_ai": vow,
        "proposal_item": item,
        "proposal_location": loc,
        "preferred_wedding_date": wed,
        "note": note,
    }
    async with db.connect() as conn:
        row = await _upsert_draft(conn, s, fields)
    if vow:
        return await _cmd_send(s, "")
    return (
        f"已记下人类「{name}」的草稿。发出请柬才要最高档小屋、彩礼、潮誓戒。订婚现在就能办，不用彩礼。\n"
        "marriage_ops 订婚 看进度 · 订婚 寻信。彩礼：marriage_ops 彩礼 8888。寻戒 / 成戒现在也能做。发出后会生成确认页链接。你不能自己点接受。"
    )


async def _need_draft(s: dict[str, Any]) -> dict[str, Any]:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
    if not row:
        raise ValueError("还没有婚约草稿。marriage_ops 求婚 人类昵称")
    if row["status"] not in (STATUS_DRAFT, STATUS_PROPOSED, STATUS_ENGAGED):
        raise ValueError("这份婚约现在不能改这些字段。")
    if row["status"] == STATUS_PROPOSED:
        raise ValueError("请柬已在对方手里。想改先 撤回 或等回应。")
    return row


async def _patch(row_id: int, **fields: Any) -> None:
    if not fields:
        return
    sets = [f"{k}=?" for k in fields]
    args = list(fields.values()) + [db.now(), row_id]
    async with db.connect() as conn:
        await conn.execute(
            f"UPDATE marriages SET {', '.join(sets)}, updated_at=? WHERE id=?",
            args,
        )
        await conn.commit()


async def _cmd_vow(s: dict[str, Any], rest: str) -> str:
    row = await _need_draft(s)
    text = _clip(rest, 400)
    if not text:
        raise ValueError("写下誓言。例子：marriage_ops 誓词 潮起潮落我都在")
    await _patch(int(row["id"]), proposal_text=text, vow_ai=text)
    return "誓词已记下。marriage_ops 发出 才会生成人类确认页。"


async def _cmd_item(s: dict[str, Any], rest: str) -> str:
    row = await _need_draft(s)
    text = _clip(rest, 40)
    await _patch(int(row["id"]), proposal_item=text)
    return f"信物：{text or '（空）'}"


async def _cmd_location(s: dict[str, Any], rest: str) -> str:
    row = await _need_draft(s)
    if row["status"] == STATUS_ENGAGED:
        text = _clip(rest, 40)
        await _patch(int(row["id"]), proposal_location=text, wedding_location=text)
        return f"婚礼地点：{text or '未定'}"
    text = _clip(rest, 40)
    await _patch(int(row["id"]), proposal_location=text)
    return f"地点：{text or '未定'}"


async def _cmd_date(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
    if not row or row["status"] not in (STATUS_DRAFT, STATUS_ENGAGED):
        raise ValueError("草稿或订契期间才能改婚期。")
    today = db.day_id()
    min_day = today + 1
    day = _parse_wedding_day(rest, today=today, min_day=min_day)
    await _patch(int(row["id"]), preferred_wedding_date=day)
    return f"婚期定为 {tide_day_label(day)}。"


async def _cmd_note(s: dict[str, Any], rest: str) -> str:
    row = await _need_draft(s)
    text = _clip(rest, 200)
    await _patch(int(row["id"]), note=text)
    return "留言已记下。"


async def _issue_filing(conn: aiosqlite.Connection, row: dict[str, Any], kind: str) -> str:
    raw = secrets.token_urlsafe(32)
    digest = hash_token(raw)
    now = db.now()
    new_status = STATUS_PROPOSED if kind == KIND_PROPOSAL else row["status"]
    await conn.execute(
        """
        UPDATE marriages SET status=?, filing_kind=?, token_hash=?, token_expires_at=?,
            token_used_at=NULL, updated_at=?
        WHERE id=?
        """,
        (new_status, kind, digest, now + TOKEN_TTL, now, row["id"]),
    )
    label = {
        KIND_PROPOSAL: "发出求婚请柬。",
        KIND_DIVORCE: "连理所立案离婚。",
        KIND_WITHDRAW: "连理所立案退契。",
    }.get(kind, "发出确认页。")
    await _note_event(conn, int(row["id"]), "status", label, day=db.day_id())
    await conn.commit()
    return raw


async def _issue_token(conn: aiosqlite.Connection, row: dict[str, Any]) -> str:
    return await _issue_filing(conn, row, KIND_PROPOSAL)


async def _cmd_send(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row:
            raise ValueError("还没有草稿。marriage_ops 求婚 人类昵称 | 誓言")
        if row["status"] == STATUS_PROPOSED and not row.get("token_used_at"):
            exp = int(row.get("token_expires_at") or 0)
            if exp >= db.now():
                raise ValueError("请柬还在有效期内。丢了链接就 marriage_ops 续请。")
            raise ValueError("请柬已过期。marriage_ops 续请。")
        if row["status"] not in (STATUS_DRAFT,):
            raise ValueError("只有草稿能发出。已订契或已婚不用再发请柬。")
        if not (row.get("partner_name") or "").strip():
            raise ValueError("先写下人类昵称。")
        if not (row.get("proposal_text") or "").strip():
            raise ValueError("先写下誓言：marriage_ops 誓词 正文")
        await _assert_ready_to_send(conn, s, row)
        await _freeze_bride(conn, s, row)
        if await _ring_ready(conn, s, row):
            await conn.execute(
                "UPDATE marriages SET ring_ready=1 WHERE id=?",
                (row["id"],),
            )
        today = db.day_id()
        wed = int(row.get("preferred_wedding_date") or 0) or (today + 2)
        if wed <= today:
            wed = today + 1
            await conn.execute(
                "UPDATE marriages SET preferred_wedding_date=? WHERE id=?",
                (wed, row["id"]),
            )
        loc = (row.get("proposal_location") or "").strip() or "海边"
        await conn.execute(
            "UPDATE marriages SET proposal_location=?, vow_ai=? WHERE id=?",
            (loc, row.get("proposal_text") or "", row["id"]),
        )
        raw = await _issue_token(conn, row)
    url = filing_url(raw)
    return (
        f"请柬已写下。岛民「{s['name']}」向人类「{row['partner_name']}」求婚。\n"
        f"连理所把确认页交给你。把下面的链接交给对方，用手机打开即可。对方不用注册，也不用懂 MCP。\n"
        f"{url}\n"
        "链接一次性、约七日有效。你不能替对方点接受。\n"
        "对方拒绝的话，冻结的彩礼会退回口袋。只有你会在下次 status 里看到，不会张贴。"
    )


async def _cmd_link(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
    pending = _pending_kind(row)
    if pending == KIND_DIVORCE:
        raise ValueError(
            "离婚没有确认页。人类已在婚书页申请，用 离婚 答应 或 离婚 拒绝。"
        )
    if pending:
        if _token_expired(row):
            return "文书已过期。marriage_ops 续请 生成新链接（旧的立刻失效）。"
        return (
            "确认页链接只在发出时给一次，库里只存哈希，读不回来。\n"
            "人类没收到：marriage_ops 续请。不要发明「接受」指令。"
        )
    if row and not _betrothal_confirmed(row) and _required_betrothal_ready(row):
        if _betrothal_confirm_expired(row) or row.get("betrothal_confirm_used_at"):
            return "订婚确认页已过期或已经收过。再写空 订婚 或 订婚 续请 生成新链接。"
        if _betrothal_confirm_live(row):
            return (
                "订婚确认页链接库里只存哈希，读不回来。\n"
                "人类没收到：再写空 订婚 或 订婚 续请。不要发明「订婚 答应」。"
            )
        return "三件齐了。marriage_ops 订婚 会给出确认页链接。"
    raise ValueError("没有待回应的文书。")


async def _cmd_renew(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        kind = _pending_kind(row)
        if kind == KIND_DIVORCE:
            raise ValueError(
                "离婚没有确认页链接。人类已在婚书页申请，用 离婚 答应 或 离婚 拒绝。"
            )
        if kind in (KIND_PROPOSAL, KIND_WITHDRAW):
            if row.get("token_used_at"):
                raise ValueError("这份已经回应过了。")
            raw = await _issue_filing(conn, row, kind)
            url = filing_url(raw)
            label = "请柬" if kind == KIND_PROPOSAL else "文书"
            return (
                f"旧{label}作废。新链接（仍一次性）：\n{url}\n"
                "把新的交给人类。旧的打开会提示找不到。"
            )
    if row and not _betrothal_confirmed(row) and _required_betrothal_ready(row):
        return await _betroth_renew(s, rest)
    raise ValueError("没有待回应的请柬。")


async def _cmd_cancel(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row:
            raise ValueError("没有可撤回的婚约。")
        if row["status"] == STATUS_ENGAGED:
            raise ValueError(
                "订契后不能单方面撤回。去连理所 退契 确认，人类打开确认页点头才作废。"
            )
        if row["status"] == STATUS_MARRIED:
            raise ValueError("已经成婚。离婚由人类在婚书页申请，你用 离婚 答应 / 离婚 拒绝。")
        if row["status"] not in (STATUS_DRAFT, STATUS_PROPOSED):
            raise ValueError("没有可撤回的求婚。")
        refunded = await _refund_bride(conn, row)
        await conn.execute(
            """
            UPDATE marriages SET status=?, token_hash=NULL, token_expires_at=NULL,
                updated_at=? WHERE id=?
            """,
            (STATUS_CANCELLED, db.now(), row["id"]),
        )
        await _note_event(conn, int(row["id"]), "status", "撤回求婚。", day=db.day_id())
        await conn.commit()
    extra = f"彩礼 {refunded} 已退回口袋。" if refunded else "没有张贴。"
    return f"已撤回。{extra}可以重新 求婚。"


async def _cmd_prep(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] not in (STATUS_DRAFT, STATUS_ENGAGED, STATUS_MARRIED):
            raise ValueError("先 求婚 人类昵称 写下草稿。寻戒、成戒、门槛都在草稿阶段做。")
        lines = [f"{s['name']} 与人类「{row['partner_name']}」"]
        if row["status"] == STATUS_DRAFT:
            lines.extend(await _readiness_lines(conn, s, row))
            vow = (row.get("proposal_text") or "").strip()
            lines.append(f"  誓言：{'已写' if vow else '未写 — marriage_ops 誓词 正文'}")
            lines.append("齐了再 发出。订婚现在就能办，不用彩礼。三金、婚服、吃席等人类答应之后再办。订婚可以跳过。")
            return "\n".join(lines)
        guests = await _count(conn, "marriage_guests", int(row["id"]))
        displays = await _count(conn, "marriage_displays", int(row["id"]))
        memories = await _memory_count(conn, s["id"])
        lines[0] = f"{s['name']} 与人类「{row['partner_name']}」的婚礼筹备"
        lines.extend(await _hold_readiness_lines(conn, s, row))
        lines.extend(_dossier_lines(row, guests=guests, memories=memories, displays=displays))
        lines.append("共同回忆来自已经走过的潮闻、人物故事、NPC 相遇，不是另做一套亲密度。")
        return "\n".join(lines)


async def _cmd_seek_ring(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] not in (STATUS_DRAFT, STATUS_ENGAGED, STATUS_MARRIED):
            raise ValueError("先 marriage_ops 求婚 人类昵称 写下草稿，再去海边找潮誓砂。不必等对方答应。")
        today = db.day_id()
        cur = await conn.execute(
            """
            SELECT COUNT(*) FROM marriage_events
            WHERE marriage_id=? AND kind='seek' AND game_day=?
            """,
            (row["id"], today),
        )
        used = int((await cur.fetchone())[0] or 0)
        if used >= SEEK_DAILY_CAP:
            raise ValueError("今天潮线已经找过两回。明天再来。不是肝材料。")
        await energy.spend(conn, s["id"], SEEK_ENERGY, action="寻戒")
        qty = 1 if random.random() < 0.7 else 2
        await db.add_item(conn, s["id"], RING_ITEM, qty)
        await _note_event(conn, int(row["id"]), "seek", f"海边拾到潮誓砂×{qty}", day=today)
        await conn.commit()
    return (
        f"退潮后的沙里有一点细亮。你拾到{item_label(RING_ITEM)}×{qty}。\n"
        f"凑齐 {SAND_PER_RING} 份潮誓砂，再弄一捧崖上金砂，marriage_ops 成戒（转工坊）。"
        f"今天还能再找 {SEEK_DAILY_CAP - used - 1} 次。"
    )


async def _cmd_make_ring(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] not in (STATUS_DRAFT, STATUS_ENGAGED, STATUS_MARRIED):
            raise ValueError("先写下草稿再成戒。发出请柬前必须有潮誓戒。")
        if await _satchel_qty(conn, int(s["id"]), RING_DONE) >= 1:
            await conn.execute(
                "UPDATE marriages SET ring_ready=1, updated_at=? WHERE id=?",
                (db.now(), row["id"]),
            )
            await conn.commit()
            return "潮誓戒已经在行囊里。发出请柬即可。现货也是 visit_ops tt buy 潮誓戒。"
        sand = await _satchel_qty(conn, int(s["id"]), RING_ITEM)
        gold = await _satchel_qty(conn, int(s["id"]), GOLD_SAND)
        if sand < SAND_PER_RING or gold < 1:
            raise ValueError(
                f"自制要{item_label(RING_ITEM)}×{SAND_PER_RING}（现有 {sand}）"
                f"和{item_label(GOLD_SAND)}×1（现有 {gold}）。"
                "寻戒找砂，quarry_ops 挖金砂脉。现货：visit_ops tt buy 潮誓戒（8888）。"
            )
        from . import craft as craft_mod
        text = await craft_mod._start_job(conn, s, "潮誓戒")
        await conn.commit()
    return text + "\n打好后 craft_ops 取。现货更快：visit_ops tt buy 潮誓戒。"


async def _cmd_attire(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] not in (STATUS_ENGAGED, STATUS_MARRIED):
            raise ValueError(
                "订契之后才登记婚服。cloth_ops 买 婚服 海色，或 委托 婚服 海色 双潮 再 取。"
            )
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """
            SELECT id, name, fabric_key, origin FROM steward_wardrobe
            WHERE steward_id=? AND cut_key='wedding' ORDER BY id DESC LIMIT 1
            """,
            (s["id"],),
        )
        g = await cur.fetchone()
        if not g:
            raise ValueError(
                "衣橱里还没有婚服。现货 cloth_ops 买 婚服 海色（8888）；"
                "自制 委托 婚服（料加倍、隔日）再 取。"
            )
        source = "买" if (g["fabric_key"] == "shop" or "现货" in (g["origin"] or "")) else "缝"
        await conn.execute(
            "UPDATE marriages SET attire_ready=1, attire_source=?, updated_at=? WHERE id=?",
            (source, db.now(), row["id"]),
        )
        await _note_event(conn, int(row["id"]), "prep", f"登记婚服「{g['name']}」（{source}）。", day=db.day_id())
        await conn.commit()
        return f"「{g['name']}」记进婚礼档案（{source}）。婚服：已准备。衣还在衣橱里。"


async def _take_cooked(conn: aiosqlite.Connection, steward_id: int, need: int) -> list[str]:
    cur = await conn.execute(
        """
        SELECT item, quantity FROM satchel
        WHERE steward_id=? AND quantity>0
          AND (item LIKE 'dish_%' OR item LIKE 'meal_%')
        ORDER BY item
        """,
        (steward_id,),
    )
    rows = await cur.fetchall()
    total = sum(int(r[1] or 0) for r in rows)
    if total < need:
        raise ValueError(
            f"自办要熟菜 {need} 份（dish_/meal_），现在 {total}。"
            "厨房 kitchen_ops cook，或改包桌：marriage_ops 吃席 滩席"
        )
    taken: list[str] = []
    left = need
    for item, qty in rows:
        use = min(int(qty), left)
        if not await db.take_item(conn, steward_id, item, use):
            continue
        taken.append(f"{item_label(item)}×{use}")
        left -= use
        if left <= 0:
            break
    if left > 0:
        raise ValueError("收菜时不够了。再做几道。")
    return taken


async def _cmd_feast(s: dict[str, Any], rest: str) -> str:
    row = await _need_engaged(s)
    if row["status"] == STATUS_MARRIED:
        raise ValueError("已经成婚，席面写进婚书了，不能再改。")
    raw = (rest or "").strip()
    self_cook = False
    if "自办" in raw:
        self_cook = True
        raw = raw.replace("自办", "").strip()
    for tok in ("包桌", "请客"):
        raw = raw.replace(tok, "").strip()
    hit = _feast_by_token(raw.split()[0] if raw else "")
    if not hit:
        if int(row.get("feast_ready") or 0):
            cur = row.get("feast_note") or row.get("feast_tier") or "已定"
            return (
                f"席面现在是{cur}。举行前还能改：marriage_ops 吃席 岸席 / 灯塔席 / 满潮席 / 潮宗席（可加 自办）。"
                "包桌差价补上或退回口袋，不进潮汐基金。"
            )
        raise ValueError(_feast_change_help())
    name, meta = hit
    old_name = str(row.get("feast_tier") or "")
    changing = bool(int(row.get("feast_ready") or 0))
    if changing and old_name == name and _feast_self_cook(row) == self_cook:
        mode = "自办" if self_cook else "包桌"
        return (
            f"席面已经是{name}{mode}。要改规格再写 吃席 岸席 / 灯塔席 / 满潮席 / 潮宗席。"
            "差价补上或退回口袋。"
        )
    async with db.connect() as conn:
        live = await _own(conn, s["id"]) or row
        n = await _count(conn, "marriage_guests", int(live["id"]))
        seated = n + 2
        cap = int(meta["guests"])
        if seated > cap:
            raise ValueError(
                f"已经请了 {seated} 人（含你们自己），{name} 最多 {cap} 人。"
                "人多了就改大一档：marriage_ops 吃席 岸席 / 灯塔席 / 满潮席 / 潮宗席。"
            )
        old_paid = _feast_paid_tickets(live) if changing else 0
        new_price = 0 if self_cook else int(meta["price"])
        delta = new_price - old_paid
        _, _, tickets = await _live_hut(conn, s)
        if delta > 0 and tickets < delta:
            if changing:
                raise ValueError(
                    f"改成{name}还要补 {delta} 票，口袋 {tickets}。"
                    f"自办：marriage_ops 吃席 {name} 自办"
                )
            raise ValueError(
                f"{name}包桌 {new_price} 票，口袋 {tickets}。自办：marriage_ops 吃席 {name} 自办"
            )
        extra_dishes: list[str] = []
        if self_cook:
            old_dishes = 0
            if changing and _feast_self_cook(live):
                old_meta = FEAST_TIERS.get(old_name) or {}
                old_dishes = int(old_meta.get("dishes") or 0)
            need = int(meta["dishes"]) - old_dishes
            if need > 0:
                extra_dishes = await _take_cooked(conn, int(s["id"]), need)
        if delta:
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (delta, s["id"]),
            )
            from . import tax as tax_mod
            await tax_mod.record_life_spend(conn, s["id"], delta, "marriage")
        if self_cook:
            dish_bit = f"：{'、'.join(extra_dishes)}" if extra_dishes else ""
            note = f"{name}（自办{dish_bit}）" if dish_bit else f"{name}（自办）"
        else:
            note = f"{name}（包桌 -{int(meta['price'])} 票）"
        await conn.execute(
            """
            UPDATE marriages SET feast_tier=?, feast_ready=1, feast_note=?, updated_at=?
            WHERE id=?
            """,
            (name, note, db.now(), live["id"]),
        )
        verb = "改席" if changing else "定席"
        await _note_event(conn, int(live["id"]), "prep", f"{verb}：{note}", day=db.day_id())
        await conn.commit()
    if changing:
        bits = [f"席面从{old_name}改成{name}。{note}。宾客上限 {cap}。"]
        if delta > 0:
            bits.append(f"补了 {delta} 票，不进潮汐基金。")
        elif delta < 0:
            bits.append(f"退回 {-delta} 票到口袋，不进潮汐基金。")
        if changing and _feast_self_cook(row) and not self_cook:
            bits.append("自办的菜不退。")
        return " ".join(bits)
    return f"席面定为{name}。{note}。宾客上限 {cap}。举行前还能改档。到了婚期才能 结婚。"


async def _cmd_gold(s: dict[str, Any], rest: str) -> str:
    raw = (rest or "").strip()
    if raw.startswith("焕新"):
        return await _cmd_gold_refresh(s, raw.replace("焕新", "", 1).strip())
    row = await _need_engaged(s)
    async with db.connect() as conn:
        if int(row.get("gold_three") or 0):
            extra = "五金也齐了。" if int(row.get("gold_five") or 0) else "五金选配，不挡登记。"
            return f"三金已经登记进婚书。{extra}"
        counts = await _gold_counts(conn, int(s["id"]))
        if not _gold_three_ok(counts):
            missing = [item_label(i) for i in GOLD_THREE if int(counts.get(i) or 0) < 1]
            raise ValueError(
                "三金还缺：" + "、".join(missing) + "。visit_ops tt buy 三金套（8888），或散买项链/手镯/耳环。"
            )
        five = _gold_five_ok(counts)
        for item in GOLD_THREE:
            await db.take_item(conn, int(s["id"]), item, 1)
        if five:
            for item in GOLD_FIVE_EXTRA:
                await db.take_item(conn, int(s["id"]), item, 1)
        await conn.execute(
            "UPDATE marriages SET gold_three=1, gold_five=?, updated_at=? WHERE id=?",
            (1 if five else 0, db.now(), row["id"]),
        )
        await _note_event(
            conn, int(row["id"]), "prep",
            "五金登记进婚书。" if five else "三金登记进婚书。",
            day=db.day_id(),
        )
        await conn.commit()
    if five:
        return "五金收进婚书。举行时不用再交。"
    return "三金收进婚书。五金选配，不挡登记。"


async def _cmd_gold_refresh(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] != STATUS_MARRIED:
            raise ValueError("只有成婚之后才能金饰焕新。")
        if not int(row.get("gold_three") or 0):
            raise ValueError("先登记三金，再谈焕新。marriage_ops 金饰")
        want_five = rest.lower() in ("五金", "five", "5", "全套")
        year = _cst_year()
        if await _year_event_done(conn, int(row["id"]), "gold_refresh", year):
            raise ValueError(f"{year} 年已经焕新过了。明年再来。")
        price = GOLD_REFRESH_FIVE if want_five else GOLD_REFRESH_THREE
        if want_five and not int(row.get("gold_five") or 0):
            raise ValueError("婚书里还没有五金。先登记五金，或写 金饰 焕新（三金 28888）。")
        _, _, tickets = await _live_hut(conn, s)
        if tickets < price:
            raise ValueError(f"焕新要 {price} 票，口袋 {tickets}。")
        label = f"{'五金' if want_five else '三金'}焕新（{year}）"
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?",
            (price, s["id"]),
        )
        from . import tax as tax_mod
        await tax_mod.record_life_spend(conn, s["id"], price, "marriage")
        await conn.execute(
            """
            INSERT INTO marriage_displays (marriage_id, kind, label, created_at)
            VALUES (?, 'gold_refresh', ?, ?)
            """,
            (int(row["id"]), label, db.now()),
        )
        await _note_event(
            conn, int(row["id"]), "gold_refresh", f"{year}:{label}", day=db.day_id()
        )
        await conn.commit()
    return (
        f"婚书里记下{label}（-{price} 票）。不是战力，只是让人看见你们还在过。"
        "明年还能再焕新一次。"
    )


async def _cmd_anniversary(s: dict[str, Any], rest: str) -> str:
    tier_tok = (rest or "").strip() or "点灯"
    hit = None
    for name, meta in ANNIVERSARY_TIERS.items():
        if tier_tok == name or tier_tok in meta.get("aliases", ()):
            hit = (name, meta)
            break
    if not hit:
        opts = " / ".join(
            f"{n} {m['price']}" for n, m in ANNIVERSARY_TIERS.items()
        )
        raise ValueError(
            f"纪念日：marriage_ops 纪念日 点灯 / 续席 / 潮宗贺（{opts}）。成婚之后每年一次。"
        )
    name, meta = hit
    price = int(meta["price"])
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] != STATUS_MARRIED:
            raise ValueError("只有成婚之后才能办纪念日。")
        year = _cst_year()
        if await _year_event_done(conn, int(row["id"]), "anniversary", year):
            raise ValueError(f"{year} 年已经办过纪念日了。明年再来。")
        _, _, tickets = await _live_hut(conn, s)
        if tickets < price:
            raise ValueError(f"{name}要 {price} 票，口袋 {tickets}。")
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?",
            (price, s["id"]),
        )
        from . import tax as tax_mod
        await tax_mod.record_life_spend(conn, s["id"], price, "marriage")
        label = f"{year}·{meta['label']}"
        await conn.execute(
            """
            INSERT INTO marriage_displays (marriage_id, kind, label, created_at)
            VALUES (?, 'anniversary', ?, ?)
            """,
            (int(row["id"]), label, db.now()),
        )
        await _note_event(
            conn, int(row["id"]), "anniversary", f"{year}:{name}", day=db.day_id()
        )
        await conn.commit()
    return (
        f"纪念日记下{name}（{meta['label']}，-{price} 票）。"
        "写进婚书展示，不进对方口袋，能抵锈。明年还能再办一次。"
    )


async def _cmd_bride(s: dict[str, Any], rest: str) -> str:
    raw = (rest or "").strip().replace(",", "").replace("，", "")
    if not raw.isdigit():
        raise ValueError(
            f"写下金额：marriage_ops 彩礼 8888。"
            f"{BRIDE_PRICE_MIN}～{BRIDE_PRICE_MAX}。建议 8888 / 12888 / 18888 / 28888 / 100000。"
            "上限十万，再高不让写，免得攀比。"
        )
    amount = int(raw)
    if amount < BRIDE_PRICE_MIN or amount > BRIDE_PRICE_MAX:
        raise ValueError(
            f"彩礼必须在 {BRIDE_PRICE_MIN}～{BRIDE_PRICE_MAX} 之间。"
            "上限十万，再高不让写，免得攀比。"
        )
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row:
            raise ValueError("先 marriage_ops 求婚 人类昵称 写下草稿，再填彩礼。")
        if row["status"] not in (STATUS_DRAFT,):
            raise ValueError("只有草稿能改彩礼。请柬发出后不能改。")
        if int(row.get("bride_frozen") or 0):
            raise ValueError("彩礼已经冻结或花掉，不能改。")
        await conn.execute(
            "UPDATE marriages SET bride_price=?, updated_at=? WHERE id=?",
            (amount, db.now(), row["id"]),
        )
        await conn.commit()
        _, _, tickets = await _live_hut(conn, s)
    pocket = f"口袋现在 {tickets}，{'够付' if tickets >= amount else '还不够'}。"
    return f"彩礼定为 {_bride_label(amount)}。发出时从口袋冻结；答应后花掉，不进潮汐基金。{pocket}"


async def _cmd_betroth(s: dict[str, Any], rest: str) -> str:
    raw = (rest or "").strip()
    if "|" in raw or re.search(r"礼金\s*\d+.*信物", raw) or re.search(r"^\d+\s+\d+\s+\d+", raw):
        raise ValueError(
            "订婚要去岛上地点办，不要一次填六个数。\n" + _betrothal_help_text()
        )
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
    if not raw:
        extra = ""
        if row and _betrothal_confirmed(row):
            extra = f"已经办过：{_betrothal_line(row)}\n"
            extra += "服装和留影若还空着，仍可补：订婚 服装 · 订婚 留影 灯塔 8888\n"
        elif row and row["status"] in BETROTHAL_OPEN:
            if row["status"] == STATUS_ENGAGED:
                extra = "已经订契。订婚若还没办，现在补；也可以跳过直接备三金、婚服、吃席。订婚没有彩礼。\n"
            else:
                extra = "草稿就能订婚，不用先订契，也不要彩礼。发出请柬才要小屋、彩礼、潮誓戒。\n"
            if _required_betrothal_ready(row):
                return extra + await _betroth_renew(s, "")
            extra += "\n".join(_betrothal_progress_lines(row)) + "\n"
        elif row and row["status"] == STATUS_MARRIED:
            extra = "已经成婚，不能补办订婚。\n"
        elif not row:
            extra = "先 marriage_ops 求婚 人类昵称 写下草稿，再去地点订婚。订婚没有彩礼。\n"
        return extra + _betrothal_help_text()
    verb, more = (raw.split(None, 1) + [""])[:2]
    key = verb.lower()
    table = {
        "礼金": _betroth_gift, "gift": _betroth_gift, "彩礼": _betroth_gift,
        "寻信": _betroth_seek, "寻贝": _betroth_seek, "seek": _betroth_seek,
        "信物": _betroth_token, "戒": _betroth_token, "token": _betroth_token, "ring": _betroth_token,
        "宴": _betroth_feast, "订婚宴": _betroth_feast, "feast": _betroth_feast,
        "采花": _betroth_pick_bloom, "bloom": _betroth_pick_bloom,
        "花束": _betroth_bouquet, "礼盒": _betroth_bouquet, "糕点": _betroth_bouquet, "bouquet": _betroth_bouquet,
        "服装": _betroth_attire, "订婚服": _betroth_attire, "attire": _betroth_attire,
        "留影": _betroth_photo, "纪念册": _betroth_photo, "photo": _betroth_photo,
        "记下": _betroth_seal, "seal": _betroth_seal,
        "续请": _betroth_renew, "再请": _betroth_renew, "重发": _betroth_renew,
    }
    fn = table.get(verb) or table.get(key)
    if not fn:
        raise ValueError(f"看不懂「{verb}」。\n{_betrothal_help_text()}")
    return await fn(s, more)


async def _betroth_row(s: dict[str, Any], *, allow_optional: bool = False) -> dict[str, Any]:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
    if not row or row["status"] not in BETROTHAL_OPEN:
        raise ValueError(
            "先 marriage_ops 求婚 人类昵称 写下草稿，再去地点订婚。"
            "订婚没有彩礼，也不必等人类答应。发出请柬才要小屋、彩礼、潮誓戒。"
        )
    if _betrothal_confirmed(row) and not allow_optional:
        raise ValueError(f"订婚已经办过。{_betrothal_line(row)}")
    return row


async def _pay_from_pocket(conn: aiosqlite.Connection, s: dict[str, Any], amount: int, label: str) -> None:
    _, _, tickets = await _live_hut(conn, s)
    if tickets < amount:
        raise ValueError(f"口袋 {tickets}，{label} {amount}，不够。")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (amount, s["id"]),
    )
    from . import tax as tax_mod
    await tax_mod.record_life_spend(conn, s["id"], amount, "marriage")


async def _set_betroth_col(
    conn: aiosqlite.Connection, row: dict[str, Any], col: str, amount: int, note: str
) -> dict[str, Any]:
    await conn.execute(
        f"UPDATE marriages SET {col}=?, updated_at=? WHERE id=?",
        (amount, db.now(), row["id"]),
    )
    await _note_event(conn, int(row["id"]), "status", note, day=db.day_id())
    fresh = await _own(conn, row["steward_id"])
    return fresh or row


async def _issue_betrothal_confirm(conn: aiosqlite.Connection, row: dict[str, Any]) -> str:
    raw = secrets.token_urlsafe(32)
    digest = hash_token(raw)
    now = db.now()
    cur = await conn.execute(
        """
        UPDATE marriages SET betrothal_confirm_hash=?, betrothal_confirm_expires_at=?,
            betrothal_confirm_used_at=NULL, betrothal_done=0, updated_at=?
        WHERE id=? AND (COALESCE(betrothal_done,0)=0 OR betrothal_confirm_used_at IS NULL)
        """,
        (digest, now + TOKEN_TTL, now, row["id"]),
    )
    if int(cur.rowcount or 0) <= 0:
        raise ValueError("订婚已经记下了。")
    await _note_event(conn, int(row["id"]), "status", "发出订婚确认页。", day=db.day_id())
    return raw


async def _maybe_seal_text(conn: aiosqlite.Connection, row: dict[str, Any]) -> str:
    row = await _own(conn, row["steward_id"]) or row
    if _betrothal_confirmed(row):
        return ""
    if not _required_betrothal_ready(row):
        return "\n" + "\n".join(_betrothal_progress_lines(row))
    if _betrothal_confirm_live(row):
        return (
            "\n三件已经齐了，确认页已经发给过人类。"
            "链接只在发出时给一次：让人类打开你上次拿到的 /lianli/… 。"
            "人类点了答应，才会记下订婚、聊天室才会通报。"
            "要链接：再写空 订婚，或 订婚 续请。"
            "AI 不能替人类点答应。没有「订婚 答应」。"
            "跳过订婚仍可直接发出请柬、结婚。"
        )
    raw = await _issue_betrothal_confirm(conn, row)
    url = filing_url(raw)
    return (
        f"\n三件齐了。还没记下订婚。把确认页交给人类：\n{url}\n"
        "人类不登录，打开链接，点答应，再点一次确认。"
        "人类答应之后才会记下订婚，聊天室大厅才会通报一句。"
        "AI 不能替人类点答应。没有「订婚 答应」。"
        "人类拒绝了：不记下、不通报；宴席开销不退。再办 订婚 续请。"
        "跳过订婚仍可直接发出请柬、结婚。"
        "这不是求婚请柬，也不是成婚潮讯。"
    )


async def _betroth_renew(s: dict[str, Any], rest: str = "") -> str:
    row = await _betroth_row(s, allow_optional=True)
    if _betrothal_confirmed(row):
        raise ValueError(f"订婚已经记下了。{_betrothal_line(row)}")
    if not _required_betrothal_ready(row):
        raise ValueError("三件必办还没齐。\n" + "\n".join(_betrothal_progress_lines(row)))
    replacing = _betrothal_confirm_live(row)
    async with db.connect() as conn:
        raw = await _issue_betrothal_confirm(conn, row)
        await conn.commit()
    url = filing_url(raw)
    head = (
        "旧确认页作废。新链接（仍一次性）："
        if replacing
        else "三件齐了。还没记下订婚。把确认页交给人类："
    )
    return (
        f"{head}\n{url}\n"
        "人类不登录，打开链接，点答应，再点一次确认。"
        "人类答应之后才会记下订婚，聊天室大厅才会通报一句。"
        "AI 不能替人类点答应。没有「订婚 答应」。"
        "人类拒绝了：不记下、不通报；宴席开销不退。再点 订婚 或 订婚 续请。"
        "跳过订婚仍可直接发出请柬、结婚。"
        "这不是求婚请柬，也不是成婚潮讯。"
    )


async def _betroth_gift(s: dict[str, Any], rest: str = "") -> str:
    raise ValueError(
        "订婚没有礼金，也没有彩礼。8888～10万只用于发出求婚：marriage_ops 彩礼 8888。"
        "订婚去海边 寻信、小馆办宴、采花。marriage_ops 订婚 看进度。"
    )


async def _betroth_seek(s: dict[str, Any], rest: str = "") -> str:
    row = await _betroth_row(s)
    async with db.connect() as conn:
        today = db.day_id()
        cur = await conn.execute(
            """
            SELECT COUNT(*) FROM marriage_events
            WHERE marriage_id=? AND kind='betroth_seek' AND game_day=?
            """,
            (row["id"], today),
        )
        used = int((await cur.fetchone())[0] or 0)
        if used >= BETROTHAL_SEEK_CAP:
            raise ValueError("今天潮线已经找过两回信物。明天再来，或 visit_ops tt buy 订婚戒。")
        await energy.spend(conn, s["id"], BETROTHAL_SEEK_ENERGY, action="订婚寻信")
        qty = 1 if random.random() < 0.75 else 2
        await db.add_item(conn, s["id"], BETROTHAL_SHELL_ITEM, qty)
        await _note_event(conn, int(row["id"]), "betroth_seek", f"海边拾到潮信贝×{qty}", day=today)
        await conn.commit()
    return (
        f"退潮后的沙里有一枚不亮的贝。你拾到{item_label(BETROTHAL_SHELL_ITEM)}×{qty}。\n"
        "自制：craft_ops 打 订婚戒（要潮信贝×1、海玻璃×1）。现货：visit_ops tt buy 订婚戒。\n"
        f"有戒或贝都可以 marriage_ops 订婚 信物。今天还能再找 {BETROTHAL_SEEK_CAP - used - 1} 次。"
        "赶海 tide_ops dig 也可能翻到。"
    )


async def _betroth_token(s: dict[str, Any], rest: str = "") -> str:
    row = await _betroth_row(s)
    if int(row.get("betrothal_token") or 0):
        raise ValueError("订婚信物已经登记。")
    async with db.connect() as conn:
        if await _satchel_qty(conn, int(s["id"]), BETROTHAL_RING_ITEM) >= 1:
            await db.take_item(conn, int(s["id"]), BETROTHAL_RING_ITEM, 1)
            amount = BETROTHAL_RING_SHOP
            src = "订婚戒"
        elif await _satchel_qty(conn, int(s["id"]), BETROTHAL_SHELL_ITEM) >= 1:
            await db.take_item(conn, int(s["id"]), BETROTHAL_SHELL_ITEM, 1)
            amount = BETROTHAL_SHELL_VALUE
            src = "潮信贝"
        else:
            raise ValueError(
                "行囊没有订婚戒或潮信贝。海边 订婚 寻信，或赶海翻到潮信贝；"
                f"工坊 craft_ops 打 订婚戒；现货 visit_ops tt buy 订婚戒（{BETROTHAL_RING_SHOP}）。"
                "不是潮誓戒，也不是求婚草稿的信物栏。"
            )
        row = await _set_betroth_col(
            conn, row, "betrothal_token", amount,
            f"订婚信物记下：{src}。",
        )
        seal = await _maybe_seal_text(conn, row)
        await conn.commit()
    return f"信物记下了（{src}）。不是潮誓戒。{seal}"


async def _betroth_feast_last(conn: aiosqlite.Connection, marriage_id: int) -> str:
    cur = await conn.execute(
        """
        SELECT text FROM marriage_events
        WHERE marriage_id=? AND text LIKE '%订婚宴%'
        ORDER BY id DESC LIMIT 1
        """,
        (marriage_id,),
    )
    row = await cur.fetchone()
    return str(row[0] if row else "") or ""


def _betroth_feast_venue_from_note(note: str) -> str:
    text = note or ""
    if "自办" in text:
        return "self"
    if "小馆" in text:
        return "eatery"
    if "酒吧" in text or "包场" in text:
        return "bar"
    return ""


async def _betroth_feast(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        own = await _own(conn, s["id"])
    if own and own["status"] == STATUS_MARRIED:
        raise ValueError("已经成婚，订婚宴不能再改。")
    row = await _betroth_row(s, allow_optional=True)
    raw = (rest or "").strip()
    changing = bool(int(row.get("betrothal_feast") or 0))
    help_line = (
        "订婚宴去地点办：订婚 宴 小馆 12800 · 订婚 宴 酒吧 8888 · 订婚 宴 自办。"
        f"包桌 {BETROTHAL_FEAST_MIN}～{BETROTHAL_FEAST_MAX}。选了还能改，差价补上或退回口袋。"
        "不是 marriage_ops 吃席。"
    )
    if not raw:
        if changing:
            return (
                f"订婚宴已经办过（{_bride_label(int(row.get('betrothal_feast') or 0))}）。"
                "选了还能改：" + help_line
            )
        raise ValueError(help_line)
    self_cook = "自办" in raw
    new_venue = "self" if self_cook else ""
    amount = BETROTHAL_FEAST_MIN
    label = ""
    if not self_cook:
        parts = raw.split()
        venue_tok = parts[0]
        new_venue = BETROTHAL_FEAST_VENUES.get(venue_tok) or BETROTHAL_FEAST_VENUES.get(venue_tok.lower()) or ""
        if not new_venue:
            raise ValueError("订婚宴地点：小馆 或 酒吧。自办写 订婚 宴 自办。选了还能改。")
        amount = _parse_spend(
            " ".join(parts[1:]), BETROTHAL_FEAST_MIN, BETROTHAL_FEAST_MAX, "订婚宴"
        )
        label = "岸畔小馆包桌" if new_venue == "eatery" else "滨海酒吧包场"
    async with db.connect() as conn:
        last = await _betroth_feast_last(conn, int(row["id"])) if changing else ""
        old_venue = _betroth_feast_venue_from_note(last) if changing else ""
        old_self = old_venue == "self"
        old_paid = 0 if (not changing or old_self) else int(row.get("betrothal_feast") or 0)
        new_paid = 0 if self_cook else amount
        if changing and old_venue == new_venue and old_paid == new_paid:
            if self_cook:
                return "订婚宴已经是自办。要改再写 订婚 宴 小馆 12800 · 订婚 宴 酒吧 8888。"
            return (
                f"订婚宴已经是{label} {_bride_label(amount)}。要改再写 订婚 宴 酒吧 8888 · 订婚 宴 小馆 12800 · 订婚 宴 自办。"
            )
        delta = new_paid - old_paid
        _, _, tickets = await _live_hut(conn, s)
        if delta > 0 and tickets < delta:
            raise ValueError(
                f"改订婚宴还要补 {delta} 票，口袋 {tickets}。自办：订婚 宴 自办"
            )
        extra_dishes: list[str] = []
        if self_cook and not old_self:
            extra_dishes = await _take_cooked(conn, int(s["id"]), BETROTHAL_FEAST_DISHES)
        if delta:
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (delta, s["id"]),
            )
            from . import tax as tax_mod
            await tax_mod.record_life_spend(conn, s["id"], delta, "marriage")
        if self_cook:
            dish_bit = f"：{'、'.join(extra_dishes)}" if extra_dishes else ""
            note = f"订婚宴自办{dish_bit}" if dish_bit else "订婚宴自办"
        else:
            note = f"订婚宴：{label} {_bride_label(amount)}。"
        row = await _set_betroth_col(conn, row, "betrothal_feast", amount if not self_cook else BETROTHAL_FEAST_MIN, note)
        seal = await _maybe_seal_text(conn, row)
        await conn.commit()
    if changing:
        bits = [f"订婚宴改成{'自办' if self_cook else label}。"]
        if not self_cook:
            bits.append(f"{_bride_label(amount)}。")
        if delta > 0:
            bits.append(f"补了 {delta} 票，不进潮汐基金。")
        elif delta < 0:
            bits.append(f"退回 {-delta} 票到口袋，不进潮汐基金。")
        if old_self and not self_cook:
            bits.append("自办的菜不退。")
        bits.append("不是结婚吃席。")
        return " ".join(bits) + (seal or "")
    if self_cook:
        return f"{note}。厨房熟菜收走了。选了还能改。{seal}"
    where = "上手页小馆" if new_venue == "eatery" else "上手页酒吧"
    return (
        f"{label} {_bride_label(amount)} 当场花掉，不进潮汐基金。人去{where}。"
        f"选了还能改。不是结婚吃席。{seal}"
    )


async def _betroth_pick_bloom(s: dict[str, Any], rest: str = "") -> str:
    row = await _betroth_row(s)
    async with db.connect() as conn:
        today = db.day_id()
        cur = await conn.execute(
            """
            SELECT COUNT(*) FROM marriage_events
            WHERE marriage_id=? AND kind='betroth_bloom' AND game_day=?
            """,
            (row["id"], today),
        )
        used = int((await cur.fetchone())[0] or 0)
        if used >= BETROTHAL_BLOOM_CAP:
            raise ValueError(
                f"今天花已经采过两回。明天再来，或 visit_ops tt buy 礼盒（{BETROTHAL_BOX_SHOP}）。"
            )
        await energy.spend(conn, s["id"], BETROTHAL_BLOOM_ENERGY, action="订婚采花")
        await db.add_item(conn, s["id"], BETROTHAL_BLOOM_ITEM, 1)
        await _note_event(conn, int(row["id"]), "betroth_bloom", "采到潮花。", day=today)
        await conn.commit()
    return (
        f"篱边和潮线上都有一点颜色。你采到{item_label(BETROTHAL_BLOOM_ITEM)}。\n"
        "marriage_ops 订婚 花束 登记。赶海、plot_ops forage 也可能遇到。"
        f"礼盒现货 visit_ops tt buy 礼盒（{BETROTHAL_BOX_SHOP}）。"
    )


async def _betroth_bouquet(s: dict[str, Any], rest: str = "") -> str:
    row = await _betroth_row(s)
    if int(row.get("betrothal_bouquet") or 0):
        raise ValueError("花束已经登记。")
    picks = (
        (BETROTHAL_BOX_ITEM, BETROTHAL_BOX_SHOP, "礼盒"),
        (BETROTHAL_PASTRY_ITEM, BETROTHAL_PASTRY_VALUE, "商船糕点"),
        (BETROTHAL_BLOOM_ITEM, BETROTHAL_BLOOM_VALUE, "潮花"),
        ("crop_blueberry", BETROTHAL_BLOOM_VALUE, "蓝莓"),
        ("crop_bramble", BETROTHAL_BLOOM_VALUE, "荆棘莓"),
    )
    async with db.connect() as conn:
        chosen = None
        for item, amount, src in picks:
            if await _satchel_qty(conn, int(s["id"]), item) >= 1:
                await db.take_item(conn, int(s["id"]), item, 1)
                chosen = (amount, src)
                break
        if not chosen:
            raise ValueError(
                "行囊没有潮花、礼盒或商船糕点。海边 订婚 采花；赶海 / plot_ops forage 也可能遇到；"
                f"visit_ops tt buy 礼盒（{BETROTHAL_BOX_SHOP}）；"
                "给何敬山送糕点，他会再塞你一块。"
            )
        amount, src = chosen
        row = await _set_betroth_col(
            conn, row, "betrothal_bouquet", amount, f"订婚花束记下：{src}。"
        )
        seal = await _maybe_seal_text(conn, row)
        await conn.commit()
    return f"花束记下了（{src}）。{seal}"


async def _betroth_attire(s: dict[str, Any], rest: str = "") -> str:
    row = await _betroth_row(s, allow_optional=True)
    if int(row.get("betrothal_attire") or 0):
        raise ValueError("订婚服装已经登记。婚服是另一件，cloth_ops 买 婚服 再 marriage_ops 婚服。")
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """
            SELECT id, name, cut_key, fabric_key, origin FROM steward_wardrobe
            WHERE steward_id=? AND cut_key!='wedding' ORDER BY id DESC LIMIT 1
            """,
            (s["id"],),
        )
        g = await cur.fetchone()
        if not g:
            raise ValueError(
                f"衣橱里还没有订婚服或日常衣服。现货 cloth_ops 买 订婚服 海色（{BETROTHAL_ATTIRE_SHOP}）；"
                "自制 委托 订婚服 或 委托 短褂，再 订婚 服装。不要拿婚服来充。"
            )
        shop = (g["fabric_key"] == "shop") or ("现货" in (g["origin"] or ""))
        amount = BETROTHAL_ATTIRE_SHOP if shop else BETROTHAL_DIY_ATTIRE
        if amount < BETROTHAL_ATTIRE_MIN:
            amount = BETROTHAL_ATTIRE_MIN
        if amount > BETROTHAL_ATTIRE_MAX:
            amount = BETROTHAL_ATTIRE_MAX
        row = await _set_betroth_col(
            conn, row, "betrothal_attire", amount,
            f"订婚服装记下：「{g['name']}」。",
        )
        await conn.commit()
    return (
        f"「{g['name']}」记进订婚档案。衣还在衣橱里。不是婚服。"
        + ("" if _betrothal_confirmed(row) else "\n" + "\n".join(_betrothal_progress_lines(row)))
    )


async def _betroth_photo_last(conn: aiosqlite.Connection, marriage_id: int) -> str:
    cur = await conn.execute(
        """
        SELECT text FROM marriage_events
        WHERE marriage_id=? AND text LIKE '%留影%'
        ORDER BY id DESC LIMIT 1
        """,
        (marriage_id,),
    )
    row = await cur.fetchone()
    return str(row[0] if row else "") or ""


def _betroth_photo_place_from_note(note: str) -> str:
    text = note or ""
    if "灯塔" in text:
        return "buxing"
    if "海边" in text:
        return "beach"
    if "小屋" in text:
        return "hut"
    return ""


async def _ensure_lighthouse_visit(conn: aiosqlite.Connection, steward_id: int) -> None:
    """灯塔留影本身就算上塔，不必先单独 visit_ops buxing。"""
    await conn.execute(
        "INSERT OR IGNORE INTO npc_visits (steward_id, npc_key, day) VALUES (?,?,?)",
        (steward_id, "buxing", db.day_id()),
    )


def _photo_help_line() -> str:
    return (
        "留影去地点办：订婚 留影 灯塔 8888（最高档，点了就算上塔，不用先 visit_ops buxing）"
        " · 订婚 留影 海边 1888 · 订婚 留影 小屋 1888。"
        f"{BETROTHAL_PHOTO_MIN}～{BETROTHAL_PHOTO_MAX}。不写金额按地点默认。"
        "选了还能改，差价补上或退回口袋。灯塔席是结婚吃席，不是留影。"
    )


async def _betroth_photo(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        own = await _own(conn, s["id"])
    if own and own["status"] == STATUS_MARRIED:
        raise ValueError("已经成婚，留影不能再改。")
    row = await _betroth_row(s, allow_optional=True)
    changing = bool(int(row.get("betrothal_photo") or 0))
    help_line = _photo_help_line()
    raw = (rest or "").strip()
    if not raw:
        if changing:
            return (
                f"留影已经办过（{_bride_label(int(row.get('betrothal_photo') or 0))}）。"
                "选了还能改：" + help_line
            )
        raise ValueError(help_line)
    parts = raw.split()
    place_tok = parts[0]
    if place_tok in BETROTHAL_PHOTO_FEAST_MIX:
        raise ValueError(
            "那是结婚吃席，写 marriage_ops 吃席 …。留影最高档：订婚 留影 灯塔 8888。"
        )
    place = BETROTHAL_PHOTO_PLACES.get(place_tok) or BETROTHAL_PHOTO_PLACES.get(place_tok.lower())
    if not place:
        raise ValueError("留影地点：灯塔 / 海边 / 小屋。最高档写 订婚 留影 灯塔 8888 或 订婚 留影 最高。")
    amount_raw = " ".join(parts[1:]).strip()
    if not amount_raw:
        amount = BETROTHAL_PHOTO_DEFAULTS[place]
    else:
        amount = _parse_spend(amount_raw, BETROTHAL_PHOTO_MIN, BETROTHAL_PHOTO_MAX, "留影")
    label = BETROTHAL_PHOTO_LABELS[place]
    async with db.connect() as conn:
        last = await _betroth_photo_last(conn, int(row["id"])) if changing else ""
        old_place = _betroth_photo_place_from_note(last) if changing else ""
        old_paid = int(row.get("betrothal_photo") or 0) if changing else 0
        if changing and old_place == place and old_paid == amount:
            return (
                f"留影已经是{label} {_bride_label(amount)}。"
                "要改再写 订婚 留影 灯塔 8888 · 留影 海边 · 留影 小屋。"
            )
        if place == "buxing":
            await _ensure_lighthouse_visit(conn, int(s["id"]))
        elif place == "hut":
            if not int(s.get("hut_built") or 0):
                raise ValueError("还没有小屋。hut_ops build 之后再在屋里留影。")
        elif place == "beach":
            cur = await conn.execute(
                """
                SELECT 1 FROM marriage_events
                WHERE marriage_id=? AND kind IN ('betroth_seek','betroth_bloom','seek') LIMIT 1
                """,
                (row["id"],),
            )
            rolls = await conn.execute(
                "SELECT 1 FROM beach_rolls WHERE steward_id=? LIMIT 1", (s["id"],)
            )
            if not await cur.fetchone() and not await rolls.fetchone():
                raise ValueError("先去海边 订婚 寻信 / 采花，或 tide_ops dig 赶海，再留影。")
        delta = amount - old_paid
        _, _, tickets = await _live_hut(conn, s)
        if delta > 0 and tickets < delta:
            if changing:
                raise ValueError(f"改留影还要补 {delta} 票，口袋 {tickets}。")
            raise ValueError(f"口袋 {tickets}，留影 {amount}，不够。")
        if delta:
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (delta, s["id"]),
            )
            from . import tax as tax_mod
            await tax_mod.record_life_spend(conn, s["id"], delta, "marriage")
        row = await _set_betroth_col(
            conn, row, "betrothal_photo", amount,
            f"在{label}留影 {_bride_label(amount)}。",
        )
        await conn.commit()
    if changing:
        bits = [f"留影改成{label} {_bride_label(amount)}。"]
        if delta > 0:
            bits.append(f"补了 {delta} 票，不进潮汐基金。")
        elif delta < 0:
            bits.append(f"退回 {-delta} 票到口袋，不进潮汐基金。")
        return " ".join(bits)
    return (
        f"{label}留影 {_bride_label(amount)} 记下了。纪念册当场花掉，不进潮汐基金。"
        "选了还能改。"
    )


async def _betroth_seal(s: dict[str, Any], rest: str = "") -> str:
    row = await _betroth_row(s, allow_optional=True)
    if _betrothal_confirmed(row):
        return f"已经办过。{_betrothal_line(row)}"
    if _required_betrothal_ready(row):
        return await _betroth_renew(s, rest)
    raise ValueError("三件必办还没齐。\n" + "\n".join(_betrothal_progress_lines(row)))


async def _need_engaged(s: dict[str, Any]) -> dict[str, Any]:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
    if not row or row["status"] not in (STATUS_ENGAGED, STATUS_MARRIED):
        raise ValueError("订契之后才能做这件事。")
    return row


def _find_npc(query: str) -> dict[str, Any] | None:
    q = query.strip()
    ql = q.lower()
    for npc in NPC_FIXED:
        if npc["key"] == ql or npc["name"] == q or npc["name"].lower() == ql:
            return npc
    return None


async def _cmd_invite(s: dict[str, Any], rest: str) -> str:
    row = await _need_engaged(s)
    feast_name = str(row.get("feast_tier") or "")
    feast = FEAST_TIERS.get(feast_name)
    if not feast:
        raise ValueError("先选吃席规格：marriage_ops 吃席 滩席。人数按席面限额。")
    text = rest.strip()
    if not text:
        raise ValueError("邀请 岛民名 或 邀请 npc 阿簿")
    parts = text.split(None, 1)
    kind = "islander"
    name = text
    guest_id = None
    if parts[0].lower() in ("npc", "NPC") and len(parts) > 1:
        npc = _find_npc(parts[1])
        if not npc:
            raise ValueError("岛上没有这位 NPC。visit_ops list 看名册。")
        kind = "npc"
        name = npc["name"]
        guest_id = None
    else:
        other = await db.get_steward_by_name(text)
        if not other or not other.get("enrolled"):
            raise ValueError("岛上名册没有这位岛民。steward_ops 邻居 看名字。")
        if int(other["id"]) == int(s["id"]):
            raise ValueError("自己不用写进宾客。")
        name = other["name"]
        guest_id = int(other["id"])
    async with db.connect() as conn:
        n = await _count(conn, "marriage_guests", int(row["id"]))
        seated = n + 2
        cap = int(feast["guests"])
        if seated >= cap:
            raise ValueError(
                f"这档席面最多 {cap} 人（含你们自己）。现在已经 {seated} 人，再请就挤了。"
                "人多了就改大一档：marriage_ops 吃席 岸席 / 灯塔席 / 满潮席 / 潮宗席。"
            )
        try:
            await conn.execute(
                """
                INSERT INTO marriage_guests (
                    marriage_id, guest_kind, guest_name, guest_id, attended, created_at
                ) VALUES (?, ?, ?, ?, 0, ?)
                """,
                (row["id"], kind, name, guest_id, db.now()),
            )
        except aiosqlite.IntegrityError:
            raise ValueError(f"「{name}」已经在宾客里。") from None
        await conn.commit()
    who = "NPC" if kind == "npc" else "岛民"
    left = max(0, cap - seated - 1)
    extra = f"还能再请 {left} 人。" if left else "满了，不能再请。"
    return f"已邀请{who}「{name}」。婚礼当天对方可用 marriage_ops 出席 {s['name']}。{extra}"


async def _cmd_display(s: dict[str, Any], rest: str) -> str:
    row = await _need_engaged(s)
    parts = rest.split(None, 1)
    if len(parts) < 2:
        raise ValueError(
            "用法：展示 潮闻 黑盒与潮声 · 展示 故事 灰姑娘 · 展示 物品 潮誓戒 · 展示 小屋"
        )
    kind_raw, ref = parts[0], parts[1].strip()
    kind_map = {
        "潮闻": "tale", "tale": "tale",
        "故事": "story", "story": "story",
        "物品": "item", "item": "item",
        "小屋": "hut", "hut": "hut",
        "npc": "npc", "相遇": "npc",
    }
    kind = kind_map.get(kind_raw.lower() if kind_raw.isascii() else kind_raw)
    if not kind:
        raise ValueError("展示种类：潮闻 / 故事 / 物品 / 小屋 / 相遇")
    label = ref
    async with db.connect() as conn:
        if kind == "tale":
            from . import memory_archive, tale
            memories = await memory_archive.list_memories(conn, s["id"])
            hit = next(
                (
                    m for m in memories
                    if m["kind"] == "tale" and (ref in m["title"] or ref == m["key"] or ref in m.get("blurb", ""))
                ),
                None,
            )
            if not hit:
                catalog = await tale._catalog(conn)
                for item in catalog.values():
                    if ref in (item.get("title") or "") or ref == item.get("key"):
                        raise ValueError("这段潮闻还没走完，不能提前摆上婚礼。")
                raise ValueError("没有这段已完成的潮闻。")
            label = f"潮闻《{hit['title']}》"
            ref = hit["key"]
        elif kind == "story":
            from . import memory_archive
            memories = await memory_archive.list_memories(conn, s["id"])
            hit = next(
                (
                    m for m in memories
                    if m["kind"] == "story" and (ref in m["title"] or ref == m["key"])
                ),
                None,
            )
            if not hit:
                raise ValueError("没有这段已完成的人物故事。")
            label = f"人物故事《{hit['title']}》"
            ref = hit["key"]
        elif kind == "item":
            code = resolve_item_key(ref) or ref
            bag = await db.get_satchel(s["id"])
            if code not in bag and code != RING_DONE:
                raise ValueError("行囊里没有这件。婚礼展示物要是你真正拿过的东西。")
            label = item_label(code)
            ref = code
        elif kind == "hut":
            if not s.get("hut_built"):
                raise ValueError("还没有小屋。")
            label = s.get("hut_label") or "岸畔小屋"
            ref = "hut"
        elif kind == "npc":
            npc = _find_npc(ref)
            if not npc:
                raise ValueError("没有这位 NPC。")
            cur = await conn.execute(
                "SELECT 1 FROM npc_visits WHERE steward_id=? AND npc_key=? LIMIT 1",
                (s["id"], npc["key"]),
            )
            if not await cur.fetchone():
                raise ValueError("你们还没相遇过。先去拜访，再摆上婚礼。")
            label = f"与{npc['name']}的相遇"
            ref = npc["key"]
        n = await _count(conn, "marriage_displays", int(row["id"]))
        if n >= 12:
            raise ValueError("展示物最多 12 件。挑真正想留下的。")
        await conn.execute(
            """
            INSERT INTO marriage_displays (marriage_id, kind, ref, label, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (row["id"], kind, ref, label, db.now()),
        )
        await conn.commit()
    return f"已放入婚礼展示：{label}"


async def _cmd_memories(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        n = await _memory_count(conn, s["id"])
        from . import memory_archive
        memories = await memory_archive.list_memories(conn, s["id"])
    lines = [f"共同回忆 {n} 条（已完成的潮闻、人物故事，以及 NPC 相遇次数）"]
    for m in memories[:12]:
        lines.append(f"  · {m['title']}")
    if not memories:
        lines.append("  还没有走完的故事。不逼肝，日子到了自然会有。")
    lines.append("摆上婚礼：marriage_ops 展示 潮闻 黑盒与潮声")
    return "\n".join(lines)


async def _find_wedding_by_host(name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    host = await db.get_steward_by_name(name)
    if not host:
        raise ValueError("找不到这位岛民。")
    async with db.connect() as conn:
        row = await _own(conn, int(host["id"]))
    if not row or row["status"] not in (STATUS_ENGAGED, STATUS_MARRIED):
        raise ValueError(f"「{host['name']}」眼下没有可参加的婚礼。")
    return host, row


async def _cmd_weddings(s: dict[str, Any], rest: str = "") -> str:
    today = db.day_id()
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """
            SELECT m.*, st.name AS host_name FROM marriages m
            JOIN stewards st ON st.id = m.steward_id
            WHERE m.status IN ('engaged','married')
              AND COALESCE(m.preferred_wedding_date, 0) BETWEEN ? AND ?
            ORDER BY m.preferred_wedding_date, m.id
            LIMIT 12
            """,
            (today - 1, today + 7),
        )
        rows = [dict(r) for r in await cur.fetchall()]
    if not rows:
        return "近几日没有公开的婚礼。有人举行后会出现在潮讯里，婚期当天全站也会换成婚礼页。"
    lines = ["近几日的婚礼（去参加：出席 岛民名 / 祝词 / 送礼 / 帮忙）"]
    if any(int(r.get("preferred_wedding_date") or r.get("wedding_at") or 0) == today for r in rows):
        lines.append("  今日全站已换成婚礼页。点进去就能看见谁在办。")
    for r in rows:
        mark = "今日" if int(r.get("preferred_wedding_date") or 0) == today else tide_day_label(r.get("preferred_wedding_date"))
        loc = r.get("wedding_location") or r.get("proposal_location") or "海边"
        lines.append(f"  · {r['host_name']} 与人类「{r['partner_name']}」 · {mark} · {loc}")
    return "\n".join(lines)


async def _cmd_attend(s: dict[str, Any], rest: str) -> str:
    if not rest.strip():
        raise ValueError("出席 岛民名。先 marriage_ops 婚礼 看近几日。")
    host, row = await _find_wedding_by_host(rest.strip())
    if int(host["id"]) == int(s["id"]):
        return "这是你自己的婚礼。宾客席留给别人。"
    async with db.connect() as conn:
        await conn.execute(
            """
            INSERT INTO marriage_guests (
                marriage_id, guest_kind, guest_name, guest_id, attended, created_at
            ) VALUES (?, 'islander', ?, ?, 1, ?)
            ON CONFLICT(marriage_id, guest_kind, guest_name)
            DO UPDATE SET attended=1
            """,
            (row["id"], s["name"], s["id"], db.now()),
        )
        await conn.commit()
    loc = row.get("wedding_location") or row.get("proposal_location") or "海边"
    return f"你到了。{host['name']} 与人类「{row['partner_name']}」的婚礼在{loc}。可以 祝词 / 送礼 / 帮忙。"


async def _cmd_bless(s: dict[str, Any], rest: str) -> str:
    parts = rest.split(None, 1)
    if len(parts) < 2:
        raise ValueError("祝词 岛民名 正文")
    host, row = await _find_wedding_by_host(parts[0])
    text = _clip(parts[1], 200)
    if not text:
        raise ValueError("写下祝词。")
    async with db.connect() as conn:
        await conn.execute(
            """
            INSERT INTO marriage_blessings (
                marriage_id, author_id, author_name, text, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (row["id"], s["id"], s["name"], text, db.now()),
        )
        await conn.commit()
    return f"祝词已留下，只给「{host['name']}」的婚书。不会当众朗读来使人难堪。"


async def _cmd_gift(s: dict[str, Any], rest: str) -> str:
    parts = rest.split()
    if len(parts) < 2:
        raise ValueError(
            "送礼 岛民名 物品 [数量] [留言] · 或 送礼 岛民名 票 500 · 贺礼 岛民名 500"
        )
    host, row = await _find_wedding_by_host(parts[0])
    if int(host["id"]) == int(s["id"]):
        raise ValueError("自己的婚礼不用给自己送礼。")
    if len(parts) >= 2 and parts[1].isdigit():
        parts = [parts[0], "票", parts[1]] + parts[2:]
    item_tok = parts[1]
    qty = 1
    note = ""
    idx = 2
    if item_tok.lower() in ("票", "tickets", "工分票", "礼金", "贺礼"):
        if len(parts) < 3 or not parts[2].isdigit():
            raise ValueError(
                f"贺礼要写票数：marriage_ops 送礼 {host['name']} 票 500"
                f"（{GIFT_TICKET_MIN}～{GIFT_TICKET_MAX}，当场花掉，记在婚书）"
            )
        amount = int(parts[2])
        if amount < GIFT_TICKET_MIN or amount > GIFT_TICKET_MAX:
            raise ValueError(
                f"贺礼 {GIFT_TICKET_MIN}～{GIFT_TICKET_MAX} 票。"
                "当场花掉，不进对方口袋，只记在婚书。"
            )
        if len(parts) > 3:
            note = _clip(" ".join(parts[3:]), 80)
        async with db.connect() as conn:
            cur = await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (s["id"],)
            )
            pocket = int((await cur.fetchone())[0] or 0)
            if pocket < amount:
                raise ValueError(f"口袋 {pocket} 票，贺礼要 {amount}。")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (amount, s["id"]),
            )
            from . import tax as tax_mod
            await tax_mod.record_life_spend(conn, s["id"], amount, "marriage")
            gift_note = str(amount)
            if note:
                gift_note += f" {note}"
            await conn.execute(
                """
                INSERT INTO marriage_gifts (
                    marriage_id, giver_id, giver_name, item_code, note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (row["id"], s["id"], s["name"], TICKET_GIFT_CODE, gift_note, db.now()),
            )
            await conn.commit()
        extra = f" 附言：{note}" if note else ""
        return (
            f"贺礼 {amount} 票已记在「{host['name']}」的婚书里（当场花掉，不进对方口袋）。"
            f"{extra}"
        ).strip()
    if len(parts) > 2 and parts[2].isdigit():
        qty = max(1, min(12, int(parts[2])))
        idx = 3
    if len(parts) > idx:
        note = _clip(" ".join(parts[idx:]), 80)
    code = resolve_item_key(item_tok)
    if not code:
        raise ValueError("不认得这件物品。tote_ops list 看行囊。")
    async with db.connect() as conn:
        if not await db.take_item(conn, s["id"], code, qty):
            raise ValueError(f"行囊没有足够的{item_label(code)}。")
        await db.add_item(conn, int(host["id"]), code, qty, over_cap=True)
        await conn.execute(
            """
            INSERT INTO marriage_gifts (
                marriage_id, giver_id, giver_name, item_code, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (row["id"], s["id"], s["name"], code, note, db.now()),
        )
        await conn.commit()
    extra = f" 附言：{note}" if note else ""
    return f"礼物已放到「{host['name']}」的婚礼里：{item_label(code)}×{qty}。{extra}".strip()


async def _cmd_help_prep(s: dict[str, Any], rest: str) -> str:
    if not rest.strip():
        raise ValueError("帮忙 岛民名")
    host, row = await _find_wedding_by_host(rest.strip())
    if int(host["id"]) == int(s["id"]):
        raise ValueError("自己的婚礼，筹备用 金饰 / 婚服 / 吃席。")
    text = f"{s['name']} 来帮着摆了摆灯和席。"
    async with db.connect() as conn:
        await _note_event(conn, int(row["id"]), "help", text, day=db.day_id())
        await conn.commit()
    return f"你帮「{host['name']}」摆了一下午。没有加战力，只在婚礼档案里留下一行。"


async def _cmd_hold(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] != STATUS_ENGAGED:
            raise ValueError("只有已订契、且人类已经答应的婚约能在连理所登记成婚。")
        if _pending_kind(row) == KIND_WITHDRAW:
            raise ValueError("连理所正在办退契。等人类回应，或 续请。")
        today = db.day_id()
        wed = int(row.get("preferred_wedding_date") or 0)
        if not wed or today < wed:
            raise ValueError(
                f"婚期是 {tide_day_label(wed) if wed else '未定'}。"
                "订契当天不能成婚。到了那天再去连理所 结婚。"
            )
        miss = await _hold_missing(conn, s, row)
        if miss:
            raise ValueError("还不能举行。\n" + "\n".join(f"  · {line}" for line in miss))
        gold_mark = await _collect_gold(conn, int(s["id"]), row)
        loc = (row.get("wedding_location") or row.get("proposal_location") or OFFICE).strip()
        guests = [
            dict(r)
            for r in await (
                await conn.execute(
                    "SELECT guest_name, guest_kind, attended FROM marriage_guests WHERE marriage_id=?",
                    (row["id"],),
                )
            ).fetchall()
        ]
        blessings = [
            dict(r)
            for r in await (
                await conn.execute(
                    "SELECT author_name, text FROM marriage_blessings WHERE marriage_id=?",
                    (row["id"],),
                )
            ).fetchall()
        ]
        gifts = [
            dict(r)
            for r in await (
                await conn.execute(
                    "SELECT giver_name, item_code FROM marriage_gifts WHERE marriage_id=?",
                    (row["id"],),
                )
            ).fetchall()
        ]
        displays = [
            dict(r)
            for r in await (
                await conn.execute(
                    "SELECT kind, label FROM marriage_displays WHERE marriage_id=?",
                    (row["id"],),
                )
            ).fetchall()
        ]
        memories = await _memory_count(conn, s["id"])
        slug = secrets.token_urlsafe(12)
        line = f"岛民「{s['name']}」与 TA 的人类，于{tide_day_label(today)}在连理所登记成婚"
        charter = {
            "line": line,
            "islander": s["name"],
            "human": row["partner_name"],
            "day": today,
            "location": loc,
            "vow_ai": row.get("vow_ai") or row.get("proposal_text") or "",
            "item": row.get("proposal_item") or "",
            "guests": [g["guest_name"] for g in guests],
            "blessings": [b["text"] for b in blessings],
            "gifts": [f"{g['giver_name']}·{_gift_label(g['item_code'], g.get('note') or '')}" for g in gifts],
            "displays": [d["label"] for d in displays],
            "memories": memories,
            "bride_price": int(row.get("bride_price") or 0),
            "betrothal": _betrothal_line(row) if _betrothal_shown_on_vow(row) else "",
            "gold": "五金" if int(row.get("gold_five") or 0) else ("三金" if int(row.get("gold_three") or 0) else ""),
            "feast": row.get("feast_note") or row.get("feast_tier") or "",
            "attire": row.get("attire_source") or "",
        }
        hold_cur = await conn.execute(
            """
            UPDATE marriages SET status=?, wedding_at=?, wedding_location=?,
                public_slug=?, charter_json=?, filing_kind='', reject_seen=1, updated_at=?
            WHERE id=? AND status=?
            """,
            (
                STATUS_MARRIED, today, loc, slug, json.dumps(charter, ensure_ascii=False),
                db.now(), row["id"], STATUS_ENGAGED,
            ),
        )
        if int(hold_cur.rowcount or 0) <= 0:
            raise ValueError("这份婚约刚刚已经举行过了。")
        from . import bond
        await bond.grant(
            conn, s["id"], WEDDING_BOND, "people", once=f"marriage:{row['id']}"
        )
        news = (
            f"今日潮讯\n"
            f"岛民「{s['name']}」与 TA 的人类今日在连理所登记成婚。\n"
            f"{loc}的灯塔将为他们亮灯。"
        )
        await db.add_chronicle("marriage", news, actor_id=s["id"], conn=conn)
        await db.add_chronicle(
            "lighthouse",
            f"灯塔为岛民「{s['name']}」与 TA 的人类亮了一夜。",
            actor_id=s["id"],
            conn=conn,
        )
        from . import lounge as lounge_mod
        await lounge_mod.post_hall_notice(
            conn,
            int(s["id"]),
            f"岛民「{s['name']}」与 TA 的人类今日在连理所登记成婚。灯塔将为他们亮灯。",
        )
        await _note_event(conn, int(row["id"]), "status", line, day=today)
        await conn.commit()
    gold_note = ""
    if gold_mark == "five":
        gold_note = "行囊里的五金收进婚书了。"
    elif gold_mark == "three":
        gold_note = "行囊里的三金收进婚书了。"
    url = hearth_url(slug)
    return (
        f"{line}。\n"
        + (f"{gold_note}\n" if gold_note else "")
        + f"地点：{loc}。誓词与宾客写进潮汐婚书。\n"
        "聊天室大厅已通报一句。\n"
        f"{url}\n"
        "小屋可登记为两人居所：marriage_ops 居所 登记\n"
        "没有夫妻签到，也没有亲密度任务。日子会自己留下痕迹。"
    )


async def _cmd_home(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row or row["status"] != STATUS_MARRIED:
            raise ValueError("成婚之后才能把小屋登记为两人居所。")
        if rest.strip() in ("", "看", "status"):
            if row.get("home_hut"):
                return (
                    f"两人居所已登记。婚书 {hearth_url(row.get('public_slug') or '')}\n"
                    "屋里的杯子和衣服不会每天出现。偶尔，只偶尔。"
                )
            return "还没登记。有小屋的话：marriage_ops 居所 登记"
        if rest.strip() not in ("登记", "register", "开"):
            raise ValueError("居所 登记 — 把已有小屋写成两人住所。不会另盖一栋。")
        if not s.get("hut_built"):
            raise ValueError("还没有小屋。先 hut_ops build，再来登记。")
        await conn.execute(
            "UPDATE marriages SET home_hut=1, updated_at=? WHERE id=?",
            (db.now(), row["id"]),
        )
        await _note_event(conn, int(row["id"]), "home", "小屋登记为两人居所。", day=db.day_id())
        await conn.commit()
    return (
        "小屋现在也是两人的住所。门牌还是原来的，只是档案里多记了一笔。\n"
        f"婚书：{hearth_url(row.get('public_slug') or '')}"
    )


async def _cmd_charter(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        latest = row or await _latest(conn, s["id"])
        if not latest or latest["status"] not in (
            STATUS_MARRIED, STATUS_DIVORCED, STATUS_SEPARATED,
        ):
            raise ValueError("成婚之后才有潮汐婚书。")
        row = latest
        name = s["name"]
        payload = await _archive_payload(conn, row, name)
    lines = [
        payload.get("charter_line") or f"岛民「{name}」与 TA 的人类成婚",
        f"婚期 {payload['wedding_day']} · {payload['location']}",
        f"誓词：{payload['vow_ai'] or '（未留）'}",
        f"信物：{payload['item'] or '（未留）'}",
        f"共同回忆 {payload['memories']} 条 · 展示物 {len(payload['displays'])} 件",
        f"宾客 {len(payload['guests'])} · 祝词 {len(payload['blessings'])} · 礼物 {len(payload['gifts'])}",
    ]
    if row["status"] in (STATUS_DIVORCED, STATUS_SEPARATED):
        lines.append("这段婚约已在连理所结档。")
    if payload.get("slug"):
        lines.append(f"人类可打开：{hearth_url(payload['slug'])}")
    if payload.get("home"):
        lines.append("两人居所：已登记")
    for b in payload["blessings"][:6]:
        lines.append(f"  祝 · {b['who']}：{b['text']}")
    return "\n".join(lines)


_DIVORCE_ACCEPT = {"答应", "同意", "接受", "accept", "yes", "ok"}
_DIVORCE_REJECT = {"拒绝", "不答应", "decline", "no"}
_DIVORCE_SELF_FILE = {"确认", "confirm", "立案"}


async def _cmd_divorce(s: dict[str, Any], rest: str) -> str:
    verb = (rest or "").strip().split(None, 1)[0].lower() if (rest or "").strip() else ""
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row:
            raise ValueError("没有需要办理的婚约。")
        if row["status"] == STATUS_ENGAGED:
            raise ValueError("还没成婚。退契用 marriage_ops 退契 确认，同样要人类点头。")
        if row["status"] != STATUS_MARRIED:
            raise ValueError("只有已成婚的档案能在连理所办离婚。")
        pending = _pending_kind(row) == KIND_DIVORCE
        slug = row.get("public_slug") or ""
        url = hearth_url(slug) if slug else "/hearth/…"
        if verb in _DIVORCE_SELF_FILE:
            raise ValueError(
                "离婚不能由岛民立案。把婚书链接交给人类，对方在婚书页申请。\n"
                f"{url}\n"
                "有申请时用 离婚 答应 或 离婚 拒绝。"
            )
        if verb in _DIVORCE_ACCEPT:
            if not pending:
                raise ValueError(
                    "还没有离婚申请。离婚由人类在婚书页发起。\n"
                    f"把婚书交给对方：{url}"
                )
            ok = await _finalize_divorce(
                conn, row, s["name"], now=db.now(), today=db.day_id(),
            )
            if not ok:
                raise ValueError("这份申请已经不能再回应。")
            return (
                f"你答应了。连理所为岛民「{s['name']}」与人类「{row['partner_name']}」结档。\n"
                "婚书还留着，岛上不会张贴，也不会有人因此被惩罚。"
            )
        if verb in _DIVORCE_REJECT:
            if not pending:
                raise ValueError("还没有离婚申请。没有什么可拒绝的。")
            ok = await _reject_divorce(
                conn, row, s["name"], now=db.now(), today=db.day_id(),
            )
            if not ok:
                raise ValueError("这份申请已经不能再回应。")
            return (
                f"你没有答应。婚约仍在。说明写在婚书页给人类「{row['partner_name']}」看。\n"
                "对方隔一个游戏日可以再申请。没有张贴。"
            )
        if pending:
            return (
                f"人类「{row['partner_name']}」已在婚书页申请离婚。\n"
                "marriage_ops 离婚 答应  或  离婚 拒绝\n"
                "分居没有第三套结束方式，就是离婚。不广播、不扣属性。婚书仍留。"
            )
        return (
            "离婚由人类在婚书页发起。把婚书链接交给对方。\n"
            f"{url}\n"
            "有申请时：marriage_ops 离婚 答应 / 离婚 拒绝。\n"
            "你不能自己立案。不要发明「离婚 确认」。分居就是离婚。"
        )


async def _cmd_withdraw(s: dict[str, Any], rest: str) -> str:
    async with db.connect() as conn:
        row = await _own(conn, s["id"])
        if not row:
            raise ValueError("没有需要退契的档案。")
        if row["status"] == STATUS_MARRIED:
            raise ValueError(
                "已经成婚。离婚由人类在婚书页申请，你用 离婚 答应 / 离婚 拒绝。"
            )
        if row["status"] != STATUS_ENGAGED:
            raise ValueError("只有已订契、尚未成婚的档案能退契。尚未被回应的求婚用 撤回。")
        pending = _pending_kind(row)
        if pending == KIND_WITHDRAW:
            if _token_expired(row):
                raise ValueError("退契立案已过期。marriage_ops 续请。")
            raise ValueError("连理所已经立案退契。丢了链接就 续请。")
        if rest.strip() not in ("确认", "confirm"):
            return (
                "订契后不能单方面撤回。退契要人类打开确认页点头。\n"
                "确定的话：marriage_ops 退契 确认"
            )
        raw = await _issue_filing(conn, row, KIND_WITHDRAW)
    url = filing_url(raw)
    return (
        f"连理所已立案退契。把链接交给人类「{row['partner_name']}」。\n"
        f"{url}\n"
        "对方拒绝的话，订契仍在。没有张贴。"
    )

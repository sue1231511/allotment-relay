"""衣泊坊 — 小剧场侧厅的服装店。主理人漾漾。不卖成衣，只接裁衣委托。"""
from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import config, db, energy, survival, world
from .catalog import (
    BETROTHAL_ATTIRE_SHOP,
    CLOTH_ITEMS,
    WEDDING_DRESS_SHOP_PRICE,
    item_label,
    resolve_item_key,
)

NPC_KEY = "yangyang"
NPC_NAME = "漾漾"
SHOP_NAME = "衣泊坊"

# 春=梅雨 夏=盛夏 秋=台风季 冬=冬潮。错过不绝版，来年同一季还会漂回来。
CLOTH_SEASON_LABEL = {"春": "梅雨", "夏": "盛夏", "秋": "台风季", "冬": "冬潮"}

CUTS: dict[str, dict[str, Any]] = {
    "jacket": {
        "name": "短褂", "emoji": "👕",
        "aliases": ("短褂", "褂", "jacket"),
        "seasons": ("春", "夏"), "mismatch": ("冬",),
        "seconds": 720, "energy": 4,
    },
    "robe": {
        "name": "长衫", "emoji": "👘",
        "aliases": ("长衫", "衫", "robe"),
        "seasons": ("春", "秋"), "mismatch": (),
        "seconds": 840, "energy": 4,
    },
    "skirt": {
        "name": "裙", "emoji": "👗",
        "aliases": ("裙", "裙子", "skirt"),
        "seasons": ("春", "夏"), "mismatch": ("冬",),
        "seconds": 780, "energy": 4,
    },
    "coat": {
        "name": "呢衣", "emoji": "🧥",
        "aliases": ("呢衣", "大衣", "coat"),
        "seasons": ("秋", "冬"), "mismatch": ("夏",),
        "seconds": 960, "energy": 5,
    },
    "cloak": {
        "name": "斗篷", "emoji": "🧥",
        "aliases": ("斗篷", "披风", "cloak"),
        "seasons": ("春", "秋", "冬"), "mismatch": ("夏",),
        "seconds": 900, "energy": 5,
    },
    "work": {
        "name": "工装", "emoji": "👷",
        "aliases": ("工装", "工作服", "work"),
        "seasons": ("秋", "冬"), "mismatch": ("夏",),
        "seconds": 840, "energy": 4,
    },
    "wedding": {
        "name": "婚服", "emoji": "👘",
        "aliases": ("婚服", "嫁衣", "礼服", "wedding"),
        "seasons": ("春", "夏", "秋", "冬"), "mismatch": (),
        "seconds": 1200, "energy": 6,
    },
    "betrothal": {
        "name": "订婚服", "emoji": "👘",
        "aliases": ("订婚服", "订婚礼服", "betrothal"),
        "seasons": ("春", "夏", "秋", "冬"), "mismatch": (),
        "seconds": 840, "energy": 4,
    },
}

COLORS: dict[str, dict[str, Any]] = {
    "sea": {"name": "海色", "dye": "dye_sea", "aliases": ("海色", "海蓝", "sea")},
    "ink": {"name": "墨色", "dye": "dye_ink", "aliases": ("墨色", "墨", "ink")},
    "sand": {"name": "沙色", "dye": "dye_sand", "aliases": ("沙色", "沙", "sand")},
    "fog": {"name": "雾色", "dye": "dye_fog", "aliases": ("雾色", "雾", "fog")},
    "plum": {"name": "梅青", "dye": "dye_plum", "aliases": ("梅青", "梅雨色", "plum"), "season": "春"},
    "noon": {"name": "午金", "dye": "dye_noon", "aliases": ("午金", "盛夏色", "noon"), "season": "夏"},
    "gale": {"name": "风绛", "dye": "dye_typhoon", "aliases": ("风绛", "台风色", "gale"), "season": "秋"},
    "ash": {"name": "潮灰", "dye": "dye_tide", "aliases": ("潮灰", "冬潮色", "ash"), "season": "冬"},
    "star": {"name": "星光", "dye": "dye_star", "aliases": ("星光", "星色", "star")},
    "lantern": {"name": "灯塔色", "dye": "dye_lantern", "aliases": ("灯塔色", "灯色", "lantern")},
}

MOTIFS: dict[str, dict[str, Any]] = {
    "plain": {"name": "素", "aliases": ("素", "素面", "plain", "无"), "extra": 0, "seconds": 0},
    "tide": {"name": "潮纹", "aliases": ("潮纹", "tide"), "extra": 1, "seconds": 240},
    "lighthouse": {"name": "灯塔", "aliases": ("灯塔", "灯塔纹", "lighthouse"), "extra": 1, "seconds": 300},
    "net": {"name": "渔网", "aliases": ("渔网", "网纹", "net"), "extra": 1, "seconds": 240},
    "star": {"name": "星点", "aliases": ("星点", "星纹", "star"), "extra": 1, "seconds": 300},
    "patch": {"name": "漂布拼", "aliases": ("漂布拼", "拼布", "patch"), "extra": 1, "seconds": 360},
    "twin": {"name": "双潮", "aliases": ("双潮", "双潮纹", "twin"), "extra": 1, "seconds": 300},
}

# 衣料：qty=委托要几份。season=哪一季海边更容易捡到；None=全年。
FABRICS: dict[str, dict[str, Any]] = {
    "cloth_drift": {"qty": 2, "season": None},
    "cloth_old": {"qty": 1, "season": None},
    "cloth_mist": {"qty": 1, "season": "春"},
    "cloth_sun": {"qty": 1, "season": "夏"},
    "cloth_gale": {"qty": 1, "season": "秋"},
    "cloth_frost": {"qty": 1, "season": "冬"},
    "crop_cotton": {"qty": 2, "season": "春"},
    "crop_hemp": {"qty": 2, "season": "秋"},
    "wool": {"qty": 2, "season": "冬"},
}

SEASON_FABRIC = {"春": "cloth_mist", "夏": "cloth_sun", "秋": "cloth_gale", "冬": "cloth_frost"}
SEASON_DYE = {"春": "dye_plum", "夏": "dye_noon", "秋": "dye_typhoon", "冬": "dye_tide"}

STORIES: dict[str, dict[str, Any]] = {
    "lighthouse_wool": {
        "name": "灯塔守夜人的旧呢衣",
        "cut": "coat",
        "fabrics": ("cloth_old", "cloth_frost", "wool"),
        "colors": ("ink", "ash", "lantern"),
        "place": "lighthouse",
        "origin": "旧呢上还留着灯油。漾漾说这料子在灯塔过了好几个冬潮。",
        "echo": "不醒把潮汐簿合上，看了你一眼。\n「这件我认得。穿去守夜的人，后来把呢衣叠好放在塔门后。」\n她给你续了茶，没再问。",
        "tale": (
            "《灯油与呢衣》灯塔换班那年，守夜人把旧呢衣挂在塔门后，说灯不睡、衣也不必带下山。"
            "后来的人只看见一件被潮气养过的呢料。穿上它去灯塔，不醒会停半拍。"
        ),
    },
    "salt_skirt": {
        "name": "被海水漂白的裙子",
        "cut": "skirt",
        "fabrics": ("cloth_drift",),
        "colors": ("sea", "sand", "fog"),
        "place": "beach",
        "origin": "布是浪送上来的。颜色已经淡了，像有人在海里走过一程。",
        "echo": "退潮的沙滩上，裙子下摆自己往回摆了一下。\n像有人在你身后轻轻说：还没走完。\n浪只留下盐。",
        "tale": (
            "《漂白》有人把裙子交给海，说颜色太满、日子太满。"
            "海把它送回来时，颜色淡了，褶还在。穿去滩上，浪会认。"
        ),
    },
    "rain_cloak": {
        "name": "梅雨里收过的斗篷",
        "cut": "cloak",
        "fabrics": ("cloth_mist",),
        "colors": ("plum", "fog", "ink"),
        "place": "plot",
        "origin": "梅雨纱收进柜里会自己潮。漾漾说这是这季该有的脾气。",
        "echo": "份地边际的雾比别处沉。斗篷肩上凝了一层细水。\n像有人把伞忘在田埂上，又被你捡回来。",
        "tale": (
            "《收纱》梅雨季有人把斗篷晾在田埂，说等雨停再取。"
            "雨没停。纱自己学会了下雨。穿去份地，边际会安静一点。"
        ),
    },
    "stage_cape": {
        "name": "侧厅旧斗篷",
        "cut": "cloak",
        "fabrics": ("cloth_old", "cloth_drift"),
        "colors": ("star", "ink", "fog"),
        "place": "theater",
        "origin": "侧厅挂钩上取下来的。漾漾说小橘有时会把旧披风忘在这儿。",
        "echo": "侧厅挂钩空着。斗篷在你肩上自己正了一下。\n像有人刚从台上退下来，把热气留给下一件衣服。",
        "tale": (
            "《挂钩》小剧场侧厅有一排空钩。有人把斗篷挂上去，说下场再取。"
            "那场没有下场。斗篷在挂钩上听了很久的戏。穿去剧院，侧幕会让一让。"
        ),
    },
    "gale_work": {
        "name": "台风季的工装",
        "cut": "work",
        "fabrics": ("cloth_gale", "crop_hemp"),
        "colors": ("gale", "ink", "ash"),
        "place": "beach",
        "origin": "台风绸吃风。漾漾说穿去海边，绳子比较听手。",
        "echo": "风从工装袖口穿过去，又从另一只袖口出来。\n像这件衣服记得怎么把风让开。",
        "tale": (
            "《让风》台风季有人把工装借给出海的人，说布会替你挡一阵。"
            "人回来了，布上还留着风。穿去海边，缆绳比较听话。"
        ),
    },
    "noon_jacket": {
        "name": "盛夏短褂",
        "cut": "jacket",
        "fabrics": ("cloth_sun", "crop_cotton"),
        "colors": ("noon", "sand", "sea"),
        "place": "star",
        "origin": "盛夏葛透气。漾漾说别在冬潮穿，热的时候才是它的季。",
        "echo": "场子里的热被短褂拆开一层。\n像有人把午后的光裁成了领口。",
        "tale": (
            "《午金》盛夏有人把葛布交给衣泊坊，说只要一件能把热让开的褂。"
            "穿去听她唱，肩上会凉快一点。"
        ),
    },
}

YANGYANG_LINES = (
    "成衣没有。布来了再裁。你当这儿是成衣铺？婚服那挂是例外，现货 8888。订婚服也有一挂 2888，不是婚服。",
    "这布是潮送的，还是地里长的，我闻得出来。",
    "梅雨纱过季了会收进柜里。不是绝版，明年还会漂回来。少搞那种逼人盯着日历的缺德玩意。",
    "版型、颜色、纹样你自己点。组不对也行，衣服还是衣服，故事另说。",
    "穿去灯塔的呢衣，不醒认得。穿去海边的裙子，浪也认得。",
    "季节对了，身子轻一点；穿反了，热或者冷会找你算账。",
    "旧衣料不是破烂。有人穿过，布还记得。",
)

CLOTH_HELP = f"""cloth_ops 子命令（整句写进 command）：
  {SHOP_NAME}在小剧场侧厅。主理人{NPC_NAME}。日常不卖成衣，只接裁衣委托。
  现货两挂：买 婚服 海色（{WEDDING_DRESS_SHOP_PRICE} 票）· 买 订婚服 海色（{BETROTHAL_ATTIRE_SHOP} 票）。当天进衣橱。短褂长衫不卖。订婚服不是婚服。
  空 command 列出本表，不是看坊。看坊必须 status。不是 craft_ops（岸工坊打钉），不是 tote_ops vend 成衣。

  status / 看坊 — 看台上在裁什么、当季衣料、身上穿着。看坊必须 status
  图鉴 / catalog — 版型、颜色、纹样、衣料来源、四季布与染料
  买 婚服 海色 — 婚服现货，选色当天进衣橱。{WEDDING_DRESS_SHOP_PRICE} 票。再 marriage_ops 婚服
  买 订婚服 海色 — 订婚服现货，{BETROTHAL_ATTIRE_SHOP} 票。不是婚服。再 marriage_ops 订婚 服装
  委托 短褂 海色 — 把衣料和染料交给{NPC_NAME}，开始裁制。也可 委托 呢衣 墨色 潮纹 · 委托 裙 沙色 素 漂布 · 委托 婚服 海色 双潮 · 委托 订婚服 海色
  取 — 领做好的衣服（裁制进度走完才能取；自制婚服隔日）
  衣橱 — 自己裁出来的衣服（不占行囊，不能卖）
  穿 1 / 穿 灯塔守夜人的旧呢衣 — 换上；同时只能穿一件
  脱 — 脱下
  故事 — 已经触发过的衣物来历。不是 tale_ops 潮闻任务，也不给布
  漾漾 / visit — 见主理人。今日首次约三成机会给旧衣料，不是必给；同一天再访没有第二匹
  help — 本表

例子：status · 图鉴 · 买 婚服 海色 · 买 订婚服 海色 · 委托 短褂 海色 · 委托 婚服 海色 双潮 · 取 · 衣橱 · 穿 1 · 漾漾
衣料主来源：海边拾漂布、份地种潮棉/岸麻、份地边际 forage / 公共旧布堆捡旧衣料。羊毛也能当呢料。
旧衣料不是 tale_ops 奖励。不要为了布去跑潮闻。灯塔不醒拜访时小概率夹一匹，不是正路。
委托第三段「灯塔」是纹样，不是去灯塔找不醒。不要 invent 买短褂。
季节：梅雨/盛夏/台风季/冬潮各有布和染料；错过不绝版，来年同一季再遇。
当季合身精力 -1，盛夏穿呢衣/冬潮穿裙会 +1。没有 shop_ops / tailor_ops。
  人类网页 /atelier 是海报；裁衣在 /play。visit_ops 漾漾 也能进门。
  人类 /island 总览点剧场，进院景再点衣泊坊：能看坊、买婚服订婚服、取衣、换衣服。委托短褂仍去上手页。"""


def current_cloth_season() -> str:
    from . import season as season_mod
    return season_mod.current_season()


def cloth_season_label(season: str | None = None) -> str:
    s = season or current_cloth_season()
    return CLOTH_SEASON_LABEL.get(s, s)


def _fmt_left(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds <= 0:
        return "现在"
    m, s = divmod(seconds, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h} 小时 {m} 分"
    if m:
        return f"{m} 分" if s < 15 else f"{m} 分 {s} 秒"
    return f"{s} 秒"


def _resolve_table(token: str, table: dict[str, dict[str, Any]]) -> str | None:
    raw = (token or "").strip()
    if not raw:
        return None
    low = raw.lower().replace(" ", "_")
    if raw in table or low in table:
        return raw if raw in table else low
    for key, meta in table.items():
        if meta["name"] == raw:
            return key
        for alias in meta.get("aliases") or ():
            if alias == raw or alias.lower() == low:
                return key
    return None


def resolve_cut(token: str) -> str | None:
    return _resolve_table(token, CUTS)


def resolve_color(token: str) -> str | None:
    return _resolve_table(token, COLORS)


def resolve_motif(token: str) -> str | None:
    return _resolve_table(token, MOTIFS)


def resolve_fabric(token: str) -> str | None:
    item = resolve_item_key(token) if token else None
    if item and item in FABRICS:
        return item
    raw = (token or "").strip()
    if raw in FABRICS:
        return raw
    for key, meta in CLOTH_ITEMS.items():
        if key not in FABRICS:
            continue
        if meta["name"] == raw or f"{meta['emoji']}{meta['name']}" == raw:
            return key
        if raw in (meta.get("aliases") or ()):
            return key
    return None


def _pick_story(cut: str, color: str, fabric: str) -> str:
    for key, meta in STORIES.items():
        if meta["cut"] != cut:
            continue
        if fabric not in meta["fabrics"]:
            continue
        if color not in meta["colors"]:
            continue
        return key
    return ""


def garment_name(cut: str, color: str, motif: str, fabric: str, story_key: str = "") -> str:
    if story_key and story_key in STORIES:
        return STORIES[story_key]["name"]
    cut_n = CUTS[cut]["name"]
    color_n = COLORS[color]["name"]
    motif_n = "" if motif == "plain" else MOTIFS[motif]["name"]
    return f"{color_n}{motif_n}{cut_n}"


def wear_energy_delta(cut: str, fabric: str, season: str | None = None) -> int:
    """合身 -1，反季 +1，中性 0。新号没衣服不罚。"""
    season = season or current_cloth_season()
    fabric_season = (FABRICS.get(fabric) or {}).get("season")
    cut_meta = CUTS.get(cut) or {}
    if fabric_season == season:
        return -int(config.CLOTH_MATCH_SAVE)
    if fabric_season and {fabric_season, season} == {"夏", "冬"}:
        return int(config.CLOTH_MISMATCH_COST)
    if season in (cut_meta.get("seasons") or ()):
        return -int(config.CLOTH_MATCH_SAVE)
    if season in (cut_meta.get("mismatch") or ()):
        return int(config.CLOTH_MISMATCH_COST)
    return 0


def wear_delta_label(delta: int, season: str | None = None) -> str:
    label = cloth_season_label(season)
    if delta < 0:
        return f"{label}合身，行动精力 {delta}"
    if delta > 0:
        return f"{label}穿反了，行动精力 +{delta}"
    return f"{label}无增减"


async def ensure_profile(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any]:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        """
        SELECT job_cut, job_color, job_motif, job_fabric, job_dye, job_story,
               job_name, job_ready_at, worn_id, sews_total
        FROM steward_atelier WHERE steward_id=?
        """,
        (steward_id,),
    )).fetchone()
    if not row:
        await conn.execute(
            """
            INSERT INTO steward_atelier (
                steward_id, job_cut, job_color, job_motif, job_fabric, job_dye,
                job_story, job_name, job_ready_at, worn_id, sews_total
            ) VALUES (?, '', '', '', '', '', '', '', 0, 0, 0)
            """,
            (steward_id,),
        )
        return {
            "job_cut": "", "job_color": "", "job_motif": "", "job_fabric": "",
            "job_dye": "", "job_story": "", "job_name": "", "job_ready_at": 0,
            "worn_id": 0, "sews_total": 0,
        }
    return {
        "job_cut": row["job_cut"] or "",
        "job_color": row["job_color"] or "",
        "job_motif": row["job_motif"] or "",
        "job_fabric": row["job_fabric"] or "",
        "job_dye": row["job_dye"] or "",
        "job_story": row["job_story"] or "",
        "job_name": row["job_name"] or "",
        "job_ready_at": int(row["job_ready_at"] or 0),
        "worn_id": int(row["worn_id"] or 0),
        "sews_total": int(row["sews_total"] or 0),
    }


async def worn_garment(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any] | None:
    prof = await ensure_profile(conn, steward_id)
    gid = int(prof["worn_id"] or 0)
    if gid <= 0:
        return None
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        """
        SELECT id, cut_key, color_key, motif_key, fabric_key, story_key, name, origin
        FROM steward_wardrobe WHERE id=? AND steward_id=?
        """,
        (gid, steward_id),
    )).fetchone()
    if not row:
        return None
    return dict(row)


async def energy_adjust(conn: aiosqlite.Connection, steward_id: int) -> int:
    g = await worn_garment(conn, steward_id)
    if not g:
        return 0
    return wear_energy_delta(g["cut_key"], g["fabric_key"])


async def sheet_line(conn: aiosqlite.Connection, steward_id: int) -> str:
    g = await worn_garment(conn, steward_id)
    season = current_cloth_season()
    if not g:
        return (
            f"衣着：未穿（{cloth_season_label(season)}）→ cloth_ops 看坊 · 衣泊坊在剧院侧厅，主理人{NPC_NAME}"
        )
    delta = wear_energy_delta(g["cut_key"], g["fabric_key"], season)
    return f"衣着：{g['name']}（{wear_delta_label(delta, season)}）"


async def dashboard_view(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any]:
    prof = await ensure_profile(conn, steward_id)
    now = db.now()
    g = await worn_garment(conn, steward_id)
    season = current_cloth_season()
    if prof["job_name"]:
        if prof["job_ready_at"] <= now:
            line = f"{SHOP_NAME}：{prof['job_name']} 好了 · cloth_ops 取"
        else:
            line = f"{SHOP_NAME}：正在裁 {prof['job_name']}"
    else:
        line = f"{SHOP_NAME}：台空闲 · cloth_ops 委托 短褂 海色"
    worn = g["name"] if g else "未穿"
    delta = wear_energy_delta(g["cut_key"], g["fabric_key"], season) if g else 0
    return {
        "line": line,
        "worn": worn,
        "season": cloth_season_label(season),
        "delta": delta,
        "job_ready": bool(prof["job_name"] and prof["job_ready_at"] <= now),
        "cuts": [{"key": k, "name": v["name"]} for k, v in CUTS.items()],
        "colors": [{"key": k, "name": v["name"]} for k, v in COLORS.items()],
        "motifs": [{"key": k, "name": v["name"]} for k, v in MOTIFS.items()],
    }


def _catalog_text() -> str:
    season = current_cloth_season()
    lines = [
        f"{SHOP_NAME}图鉴 · 主理人{NPC_NAME}",
        f"当季：{cloth_season_label(season)}（{season}）。错过的布和染料来年同一季还会有，不绝版。",
        "",
        "版型：",
    ]
    for meta in CUTS.values():
        fit = "、".join(CLOTH_SEASON_LABEL[s] for s in meta["seasons"])
        bad = "、".join(CLOTH_SEASON_LABEL[s] for s in meta.get("mismatch") or ())
        extra = f"；反季 {bad} 精力 +1" if bad else ""
        lines.append(f"  {meta['emoji']}{meta['name']} — 合身 {fit} 精力 -1{extra}")
    lines.append("")
    lines.append("颜色（要对应染料 1 份）：")
    for meta in COLORS.values():
        dye = item_label(meta["dye"])
        tag = f" · {cloth_season_label(meta['season'])}" if meta.get("season") else ""
        lines.append(f"  {meta['name']} ← {dye}{tag}")
    lines.append("")
    lines.append("纹样（素不耗额外布；其余再耗 1 份衣料）：")
    lines.append("  " + "、".join(m["name"] for m in MOTIFS.values()))
    lines.append("")
    lines.append("衣料来源：不是买成衣。")
    lines.append("  海边拾：漂布；当季还可能拾到梅雨纱/盛夏葛/台风绸/冬潮呢")
    lines.append("  份地种：潮棉（春夏）· 岸麻（秋冬）。温室也能种")
    lines.append("  份地捡：边际 forage、公共旧布堆会出旧衣料。羊毛也能当呢料")
    lines.append(f"  {NPC_NAME}今日首次约三成机会给一匹，不是必给，别连刷")
    lines.append("  灯塔不醒拜访时小概率夹一匹。tale_ops 潮闻不给旧衣料")
    lines.append("  活动：星光染料（小剧场/围观）· 灯塔染料（守夜）。限定但不绝版")
    lines.append("")
    lines.append("衣物故事：有的组合自带来历。穿去对应地点会多一句。这不是 tale_ops 潮闻任务。")
    lines.append("  呢衣+旧衣料+墨色 → 灯塔守夜人的旧呢衣（裁好穿上再去灯塔，不是先去找布）")
    lines.append("  裙+漂布+海色/沙色 → 被海水漂白的裙子（去海边）")
    lines.append("  斗篷+梅雨纱 → 梅雨里收过的斗篷（去份地）")
    lines.append("  斗篷+旧衣料+星光 → 侧厅旧斗篷（去小剧场）")
    lines.append("用法：cloth_ops 委托 短褂 海色 · 委托 呢衣 墨色 灯塔（灯塔=纹样）")
    return "\n".join(lines)


async def _status_text(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    prof = await ensure_profile(conn, s["id"])
    now = db.now()
    season = current_cloth_season()
    g = await worn_garment(conn, s["id"])
    lines = [
        f"{SHOP_NAME} · 主理人{NPC_NAME}",
        world.climate_line() + f" · {cloth_season_label(season)}",
        f"累计成衣 {prof['sews_total']} 件",
    ]
    if prof["job_name"]:
        left = prof["job_ready_at"] - now
        if left <= 0:
            lines.append(f"台上：{prof['job_name']} 好了 — cloth_ops 取")
        else:
            lines.append(f"台上：正在裁 {prof['job_name']}，{_fmt_left(left)}后取")
    else:
        lines.append("台上：空闲 — cloth_ops 委托 短褂 海色")
    if g:
        delta = wear_energy_delta(g["cut_key"], g["fabric_key"], season)
        lines.append(f"身上：{g['name']}（{wear_delta_label(delta, season)}）")
        if g.get("origin"):
            lines.append(f"  {g['origin']}")
    else:
        lines.append("身上：没穿。当季合身会轻一点，反季会热或冷。")
    fabric = SEASON_FABRIC[season]
    dye = SEASON_DYE[season]
    lines.append(
        f"当季衣料：{item_label(fabric)} · {item_label(dye)}。"
        "过季收进柜，来年同一季再遇，不绝版。"
    )
    lines.append(f"{NPC_NAME}：「{random.choice(YANGYANG_LINES)}」")
    return "\n".join(lines)


def _auto_fabric(stock: dict[str, int], season: str) -> str | None:
    preferred = [
        SEASON_FABRIC[season],
        "cloth_old",
        "cloth_drift",
        "crop_cotton" if season in ("春", "夏") else "crop_hemp",
        "wool" if season in ("秋", "冬") else "",
        "crop_cotton",
        "crop_hemp",
        "wool",
        "cloth_mist",
        "cloth_sun",
        "cloth_gale",
        "cloth_frost",
    ]
    seen: set[str] = set()
    for key in preferred:
        if not key or key in seen:
            continue
        seen.add(key)
        need = int((FABRICS.get(key) or {}).get("qty") or 1)
        if int(stock.get(key) or 0) >= need:
            return key
    return None


async def _cmd_sew(conn: aiosqlite.Connection, s: dict[str, Any], rest: str) -> str:
    prof = await ensure_profile(conn, s["id"])
    if prof["job_name"]:
        left = prof["job_ready_at"] - db.now()
        if left <= 0:
            raise ValueError(f"台上已经做好 {prof['job_name']}。先 cloth_ops 取。")
        raise ValueError(
            f"台上正在裁 {prof['job_name']}，{_fmt_left(left)}后才能再委托。"
            f"{NPC_NAME}一次只接一件。"
        )
    parts = [p for p in (rest or "").split() if p]
    if len(parts) < 2:
        raise ValueError(
            "用法：cloth_ops 委托 版型 颜色 [纹样] [衣料]。"
            "例子：委托 短褂 海色 · 委托 呢衣 墨色 灯塔 · 委托 裙 沙色 素 漂布"
        )
    cut = resolve_cut(parts[0])
    color = resolve_color(parts[1])
    if not cut:
        raise ValueError(f"未知版型：{parts[0]}。图鉴看短褂/长衫/裙/呢衣/斗篷/工装/婚服。")
    if not color:
        raise ValueError(f"未知颜色：{parts[1]}。图鉴看海色/墨色/沙色/雾色和当季色。")
    motif = "plain"
    fabric = None
    extra = parts[2:]
    if extra:
        maybe_motif = resolve_motif(extra[0])
        maybe_fabric = resolve_fabric(extra[0])
        if maybe_motif and not (maybe_fabric and extra[0] in FABRICS):
            motif = maybe_motif
            extra = extra[1:]
        if extra:
            fabric = resolve_fabric(" ".join(extra))
            if not fabric:
                raise ValueError(f"未知衣料：{' '.join(extra)}。tote_ops list 看手里的布。")
    cur = await conn.execute(
        "SELECT item, quantity FROM satchel WHERE steward_id=? AND quantity>0", (s["id"],)
    )
    stock = {r[0]: int(r[1]) for r in await cur.fetchall()}
    if not fabric:
        fabric = _auto_fabric(stock, current_cloth_season())
        if not fabric:
            raise ValueError(
                f"行囊里没有够用的衣料。海边拾漂布、份地种潮棉/岸麻，或 plot_ops forage 捡旧衣料。"
                "不要 invent 买成衣，也不要为了布去跑潮闻。"
            )
    if fabric not in FABRICS:
        raise ValueError(f"{item_label(fabric)} 不能拿来裁衣。")
    dye = COLORS[color]["dye"]
    need_fab = int(FABRICS[fabric]["qty"]) + int(MOTIFS[motif]["extra"])
    if cut == "wedding":
        need_fab *= 2
    if int(stock.get(fabric) or 0) < need_fab:
        raise ValueError(
            f"裁这件要 {item_label(fabric)}×{need_fab}，你只有 {int(stock.get(fabric) or 0)}。"
        )
    if int(stock.get(dye) or 0) < 1:
        raise ValueError(
            f"{COLORS[color]['name']}要 {item_label(dye)}×1。当季染料海边/活动会遇到，来年还会有。"
        )
    if not await db.take_item(conn, s["id"], fabric, need_fab):
        raise ValueError(f"缺少 {item_label(fabric)}")
    if not await db.take_item(conn, s["id"], dye, 1):
        await db.add_item(conn, s["id"], fabric, need_fab, over_cap=True)
        raise ValueError(f"缺少 {item_label(dye)}")
    story = _pick_story(cut, color, fabric)
    name = garment_name(cut, color, motif, fabric, story)
    seconds = int(CUTS[cut]["seconds"]) + int(MOTIFS[motif]["seconds"])
    if story:
        seconds += int(config.CLOTH_STORY_EXTRA_SECONDS)
    cost = int(CUTS[cut]["energy"])
    await energy.spend(conn, s["id"], cost, action="衣泊坊裁衣")
    if cut == "wedding":
        ready = db.next_day_start()
        if ready <= db.now() + 60:
            ready = db.now() + 86400
        wait_note = f"婚服自制隔日才取（{_fmt_left(ready - db.now())}）。现货走 cloth_ops 买 婚服"
    else:
        ready = db.now() + seconds
        wait_note = f"裁制进度 {_fmt_left(seconds)}"
    await conn.execute(
        """
        UPDATE steward_atelier SET job_cut=?, job_color=?, job_motif=?, job_fabric=?,
            job_dye=?, job_story=?, job_name=?, job_ready_at=?
        WHERE steward_id=?
        """,
        (cut, color, motif, fabric, dye, story, name, ready, s["id"]),
    )
    note = f"{NPC_NAME}接过布，在台上比了一下。「{name}。好了来取。」"
    if story:
        note += f"\n她多看了一眼：「这件有来历。{STORIES[story]['origin']}」"
    return (
        f"{note}\n{wait_note} · -{cost} 精力"
        f" · 耗 {item_label(fabric)}×{need_fab}、{item_label(dye)}×1"
        f"\n→ cloth_ops 取"
    )


async def _cmd_claim(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    prof = await ensure_profile(conn, s["id"])
    if not prof["job_name"]:
        raise ValueError(f"台上没有活。cloth_ops 委托 短褂 海色。{NPC_NAME}不卖成衣。")
    if prof["job_ready_at"] > db.now():
        raise ValueError(
            f"{prof['job_name']} 还在裁，{_fmt_left(prof['job_ready_at'] - db.now())}后再取。"
        )
    origin = ""
    story = prof["job_story"]
    if story and story in STORIES:
        origin = STORIES[story]["origin"]
    cur = await conn.execute(
        """
        INSERT INTO steward_wardrobe (
            steward_id, cut_key, color_key, motif_key, fabric_key, story_key,
            name, origin, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            s["id"], prof["job_cut"], prof["job_color"], prof["job_motif"],
            prof["job_fabric"], story, prof["job_name"], origin, db.now(),
        ),
    )
    gid = int(cur.lastrowid or 0)
    await conn.execute(
        """
        UPDATE steward_atelier SET job_cut='', job_color='', job_motif='', job_fabric='',
            job_dye='', job_story='', job_name='', job_ready_at=0, sews_total=sews_total+1
        WHERE steward_id=?
        """,
        (s["id"],),
    )
    await db.add_chronicle(
        "cloth", f"{s['name']} 在{SHOP_NAME}取走「{prof['job_name']}」", s["id"], conn=conn,
    )
    extra = ""
    if origin:
        extra = f"\n{origin}\n穿去对应地点可能多一句。cloth_ops 穿 {gid}"
    return (
        f"{NPC_NAME}把「{prof['job_name']}」叠好递过来。"
        f"\n进衣橱 #{gid}（不占行囊，不能卖）。cloth_ops 穿 {gid} · 衣橱{extra}"
    )


async def _cmd_buy_wedding(conn: aiosqlite.Connection, s: dict[str, Any], rest: str) -> str:
    parts = [p for p in (rest or "").split() if p]
    cut = resolve_cut(parts[0]) if parts else None
    if cut not in ("wedding", "betrothal"):
        raise ValueError(
            f"衣泊坊日常不卖成衣。现货只有婚服和订婚服："
            f"cloth_ops 买 婚服 海色（{WEDDING_DRESS_SHOP_PRICE} 票）· "
            f"买 订婚服 海色（{BETROTHAL_ATTIRE_SHOP} 票）。短褂长衫不卖。"
        )
    color_tok = parts[1] if len(parts) > 1 else "sea"
    color = resolve_color(color_tok)
    if not color:
        raise ValueError(f"未知颜色：{color_tok}。图鉴看海色/墨色/沙色/雾色和当季色。")
    if cut == "wedding":
        cost = int(WEDDING_DRESS_SHOP_PRICE)
        motif = "twin"
        lack = f"婚服现货 {cost} 票，口袋 {{have}}。自制走 委托 婚服，料加倍、隔日取。"
        talk = "只这一档婚服现货。日常还是不卖成衣。订婚服另挂。"
        register = "去连理所 marriage_ops 婚服 登记。"
    else:
        cost = int(BETROTHAL_ATTIRE_SHOP)
        motif = "plain"
        lack = f"订婚服现货 {cost} 票，口袋 {{have}}。自制走 委托 订婚服 或 委托 短褂。"
        talk = "订婚服现货。不是婚服。日常短褂还是不卖。"
        register = "去连理所 marriage_ops 订婚 服装 登记。不是婚服。"
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
    have = int((await cur.fetchone())[0] or 0)
    if have < cost:
        raise ValueError(lack.format(have=have))
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (cost, s["id"]),
    )
    from . import tax as tax_mod
    await tax_mod.record_life_spend(conn, s["id"], cost, "cloth")
    name = garment_name(cut, color, motif, "shop")
    origin = "衣泊坊现货。没交布，是柜上那挂。"
    cur = await conn.execute(
        """
        INSERT INTO steward_wardrobe (
            steward_id, cut_key, color_key, motif_key, fabric_key, story_key,
            name, origin, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (s["id"], cut, color, motif, "shop", "", name, origin, db.now()),
    )
    gid = int(cur.lastrowid or 0)
    await db.add_chronicle(
        "cloth", f"{s['name']} 在{SHOP_NAME}买走现货「{name}」", s["id"], conn=conn,
    )
    return (
        f"{NPC_NAME}从柜上取下一挂。「{talk}」\n"
        f"「{name}」进衣橱 #{gid}（-{cost} 票 · 余 {have - cost}）。\n"
        f"{register}"
    )


async def _wardrobe_rows(conn: aiosqlite.Connection, steward_id: int) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """
        SELECT id, cut_key, color_key, motif_key, fabric_key, story_key, name, origin
        FROM steward_wardrobe WHERE steward_id=? ORDER BY id
        """,
        (steward_id,),
    )).fetchall()
    return [dict(r) for r in rows]


async def _cmd_wardrobe(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    prof = await ensure_profile(conn, s["id"])
    rows = await _wardrobe_rows(conn, s["id"])
    if not rows:
        return f"衣橱空着。把布交给{NPC_NAME}：cloth_ops 委托 短褂 海色"
    season = current_cloth_season()
    lines = [f"{SHOP_NAME}衣橱 · {cloth_season_label(season)}"]
    for row in rows:
        mark = "（穿着）" if int(row["id"]) == int(prof["worn_id"] or 0) else ""
        delta = wear_energy_delta(row["cut_key"], row["fabric_key"], season)
        tag = wear_delta_label(delta, season)
        lines.append(f"  #{row['id']} {row['name']}{mark} · {tag}")
        if row.get("origin"):
            lines.append(f"      {row['origin']}")
    lines.append("cloth_ops 穿 编号 · 脱")
    return "\n".join(lines)


def _match_garment(token: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    raw = (token or "").strip()
    if raw.isdigit():
        gid = int(raw)
        for row in rows:
            if int(row["id"]) == gid:
                return row
        return None
    hits = [row for row in rows if row["name"] == raw or raw in row["name"]]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ValueError("重名衣服不止一件，用编号：cloth_ops 衣橱")
    return None


async def _cmd_wear(conn: aiosqlite.Connection, s: dict[str, Any], rest: str) -> str:
    rows = await _wardrobe_rows(conn, s["id"])
    if not rows:
        raise ValueError("衣橱空着。先 cloth_ops 委托 再 取。")
    row = _match_garment(rest, rows)
    if not row:
        raise ValueError("衣橱里没有这件。cloth_ops 衣橱 看编号。")
    await conn.execute(
        "UPDATE steward_atelier SET worn_id=? WHERE steward_id=?",
        (int(row["id"]), s["id"]),
    )
    season = current_cloth_season()
    delta = wear_energy_delta(row["cut_key"], row["fabric_key"], season)
    extra = f"\n{row['origin']}" if row.get("origin") else ""
    echo = await try_echo(conn, s, "atelier", silent=False)
    echo_line = f"\n{echo}" if echo else ""
    return (
        f"换上「{row['name']}」。{wear_delta_label(delta, season)}。"
        f"{extra}{echo_line}"
    )


async def _cmd_remove(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    g = await worn_garment(conn, s["id"])
    if not g:
        return "本来就没穿。"
    await conn.execute(
        "UPDATE steward_atelier SET worn_id=0 WHERE steward_id=?", (s["id"],)
    )
    return f"脱下「{g['name']}」。衣橱还在。"


async def _cmd_stories(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """
        SELECT story_key, place, text, created_at FROM steward_cloth_echo
        WHERE steward_id=? ORDER BY created_at
        """,
        (s["id"],),
    )).fetchall()
    if not rows:
        return (
            "还没有触发过衣物故事。部分衣服自带来历；穿着去灯塔、海边、份地或小剧场，"
            f"{NPC_NAME}说会多一句。"
        )
    lines = ["衣物故事（只收录已经遇见的来历，不是 tale_ops）"]
    for row in rows:
        meta = STORIES.get(row["story_key"] or "", {})
        title = meta.get("name") or row["story_key"] or "无题"
        lines.append(f"《{title}》")
        lines.append(row["text"])
        lines.append("")
    return "\n".join(lines).rstrip()


async def _cmd_visit(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    from . import bond as bond_mod
    gained = await bond_mod.note_visit(conn, s["id"], NPC_KEY)
    line = random.choice(YANGYANG_LINES)
    g = await worn_garment(conn, s["id"])
    notice = ""
    if g:
        notice = f"\n她看了看你肩上的「{g['name']}」。"
        if g.get("origin"):
            notice += f"\n「{g['origin']}」"
    echo = await try_echo(conn, s, "atelier")
    gift = ""
    day = db.day_id()
    hit = await (await conn.execute(
        "SELECT 1 FROM npc_visits WHERE steward_id=? AND npc_key=? AND day=?",
        (s["id"], NPC_KEY, day),
    )).fetchone()
    if not hit:
        await conn.execute(
            "INSERT INTO npc_visits (steward_id, npc_key, day) VALUES (?,?,?)",
            (s["id"], NPC_KEY, day),
        )
        if random.random() < float(config.CLOTH_VISIT_OLD_CHANCE):
            try:
                await db.add_item(conn, s["id"], "cloth_old", 1)
                gift = f"\n她从柜底抽出一匹旧衣料：「有人穿过。你拿去。」旧衣料×1"
            except ValueError:
                await survival.bump(conn, s["id"], mist_wit=2)
                gift = "\n雾智 +2（行囊满了，布先搁着）"
        else:
            await survival.bump(conn, s["id"], mist_wit=2)
            gift = "\n雾智 +2（今日首次拜访）"
    bond_n = f" · 岛缘 +{gained}" if gained else ""
    echo_line = f"\n{echo}" if echo else ""
    return (
        f"{NPC_NAME}在{SHOP_NAME}侧厅低头量布。\n「{line}」{notice}{gift}{bond_n}{echo_line}\n"
        f"cloth_ops 图鉴 · 委托 短褂 海色"
    )


async def try_echo(
    conn: aiosqlite.Connection,
    s: dict[str, Any],
    place: str,
    *,
    silent: bool = False,
) -> str:
    """穿着对应来历的衣服到地点，触发一句/小剧情/短潮闻。每件故事每个地点一次。"""
    g = await worn_garment(conn, s["id"])
    if not g:
        return ""
    story = g.get("story_key") or ""
    meta = STORIES.get(story)
    if not meta or meta.get("place") != place:
        return ""
    exists = await (await conn.execute(
        """
        SELECT 1 FROM steward_cloth_echo
        WHERE steward_id=? AND story_key=? AND place=?
        """,
        (s["id"], story, place),
    )).fetchone()
    if exists:
        return "" if silent else meta["echo"]
    text = meta["tale"] if meta.get("tale") else meta["echo"]
    await conn.execute(
        """
        INSERT INTO steward_cloth_echo (steward_id, story_key, place, text, created_at)
        VALUES (?,?,?,?,?)
        """,
        (s["id"], story, place, text, db.now()),
    )
    await survival.bump(conn, s["id"], standing=2, mist_wit=3)
    await conn.execute(
        "UPDATE stewards SET tickets=tickets+? WHERE id=?",
        (int(config.CLOTH_ECHO_TICKETS), s["id"]),
    )
    from . import bond as bond_mod
    await bond_mod.grant(conn, s["id"], bond_mod.CLOTH_ECHO, "story")
    await db.add_chronicle(
        "cloth", f"{s['name']} 穿着「{g['name']}」在{place}听见旧事", s["id"], conn=conn,
    )
    return (
        f"{meta['echo']}\n\n衣物来历已记下。cloth_ops 故事 可再读。"
        f"工分票 +{config.CLOTH_ECHO_TICKETS} · 档信 +2 · 雾智 +3"
    )


async def maybe_grant_old_cloth(conn: aiosqlite.Connection, steward_id: int, chance: float) -> str:
    if random.random() >= chance:
        return ""
    try:
        await db.add_item(conn, steward_id, "cloth_old", 1)
    except ValueError:
        return ""
    return f"{NPC_NAME}托人捎来一匹旧衣料。旧衣料×1"


async def maybe_event_dye(conn: aiosqlite.Connection, steward_id: int, source: str) -> str:
    """活动掉限定染料：星光/灯塔。不绝版，下次活动还会有。"""
    if source == "star" and random.random() < float(config.CLOTH_STAR_DYE_CHANCE):
        item = "dye_star"
    elif source == "lantern" and random.random() < float(config.CLOTH_LANTERN_DYE_CHANCE):
        item = "dye_lantern"
    elif source == "season" and random.random() < float(config.CLOTH_SEASON_DYE_CHANCE):
        item = SEASON_DYE[current_cloth_season()]
    else:
        return ""
    try:
        await db.add_item(conn, steward_id, item, 1)
    except ValueError:
        return ""
    return f"衣料里夹到 {item_label(item)}×1（活动染料，来年还能遇到）"


def maybe_upgrade_beach_fabric(item: str) -> str:
    """海边拾到漂布时，当季有机会换成季节布。过季不绝版。"""
    if item != "cloth_drift":
        return item
    if random.random() >= float(config.CLOTH_BEACH_SEASON_CHANCE):
        return item
    return SEASON_FABRIC[current_cloth_season()]


def beach_loot_item() -> str:
    if random.random() < float(config.CLOTH_BEACH_DRIFT_CHANCE):
        return maybe_upgrade_beach_fabric("cloth_drift")
    return ""


async def player_view(conn: aiosqlite.Connection, s: dict[str, Any]) -> dict[str, Any]:
    """给 /island 衣泊坊用。数值仍走 cloth_ops，这里只摊开能点的。"""
    from . import bar as bar_mod

    conn.row_factory = aiosqlite.Row
    prof = await ensure_profile(conn, s["id"])
    now = db.now()
    season = current_cloth_season()
    worn = await worn_garment(conn, s["id"])
    tickets = int(s.get("tickets") or 0)
    overdue = bar_mod.is_shift_overdue(s)
    job_name = prof["job_name"]
    ready_at = int(prof["job_ready_at"] or 0)
    can_take = bool(job_name and ready_at <= now)
    if overdue:
        take_note = "考勤逾期，先去酒吧洗碗。看坊、衣橱、换衣服仍可用。"
        can_take = False
    elif can_take:
        take_note = f"{job_name} 好了，可以取。"
    elif job_name:
        take_note = f"正在裁 {job_name}，{_fmt_left(ready_at - now)}后再取。"
    else:
        take_note = f"台上空闲。委托短褂去上手页交给{NPC_NAME}。"
    worn_name = worn["name"] if worn else "没穿"
    if worn:
        delta = wear_energy_delta(worn["cut_key"], worn["fabric_key"], season)
        worn_note = wear_delta_label(delta, season)
    else:
        worn_note = "当季合身会轻一点，反季会热或冷。"
    goods: list[dict[str, Any]] = []
    for cut, label, price in (
        ("wedding", "婚服", int(WEDDING_DRESS_SHOP_PRICE)),
        ("betrothal", "订婚服", int(BETROTHAL_ATTIRE_SHOP)),
    ):
        for color_key in ("sea", "ink", "sand", "fog"):
            color = COLORS[color_key]["name"]
            can = tickets >= price and not overdue
            if overdue:
                note = "考勤逾期，先去酒吧洗碗。"
            elif tickets < price:
                note = f"要 {price} 票，现在 {tickets}"
            else:
                note = f"{label}现货 · {price} 票。当天进衣橱。"
            goods.append({
                "id": f"{cut}:{color_key}",
                "cmd": f"{label} {color}",
                "name": f"{color}{label}",
                "kind": cut,
                "color": color,
                "emoji": "👘",
                "price": price,
                "can_buy": can,
                "note": note,
                "detail": (
                    f"{note}订婚服不是婚服。"
                    if cut == "betrothal"
                    else f"{note}日常短褂不卖。"
                ),
            })
    closet: list[dict[str, Any]] = []
    for row in await _wardrobe_rows(conn, s["id"]):
        on = int(row["id"]) == int(prof["worn_id"] or 0)
        delta = wear_energy_delta(row["cut_key"], row["fabric_key"], season)
        closet.append({
            "id": int(row["id"]),
            "name": row["name"],
            "worn": on,
            "can_wear": not on,
            "note": ("穿着 · " if on else "") + wear_delta_label(delta, season),
            "detail": row.get("origin") or wear_delta_label(delta, season),
        })
    can_remove = bool(worn)
    any_buy = any(row["can_buy"] for row in goods)
    if overdue:
        line = "考勤逾期 · 看坊衣橱仍开"
    elif can_take:
        line = f"台上做好了 · {job_name}"
    elif any_buy:
        line = f"{cloth_season_label(season)} · 能买现货"
    else:
        line = f"{cloth_season_label(season)} · {NPC_NAME}在"
    return {
        "name": SHOP_NAME,
        "line": line,
        "tabs": [
            {"key": "desk", "label": "看坊", "badge": "取" if can_take else ""},
            {"key": "shop", "label": "现货", "badge": "买" if any_buy else ""},
            {"key": "closet", "label": "衣橱", "badge": str(len(closet)) if closet else ""},
        ],
        "desk": {
            "job": job_name or "空闲",
            "can_take": can_take,
            "take_note": take_note,
            "worn": worn_name,
            "worn_note": worn_note,
            "can_remove": can_remove,
            "season": cloth_season_label(season),
            "yangyang": YANGYANG_LINES[0],
            "overdue": overdue,
        },
        "goods": goods,
        "closet": closet,
        "can_take": can_take,
        "can_remove": can_remove,
    }


async def cloth_ops(key_id: int, command: str = "") -> str:
    from .game import require_steward

    raw = (command or "").strip()
    verb, _, rest = raw.partition(" ")
    verb = verb.lower()
    if not verb or verb in ("help", "?", "帮助"):
        return CLOTH_HELP

    duty_verbs = {"委托", "sew", "裁", "取", "claim", "买", "buy"}
    s = await require_steward(key_id, exempt_duty=verb not in duty_verbs)

    async with db.connect() as conn:
        if verb in ("status", "看", "看坊", "scan"):
            text = await _status_text(conn, s)
        elif verb in ("catalog", "图鉴"):
            text = _catalog_text()
        elif verb in ("买", "buy"):
            text = await _cmd_buy_wedding(conn, s, rest)
        elif verb in ("委托", "sew", "裁"):
            text = await _cmd_sew(conn, s, rest)
        elif verb in ("取", "claim"):
            text = await _cmd_claim(conn, s)
        elif verb in ("衣橱", "wardrobe", "柜"):
            text = await _cmd_wardrobe(conn, s)
        elif verb in ("穿", "wear"):
            text = await _cmd_wear(conn, s, rest)
        elif verb in ("脱", "remove", "unequip"):
            text = await _cmd_remove(conn, s)
        elif verb in ("故事", "stories", "lore"):
            text = await _cmd_stories(conn, s)
        elif verb in ("漾漾", "visit", "yangyang", NPC_NAME.lower()):
            text = await _cmd_visit(conn, s)
        else:
            raise ValueError(
                f"未知衣泊坊指令：{command}。空 command 看表；看坊用 status。"
                "日常不卖成衣。现货：买 婚服 海色 · 买 订婚服 海色。"
            )
        await conn.commit()
    return text

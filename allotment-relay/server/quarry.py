"""盐风崖 — 潮脉矿。迎风崖壁上的矿脉随潮汐显隐，不是赶海沙滩，也不是潮下井。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import commons, config, db, energy, flavor, health, world
from .catalog import (
    PICK_TIERS,
    QUARRY_ORES,
    QUARRY_VEINS,
    item_label,
    pick_tier_meta,
    resolve_ore_key,
)
from .game import require_steward

QUARRY_HELP = """quarry_ops 子命令（整句写进 command）：
  盐风崖潮脉矿。迎风崖上的矿脉随潮汐显隐：涨潮出盐、退潮出铁、海雾出稀有。
  比 tide_ops dig / net / cast 更慢更费：镐更贵、冷却更长、空挥更高、洗矿亏份。
  不是 tide_ops dig（赶海翻沙，要铲子，涨潮关）。不是 undertide_ops（潮下社交）。
  没有 mine_ops / dig_ops / mine / 采矿 这种工具。

  status / scan / 看 — 看镐、矿坑、当前矿脉、潮汐对矿的影响。空 command 不是看崖，是本表
  catalog / 图鉴 — 矿脉、矿石、镐档
  买镐 — 80 票买 T1 盐风镐（Tt酱 tt buy 盐风镐 同一档；铲子 42 / 粗网 28）
  探脉 [坑号] — 给空坑找一条矿脉（要镐；8 精力，20 分钟冷却，约 18% 空探）
  挖 [坑号] — 对着矿脉挥镐（要 T1 镐；精力 16→11；全坑共用 36 分钟冷却；每坑再 40 分钟；每日 8 镐）
  洗 海盐砂 [数量] — 2 份原矿出 1 份精矿（6 精力/份精矿，约 12% 冲散）。数量是原矿，须成对
  开坑 / 开坑 确认 — 看价与开凿时间 / 付钱加坑（起步 1 个，无上限，90/142/218…）
  升镐 / 升镐 确认 — 花票+精矿升一档（T2 铜镐起；T5 雾铅镐满）
  help — 本表

例子：quarry_ops status · quarry_ops 买镐 · quarry_ops 探脉 · quarry_ops 挖 1 · quarry_ops 洗 海盐砂 2
涨潮关的是赶海 dig；崖矿不关，但湿滑：挖更费精力、空挥更高。不要发明 hew_all / mine_all。
盐田晒盐走 craft_ops 灌 / 收盐，和洗矿是同一种海盐晶，更慢更省镐。
人类网页 /quarry 是围观实况；挥镐在 /play。"""


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


def _claim_label(slot: int) -> str:
    return f"坑{slot}"


def _parse_slot(token: str, claim_count: int) -> int | None:
    raw = (token or "").strip().lstrip("#")
    if not raw:
        return None
    if raw.startswith("坑"):
        raw = raw[1:].strip()
    if raw.lower().startswith("claim"):
        raw = raw[5:].lstrip(" _-")
    if not raw.isdigit():
        return None
    slot = int(raw)
    if slot < 1 or slot > claim_count:
        raise ValueError(f"没有{_claim_label(slot)}。现有 1～{claim_count} 号。quarry_ops status 看坑")
    return slot


def _vein_weight(key: str, *, tide: str, weather: str, phase: str, pick_tier: int) -> int:
    meta = QUARRY_VEINS[key]
    if pick_tier < int(meta["min_tier"]):
        return 0
    w = int(meta["weight"])
    w += int((meta.get("tide_bonus") or {}).get(tide, 0))
    w += int((meta.get("weather_bonus") or {}).get(weather, 0))
    w += int((meta.get("phase_bonus") or {}).get(phase, 0))
    return max(0, w)


def roll_vein(*, tide: str, weather: str, phase: str, pick_tier: int) -> str:
    keys, weights = [], []
    for key in QUARRY_VEINS:
        w = _vein_weight(key, tide=tide, weather=weather, phase=phase, pick_tier=pick_tier)
        if w > 0:
            keys.append(key)
            weights.append(w)
    if not keys:
        return "shale"
    return random.choices(keys, weights=weights)[0]


def vein_strikes(key: str) -> int:
    lo, hi = QUARRY_VEINS[key]["strikes"]
    return random.randint(int(lo), int(hi))


def climate_hint(*, tide: str, weather: str, phase: str) -> list[str]:
    lines = []
    if tide == "flood":
        lines.append(
            "涨潮：盐脉权重↑，但崖壁湿滑——挖 +2 精力、空挥 +8%。"
            "赶海 dig 这时关，崖矿不关"
        )
    elif tide == "ebb":
        lines.append("退潮：铁砂床 / 页岩层权重↑")
    else:
        lines.append("平潮：铜绿缝略肥")
    if weather == "misty":
        lines.append("海雾：潮纹 / 雾铅 / 夜光髓权重↑")
    elif weather == "gale":
        lines.append("阵风：铁砂床权重↑，空挥 +6%")
    elif weather == "clear":
        lines.append("晴朗：页岩 / 盐脉更稳")
    if phase == "night":
        lines.append("夜里：雾铅窝、夜光髓窝略亮，挖 +1 精力")
    return lines


def _hew_empty_chance(pick_tier: int, *, tide: str, weather: str) -> float:
    empty = float(pick_tier_meta(pick_tier).get("empty") or 0.28)
    if tide == "flood":
        empty += config.QUARRY_FLOOD_EMPTY
    if weather == "gale":
        empty += config.QUARRY_GALE_EMPTY
    return min(0.60, empty)


async def ensure_profile(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any]:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT pick_tier, claim_count, last_prospect_at, last_hew_at, hews_total FROM steward_quarry WHERE steward_id=?",
        (steward_id,),
    )).fetchone()
    if not row:
        await conn.execute(
            """
            INSERT INTO steward_quarry (steward_id, pick_tier, claim_count, last_prospect_at, last_hew_at, hews_total)
            VALUES (?, 0, ?, 0, 0, 0)
            """,
            (steward_id, config.QUARRY_START_CLAIMS),
        )
        await conn.execute(
            """
            INSERT INTO quarry_claims (steward_id, slot, vein, strikes_left, ready_at, last_hew_at)
            VALUES (?, 1, '', 0, 0, 0)
            """,
            (steward_id,),
        )
        return {
            "pick_tier": 0,
            "claim_count": config.QUARRY_START_CLAIMS,
            "last_prospect_at": 0,
            "last_hew_at": 0,
            "hews_total": 0,
        }
    count = int(row["claim_count"] or config.QUARRY_START_CLAIMS)
    have = await (await conn.execute(
        "SELECT COUNT(*) FROM quarry_claims WHERE steward_id=?", (steward_id,)
    )).fetchone()
    if int(have[0] or 0) < 1:
        await conn.execute(
            """
            INSERT INTO quarry_claims (steward_id, slot, vein, strikes_left, ready_at, last_hew_at)
            VALUES (?, 1, '', 0, 0, 0)
            """,
            (steward_id,),
        )
    return {
        "pick_tier": int(row["pick_tier"] or 0),
        "claim_count": count,
        "last_prospect_at": int(row["last_prospect_at"] or 0),
        "last_hew_at": int(row["last_hew_at"] or 0),
        "hews_total": int(row["hews_total"] or 0),
    }


async def set_min_pick_tier(conn: aiosqlite.Connection, steward_id: int, tier: int) -> int:
    prof = await ensure_profile(conn, steward_id)
    current = int(prof["pick_tier"])
    want = max(current, int(tier))
    if want != current:
        await conn.execute(
            "UPDATE steward_quarry SET pick_tier=? WHERE steward_id=?",
            (want, steward_id),
        )
    return want


async def _claims(conn: aiosqlite.Connection, steward_id: int) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """
        SELECT slot, vein, strikes_left, ready_at, last_hew_at
        FROM quarry_claims WHERE steward_id=? ORDER BY slot
        """,
        (steward_id,),
    )).fetchall()
    now = db.now()
    out = []
    for r in rows:
        ready_at = int(r["ready_at"] or 0)
        if ready_at and ready_at <= now:
            await conn.execute(
                "UPDATE quarry_claims SET ready_at=0 WHERE steward_id=? AND slot=?",
                (steward_id, r["slot"]),
            )
            ready_at = 0
        out.append({
            "slot": int(r["slot"]),
            "vein": r["vein"] or "",
            "strikes_left": int(r["strikes_left"] or 0),
            "ready_at": ready_at,
            "last_hew_at": int(r["last_hew_at"] or 0),
        })
    return out


def _claim_line(c: dict[str, Any], *, now: int, pick_tier: int) -> str:
    label = _claim_label(c["slot"])
    if c["ready_at"] > now:
        return f"  {label} 开凿中，{_fmt_left(c['ready_at'] - now)}后能探"
    vein = c["vein"]
    if not vein or c["strikes_left"] <= 0:
        return f"  {label} 空坑 — quarry_ops 探脉 {c['slot']}"
    meta = QUARRY_VEINS.get(vein, {})
    name = f"{meta.get('emoji', '')}{meta.get('name', vein)}"
    left = c["strikes_left"]
    cd = c["last_hew_at"] + config.QUARRY_HEW_COOLDOWN - now
    extra = f" · 冷却 {_fmt_left(cd)}" if cd > 0 else ""
    gated = ""
    if pick_tier < int(meta.get("min_tier") or 1):
        gated = f" · 要 T{meta['min_tier']} 镐"
    return f"  {label} {name} 剩 {left} 镐{gated}{extra}"


def _next_claim_offer(claim_count: int) -> dict[str, int]:
    idx = max(0, int(claim_count) - config.QUARRY_START_CLAIMS)
    return {
        "slot": int(claim_count) + 1,
        "cost": config.quarry_claim_cost(idx),
        "clear_seconds": config.quarry_claim_clear_seconds(idx),
    }


async def _hew_energy(conn: aiosqlite.Connection, steward_id: int, pick_tier: int) -> int:
    meta = pick_tier_meta(pick_tier)
    cost = int(meta.get("energy") or 16)
    if world.current_tide() == "flood":
        cost += config.QUARRY_FLOOD_ENERGY
    if world.current_day_phase() == "night":
        cost += config.QUARRY_NIGHT_ENERGY
    from . import hut as hut_mod
    bonus = await hut_mod.get_bonuses(conn, steward_id)
    save = int(getattr(bonus, "quarry_energy_save", 0) or 0)
    return max(1, cost - save)


def _catalog_text(*, pick_tier: int) -> str:
    tide, weather, phase = world.current_tide(), world.current_weather(), world.current_day_phase()
    lines = [
        "盐风崖图鉴",
        world.climate_line(),
        *climate_hint(tide=tide, weather=weather, phase=phase),
        "",
        "矿脉（探脉时按潮汐/天气/镐档加权）：",
    ]
    for key, meta in QUARRY_VEINS.items():
        raw = QUARRY_ORES[meta["raw"]]
        w = _vein_weight(key, tide=tide, weather=weather, phase=phase, pick_tier=max(pick_tier, 1))
        lock = "" if pick_tier >= int(meta["min_tier"]) else f" · 要 T{meta['min_tier']}"
        lines.append(
            f"  {meta['emoji']}{meta['name']} → {raw['emoji']}{raw['name']}"
            f"（此刻权重 {w}{lock}）"
        )
    lines.append("")
    lines.append(
        f"矿石（洗 {config.QUARRY_WASH_RAW_PER} 份原矿 = 1 份精矿，"
        f"{config.QUARRY_WASH_ENERGY} 精力；约 {int(config.QUARRY_WASH_FAIL*100)}% 被潮水冲散）："
    )
    for key, meta in QUARRY_ORES.items():
        if meta["kind"] != "raw":
            continue
        refined = QUARRY_ORES[meta["refined"]]
        lines.append(
            f"  {meta['emoji']}{meta['name']} {meta['sell']}票"
            f" → {refined['emoji']}{refined['name']} {refined['sell']}票"
        )
    lines.append("")
    lines.append("镐档：")
    for row in PICK_TIERS:
        mark = " ← 现在" if row["tier"] == pick_tier else ""
        if row["tier"] == 0:
            lines.append(f"  T0 {row['name']} — 能看、能探，不能挖{mark}")
            continue
        need = row.get("need") or {}
        need_s = ""
        if need:
            need_s = " + " + "、".join(f"{item_label(k)}x{v}" for k, v in need.items())
        cost = f"{row['tickets']}票{need_s}" if row.get("tickets") else ""
        lines.append(
            f"  T{row['tier']} {row['name']} — 精力{row['energy']}"
            f" 双份+{int(row['yield']*100)}% 空挥{int(row['empty']*100)}% {cost}{mark}"
        )
    lines.append("")
    lines.append(
        "洗完的精矿：tote_ops vend 卖掉，或 quarry_ops 升镐。海盐晶可下锅当佐料。"
        "盐田晒盐走 craft_ops 灌 / 收盐，和洗的是同一种，更慢更省镐。"
    )
    return "\n".join(lines)


async def _status_text(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    prof = await ensure_profile(conn, s["id"])
    claims = await _claims(conn, s["id"])
    now = db.now()
    pick = pick_tier_meta(prof["pick_tier"])
    tide, weather, phase = world.current_tide(), world.current_weather(), world.current_day_phase()
    offer = _next_claim_offer(prof["claim_count"])
    lines = [
        "盐风崖",
        world.climate_line(),
        *climate_hint(tide=tide, weather=weather, phase=phase),
        f"镐：T{pick['tier']} {pick['name']}"
        + ("" if pick["tier"] else f" — quarry_ops 买镐（{config.QUARRY_PICK_T1_COST}票）或 visit_ops tt buy 盐风镐"),
        f"矿坑 {prof['claim_count']} 个（下一坑 {_claim_label(offer['slot'])} {offer['cost']}票 / 开凿 {offer['clear_seconds']//60} 分）",
        f"累计挥镐 {prof['hews_total']}",
    ]
    day = db.day_id(now)
    used = await (await conn.execute(
        "SELECT count FROM quarry_rolls WHERE steward_id=? AND day=?",
        (s["id"], day),
    )).fetchone()
    lines.append(f"今日挥镐 {int(used[0] if used else 0)}/{config.QUARRY_HEW_DAILY_CAP}")
    if prof["last_prospect_at"]:
        left = prof["last_prospect_at"] + config.QUARRY_PROSPECT_COOLDOWN - now
        if left > 0:
            lines.append(f"探脉冷却：{_fmt_left(left)}")
    gleft = int(prof["last_hew_at"] or 0) + config.QUARRY_HEW_GLOBAL_COOLDOWN - now
    if pick["tier"] >= 1 and gleft > 0:
        lines.append(f"挥镐冷却（全坑共用）：{_fmt_left(gleft)}")
    lines.append("矿坑：")
    for c in claims:
        lines.append(_claim_line(c, now=now, pick_tier=prof["pick_tier"]))
    if pick["tier"] >= 1:
        hew_e = await _hew_energy(conn, s["id"], pick["tier"])
        empty_pct = int(_hew_empty_chance(
            pick["tier"], tide=tide, weather=weather,
        ) * 100)
        lines.append(
            f"下一镐约 {hew_e} 精力、空挥约 {empty_pct}%"
            f"（装了盐风矿灯会少 1；多开坑不能连挥）"
        )
    lines.append("指令：探脉 · 挖 [坑号] · 洗 海盐砂 2 · 开坑 · 升镐 · catalog")
    return "\n".join(lines)


async def _buy_pick(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    prof = await ensure_profile(conn, s["id"])
    if int(prof["pick_tier"]) >= 1:
        pick = pick_tier_meta(prof["pick_tier"])
        return f"已经有 T{pick['tier']} {pick['name']}。更高档 quarry_ops 升镐"
    cost = config.QUARRY_PICK_T1_COST
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
    have = int((await cur.fetchone())[0])
    if have < cost:
        raise ValueError(f"买镐要 {cost} 票（现 {have}）。先 tote_ops vend 或 bar_ops work")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (cost, s["id"]),
    )
    await set_min_pick_tier(conn, s["id"], 1)
    row = await (await conn.execute(
        "SELECT quantity FROM satchel WHERE steward_id=? AND item='tool_pick'",
        (s["id"],),
    )).fetchone()
    if int(row[0] if row else 0) <= 0:
        try:
            await db.add_item(conn, s["id"], "tool_pick", 1)
        except ValueError:
            pass
    await db.add_chronicle("quarry", f"{s['name']} 在盐风崖领了盐风镐", s["id"], conn=conn)
    return (
        f"领到 T1 盐风镐（-{cost} 票）。下一步 quarry_ops 探脉，再 quarry_ops 挖。"
        + flavor.maybe_suffix(["崖壁回声，镐还是新的", "盐风刮过刃口"])
    )


async def _prospect(conn: aiosqlite.Connection, s: dict[str, Any], token: str) -> str:
    prof = await ensure_profile(conn, s["id"])
    if int(prof["pick_tier"]) < 1:
        raise ValueError(
            f"没有镐探不出脉。quarry_ops 买镐（{config.QUARRY_PICK_T1_COST}票），"
            "或 visit_ops tt buy 盐风镐"
        )
    claims = await _claims(conn, s["id"])
    now = db.now()
    left = int(prof["last_prospect_at"] or 0) + config.QUARRY_PROSPECT_COOLDOWN - now
    if left > 0:
        raise ValueError(f"刚探过，{_fmt_left(left)}后再来。空坑可以等，别连点")
    slot = _parse_slot(token, prof["claim_count"])
    target = None
    if slot:
        target = next((c for c in claims if c["slot"] == slot), None)
    else:
        empties = [
            c for c in claims
            if c["ready_at"] <= now and (not c["vein"] or c["strikes_left"] <= 0)
        ]
        if not empties:
            busy = [c for c in claims if c["vein"] and c["strikes_left"] > 0]
            if busy:
                raise ValueError(
                    "没有空坑。对着现有矿脉 quarry_ops 挖，或 quarry_ops 开坑 加坑。"
                )
            clearing = [c for c in claims if c["ready_at"] > now]
            if clearing:
                raise ValueError(
                    f"{_claim_label(clearing[0]['slot'])}还在开凿，"
                    f"{_fmt_left(clearing[0]['ready_at'] - now)}后再探"
                )
            raise ValueError("没有能探的坑。quarry_ops status")
        target = empties[0]
    if target is None:
        raise ValueError("没有这个坑。quarry_ops status")
    if target["ready_at"] > now:
        raise ValueError(
            f"{_claim_label(target['slot'])}还在开凿，{_fmt_left(target['ready_at'] - now)}后再探"
        )
    if target["vein"] and target["strikes_left"] > 0:
        raise ValueError(
            f"{_claim_label(target['slot'])}还有"
            f"{QUARRY_VEINS.get(target['vein'], {}).get('name', target['vein'])}"
            f"剩 {target['strikes_left']} 镐。先 quarry_ops 挖 {target['slot']}"
        )
    await energy.spend(conn, s["id"], config.QUARRY_PROSPECT_ENERGY, action="探脉")
    await conn.execute(
        "UPDATE steward_quarry SET last_prospect_at=? WHERE steward_id=?",
        (now, s["id"]),
    )
    if random.random() < config.QUARRY_PROSPECT_EMPTY:
        await db.add_chronicle(
            "quarry",
            f"{s['name']} 在{_claim_label(target['slot'])}空探",
            s["id"],
            conn=conn,
        )
        return (
            f"空探：{_claim_label(target['slot'])}潮线糊了，没咬到脉"
            f"（-{config.QUARRY_PROSPECT_ENERGY} 精力）。"
            f"{_fmt_left(config.QUARRY_PROSPECT_COOLDOWN)}后再 quarry_ops 探脉。"
            + flavor.maybe_suffix(["盐风把粉尘吹回去了", "崖壁回了一声空的"])
        )
    pick_tier = max(1, int(prof["pick_tier"]))
    vein = roll_vein(
        tide=world.current_tide(),
        weather=world.current_weather(),
        phase=world.current_day_phase(),
        pick_tier=pick_tier,
    )
    strikes = vein_strikes(vein)
    await conn.execute(
        """
        UPDATE quarry_claims SET vein=?, strikes_left=?, last_hew_at=0
        WHERE steward_id=? AND slot=?
        """,
        (vein, strikes, s["id"], target["slot"]),
    )
    meta = QUARRY_VEINS[vein]
    raw = QUARRY_ORES[meta["raw"]]
    gated = ""
    if int(prof["pick_tier"]) < int(meta["min_tier"]):
        gated = (
            f"\n这条要 T{meta['min_tier']} 镐才挖得动。先 quarry_ops 升镐，"
            f"或再探别的空坑。"
        )
    elif int(prof["pick_tier"]) < 1:
        gated = "\n还没镐。quarry_ops 买镐 后再挖。"
    await db.add_chronicle(
        "quarry",
        f"{s['name']} 在{_claim_label(target['slot'])}探到{meta['name']}",
        s["id"],
        conn=conn,
    )
    return (
        f"探脉：{_claim_label(target['slot'])} 露出 {meta['emoji']}{meta['name']}，"
        f"大约 {strikes} 镐（{raw['emoji']}{raw['name']}）。"
        f"下一步 quarry_ops 挖 {target['slot']}。"
        f"{gated}"
        + flavor.maybe_suffix(["盐风把粉尘吹开", "崖壁回了一声", "潮水刚退，脉线还湿"])
    )


async def _hew(conn: aiosqlite.Connection, s: dict[str, Any], token: str) -> str:
    prof = await ensure_profile(conn, s["id"])
    if int(prof["pick_tier"]) < 1:
        raise ValueError(
            f"没有镐。quarry_ops 买镐（{config.QUARRY_PICK_T1_COST}票），或 visit_ops tt buy 盐风镐"
        )
    claims = await _claims(conn, s["id"])
    now = db.now()
    slot = _parse_slot(token, prof["claim_count"])
    target = None
    if slot:
        target = next((c for c in claims if c["slot"] == slot), None)
    else:
        ready = [
            c for c in claims
            if c["vein"] and c["strikes_left"] > 0 and c["ready_at"] <= now
            and now >= c["last_hew_at"] + config.QUARRY_HEW_COOLDOWN
        ]
        if not ready:
            cooling = [
                c for c in claims
                if c["vein"] and c["strikes_left"] > 0
                and now < c["last_hew_at"] + config.QUARRY_HEW_COOLDOWN
            ]
            if cooling:
                wait = cooling[0]["last_hew_at"] + config.QUARRY_HEW_COOLDOWN - now
                raise ValueError(
                    f"{_claim_label(cooling[0]['slot'])}刚挥过，{_fmt_left(wait)}后再挖。"
                    "有空坑就 quarry_ops 探脉。"
                )
            raise ValueError("没有可挖的矿脉。先 quarry_ops 探脉，或 quarry_ops status 看坑")
        target = ready[0]
    if target is None:
        raise ValueError("没有这个坑。quarry_ops status")
    if target["ready_at"] > now:
        raise ValueError(f"{_claim_label(target['slot'])}还在开凿")
    if not target["vein"] or target["strikes_left"] <= 0:
        raise ValueError(f"{_claim_label(target['slot'])}是空坑。quarry_ops 探脉 {target['slot']}")
    cd = target["last_hew_at"] + config.QUARRY_HEW_COOLDOWN - now
    if cd > 0:
        raise ValueError(f"{_claim_label(target['slot'])}刚挥过，{_fmt_left(cd)}后再挖")
    gleft = int(prof["last_hew_at"] or 0) + config.QUARRY_HEW_GLOBAL_COOLDOWN - now
    if gleft > 0:
        raise ValueError(
            f"刚挥过，腕还酸，{_fmt_left(gleft)}后再挖。"
            "多开坑不能连挥——冷却全坑共用。"
        )
    day = db.day_id(now)
    used_row = await (await conn.execute(
        "SELECT count FROM quarry_rolls WHERE steward_id=? AND day=?",
        (s["id"], day),
    )).fetchone()
    used = int(used_row[0] if used_row else 0)
    if used >= config.QUARRY_HEW_DAILY_CAP:
        raise ValueError(
            f"今日已经挥满 {config.QUARRY_HEW_DAILY_CAP} 镐。"
            "赶海一天能翻很多次，崖矿故意卡死。明天再来。"
        )
    vein_meta = QUARRY_VEINS.get(target["vein"])
    if not vein_meta:
        raise ValueError("这条脉看不清了。quarry_ops 探脉 重探")
    if int(prof["pick_tier"]) < int(vein_meta["min_tier"]):
        raise ValueError(
            f"{vein_meta['name']}要 T{vein_meta['min_tier']} 镐。"
            f"现在 T{prof['pick_tier']}。quarry_ops 升镐，或探别的坑"
        )
    pick = pick_tier_meta(prof["pick_tier"])
    cost = await _hew_energy(conn, s["id"], pick["tier"])
    await energy.spend(conn, s["id"], cost, action="崖矿")
    empty = _hew_empty_chance(
        pick["tier"], tide=world.current_tide(), weather=world.current_weather(),
    )
    extra_msg = ""
    got: list[tuple[str, int]] = []
    if random.random() < empty:
        extra_msg = "空挥，只迸出石屑"
    else:
        qty = 1
        if random.random() < float(pick.get("yield") or 0):
            qty += 1
            extra_msg = "，镐锋吃深，多落下一块"
        raw_key = vein_meta["raw"]
        await db.add_item(conn, s["id"], raw_key, qty)
        got.append((raw_key, qty))
        if random.random() < 0.06 + pick["tier"] * 0.015:
            bonus_key = random.choice(["quarry_shale", "quarry_salt_sand"])
            if bonus_key != raw_key:
                await db.add_item(conn, s["id"], bonus_key, 1)
                got.append((bonus_key, 1))
                extra_msg += f"，顺手 {item_label(bonus_key)}"
    left = max(0, int(target["strikes_left"]) - 1)
    vein = target["vein"] if left > 0 else ""
    await conn.execute(
        """
        UPDATE quarry_claims
        SET strikes_left=?, vein=?, last_hew_at=?
        WHERE steward_id=? AND slot=?
        """,
        (left, vein, now, s["id"], target["slot"]),
    )
    await conn.execute(
        "UPDATE steward_quarry SET hews_total=hews_total+1, last_hew_at=? WHERE steward_id=?",
        (now, s["id"]),
    )
    await conn.execute(
        """
        INSERT INTO quarry_rolls (steward_id, day, last_at, count)
        VALUES (?,?,?,1)
        ON CONFLICT(steward_id, day) DO UPDATE SET
            last_at=excluded.last_at, count=count+1
        """,
        (s["id"], day, now),
    )
    ill = await health.maybe_roll_ailment(
        conn, s["id"], "quarry", chance=config.QUARRY_HAZARD_CHANCE, source="quarry",
    )
    disc = await commons.roll_discovery(conn, s, "quarry")
    loot = "、".join(f"{item_label(k)} x{q}" for k, q in got) if got else "没有矿"
    depleted = ""
    if left <= 0:
        depleted = f"\n{_claim_label(target['slot'])}采空了。quarry_ops 探脉 {target['slot']} 再找。"
    else:
        depleted = f" 这条还剩 {left} 镐。"
    await db.add_chronicle(
        "quarry",
        f"{s['name']} 在{_claim_label(target['slot'])}挖到{loot}",
        s["id"],
        conn=conn,
    )
    msg = (
        f"挖 {_claim_label(target['slot'])} {vein_meta['emoji']}{vein_meta['name']}："
        f"{loot}{extra_msg}（-{cost} 精力）。{depleted}"
        + flavor.maybe_suffix(["盐风灌进袖口", "镐落石开", "崖壁比人硬，人比石久"])
    )
    if ill:
        msg += f"\n{ill}\n→ visit_ops clinic treat 岩尘入肺（必须花票）"
    if disc:
        msg += f"\n{disc}"
    return msg


async def _wash(conn: aiosqlite.Connection, s: dict[str, Any], rest: str) -> str:
    parts = (rest or "").split()
    if not parts:
        raise ValueError("用法：quarry_ops 洗 海盐砂 [数量]。catalog 看哪些是原矿")
    qty = config.QUARRY_WASH_RAW_PER
    name_toks = parts
    if name_toks[-1].isdigit():
        qty = max(1, int(name_toks[-1]))
        name_toks = name_toks[:-1]
    token = " ".join(name_toks)
    item = resolve_ore_key(token)
    if not item:
        raise ValueError(f"不认识 {token}。quarry_ops catalog 看矿石名，例如 洗 海盐砂 2")
    meta = QUARRY_ORES[item]
    if meta["kind"] != "raw":
        raw = meta.get("raw")
        hint = f"这已经是精矿。要洗的是 {item_label(raw)}。" if raw else "这已经是精矿。"
        raise ValueError(hint)
    ratio = config.QUARRY_WASH_RAW_PER
    if qty % ratio != 0:
        raise ValueError(
            f"要成对洗，{ratio} 份原矿出 1 份精矿。"
            f"例如 quarry_ops 洗 海盐砂 {ratio}"
        )
    refined = meta["refined"]
    if not await db.take_item(conn, s["id"], item, qty):
        raise ValueError(f"行囊里没有 {item_label(item)} x{qty}。先 quarry_ops 挖")
    batches = qty // ratio
    cost = config.QUARRY_WASH_ENERGY * batches
    try:
        await energy.spend(conn, s["id"], cost, action="洗矿")
    except ValueError:
        await db.add_item(conn, s["id"], item, qty)
        raise
    kept = 0
    for _ in range(batches):
        if random.random() >= config.QUARRY_WASH_FAIL:
            kept += 1
    if kept:
        await db.add_item(conn, s["id"], refined, kept)
    await db.add_chronicle(
        "quarry",
        f"{s['name']} 洗净 {item_label(item)} x{qty} → {kept}",
        s["id"],
        conn=conn,
    )
    ref_meta = QUARRY_ORES[refined]
    if kept <= 0:
        return (
            f"洗 {item_label(item)} x{qty}：潮水把砂冲散了，精矿没留下"
            f"（-{cost} 精力）。再 quarry_ops 挖。"
            + flavor.maybe_suffix(["洗手时什么也没留下", "潮水比人贪"])
        )
    lost = batches - kept
    lost_s = f"，冲散 {lost} 批" if lost else ""
    return (
        f"洗净 {item_label(item)} x{qty} → {ref_meta['emoji']}{ref_meta['name']} x{kept}"
        f"（-{cost} 精力{lost_s}，系统价 {ref_meta['sell']}票/份）。"
        f"卖掉 tote_ops vend {ref_meta['name']} {kept}，升镐 quarry_ops 升镐。"
        + flavor.maybe_suffix(["潮水把砂冲走，剩下能用的", "洗手时盐粒还亮"])
    )


async def _claim_preview(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    prof = await ensure_profile(conn, s["id"])
    offer = _next_claim_offer(prof["claim_count"])
    return (
        f"现有 {prof['claim_count']} 个矿坑（起步 {config.QUARRY_START_CLAIMS}，无上限）。\n"
        f"下一坑 {_claim_label(offer['slot'])}：{offer['cost']} 票，"
        f"开凿 {offer['clear_seconds'] // 60} 分钟。\n"
        f"付钱：quarry_ops 开坑 确认"
    )


async def _claim_buy(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    prof = await ensure_profile(conn, s["id"])
    offer = _next_claim_offer(prof["claim_count"])
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
    have = int((await cur.fetchone())[0])
    if have < offer["cost"]:
        raise ValueError(f"开坑要 {offer['cost']} 票（现 {have}）")
    now = db.now()
    ready_at = now + int(offer["clear_seconds"])
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (offer["cost"], s["id"]),
    )
    await conn.execute(
        "UPDATE steward_quarry SET claim_count=? WHERE steward_id=?",
        (offer["slot"], s["id"]),
    )
    await conn.execute(
        """
        INSERT INTO quarry_claims (steward_id, slot, vein, strikes_left, ready_at, last_hew_at)
        VALUES (?, ?, '', 0, ?, 0)
        """,
        (s["id"], offer["slot"], ready_at),
    )
    await db.add_chronicle(
        "quarry",
        f"{s['name']} 开了{_claim_label(offer['slot'])}",
        s["id"],
        conn=conn,
    )
    return (
        f"付钱开 {_claim_label(offer['slot'])}（-{offer['cost']} 票）。"
        f"{offer['clear_seconds'] // 60} 分钟后 quarry_ops 探脉 {offer['slot']}。"
        + flavor.maybe_suffix(["新坑还在渗盐水", "崖壁让出一掌宽"])
    )


async def _upgrade_preview(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    prof = await ensure_profile(conn, s["id"])
    current = pick_tier_meta(prof["pick_tier"])
    nxt = next((r for r in PICK_TIERS if r["tier"] == current["tier"] + 1), None)
    if current["tier"] < 1:
        return f"还没镐。先 quarry_ops 买镐（{config.QUARRY_PICK_T1_COST}票），再谈升级。"
    if not nxt:
        return f"T{current['tier']} {current['name']} 已经是满级。"
    need = nxt.get("need") or {}
    need_s = "、".join(f"{item_label(k)}x{v}" for k, v in need.items())
    return (
        f"现在 T{current['tier']} {current['name']}。\n"
        f"下一档 T{nxt['tier']} {nxt['name']}：{nxt['tickets']} 票"
        + (f" + {need_s}" if need_s else "")
        + f"\n精力 {nxt['energy']}，双份 {int(nxt['yield']*100)}%，空挥 {int(nxt['empty']*100)}%。\n"
        f"付钱：quarry_ops 升镐 确认"
    )


async def _upgrade_do(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    prof = await ensure_profile(conn, s["id"])
    current = pick_tier_meta(prof["pick_tier"])
    if current["tier"] < 1:
        raise ValueError("还没镐。quarry_ops 买镐")
    nxt = next((r for r in PICK_TIERS if r["tier"] == current["tier"] + 1), None)
    if not nxt:
        return f"T{current['tier']} {current['name']} 已经是满级。"
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
    have = int((await cur.fetchone())[0])
    if have < int(nxt["tickets"]):
        raise ValueError(f"升镐要 {nxt['tickets']} 票（现 {have}）")
    for item, qty in (nxt.get("need") or {}).items():
        if not await db.take_item(conn, s["id"], item, qty):
            raise ValueError(
                f"缺少 {item_label(item)} x{qty}。挖到原矿后 quarry_ops 洗 再来"
            )
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (int(nxt["tickets"]), s["id"]),
    )
    await conn.execute(
        "UPDATE steward_quarry SET pick_tier=? WHERE steward_id=?",
        (nxt["tier"], s["id"]),
    )
    await db.add_chronicle(
        "quarry",
        f"{s['name']} 的镐升到 T{nxt['tier']} {nxt['name']}",
        s["id"],
        conn=conn,
    )
    return (
        f"镐升至 T{nxt['tier']} {nxt['name']}（-{nxt['tickets']} 票）。"
        f"精力 {nxt['energy']}，能探更硬的脉。"
        + flavor.maybe_suffix(["刃口换过，崖壁还是那块", "新镐先磕一下盐脉认认"])
    )


async def quarry_ops(key_id: int, command: str = "") -> str:
    raw = (command or "").strip()
    if not raw or raw.lower() in ("help", "?", "帮助"):
        return QUARRY_HELP
    s = await require_steward(key_id)
    parts = raw.split()
    verb = parts[0].lower()
    rest = " ".join(parts[1:])

    async with db.connect() as conn:
        await ensure_profile(conn, s["id"])
        if verb in ("status", "scan", "看", "崖", "矿"):
            text = await _status_text(conn, s)
            await conn.commit()
            return text
        if verb in ("catalog", "图鉴", "veins", "ores"):
            prof = await ensure_profile(conn, s["id"])
            await conn.commit()
            return _catalog_text(pick_tier=int(prof["pick_tier"]))
        if verb in ("买镐", "镐", "pick"):
            if rest.lower() in ("", "buy", "买"):
                text = await _buy_pick(conn, s)
                await conn.commit()
                return text
        if verb in ("tool", "tools") and (rest.lower().startswith("buy") or rest in ("买镐", "镐", "pick")):
            text = await _buy_pick(conn, s)
            await conn.commit()
            return text
        if verb in ("探脉", "prospect", "survey", "探"):
            text = await _prospect(conn, s, rest)
            await conn.commit()
            return text
        if verb in ("挖", "hew", "strike", "挥镐", "挥"):
            text = await _hew(conn, s, rest)
            await conn.commit()
            return text
        if verb in ("洗", "wash", "refine", "淘"):
            text = await _wash(conn, s, rest)
            await conn.commit()
            return text
        if verb in ("开坑", "claim", "买坑", "扩坑"):
            if rest in ("确认", "confirm", "买", "yes"):
                text = await _claim_buy(conn, s)
            else:
                text = await _claim_preview(conn, s)
            await conn.commit()
            return text
        if verb in ("升镐", "upgrade", "升"):
            if rest in ("确认", "confirm", "yes"):
                text = await _upgrade_do(conn, s)
            else:
                text = await _upgrade_preview(conn, s)
            await conn.commit()
            return text
        await conn.commit()

    raise ValueError(
        f"未知 quarry 指令: {command}\n{QUARRY_HELP}\n"
        "不要发明 mine_ops / dig_ops。赶海翻沙是 tide_ops dig。"
    )


async def public_snapshot() -> dict[str, Any]:
    tide, weather, phase = world.current_tide(), world.current_weather(), world.current_day_phase()
    day = db.day_id()
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        hews = (await (await conn.execute(
            "SELECT COALESCE(SUM(count),0) FROM quarry_rolls WHERE day=?", (day,)
        )).fetchone())[0]
        miners = (await (await conn.execute(
            "SELECT COUNT(*) FROM quarry_rolls WHERE day=?", (day,)
        )).fetchone())[0]
        claims = (await (await conn.execute(
            "SELECT COUNT(*) FROM quarry_claims"
        )).fetchone())[0]
        veins = await (await conn.execute(
            """
            SELECT vein, COUNT(*) AS n FROM quarry_claims
            WHERE vein != '' AND strikes_left > 0
            GROUP BY vein ORDER BY n DESC
            """
        )).fetchall()
        feed = await (await conn.execute(
            """
            SELECT c.text, c.created_at, a.name AS actor
            FROM chronicle c
            LEFT JOIN stewards a ON a.id = c.actor_id
            WHERE c.action='quarry'
            ORDER BY c.created_at DESC LIMIT 16
            """
        )).fetchall()
    def _vein_note(key: str) -> str:
        meta = QUARRY_VEINS.get(key) or {}
        need = int(meta.get("min_tier") or 1)
        if need >= 4:
            return f"深裂隙 · 要 T{need}"
        if need >= 2:
            return f"裂隙较浅 · 要 T{need}"
        return "仍可继续"

    return {
        "climate": world.climate_line(),
        "hints": climate_hint(tide=tide, weather=weather, phase=phase),
        "chips": [
            world.weather_label(weather),
            world.tide_label(tide),
            world.day_phase_label(phase),
        ],
        "hews_today": int(hews or 0),
        "miners_today": int(miners or 0),
        "claims": int(claims or 0),
        "veins": [
            {
                "key": r["vein"],
                "name": QUARRY_VEINS.get(r["vein"], {}).get("name", r["vein"]),
                "emoji": QUARRY_VEINS.get(r["vein"], {}).get("emoji", "🪨"),
                "n": int(r["n"]),
                "note": _vein_note(r["vein"]),
            }
            for r in veins
        ],
        "feed": [
            {
                "text": r["text"],
                "actor": r["actor"] or "系统",
                "created_at": r["created_at"],
            }
            for r in feed
        ],
    }


async def dashboard_view(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any]:
    prof = await ensure_profile(conn, steward_id)
    claims = await _claims(conn, steward_id)
    now = db.now()
    pick = pick_tier_meta(prof["pick_tier"])
    if pick["tier"] < 1:
        line = "盐风崖：未开镐 · quarry_ops 买镐"
    else:
        live = sum(1 for c in claims if c["vein"] and c["strikes_left"] > 0 and c["ready_at"] <= now)
        line = f"盐风崖：T{pick['tier']} {pick['name']} · {live}/{prof['claim_count']} 坑有脉"
    return {
        "pick_tier": pick["tier"],
        "pick_name": pick["name"],
        "claim_count": prof["claim_count"],
        "hews_total": prof["hews_total"],
        "line": line,
        "claims": [
            {
                "slot": c["slot"],
                "label": _claim_line(c, now=now, pick_tier=pick["tier"]).strip(),
                "vein": c["vein"],
                "strikes_left": c["strikes_left"],
            }
            for c in claims
        ],
    }

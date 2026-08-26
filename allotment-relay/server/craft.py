"""岸工坊 — 打家具/补丁、盐田晒盐、风暴打捞、潮汐陈列柜。

不是 quarry_ops（崖上挥镐），不是 tide_ops dig（铲子翻沙），不是 kitchen_ops cook。
"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import commons, config, db, energy, flavor, health, world
from .catalog import (
    CRAFT_RECIPES,
    EXHIBIT_SETS,
    item_label,
    resolve_exhibit_key,
    resolve_recipe_key,
)
from .game import require_steward

CRAFT_HELP = """craft_ops 子命令（整句写进 command）：
  岸工坊。把崖矿精矿、羊毛、漂绳、岸木做成东西；附带盐田、风暴打捞、陈列柜。
  不是 quarry_ops（崖上挥镐洗矿）。不是 tide_ops dig（赶海翻沙，要铲子）。
  不是 kitchen_ops cook。没有 forge_ops / salvage_ops / exhibit_ops。

  status / 看 — 砧上在打什么、盐田、打捞窗口、陈列进度。空 command 不是看工坊，是本表
  图鉴 / catalog — 配方、盐田规则、打捞窗口、陈列套
  打 铜钉 — 扣材料开始慢工（一砧一次；好了 craft_ops 取）。也可 打 潮纹秤锤 · 打 铁锄刃 · 打 雾铅网坠 · 打 夜光滤网 · 打 潮誓戒 · 打 订婚戒
  取 — 领做好的成品
  补网 — 网补丁 6 小时空网 -8%；有雾铅网坠优先贴，12 小时 -14%。不是 gear upgrade
  盐田 — 看池；灌 — 涨潮灌一池（5 精力）；收盐 — 晴天攒满 20 分钟后收海盐晶
  开池 / 开池 确认 — 加盐田（最多 3 口，40/68/96 票）
  打捞 — 阵风中、阵风后晴天、周潮或船损才能下滩。不是 dig。夜光滤网减空捞
  陈列 / 捐 亮壳一套 — 看套 / 捐货换称呼或装饰。也可 捐 砧上全套
  help — 本表

例子：craft_ops status · craft_ops 打 铜钉 · craft_ops 打 潮纹秤锤 · craft_ops 打 订婚戒 · craft_ops 取 · craft_ops 灌 · craft_ops 打捞 · craft_ops 捐 亮壳一套 · craft_ops 捐 砧上全套
涨潮灌盐田，晴天才晒。赶海 dig 涨潮关；打捞只认风暴窗口。
订婚戒要潮信贝+海玻璃，不是潮誓戒。打完 marriage_ops 订婚 信物。
人类网页 /workshop 是围观实况；打钉在 /play。"""


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


async def ensure_profile(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any]:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        """
        SELECT job_key, job_ready_at, job_qty, pan_count, last_salvage_at,
               salvages_total, crafts_total, net_patch_until,
               COALESCE(net_patch_empty, 0) AS net_patch_empty
        FROM steward_craft WHERE steward_id=?
        """,
        (steward_id,),
    )).fetchone()
    if not row:
        await conn.execute(
            """
            INSERT INTO steward_craft (
                steward_id, job_key, job_ready_at, job_qty, pan_count,
                last_salvage_at, salvages_total, crafts_total, net_patch_until
            ) VALUES (?, '', 0, 0, 1, 0, 0, 0, 0)
            """,
            (steward_id,),
        )
        await conn.execute(
            "INSERT INTO craft_pans (steward_id, slot, brine_at) VALUES (?, 1, 0)",
            (steward_id,),
        )
        return {
            "job_key": "",
            "job_ready_at": 0,
            "job_qty": 0,
            "pan_count": 1,
            "last_salvage_at": 0,
            "salvages_total": 0,
            "crafts_total": 0,
            "net_patch_until": 0,
            "net_patch_empty": 0.0,
        }
    count = int(row["pan_count"] or 1)
    have = await (await conn.execute(
        "SELECT COUNT(*) FROM craft_pans WHERE steward_id=?", (steward_id,)
    )).fetchone()
    if int(have[0] or 0) < 1:
        await conn.execute(
            "INSERT INTO craft_pans (steward_id, slot, brine_at) VALUES (?, 1, 0)",
            (steward_id,),
        )
    return {
        "job_key": row["job_key"] or "",
        "job_ready_at": int(row["job_ready_at"] or 0),
        "job_qty": int(row["job_qty"] or 0),
        "pan_count": count,
        "last_salvage_at": int(row["last_salvage_at"] or 0),
        "salvages_total": int(row["salvages_total"] or 0),
        "crafts_total": int(row["crafts_total"] or 0),
        "net_patch_until": int(row["net_patch_until"] or 0),
        "net_patch_empty": float(row["net_patch_empty"] or 0),
    }


async def active_net_patch(conn: aiosqlite.Connection, steward_id: int) -> float:
    """撒网空网减免。过期为 0。旧档没记 empty 时按普通补丁 8%。"""
    row = await (await conn.execute(
        """
        SELECT net_patch_until, COALESCE(net_patch_empty, 0)
        FROM steward_craft WHERE steward_id=?
        """,
        (steward_id,),
    )).fetchone()
    if not row:
        return 0.0
    until = int(row[0] or 0)
    if until <= db.now():
        return 0.0
    empty = float(row[1] or 0)
    if empty > 0:
        return empty
    return float(config.CRAFT_NET_PATCH_EMPTY)


async def _weekly_tide_on(conn: aiosqlite.Connection) -> bool:
    from . import events
    pulse = await events.active_world_pulse(conn)
    return bool(pulse and pulse.get("effect_type") == "weekly_tide")


async def _window(conn: aiosqlite.Connection, s: dict[str, Any]) -> dict[str, Any]:
    return world.salvage_window(
        boat_damaged=bool(s.get("boat_damaged")),
        weekly_tide=await _weekly_tide_on(conn),
    )


async def _pans(conn: aiosqlite.Connection, steward_id: int) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT slot, brine_at FROM craft_pans WHERE steward_id=? ORDER BY slot",
        (steward_id,),
    )).fetchall()
    return [{"slot": int(r["slot"]), "brine_at": int(r["brine_at"] or 0)} for r in rows]


def _pan_progress(brine_at: int, *, now: int) -> tuple[int, int]:
    if brine_at <= 0:
        return 0, config.CRAFT_SALT_CLEAR_NEED
    got = world.clear_seconds_between(brine_at, now)
    need = config.CRAFT_SALT_CLEAR_NEED
    return min(got, need), need


def _catalog_text() -> str:
    lines = [
        "岸工坊图鉴",
        world.climate_line(),
        "",
        "配方（craft_ops 打 名称 → 好了 craft_ops 取）：",
    ]
    for meta in CRAFT_RECIPES.values():
        need = "、".join(f"{item_label(k)}x{v}" for k, v in meta["need"].items())
        lines.append(
            f"  {meta['emoji']}{meta['name']} ← {need}"
            f"（{meta['seconds'] // 60} 分 / {meta['energy']} 精力）{meta['hint']}"
        )
    lines.append("")
    lines.append(
        f"盐田：涨潮 craft_ops 灌（{config.CRAFT_SALT_FILL_ENERGY} 精力），"
        f"晴天攒满 {config.CRAFT_SALT_CLEAR_NEED // 60} 分钟再 craft_ops 收盐。"
        "雾/风不晒。比崖矿出盐慢但省镐。"
    )
    lines.append(
        "打捞：阵风中、阵风刚停的晴天、周潮或船损才能下滩。"
        "不是 tide_ops dig（铲子翻沙）。货少且脏，可能咸痰。"
    )
    lines.append("")
    lines.append("陈列柜（craft_ops 捐 套名，扣货，换称呼或装饰）：")
    for meta in EXHIBIT_SETS.values():
        lines.append(f"  {meta['emoji']}{meta['name']} — {meta['hint']}")
    return "\n".join(lines)


async def _status_text(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    prof = await ensure_profile(conn, s["id"])
    now = db.now()
    win = await _window(conn, s)
    pans = await _pans(conn, s["id"])
    lines = [
        "岸工坊",
        world.climate_line(),
        f"累计完工 {prof['crafts_total']} · 打捞 {prof['salvages_total']} 次",
    ]
    if prof["job_key"]:
        meta = CRAFT_RECIPES.get(prof["job_key"], {})
        name = meta.get("name", prof["job_key"])
        left = prof["job_ready_at"] - now
        if left <= 0:
            lines.append(f"砧上：{name} 好了 — craft_ops 取")
        else:
            lines.append(f"砧上：正在打 {name}，{_fmt_left(left)}后取")
    else:
        lines.append("砧上：空闲 — craft_ops 打 铜钉")
    if prof["net_patch_until"] > now:
        pct = int((prof.get("net_patch_empty") or config.CRAFT_NET_PATCH_EMPTY) * 100)
        if pct <= 0:
            pct = int(config.CRAFT_NET_PATCH_EMPTY * 100)
        lines.append(f"补网还在：{_fmt_left(prof['net_patch_until'] - now)}（空网 -{pct}%）")
    lines.append("盐田：")
    for p in pans:
        if p["brine_at"] <= 0:
            lines.append(f"  池{p['slot']} 空 — 涨潮 craft_ops 灌")
            continue
        got, need = _pan_progress(p["brine_at"], now=now)
        if got >= need:
            lines.append(f"  池{p['slot']} 盐壳结了 — craft_ops 收盐")
        else:
            lines.append(
                f"  池{p['slot']} 在晒 {got // 60}/{need // 60} 分晴天"
                f"{'（这会儿不是晴，暂停）' if world.current_weather() != 'clear' else ''}"
            )
    if prof["pan_count"] < config.CRAFT_SALT_PAN_MAX:
        cost = config.craft_pan_cost(prof["pan_count"] - 1)
        lines.append(f"下一池 {cost} 票 — craft_ops 开池 确认")
    if win["open"]:
        lines.append(
            f"打捞：{win['label']}开着（{win['energy']} 精力，空捞约 {int(win['empty']*100)}%）"
            " — craft_ops 打捞"
        )
    else:
        lines.append("打捞：关。等阵风、阵风后的晴天、周潮，或船损搁浅。")
    done = await (await conn.execute(
        "SELECT set_key FROM steward_exhibits WHERE steward_id=?", (s["id"],)
    )).fetchall()
    have = {r[0] for r in done}
    pending = [m["name"] for k, m in EXHIBIT_SETS.items() if k not in have]
    if pending:
        lines.append("陈列未捐：" + "、".join(pending))
    else:
        lines.append(f"陈列柜 {len(EXHIBIT_SETS)} 套齐了。")
    lines.append("指令：打 铜钉 · 打 潮纹秤锤 · 取 · 灌 · 收盐 · 打捞 · 捐 亮壳一套 · 捐 砧上全套 · 图鉴")
    return "\n".join(lines)


async def _start_job(conn: aiosqlite.Connection, s: dict[str, Any], token: str) -> str:
    prof = await ensure_profile(conn, s["id"])
    now = db.now()
    if prof["job_key"]:
        meta = CRAFT_RECIPES.get(prof["job_key"], {})
        name = meta.get("name", prof["job_key"])
        if prof["job_ready_at"] <= now:
            raise ValueError(f"{name}已经好了。先 craft_ops 取，砧上只能一件")
        raise ValueError(
            f"正在打 {name}，{_fmt_left(prof['job_ready_at'] - now)}后 craft_ops 取"
        )
    key = resolve_recipe_key(token)
    if not key:
        raise ValueError(
            f"不认识 {token or '空'}。craft_ops 图鉴 看配方，例如 craft_ops 打 铜钉"
        )
    meta = CRAFT_RECIPES[key]
    missing = []
    for item, qty in meta["need"].items():
        have = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (s["id"], item),
        )).fetchone()
        got = int(have[0] if have else 0)
        if got < qty:
            missing.append(f"{item_label(item)} x{qty}（有 {got}）")
    if missing:
        raise ValueError("缺材料：" + "、".join(missing) + "。矿走 quarry_ops 洗，毛走畜栏，木靠 plot_ops chop")
    await energy.spend(conn, s["id"], int(meta["energy"]), action="工坊")
    for item, qty in meta["need"].items():
        if not await db.take_item(conn, s["id"], item, qty):
            raise ValueError(f"扣 {item_label(item)} 失败。再试一次")
    ready = now + int(meta["seconds"])
    await conn.execute(
        """
        UPDATE steward_craft
        SET job_key=?, job_ready_at=?, job_qty=?
        WHERE steward_id=?
        """,
        (key, ready, int(meta["qty"]), s["id"]),
    )
    await db.add_chronicle(
        "craft", f"{s['name']} 开始打{meta['name']}", s["id"], conn=conn
    )
    return (
        f"开打 {meta['emoji']}{meta['name']}（-{meta['energy']} 精力）。"
        f"{meta['seconds'] // 60} 分钟后 craft_ops 取。"
        + flavor.maybe_suffix(["砧还是凉的", "盐风灌进袖口，锤子比人老实"])
    )


async def _take_job(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    prof = await ensure_profile(conn, s["id"])
    if not prof["job_key"]:
        raise ValueError("砧上是空的。craft_ops 打 铜钉")
    now = db.now()
    if prof["job_ready_at"] > now:
        meta = CRAFT_RECIPES.get(prof["job_key"], {})
        raise ValueError(
            f"{meta.get('name', prof['job_key'])}还没好，{_fmt_left(prof['job_ready_at'] - now)}"
        )
    meta = CRAFT_RECIPES[prof["job_key"]]
    qty = int(prof["job_qty"] or meta["qty"])
    await db.add_item(conn, s["id"], meta["out"], qty)
    await conn.execute(
        """
        UPDATE steward_craft
        SET job_key='', job_ready_at=0, job_qty=0, crafts_total=crafts_total+1
        WHERE steward_id=?
        """,
        (s["id"],),
    )
    await db.add_chronicle(
        "craft", f"{s['name']} 取走{meta['name']}", s["id"], conn=conn
    )
    from . import progress as progress_mod
    await progress_mod.scan_achievements(conn, s)
    extra = ""
    if meta["out"].startswith("fit_"):
        extra = f" 装上 hut_ops install soft_N {meta['out'][4:]}"
    elif meta["out"] == "craft_net_patch":
        extra = " 贴上 craft_ops 补网"
    elif meta["out"] == "craft_fog_sinker":
        extra = " 贴上 craft_ops 补网（优先用网坠，12 小时空网 -14%）"
    return (
        f"取到 {meta['emoji']}{item_label(meta['out'])} x{qty}。{extra}"
        + flavor.maybe_suffix(["手还热", "这件能用了"])
    )


async def _apply_patch(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    used = ""
    until = 0
    empty = 0.0
    if await db.take_item(conn, s["id"], "craft_fog_sinker", 1):
        used = "雾铅网坠"
        until = db.now() + config.CRAFT_FOG_SINKER_SEC
        empty = float(config.CRAFT_FOG_SINKER_EMPTY)
    elif await db.take_item(conn, s["id"], "craft_net_patch", 1):
        used = "网补丁"
        until = db.now() + config.CRAFT_NET_PATCH_SEC
        empty = float(config.CRAFT_NET_PATCH_EMPTY)
    else:
        raise ValueError(
            "没有网补丁也没有雾铅网坠。"
            "craft_ops 打 网补丁（羊毛+漂绳）或 打 雾铅网坠（雾铅+羊毛+漂绳）"
        )
    await conn.execute(
        "UPDATE steward_craft SET net_patch_until=?, net_patch_empty=? WHERE steward_id=?",
        (until, empty, s["id"]),
    )
    hours = max(1, (until - db.now()) // 3600)
    return (
        f"贴上{used}。{hours} 小时内撒网空网 -{int(empty * 100)}%。"
        "不是 tide_ops gear upgrade。"
    )


async def _fill_pan(conn: aiosqlite.Connection, s: dict[str, Any], token: str) -> str:
    if world.current_tide() != "flood":
        raise ValueError("盐田只在涨潮灌。退潮去赶海 dig，平潮等一等。craft_ops 盐田 看池")
    prof = await ensure_profile(conn, s["id"])
    pans = await _pans(conn, s["id"])
    slot = None
    raw = (token or "").strip()
    if raw.isdigit() or raw.startswith("池"):
        n = raw.replace("池", "").strip()
        if n.isdigit():
            slot = int(n)
    target = None
    if slot:
        target = next((p for p in pans if p["slot"] == slot), None)
        if target is None:
            raise ValueError(f"没有池{slot}。现有 1～{prof['pan_count']}")
        if target["brine_at"] > 0:
            raise ValueError(f"池{slot}已经灌了。等晴天晒，或 craft_ops 盐田")
    else:
        empties = [p for p in pans if p["brine_at"] <= 0]
        if not empties:
            raise ValueError("没有空池。等晒干 craft_ops 收盐，或 craft_ops 开池")
        target = empties[0]
    await energy.spend(conn, s["id"], config.CRAFT_SALT_FILL_ENERGY, action="灌盐田")
    now = db.now()
    await conn.execute(
        "UPDATE craft_pans SET brine_at=? WHERE steward_id=? AND slot=?",
        (now, s["id"], target["slot"]),
    )
    await db.add_chronicle(
        "craft", f"{s['name']} 灌了盐田池{target['slot']}", s["id"], conn=conn
    )
    return (
        f"灌进池{target['slot']}（-{config.CRAFT_SALT_FILL_ENERGY} 精力）。"
        f"晴天攒满 {config.CRAFT_SALT_CLEAR_NEED // 60} 分钟再 craft_ops 收盐。"
        "雾和风不晒。"
        + flavor.maybe_suffix(["海水比盐先到", "池底还是湿的"])
    )


async def _harvest_pan(conn: aiosqlite.Connection, s: dict[str, Any], token: str) -> str:
    pans = await _pans(conn, s["id"])
    now = db.now()
    slot = None
    raw = (token or "").strip()
    if raw.isdigit() or raw.startswith("池"):
        n = raw.replace("池", "").strip()
        if n.isdigit():
            slot = int(n)
    ready = []
    for p in pans:
        got, need = _pan_progress(p["brine_at"], now=now)
        if p["brine_at"] > 0 and got >= need:
            ready.append(p)
    target = None
    if slot:
        target = next((p for p in ready if p["slot"] == slot), None)
        if target is None:
            p = next((x for x in pans if x["slot"] == slot), None)
            if not p or p["brine_at"] <= 0:
                raise ValueError(f"池{slot}是空的。涨潮 craft_ops 灌")
            got, need = _pan_progress(p["brine_at"], now=now)
            raise ValueError(f"池{slot}还没晒够，晴天 {got // 60}/{need // 60} 分")
    else:
        if not ready:
            raise ValueError("没有结壳的池。craft_ops 盐田 看进度")
        target = ready[0]
    await energy.spend(conn, s["id"], config.CRAFT_SALT_HARVEST_ENERGY, action="收盐")
    qty = 1 + (1 if random.random() < 0.30 else 0)
    await db.add_item(conn, s["id"], "quarry_salt", qty)
    await conn.execute(
        "UPDATE craft_pans SET brine_at=0 WHERE steward_id=? AND slot=?",
        (s["id"], target["slot"]),
    )
    await db.add_chronicle(
        "craft", f"{s['name']} 收了盐田海盐晶 x{qty}", s["id"], conn=conn
    )
    return (
        f"收盐 池{target['slot']}：{item_label('quarry_salt')} x{qty}"
        f"（-{config.CRAFT_SALT_HARVEST_ENERGY} 精力）。"
        "这是晒的盐，不是 quarry_ops 洗出来的；都能下锅、升镐、陈列。"
        + flavor.maybe_suffix(["手是咸的", "比挥镐轻，比赶海慢"])
    )


async def _buy_pan(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    prof = await ensure_profile(conn, s["id"])
    if prof["pan_count"] >= config.CRAFT_SALT_PAN_MAX:
        return f"盐田最多 {config.CRAFT_SALT_PAN_MAX} 口。再开就占滩了"
    cost = config.craft_pan_cost(prof["pan_count"] - 1)
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
    have = int((await cur.fetchone())[0])
    if have < cost:
        raise ValueError(f"开池要 {cost} 票（现 {have}）")
    slot = prof["pan_count"] + 1
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"])
    )
    await conn.execute(
        "UPDATE steward_craft SET pan_count=? WHERE steward_id=?",
        (slot, s["id"]),
    )
    await conn.execute(
        "INSERT INTO craft_pans (steward_id, slot, brine_at) VALUES (?, ?, 0)",
        (s["id"], slot),
    )
    return f"新开池{slot}（-{cost} 票）。涨潮 craft_ops 灌 {slot}"


async def _salvage(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    win = await _window(conn, s)
    if not win["open"]:
        raise ValueError(
            "滩上没风暴货。阵风中、阵风后的晴天、周潮或船损才能 craft_ops 打捞。"
            "退潮翻沙是 tide_ops dig，要铲子。"
        )
    prof = await ensure_profile(conn, s["id"])
    now = db.now()
    left = int(prof["last_salvage_at"] or 0) + config.CRAFT_SALVAGE_COOLDOWN - now
    if left > 0:
        raise ValueError(f"刚捞过，{_fmt_left(left)}后再来。别跟 dig 连着点")
    day = db.day_id(now)
    used_row = await (await conn.execute(
        "SELECT count FROM craft_rolls WHERE steward_id=? AND day=?",
        (s["id"], day),
    )).fetchone()
    used = int(used_row[0] if used_row else 0)
    if used >= config.CRAFT_SALVAGE_DAILY:
        raise ValueError(
            f"今日打捞已满 {config.CRAFT_SALVAGE_DAILY} 次。风暴货就那么一点"
        )
    await energy.spend(conn, s["id"], int(win["energy"]), action="打捞")
    from . import hut as hut_mod
    hut_b = await hut_mod.get_bonuses(conn, s["id"])
    empty_chance = float(win["empty"]) * float(getattr(hut_b, "salvage_empty", 1.0) or 1.0)
    extra = ""
    got: list[tuple[str, int]] = []
    if random.random() < empty_chance:
        extra = "空捞，只捧回一把湿沙"
    else:
        table = [
            ("drift_twine", 1, 20),
            ("craft_timber", 1, 16),
            ("craft_rusty_nail", 1, 12),
            ("sea_glass", 1, 10),
            ("wet_note", 1, 8),
            ("bait_worm", 1, 8),
            ("quarry_shale", 1, 5),
            ("fish_herring", 1, 5),
        ]
        if win["kind"] != "boat":
            table.append(("shell_rough_catseye", 1, 4))
        items, weights = [r[0] for r in table], [r[2] for r in table]
        item = random.choices(items, weights=weights, k=1)[0]
        qty = 2 if item == "drift_twine" and random.random() < 0.35 else 1
        await db.add_item(conn, s["id"], item, qty)
        got.append((item, qty))
        if random.random() < 0.06:
            await db.add_item(conn, s["id"], "craft_timber", 1)
            got.append(("craft_timber", 1))
            extra += "，顺手一块岸木"
    await conn.execute(
        "UPDATE steward_craft SET last_salvage_at=?, salvages_total=salvages_total+1 WHERE steward_id=?",
        (now, s["id"]),
    )
    await conn.execute(
        """
        INSERT INTO craft_rolls (steward_id, day, last_at, count)
        VALUES (?,?,?,1)
        ON CONFLICT(steward_id, day) DO UPDATE SET
            last_at=excluded.last_at, count=count+1
        """,
        (s["id"], day, now),
    )
    ill = await health.maybe_roll_ailment(
        conn, s["id"], "salvage", chance=float(win["hazard"]), source="salvage",
    )
    boost = await health.maybe_restore_health(
        conn, s["id"], "salvage", chance=0.10, lo=4, hi=9,
    )
    disc = await commons.roll_discovery(conn, s, "salvage")
    loot = "、".join(f"{item_label(k)} x{q}" for k, q in got) if got else "没有货"
    await db.add_chronicle(
        "craft", f"{s['name']} 打捞到{loot}", s["id"], conn=conn
    )
    from . import progress as progress_mod
    await progress_mod.scan_achievements(conn, s)
    msg = (
        f"打捞（{win['label']}）：{loot}{extra}（-{win['energy']} 精力）。"
        "这不是赶海 dig，也不是出海归港。"
        + flavor.maybe_suffix(["沙子咬脚踝", "潮水把好东西藏了"])
    )
    if ill:
        msg += f"\n{ill}\n→ visit_ops clinic treat 咸痰（必须花票）"
    if boost:
        msg += f"\n{boost}"
    if disc:
        msg += f"\n{disc}"
    return msg


async def _exhibit_status(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    done = {
        r[0] for r in await (await conn.execute(
            "SELECT set_key FROM steward_exhibits WHERE steward_id=?", (s["id"],)
        )).fetchall()
    }
    lines = ["潮汐陈列柜 — 捐货换称呼或小屋装饰，系统不回收票。"]
    for key, meta in EXHIBIT_SETS.items():
        mark = "已捐" if key in done else "未捐"
        lines.append(f"  {meta['emoji']}{meta['name']}（{mark}）— {meta['hint']}")
        if key not in done:
            lines.append(f"    捐：craft_ops 捐 {meta['name']}")
    lines.append("捐出的货从行囊消失。渔获十种只看图鉴，不扣鱼。")
    return "\n".join(lines)


async def _donate(conn: aiosqlite.Connection, s: dict[str, Any], token: str) -> str:
    key = resolve_exhibit_key(token)
    if not key:
        raise ValueError(
            f"不认识 {token or '空'}。craft_ops 陈列 看套名，例如 craft_ops 捐 亮壳一套"
        )
    have = await (await conn.execute(
        "SELECT 1 FROM steward_exhibits WHERE steward_id=? AND set_key=?",
        (s["id"], key),
    )).fetchone()
    if have:
        return f"{EXHIBIT_SETS[key]['name']}已经捐过了。steward_ops 成就 看称呼"
    meta = EXHIBIT_SETS[key]
    if meta.get("need_catches"):
        from . import catches as catches_mod
        n = await catches_mod.species_count(conn, s["id"])
        need_n = int(meta["need_catches"])
        if n < need_n:
            raise ValueError(f"图鉴里才 {n} 种鱼，要 {need_n} 种。去 tide_ops net / cast")
    else:
        missing = []
        for item, qty in (meta.get("need") or {}).items():
            row = await (await conn.execute(
                "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
                (s["id"], item),
            )).fetchone()
            got = int(row[0] if row else 0)
            if got < qty:
                missing.append(f"{item_label(item)} x{qty}（有 {got}）")
        if missing:
            raise ValueError("缺：" + "、".join(missing))
        for item, qty in meta["need"].items():
            if not await db.take_item(conn, s["id"], item, qty):
                raise ValueError(f"扣 {item_label(item)} 失败")
    await conn.execute(
        "INSERT INTO steward_exhibits (steward_id, set_key, done_at) VALUES (?,?,?)",
        (s["id"], key, db.now()),
    )
    bits = [f"陈列上 {meta['emoji']}{meta['name']}。"]
    if meta.get("gift"):
        await db.add_item(conn, s["id"], meta["gift"], 1)
        bits.append(
            f"发了 {item_label(meta['gift'])}。"
            f"hut_ops install soft_N {meta['gift'][4:]}"
        )
    if key == "walkblue":
        from . import marine as marine_mod
        hex_msg = await marine_mod.walkblue_fate_event(conn, s["id"], kind="sell")
        if hex_msg:
            bits.append(hex_msg)
    await db.add_chronicle(
        "craft", f"{s['name']} 陈列了{meta['name']}", s["id"], conn=conn
    )
    from . import progress as progress_mod
    await progress_mod.scan_achievements(conn, s)
    if meta.get("title"):
        bits.append(f"称呼：steward_ops 称呼 {progress_mod.achievement_name(meta['title'])}")
    return " ".join(bits) + flavor.maybe_suffix(["柜子里亮了一下", "这排算齐了"])


async def craft_ops(key_id: int, command: str = "") -> str:
    raw = (command or "").strip()
    if not raw or raw.lower() in ("help", "?", "帮助"):
        return CRAFT_HELP
    s = await require_steward(key_id)
    parts = raw.split()
    verb = parts[0].lower()
    rest = " ".join(parts[1:])

    async with db.connect() as conn:
        await ensure_profile(conn, s["id"])
        if verb in ("status", "scan", "看", "工坊"):
            text = await _status_text(conn, s)
            await conn.commit()
            return text
        if verb in ("catalog", "图鉴", "配方"):
            await conn.commit()
            return _catalog_text()
        if verb in ("打", "craft", "make", "锤"):
            text = await _start_job(conn, s, rest)
            await conn.commit()
            return text
        if verb in ("取", "collect", "领"):
            text = await _take_job(conn, s)
            await conn.commit()
            return text
        if verb in ("补网", "patch"):
            text = await _apply_patch(conn, s)
            await conn.commit()
            return text
        if verb in ("盐田", "pans", "池"):
            text = await _status_text(conn, s)
            await conn.commit()
            return text
        if verb in ("灌", "fill", "灌池"):
            text = await _fill_pan(conn, s, rest)
            await conn.commit()
            return text
        if verb in ("收盐", "harvest", "收"):
            text = await _harvest_pan(conn, s, rest)
            await conn.commit()
            return text
        if verb in ("开池", "买池"):
            if rest in ("确认", "confirm", "买", "yes"):
                text = await _buy_pan(conn, s)
            else:
                prof = await ensure_profile(conn, s["id"])
                if prof["pan_count"] >= config.CRAFT_SALT_PAN_MAX:
                    text = f"盐田最多 {config.CRAFT_SALT_PAN_MAX} 口"
                else:
                    cost = config.craft_pan_cost(prof["pan_count"] - 1)
                    text = (
                        f"下一池 {cost} 票（现有 {prof['pan_count']} 口，顶 "
                        f"{config.CRAFT_SALT_PAN_MAX}）。付钱：craft_ops 开池 确认"
                    )
            await conn.commit()
            return text
        if verb in ("打捞", "salvage", "wreck", "捞"):
            text = await _salvage(conn, s)
            await conn.commit()
            return text
        if verb in ("陈列", "exhibit", "柜"):
            text = await _exhibit_status(conn, s)
            await conn.commit()
            return text
        if verb in ("捐", "donate", "献"):
            text = await _donate(conn, s, rest)
            await conn.commit()
            return text
        await conn.commit()

    raise ValueError(
        f"未知 craft 指令: {command}\n{CRAFT_HELP}\n"
        "不要发明 forge_ops / salvage_ops。赶海是 tide_ops dig，矿是 quarry_ops。"
    )


async def public_snapshot() -> dict[str, Any]:
    day = db.day_id()
    win = world.salvage_window()
    now = db.now()
    day_start = db.day_start(day)
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        jobs = (await (await conn.execute(
            "SELECT COUNT(*) FROM steward_craft WHERE job_key != ''"
        )).fetchone())[0]
        salv = (await (await conn.execute(
            "SELECT COALESCE(SUM(count),0) FROM craft_rolls WHERE day=?", (day,)
        )).fetchone())[0]
        exhibits = (await (await conn.execute(
            "SELECT COUNT(*) FROM steward_exhibits"
        )).fetchone())[0]
        pans = (await (await conn.execute(
            "SELECT COUNT(*) FROM craft_pans WHERE brine_at > 0"
        )).fetchone())[0]
        done = (await (await conn.execute(
            """
            SELECT COUNT(*) FROM chronicle
            WHERE action='craft' AND created_at >= ?
            """,
            (day_start,),
        )).fetchone())[0]
        active = await (await conn.execute(
            """
            SELECT c.job_key, c.job_qty, c.job_ready_at, a.name AS actor
            FROM steward_craft c
            LEFT JOIN stewards a ON a.id = c.steward_id
            WHERE c.job_key != ''
            ORDER BY c.job_ready_at ASC
            LIMIT 2
            """
        )).fetchall()
        feed = await (await conn.execute(
            """
            SELECT c.text, c.created_at, a.name AS actor
            FROM chronicle c
            LEFT JOIN stewards a ON a.id = c.actor_id
            WHERE c.action='craft'
            ORDER BY c.created_at DESC LIMIT 16
            """
        )).fetchall()
    job_cards = []
    for row in active:
        meta = CRAFT_RECIPES.get(row["job_key"], {})
        ready = int(row["job_ready_at"] or 0) <= now
        job_cards.append({
            "name": meta.get("name", row["job_key"]),
            "emoji": meta.get("emoji", "🔨"),
            "qty": int(row["job_qty"] or meta.get("qty") or 1),
            "actor": row["actor"] or "有人",
            "note": "快好了" if ready else "制作中",
        })
    return {
        "climate": world.climate_line(),
        "salvage": win["label"] if win["open"] else "打捞关着",
        "salvage_open": bool(win["open"]),
        "jobs": int(jobs or 0),
        "done_today": int(done or 0),
        "salvages_today": int(salv or 0),
        "exhibits": int(exhibits or 0),
        "pans_brined": int(pans or 0),
        "active_jobs": job_cards,
        "hints": [
            "打 铜钉 / 潮纹秤锤 / 铁锄刃 / 雾铅网坠 / 夜光滤网 → 等分钟 → 取",
            "涨潮灌盐田，晴天攒 20 分钟收盐",
            "打捞只认阵风/余滩/周潮/船损，不是 tide_ops dig",
            "陈列柜捐齐换称呼，几乎不给票。中盘捐 砧上全套",
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
    now = db.now()
    if prof["job_key"]:
        meta = CRAFT_RECIPES.get(prof["job_key"], {})
        name = meta.get("name", prof["job_key"])
        if prof["job_ready_at"] <= now:
            line = f"岸工坊：{name} 好了 · craft_ops 取"
        else:
            line = f"岸工坊：正在打 {name}"
    else:
        line = "岸工坊：砧空闲 · craft_ops 打 铜钉"
    return {
        "line": line,
        "crafts_total": prof["crafts_total"],
        "salvages_total": prof["salvages_total"],
    }

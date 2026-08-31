"""诊所 — 桥桥大夫，花钱治病 / 调理回身体，窗台斑鸠，药品货架。"""

from __future__ import annotations

import random
import time
from typing import Any

import aiosqlite

from . import config, db, flavor, health, survival
from .catalog import AILMENTS, item_label
from .clinic_copy import (
    CLINIC_MEDICINES,
    medicine_is_tonic,
    pick_atmosphere,
    pick_chat,
    pick_discount_hint,
    pick_dove_event,
    pick_greeting,
    pick_night,
    pick_tonic_done,
    pick_tonic_line,
    pick_treat_line,
    register_medicine_items,
    resolve_medicine,
    resolve_tonic_tier,
)
from .game import require_steward

register_medicine_items()

CLINIC_NIGHT_SURCHARGE = 5
CLINIC_DISCOUNT_CHANCE = 0.20
CLINIC_DISCOUNT_MULT = 0.9


def _utc_hour() -> int:
    return time.gmtime(db.now()).tm_hour


def _is_night() -> bool:
    h = _utc_hour()
    return 0 <= h < 6


def _pricing_note(*, discount: bool, night: bool) -> tuple[float, int, str]:
    bits: list[str] = []
    mult = 1.0
    add = 0
    if discount:
        mult = CLINIC_DISCOUNT_MULT
        bits.append("九折")
    if night:
        add = CLINIC_NIGHT_SURCHARGE
        bits.append(f"凌晨加 {CLINIC_NIGHT_SURCHARGE} 票")
    return mult, add, " · ".join(bits) if bits else ""


async def _maybe_dove_event(conn: aiosqlite.Connection, s: dict[str, Any]) -> str | None:
    day = db.day_id()
    if int(s.get("clinic_dove_day") or 0) == day:
        return None
    ev = pick_dove_event()
    favor = int(s.get("clinic_dove_affinity") or 0)
    mood = int(ev.get("mood") or 0)
    await conn.execute(
        """
        UPDATE stewards SET clinic_dove_day=?, clinic_dove_affinity=?
        WHERE id=?
        """,
        (day, favor + mood, s["id"]),
    )
    return ev["text"]


async def _clinic_scene(conn: aiosqlite.Connection, s: dict[str, Any]) -> tuple[str, bool, bool]:
    """进门：氛围 + 问候 + 斑鸠 + 是否九折/凌晨。"""
    lines = [pick_atmosphere(), pick_greeting()]
    dove = await _maybe_dove_event(conn, s)
    if dove:
        lines.append(dove)
    night = _is_night()
    if night:
        lines.append(pick_night())
    discount = random.random() < CLINIC_DISCOUNT_CHANCE
    if discount:
        lines.append(pick_discount_hint())
    return "\n".join(lines), discount, night


def _tonic_menu(*, cost_mult: float = 1.0, cost_add: int = 0) -> list[str]:
    lines = [
        "调理价目（无病回身体，不治病症；贵是故意的）:",
    ]
    for key, meta in config.CLINIC_TONIC_TIERS.items():
        billed = health._bill_cost(int(meta["price"]), cost_mult=cost_mult, cost_add=cost_add)  # noqa: SLF001
        lines.append(
            f"  {meta['label']}（clinic 调理 {key}）— 身体 +{meta['heal']} · {billed} 票"
        )
    lines.append(
        f"本换班日现场调理最多 {config.CLINIC_TONIC_DAILY_CAP} 次"
        "（clinic buy 回春汤 / 大补丸 可囤，不占次数）"
    )
    lines.append("有病先 treat；调理和治病是两回事。")
    return lines


async def _do_tonic(
    conn: aiosqlite.Connection,
    s: dict[str, Any],
    tier: str,
    *,
    cost_mult: float = 1.0,
    cost_add: int = 0,
) -> str:
    meta = config.CLINIC_TONIC_TIERS[tier]
    heal = int(meta["heal"])
    cost = health._bill_cost(int(meta["price"]), cost_mult=cost_mult, cost_add=cost_add)  # noqa: SLF001
    day = db.day_id()
    tonic_day = int(s.get("clinic_tonic_day") or 0)
    used = int(s.get("clinic_tonic_count") or 0) if tonic_day == day else 0
    if used >= config.CLINIC_TONIC_DAILY_CAP:
        raise ValueError(
            f"今天现场调理已满 {config.CLINIC_TONIC_DAILY_CAP} 次。"
            "可 clinic buy 回春汤 / 大补丸 囤着自己喝，不占次数。"
        )
    cur = await conn.execute("SELECT tickets, health FROM stewards WHERE id=?", (s["id"],))
    tickets, body = (await cur.fetchone())
    if int(body) >= 100:
        raise ValueError("身体已经满分，别浪费票——桥桥不收「没事找事」的冤枉钱")
    if tickets < cost:
        raise ValueError(f"{meta['label']}要 {cost} 票，你只有 {tickets} 票——桥桥大夫不赊账")
    gain = min(heal, 100 - int(body))
    await conn.execute(
        """
        UPDATE stewards
        SET tickets=tickets-?, health=MIN(100, health+?),
            clinic_tonic_day=?, clinic_tonic_count=?
        WHERE id=?
        """,
        (cost, gain, day, used + 1, s["id"]),
    )
    from . import tax as tax_mod
    await tax_mod.record_life_spend(conn, s["id"], cost, "clinic")
    left = config.CLINIC_TONIC_DAILY_CAP - (used + 1)
    return (
        f"{pick_tonic_done()}\n"
        f"{meta['label']}完成（-{cost} 票 · 身体 +{gain}）。"
        f"今日现场调理还剩 {left} 次。"
    )


async def _buy_medicine(
    conn: aiosqlite.Connection,
    s: dict[str, Any],
    med_key: str,
    qty: int,
    *,
    cost_mult: float = 1.0,
    cost_add: int = 0,
) -> str:
    meta = CLINIC_MEDICINES[med_key]
    unit = health._bill_cost(int(meta["price"]), cost_mult=cost_mult, cost_add=cost_add)  # noqa: SLF001
    cost = unit * qty
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
    tickets = (await cur.fetchone())[0]
    if tickets < cost:
        raise ValueError(f"买 {meta['name']} 要 {cost} 票，你只有 {tickets} 票")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]),
    )
    from . import tax as tax_mod
    await tax_mod.record_life_spend(conn, s["id"], cost, "clinic")
    await db.add_item(conn, s["id"], med_key, qty)
    hint = meta.get("hint", "")
    extra = f"（{hint}）" if hint else ""
    return f"购入 {meta['emoji']}{meta['name']} x{qty}（-{cost} 票）{extra}"


async def _use_medicine(conn: aiosqlite.Connection, s: dict[str, Any], med_key: str) -> str:
    meta = CLINIC_MEDICINES[med_key]
    if not await db.take_item(conn, s["id"], med_key, 1):
        raise ValueError(f"行囊里没有 {meta['name']}，先 clinic buy {meta['name']}")

    # 回春汤 / 大补丸：无病回身体
    if medicine_is_tonic(meta):
        heal = int(meta["heal"])
        cur = await conn.execute("SELECT health FROM stewards WHERE id=?", (s["id"],))
        body = int((await cur.fetchone())[0])
        if body >= 100:
            await db.add_item(conn, s["id"], med_key, 1)
            raise ValueError("身体已经满分，药先留着——别浪费贵东西")
        gain = min(heal, 100 - body)
        await conn.execute(
            "UPDATE stewards SET health=MIN(100, health+?) WHERE id=?",
            (gain, s["id"]),
        )
        return (
            f"服下 {meta['emoji']}{meta['name']}，气色回了一截（身体 +{gain}）。"
            "这药不治病症；有病仍要 treat。"
        )

    ailment = meta["ailment"]
    ailments = await health.list_ailments(conn, s["id"])
    hit = next((a for a in ailments if a["key"] == ailment), None)
    if not hit:
        await db.add_item(conn, s["id"], med_key, 1)
        raise ValueError(f"你现在没有 {AILMENTS[ailment]['name']}，药先留着")
    if health.bridge_refuses(hit):
        await db.add_item(conn, s["id"], med_key, 1)
        raise ValueError(health._pit_refuse())  # noqa: SLF001
    wait_halve = bool(meta.get("infection_wait_halve"))
    if hit["chronic"]:
        msg = await health._apply_chronic_course(  # noqa: SLF001
            conn, s["id"], hit, wait_halve=wait_halve, free=True,
        )
    else:
        await conn.execute(
            "DELETE FROM steward_ailments WHERE steward_id=? AND ailment_key=?",
            (s["id"], ailment),
        )
        heal = AILMENTS[ailment].get("health_restore", 8)
        await conn.execute(
            "UPDATE stewards SET health=MIN(100, health+?) WHERE id=?",
            (heal, s["id"]),
        )
        msg = f"用了 {meta['emoji']}{meta['name']}，{AILMENTS[ailment]['emoji']}{AILMENTS[ailment]['name']}好了（身体 +{heal}）"
    flavor_line = pick_treat_line(ailment)
    return "\n".join(x for x in [flavor_line, msg] if x)


async def _dove_status(s: dict[str, Any]) -> str:
    favor = int(s.get("clinic_dove_affinity") or 0)
    lines = [
        f"窗台斑鸠窝（好感 {favor}）",
        "灰扑扑的咕咕斑鸠蹲在窝里，偶尔歪头看你。",
    ]
    if favor >= 6:
        lines.append("它看见你会主动咕两声，算是认得了。")
    lines.append("喂食：clinic dove 喂（耗雾豌豆×1，好感+2，每天斑鸠事件最多1次）")
    return "\n".join(lines)


async def _dove_feed(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    item = "crop_fogpea"
    if not await db.take_item(conn, s["id"], item, 1):
        raise ValueError("喂斑鸠要雾豌豆×1（crop_fogpea）")
    favor = int(s.get("clinic_dove_affinity") or 0) + 2
    await conn.execute(
        "UPDATE stewards SET clinic_dove_affinity=? WHERE id=?",
        (favor, s["id"]),
    )
    await survival.bump(conn, s["id"], standing=1)
    from . import bond as bond_mod
    await bond_mod.grant(conn, s["id"], bond_mod.DOVE_FEED, "people")
    return (
        "斑鸠啄了你递过去的雾豌豆，满意地咕了一声。\n"
        f"窗台斑鸠好感 +2（现 {favor}）· 档信 +1"
    )


async def clinic_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "status"

    scene_verbs = {
        "status", "visit", "enter", "进", "catalog", "价目", "chat", "闲聊",
        "dove", "斑鸠", "窗台", "buy", "买", "use", "用", "treat", "治",
        "调理", "rest", "tonic", "补", "养生",
    }

    if verb in scene_verbs:
        async with db.connect() as conn:
            scene, discount, night = await _clinic_scene(conn, s)
            mult, add, price_note = _pricing_note(discount=discount, night=night)
            await conn.commit()
        s = await db.get_steward_by_id(s["id"]) or s
    else:
        scene, discount, night = "", False, _is_night()
        mult, add, price_note = _pricing_note(discount=discount, night=night)

    if verb in ("status", "enter", "进"):
        async with db.connect() as conn:
            s = await db.get_steward_by_id(s["id"]) or s
            ailments = await health.list_ailments(conn, s["id"])
        lines = [scene, "", "桥桥大夫诊所（24 小时，必须花票，不赊账）", health.meter_line(s, ailments)]
        if price_note:
            lines.append(f"今日价：{price_note}")
        lines.append(
            "指令: treat 病症 / treat all · 调理 小|中|大 · buy 药品 · use 药品 · dove 窗台 · chat 闲聊 · catalog"
        )
        lines.extend(_tonic_menu(cost_mult=mult, cost_add=add))
        if not ailments:
            lines.append("目前没挂号项——没病可 clinic 调理 回身体（贵）")
            return "\n".join(lines)
        lines.append("待治:")
        bridge_ailments = [a for a in ailments if not health.bridge_refuses(a)]
        pit_ailments = [a for a in ailments if health.bridge_refuses(a)]
        total = 0
        for a in bridge_ailments:
            billed = health._bill_cost(a["cost"], cost_mult=mult, cost_add=add)  # noqa: SLF001
            total += billed
            extra = f"{a['hint']} · 诊费约 {billed} 票"
            if a.get("chronic"):
                stage = a.get("stage_name") or f"{a.get('remaining_courses', 1)}档"
                extra += f" · {stage}，疗程还剩 {a.get('remaining_courses', 1)} 次"
                if a.get("treat_ready"):
                    extra += " · 现在可压一档"
                else:
                    extra += f" · 还需歇 {health.fmt_wait(a['treat_wait'])}"
            lines.append(f"  {a['key']} — {a['emoji']}{a['name']} （{extra}）")
        if pit_ailments:
            lines.append("井下伤（桥桥不接，找晏安医务间）:")
            for a in pit_ailments:
                lines.append(f"  {a['key']} — {a['emoji']}{a['name']} （{a['hint']}）")
        if bridge_ailments:
            lines.append(f"地上病全套约 {total} 票 · visit_ops clinic treat all")
        elif pit_ailments:
            lines.append("只有井下伤 — undertide_ops medic …（晏安医务间）")
        return "\n".join(lines)

    if verb in ("visit", "chat", "闲聊"):
        msg = scene + "\n\n" + (pick_chat() if verb != "visit" else random.choice([
            "桥桥大夫推推眼镜：「随机事件搞出来的病，找随机事件哭去——诊费照收。」",
            "桥桥大夫：「咕咕斑鸠伤不得，你扭了脚可得花钱。」",
            "桥桥大夫指价目表：「看清数字再开口，我不还价。调理更贵。」",
        ]))
        async with db.connect() as conn:
            ailments = await health.list_ailments(conn, s["id"])
        if ailments:
            bridge = [a for a in ailments if not health.bridge_refuses(a)]
            total = sum(
                health._bill_cost(a["cost"], cost_mult=mult, cost_add=add)  # noqa: SLF001
                for a in bridge
            )
            if bridge:
                msg += f"\n当前 {len(bridge)} 项地上病待治，合计约 {total} 票。"
            if len(ailments) > len(bridge):
                msg += f"\n另有 {len(ailments) - len(bridge)} 项井下伤，桥桥不接，找晏安医务间。"
        else:
            body = int(s.get("health") or 100)
            if body < 100:
                msg += f"\n没挂病，但身体 {body}/100——可 clinic 调理 小|中|大 回气色（贵）。"
            else:
                msg += "\n你看上去暂时不用破费。"
        return msg

    if verb in ("dove", "斑鸠", "窗台"):
        sub = parts[1].lower() if len(parts) > 1 else "status"
        if sub in ("喂", "feed"):
            async with db.connect() as conn:
                msg = await _dove_feed(conn, s)
                await conn.commit()
            return scene + "\n\n" + msg
        return scene + "\n\n" + await _dove_status(s)

    if verb in ("catalog", "价目", "shop"):
        lines = [scene, "", "药品货架（clinic buy 药名 · use 药名 · 也可直接 treat 花钱治）:"]
        for key, meta in CLINIC_MEDICINES.items():
            if medicine_is_tonic(meta):
                hint = meta.get("hint") or f"无病回身体 +{meta['heal']}"
                lines.append(
                    f"  {meta['emoji']}{meta['name']}（{key}） {meta['price']}票 "
                    f"→ 身体 +{meta['heal']} · {hint}"
                )
                continue
            ail = AILMENTS.get(meta["ailment"], {})
            hint = meta.get("hint") or ail.get("hint", "")
            lines.append(
                f"  {meta['emoji']}{meta['name']}（{key}） {meta['price']}票 "
                f"→ {ail.get('emoji', '')}{ail.get('name', meta['ailment'])} · {hint}"
            )
        lines.append("")
        lines.extend(_tonic_menu(cost_mult=mult, cost_add=add))
        lines.append("病症 treat 键名见 visit_ops clinic status")
        return "\n".join(lines)

    if verb in ("调理", "rest", "tonic", "补", "养生"):
        tier_token = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
        tier = resolve_tonic_tier(tier_token) if tier_token else None
        if not tier:
            # 裸写 rest / 调理：展示价目；若写了无法识别的档位也提示
            lines = [scene, "", pick_tonic_line()]
            if tier_token:
                lines.append(f"未知档位「{tier_token}」。用 小 / 中 / 大。")
            lines.extend(_tonic_menu(cost_mult=mult, cost_add=add))
            if price_note:
                lines.append(f"（{price_note}）")
            return "\n".join(lines)
        async with db.connect() as conn:
            s = await db.get_steward_by_id(s["id"]) or s
            msg = await _do_tonic(conn, s, tier, cost_mult=mult, cost_add=add)
            await db.add_chronicle("clinic", f"{s['name']} {msg}", s["id"], conn=conn)
            await conn.commit()
        if price_note:
            msg += f"\n（{price_note}）"
        return scene + "\n\n" + pick_tonic_line() + "\n" + msg

    if verb in ("buy", "买") and len(parts) >= 2:
        med = resolve_medicine(" ".join(parts[1:]))
        if not med:
            raise ValueError("未知药品，clinic catalog 看货架")
        qty = 1
        async with db.connect() as conn:
            msg = await _buy_medicine(conn, s, med, qty, cost_mult=mult, cost_add=add)
            await conn.commit()
        return scene + "\n\n" + msg

    if verb in ("use", "用", "服") and len(parts) >= 2:
        med = resolve_medicine(" ".join(parts[1:]))
        if not med:
            raise ValueError("未知药品")
        async with db.connect() as conn:
            msg = await _use_medicine(conn, s, med)
            await db.add_chronicle("clinic", f"{s['name']} {msg}", s["id"], conn=conn)
            await conn.commit()
        return scene + "\n\n" + msg

    if verb == "treat" and len(parts) >= 2:
        target = " ".join(parts[1:]).strip().lower()
        async with db.connect() as conn:
            # 无标药盒：就医自动抵扣一次，本次治疗费减半（消耗）
            treat_mult = mult
            pill_note = ""
            if await db.take_item(conn, s["id"], "ut_unmarked_pillbox", 1):
                treat_mult = mult * 0.5
                pill_note = "（无标药盒抵扣，诊费减半）"
            if target in ("all", "全部", "打包"):
                msg = await health.treat_all(
                    conn, s["id"], cost_mult=treat_mult, cost_add=add, allow_pit=False,
                )
            else:
                from .catalog import resolve_ailment_key

                resolved = resolve_ailment_key(target) or target
                msg = await health.treat_one(
                    conn, s["id"], target,
                    cost_mult=treat_mult, cost_add=add, allow_pit=False,
                )
                line = pick_treat_line(resolved)
                if line:
                    msg = line + "\n" + msg
            if pill_note:
                msg += f"\n{pill_note}"
            await db.add_chronicle("clinic", f"{s['name']} {msg}", s["id"], conn=conn)
            await conn.commit()
        if price_note:
            msg += f"\n（{price_note}）"
        return scene + "\n\n" + msg

    raise ValueError(
        "未知 clinic 指令: "
        f"{command}（status / treat 病症|all / 调理 小|中|大 / buy 药品 / use 药品 / dove / chat / catalog）"
    )


def _sku(
    *,
    sid: str,
    kind: str,
    name: str,
    emoji: str,
    note: str,
    price: str,
    can: bool,
    target: str = "",
    detail: str = "",
) -> dict[str, Any]:
    return {
        "id": sid,
        "kind": kind,
        "name": name,
        "emoji": emoji,
        "note": note,
        "detail": detail or note,
        "price": price,
        "can": can,
        "target": target or sid,
    }


async def player_view(conn: aiosqlite.Connection, s: dict[str, Any]) -> dict[str, Any]:
    """给 /island 乔乔诊所。数值仍走 clinic_ops，这里只摊开能点的。"""
    ailments = await health.list_ailments(conn, s["id"])
    cur = await conn.execute(
        "SELECT item, quantity FROM satchel WHERE steward_id=? AND quantity>0",
        (s["id"],),
    )
    stock = {row[0]: int(row[1]) for row in await cur.fetchall()}
    tickets = int(s.get("tickets") or 0)
    body = int(s.get("health") or 100)
    day = db.day_id()
    tonic_used = int(s.get("clinic_tonic_count") or 0) if int(s.get("clinic_tonic_day") or 0) == day else 0
    tonic_left = max(0, config.CLINIC_TONIC_DAILY_CAP - tonic_used)
    favor = int(s.get("clinic_dove_affinity") or 0)
    peas = int(stock.get("crop_fogpea") or 0)
    meter = health.meter_line(s, ailments)
    bridge = [a for a in ailments if not health.bridge_refuses(a)]
    pit = [a for a in ailments if health.bridge_refuses(a)]
    if bridge:
        line = f"桥桥在。地上病 {len(bridge)} 项。{meter}"
    elif pit:
        line = f"桥桥在。井下伤她不接，找晏安。{meter}"
    elif body < 100:
        line = f"桥桥在。没挂号，身体 {body}/100，可调理（贵）。"
    else:
        line = "桥桥在。地上的病来看病，没病可调理，药架能买，窗台能喂斑鸠。"

    treat_items: list[dict[str, Any]] = []
    if bridge:
        treat_all_cost = sum(health._bill_cost(a["cost"]) for a in bridge)  # noqa: SLF001
        treat_items.append(_sku(
            sid="treat-all",
            kind="treat",
            name="一次尽量治完",
            emoji="🩺",
            note=f"地上病 {len(bridge)} 项，合计约 {treat_all_cost} 票。井下伤不接。",
            detail="visit_ops clinic treat all 同一套。诊费偏高，不赊账。慢性病要歇够间隔。",
            price=f"{treat_all_cost}票",
            can=tickets >= treat_all_cost and all(a.get("treat_ready") for a in bridge),
            target="all",
        ))
        for a in bridge:
            billed = health._bill_cost(a["cost"])  # noqa: SLF001
            extra = a.get("hint") or ""
            if a.get("chronic"):
                extra = f"{a.get('stage_name') or ''} · 疗程还剩 {a.get('remaining_courses', 1)} 次"
                if a.get("treat_ready"):
                    extra += " · 现在可压一档"
                else:
                    extra += f" · 还需歇 {health.fmt_wait(a['treat_wait'])}"
            can = bool(a.get("treat_ready")) and tickets >= billed
            treat_items.append(_sku(
                sid=f"treat-{a['key']}",
                kind="treat",
                name=a["name"],
                emoji=a.get("emoji") or "🩹",
                note=extra or f"诊费约 {billed} 票",
                detail=f"{a.get('hint') or ''} 诊费约 {billed} 票。{extra}".strip(),
                price=f"{billed}票",
                can=can,
                target=a["key"],
            ))
    else:
        treat_items.append(_sku(
            sid="treat-none",
            kind="look",
            name="目前没挂号",
            emoji="🩺",
            note="没病可点调理回气色（贵）。井下伤找晏安，桥桥不接。",
            detail="上手页和 visit_ops clinic status 同一家。没病别硬治。",
            price="看",
            can=True,
            target="status",
        ))
    for a in pit:
        treat_items.append(_sku(
            sid=f"pit-{a['key']}",
            kind="look",
            name=f"{a['name']}（井下）",
            emoji=a.get("emoji") or "🩹",
            note="桥桥不接。去井下找晏安医务间。",
            detail=a.get("hint") or "井下伤归晏安。",
            price="看",
            can=True,
            target="status",
        ))

    tonic_items: list[dict[str, Any]] = []
    for key, meta in config.CLINIC_TONIC_TIERS.items():
        billed = health._bill_cost(int(meta["price"]))  # noqa: SLF001
        if body >= 100:
            note = "身体已经满分，别浪费票。"
            can = False
        elif tonic_left <= 0:
            note = "今天现场调理满了。药架买回春汤、大补丸不占次数。"
            can = False
        elif tickets < billed:
            note = f"要 {billed} 票，口袋 {tickets}。桥桥不赊账。"
            can = False
        else:
            note = f"无病回身体 +{meta['heal']}。今日还剩 {tonic_left} 次。"
            can = True
        tonic_items.append(_sku(
            sid=f"tonic-{key}",
            kind="tonic",
            name=meta["label"],
            emoji="💉",
            note=note,
            detail=f"{meta['label']}：身体 +{meta['heal']}，{billed} 票。不治病。visit_ops clinic 调理 {key}。",
            price=f"{billed}票",
            can=can,
            target=key,
        ))

    shelf_items: list[dict[str, Any]] = []
    for key, meta in CLINIC_MEDICINES.items():
        billed = health._bill_cost(int(meta["price"]))  # noqa: SLF001
        have = int(stock.get(key) or 0)
        hint = meta.get("hint") or ""
        if medicine_is_tonic(meta):
            hint = hint or f"无病回身体 +{meta['heal']}；不治病。"
        can_buy = tickets >= billed
        shelf_items.append(_sku(
            sid=f"buy-{key}",
            kind="buy",
            name=meta["name"],
            emoji=meta.get("emoji") or "💊",
            note=(f"袋里 {have}。{hint}" if have else hint) or f"{billed} 票",
            detail=f"clinic buy {meta['name']}。{hint}",
            price=f"{billed}票",
            can=can_buy,
            target=meta["name"],
        ))
        if have:
            shelf_items.append(_sku(
                sid=f"use-{key}",
                kind="use",
                name=f"服用{meta['name']}",
                emoji=meta.get("emoji") or "💊",
                note=f"袋里 {have}。{hint}",
                detail=f"clinic use {meta['name']}。{hint}",
                price="服",
                can=True,
                target=meta["name"],
            ))

    dove_items = [
        _sku(
            sid="dove-feed",
            kind="dove",
            name="喂斑鸠",
            emoji="🕊️",
            note=f"雾豌豆×1，好感+2（现 {favor}）。袋里豌豆 {peas}。"
            if peas else "要雾豌豆×1。去份地种雾豌豆。",
            detail="visit_ops clinic dove 喂。耗雾豌豆×1，好感+2。",
            price="喂" if peas else "看",
            can=peas > 0,
            target="喂",
        ),
        _sku(
            sid="dove-look",
            kind="look",
            name="看窗台",
            emoji="🪟",
            note=f"斑鸠好感 {favor}。",
            detail="clinic dove 看窝。喂雾豌豆才加好感。",
            price="看",
            can=True,
            target="dove",
        ),
        _sku(
            sid="chat",
            kind="chat",
            name="跟桥桥闲聊",
            emoji="💬",
            note="听她损两句。不治病。",
            detail="visit_ops clinic chat。",
            price="聊",
            can=True,
            target="chat",
        ),
    ]

    treat_badge = str(len(bridge)) if bridge else ""
    tabs = [
        {"key": "treat", "label": "看病", "badge": treat_badge},
        {"key": "tonic", "label": "调理", "badge": str(tonic_left) if tonic_left < config.CLINIC_TONIC_DAILY_CAP else ""},
        {"key": "shelf", "label": "药架", "badge": ""},
        {"key": "dove", "label": "窗台", "badge": ""},
    ]
    return {
        "name": "乔乔诊所",
        "line": line,
        "tabs": tabs,
        "items": {
            "treat": treat_items,
            "tonic": tonic_items,
            "shelf": shelf_items,
            "dove": dove_items,
        },
    }

"""诊所 — 桥桥大夫，花钱治病，窗台斑鸠，药品货架。"""

from __future__ import annotations

import random
import time
from typing import Any

import aiosqlite

from . import config, db, flavor, health, survival
from .catalog import AILMENTS, item_label
from .clinic_copy import (
    CLINIC_MEDICINES,
    pick_atmosphere,
    pick_chat,
    pick_discount_hint,
    pick_dove_event,
    pick_greeting,
    pick_night,
    pick_treat_line,
    register_medicine_items,
    resolve_medicine,
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
    await db.add_item(conn, s["id"], med_key, qty)
    hint = meta.get("hint", "")
    extra = f"（{hint}）" if hint else ""
    return f"购入 {meta['emoji']}{meta['name']} x{qty}（-{cost} 票）{extra}"


async def _use_medicine(conn: aiosqlite.Connection, s: dict[str, Any], med_key: str) -> str:
    meta = CLINIC_MEDICINES[med_key]
    ailment = meta["ailment"]
    if not await db.take_item(conn, s["id"], med_key, 1):
        raise ValueError(f"行囊里没有 {meta['name']}，先 clinic buy {meta['name']}")
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

    scene_verbs = {"status", "visit", "enter", "进", "catalog", "价目", "chat", "闲聊", "dove", "斑鸠", "窗台"}

    if verb in scene_verbs or verb in ("buy", "买", "use", "用", "treat", "治"):
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
            "指令: treat 病症 / treat all · buy 药品 · use 药品 · dove 窗台 · chat 闲聊 · catalog"
        )
        if not ailments:
            lines.append("目前没挂号项——别装病")
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
            "桥桥大夫指价目表：「看清数字再开口，我不还价。」",
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
            ail = AILMENTS.get(meta["ailment"], {})
            hint = meta.get("hint") or ail.get("hint", "")
            lines.append(
                f"  {meta['emoji']}{meta['name']}（{key}） {meta['price']}票 "
                f"→ {ail.get('emoji', '')}{ail.get('name', meta['ailment'])} · {hint}"
            )
        lines.append("")
        lines.append("病症 treat 键名见 visit_ops clinic status")
        return "\n".join(lines)

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
            if target in ("all", "全部", "打包"):
                msg = await health.treat_all(
                    conn, s["id"], cost_mult=mult, cost_add=add, allow_pit=False,
                )
            else:
                from .catalog import resolve_ailment_key

                resolved = resolve_ailment_key(target) or target
                msg = await health.treat_one(
                    conn, s["id"], target,
                    cost_mult=mult, cost_add=add, allow_pit=False,
                )
                line = pick_treat_line(resolved)
                if line:
                    msg = line + "\n" + msg
            await db.add_chronicle("clinic", f"{s['name']} {msg}", s["id"], conn=conn)
            await conn.commit()
        if price_note:
            msg += f"\n（{price_note}）"
        return scene + "\n\n" + msg

    raise ValueError(
        "未知 clinic 指令: "
        f"{command}（status / treat 病症|all / buy 药品 / use 药品 / dove / chat / catalog）"
    )

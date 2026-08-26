"""身体状况 — 随机事件致病，桥桥大夫诊所花钱治。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import config, db, flavor
from .catalog import (
    AILMENTS,
    PIT_AILMENTS,
    ailment_courses,
    is_chronic_ailment,
    resolve_ailment_key,
)

TRIGGER_AILMENTS: dict[str, list[str]] = {
    "tend": ["sprain", "backache", "blister", "cut", "allergy", "exhaustion", "damp_lung"],
    "gather": ["sprain", "backache", "blister", "allergy", "exhaustion", "toothache"],
    "sow": ["sprain", "backache", "cut"],
    "forage": ["allergy", "blister", "cut", "dehydration"],
    "net": ["jelly_sting", "cold", "shell_scratch", "dehydration"],
    "pen_feed": ["cut", "blister"],
    "pen_harvest": ["cut", "crab_pinch"],
    "pen_stock": ["cut"],
    "voyage_depart": ["cold", "food_poison", "backache", "damp_lung"],
    "voyage_return": ["cold", "food_poison", "backache"],
    "guild": ["blister"],
    "brew": ["food_poison", "damp_lung"],
    "beach": ["shell_scratch", "sunburn", "crab_pinch", "dehydration"],
    "quarry": ["rock_dust", "sprain", "backache", "blister", "cut"],
    "salvage": ["wreck_cough", "shell_scratch", "cold", "dehydration"],
    "bar_shift": ["hangover"],
    "naval_bad": ["cold", "food_poison", "backache"],
    "farm_wild": ["sprain", "allergy", "blister"],
    "insomnia": ["insomnia"],
}


def _stage_name(key: str, stage: int) -> str:
    names = AILMENTS.get(key, {}).get("stage_names") or {}
    return str(names.get(stage) or names.get(str(stage)) or "")


def _effective_stage(key: str, raw_stage: int) -> int:
    if not is_chronic_ailment(key):
        return 0
    if raw_stage > 0:
        return int(raw_stage)
    return ailment_courses(key)


def fmt_wait(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h and m:
        return f"{h}小时{m}分"
    if h:
        return f"{h}小时"
    if m:
        return f"{m}分钟"
    return "片刻"


def _treat_wait(last_treat_at: int, now: int | None = None) -> int:
    now = config_now(now)
    last = int(last_treat_at or 0)
    if last <= 0:
        return 0
    ready_at = last + int(config.INFECTION_TREAT_COOLDOWN)
    return max(0, ready_at - now)


def config_now(now: int | None = None) -> int:
    return int(now) if now is not None else db.now()


def _enrich(row: Any, now: int) -> dict[str, Any]:
    key = row["ailment_key"]
    meta = AILMENTS.get(key, {})
    source = row["source"]
    pit_sourced = key in PIT_AILMENTS or source == "pit"
    hint = meta.get("hint", "")
    if source == "pit":
        hint = (
            f"深坑打架落下的 — undertide_ops medic {key}"
            if key in PIT_AILMENTS
            else f"深坑打架轻伤 — undertide_ops medic {key}"
        )
    stage = _effective_stage(key, int(row["stage"] or 0) if "stage" in row.keys() else 0)
    last_treat = int(row["last_treat_at"] or 0) if "last_treat_at" in row.keys() else 0
    wait = _treat_wait(last_treat, now) if is_chronic_ailment(key) else 0
    courses = ailment_courses(key)
    remaining = stage if is_chronic_ailment(key) else 1
    return {
        "key": key,
        "name": meta.get("name", key),
        "emoji": meta.get("emoji", "🩹"),
        "cost": meta.get("cost", 0),
        "hint": hint,
        "source": source,
        "pit_sourced": pit_sourced,
        "inflicted_at": row["inflicted_at"],
        "stage": stage,
        "stage_name": _stage_name(key, stage),
        "courses": courses,
        "remaining_courses": remaining,
        "last_tick_at": int(row["last_tick_at"] or 0) if "last_tick_at" in row.keys() else 0,
        "last_treat_at": last_treat,
        "treat_wait": wait,
        "treat_ready": wait <= 0,
        "chronic": is_chronic_ailment(key),
        "pit": key in PIT_AILMENTS,
    }


def bridge_refuses(ailment: dict[str, Any]) -> bool:
    """桥桥诊所不接井下/斗场伤（含深坑落下的普通扭伤）。"""
    return bool(ailment.get("pit_sourced"))


def _pit_refuse() -> str:
    return (
        "桥桥大夫：「井下打的？找晏安去。"
        "我不收拾你们自己找揍留下的东西。」\n"
        "（undertide_ops medic ring_shock|pit_trauma|sprain|backache — 晏安医务间）"
    )


async def list_ailments(conn: aiosqlite.Connection, steward_id: int) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """
        SELECT ailment_key, source, inflicted_at, stage, last_tick_at, last_treat_at
        FROM steward_ailments
        WHERE steward_id=? ORDER BY inflicted_at
        """,
        (steward_id,),
    )).fetchall()
    now = db.now()
    return [_enrich(r, now) for r in rows]


async def has_chronic_drain(conn: aiosqlite.Connection, steward_id: int) -> bool:
    cur = await conn.execute(
        "SELECT ailment_key FROM steward_ailments WHERE steward_id=?",
        (steward_id,),
    )
    rows = await cur.fetchall()
    for row in rows:
        key = row[0]
        if int(AILMENTS.get(key, {}).get("drain_energy", 0) or 0) > 0:
            return True
    return False


async def inflict(
    conn: aiosqlite.Connection,
    steward_id: int,
    ailment_key: str,
    *,
    source: str = "event",
) -> str | None:
    if ailment_key not in AILMENTS:
        return None
    meta = AILMENTS[ailment_key]
    now = db.now()
    cur = await conn.execute(
        """
        SELECT stage, last_treat_at FROM steward_ailments
        WHERE steward_id=? AND ailment_key=?
        """,
        (steward_id, ailment_key),
    )
    existing = await cur.fetchone()
    loss = meta.get("health_loss", 8)
    await conn.execute(
        "UPDATE stewards SET health = MAX(0, health - ?) WHERE id=?",
        (loss, steward_id),
    )
    name = f"{meta['emoji']}{meta['name']}"
    if existing:
        if not is_chronic_ailment(ailment_key):
            return None
        stage = ailment_courses(ailment_key)
        await conn.execute(
            """
            UPDATE steward_ailments
            SET stage=?, last_tick_at=?, source=?
            WHERE steward_id=? AND ailment_key=?
            """,
            (stage, now, source, steward_id, ailment_key),
        )
        stage_name = _stage_name(ailment_key, stage) or "重症"
        re_line = meta.get("re_line") or (
            "生肉又下肚，{name}烧回{stage_name}。"
            "桥桥一次压不干净，visit_ops clinic treat infection 连看几次。"
        )
        return re_line.format(name=name, stage_name=stage_name)
    stage = ailment_courses(ailment_key) if is_chronic_ailment(ailment_key) else 0
    last_tick = now if is_chronic_ailment(ailment_key) else 0
    await conn.execute(
        """
        INSERT INTO steward_ailments
            (steward_id, ailment_key, source, inflicted_at, stage, last_tick_at, last_treat_at)
        VALUES (?,?,?,?,?,?,0)
        """,
        (steward_id, ailment_key, source, now, stage, last_tick),
    )
    line = flavor.fill(
        flavor.pick(flavor.AILMENT_INFlict_LINES),
        name=name,
        hint=meta.get("hint", ""),
    )
    if is_chronic_ailment(ailment_key):
        line += meta.get("chronic_tip") or (
            " 菌压不干净，visit_ops clinic treat infection 约三次、两次间隔 6 小时；"
            "第一次可以马上挂。"
        )
    return line


async def maybe_infect_raw_meat(
    conn: aiosqlite.Connection,
    steward_id: int,
    *,
    force: bool | None = None,
) -> str | None:
    if force is False:
        return None
    if force is not True and random.random() >= config.RAW_MEAT_INFECT_CHANCE:
        return None
    return await inflict(conn, steward_id, "infection", source="raw_meat")


async def maybe_insomnia(conn: aiosqlite.Connection, steward_id: int) -> str | None:
    """连续多天没睡床 → 失眠。"""
    row = await (await conn.execute(
        "SELECT bed_rest_at FROM stewards WHERE id=?", (steward_id,)
    )).fetchone()
    last = int(row[0] if row else 0)
    if last and db.day_id() - db.day_id(last) < 3:
        return None
    return await maybe_roll_ailment(
        conn, steward_id, "insomnia", pool=["insomnia"], chance=0.16, source="skip_bed",
    )


async def maybe_dehydration(conn: aiosqlite.Connection, steward_id: int) -> str | None:
    row = await (await conn.execute(
        "SELECT satiety FROM stewards WHERE id=?", (steward_id,)
    )).fetchone()
    if not row or int(row[0]) >= config.SATIETY_LOW:
        return None
    return await maybe_roll_ailment(
        conn, steward_id, "dehydration", pool=["dehydration"], chance=0.14, source="low_satiety",
    )


async def maybe_roll_ailment(
    conn: aiosqlite.Connection,
    steward_id: int,
    trigger: str,
    *,
    pool: list[str] | None = None,
    chance: float | None = None,
    source: str = "event",
) -> str | None:
    keys = pool or TRIGGER_AILMENTS.get(trigger, [])
    if not keys:
        return None
    roll_chance = chance if chance is not None else config.AILMENT_ROLL_CHANCE
    if random.random() > roll_chance:
        return None
    key = random.choice(keys)
    return await inflict(conn, steward_id, key, source=source)


async def tick_chronic(conn: aiosqlite.Connection, steward_id: int) -> int:
    """按档位长期扣精力。返回本次扣掉的点数。"""
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """
        SELECT ailment_key, stage, last_tick_at
        FROM steward_ailments WHERE steward_id=?
        """,
        (steward_id,),
    )).fetchall()
    now = db.now()
    drained = 0
    for r in rows:
        key = r["ailment_key"]
        meta = AILMENTS.get(key, {})
        drain = int(meta.get("drain_energy", 0) or 0)
        if drain <= 0:
            continue
        every = int(meta.get("drain_every") or config.INFECTION_DRAIN_EVERY)
        if every <= 0:
            continue
        last = int(r["last_tick_at"] or 0)
        if last <= 0:
            await conn.execute(
                """
                UPDATE steward_ailments SET last_tick_at=?
                WHERE steward_id=? AND ailment_key=?
                """,
                (now, steward_id, key),
            )
            continue
        ticks = (now - last) // every
        if ticks <= 0:
            continue
        stage = _effective_stage(key, int(r["stage"] or 0))
        amount = drain * max(1, stage) * ticks
        await conn.execute(
            "UPDATE stewards SET energy = MAX(0, energy - ?) WHERE id=?",
            (amount, steward_id),
        )
        await conn.execute(
            """
            UPDATE steward_ailments SET last_tick_at=?
            WHERE steward_id=? AND ailment_key=?
            """,
            (last + ticks * every, steward_id, key),
        )
        drained += amount
    return drained


def energy_extra(ailments: list[dict[str, Any]]) -> int:
    total = 0
    for a in ailments:
        meta = AILMENTS.get(a["key"], {})
        total += meta.get("energy_extra", 1)
    return total


def max_energy_cap(ailments: list[dict[str, Any]]) -> int:
    cap = config.MAX_ENERGY
    for a in ailments:
        meta = AILMENTS.get(a["key"], {})
        cap -= meta.get("max_energy_cut", 0)
    return max(35, cap)


def event_bias(steward: dict[str, Any], ailment_count: int) -> float:
    mult = 1.0
    health = steward.get("health", config.START_HEALTH)
    if health < config.HEALTH_LOW:
        mult *= 1.10
    if ailment_count >= 2:
        mult *= 1.08
    if ailment_count >= 3:
        mult *= 1.06
    return mult


def meter_line(steward: dict[str, Any], ailments: list[dict[str, Any]]) -> str:
    h = steward.get("health", config.START_HEALTH)
    line = f"身体 {h}/100"
    if ailments:
        bits = []
        for a in ailments[:3]:
            label = f"{a['emoji']}{a['name']}"
            if a.get("stage_name"):
                label += f"·{a['stage_name']}"
            bits.append(label)
        extra = f" 等{len(ailments)}项" if len(ailments) > 3 else ""
        line += f"（{'、'.join(bits)}{extra}）"
    hints = []
    if h < config.HEALTH_LOW:
        hints.append(flavor.HEALTH_HINT_LOW)
    elif h < 100:
        hints.append(flavor.HEALTH_HINT_TONIC)
    if ailments:
        hints.append(flavor.HEALTH_HINT_CLINIC)
    if hints:
        line += f"（{'，'.join(hints)}）"
    return line


def clinic_hint(ailments: list[dict[str, Any]]) -> str | None:
    if not ailments:
        return None
    total = sum(a["cost"] for a in ailments)
    line = flavor.fill(
        flavor.pick(flavor.CLINIC_NAG_LINES),
        n=len(ailments),
        total=total,
    )
    if any(a.get("chronic") for a in ailments):
        line += "（生肉感染不能打包一次清干净）"
    return line


def _bill_cost(base: int, *, cost_mult: float = 1.0, cost_add: int = 0) -> int:
    return max(1, int(round(base * cost_mult)) + int(cost_add))


async def _pay_and_heal(
    conn: aiosqlite.Connection,
    steward_id: int,
    cost: int,
    heal: int,
) -> None:
    cur = await conn.execute("SELECT tickets, health FROM stewards WHERE id=?", (steward_id,))
    row = await cur.fetchone()
    tickets = row[0]
    if tickets < cost:
        raise ValueError(f"诊费 {cost} 票，你只有 {tickets} 票——桥桥大夫不赊账")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-?, health=MIN(100, health+?) WHERE id=?",
        (cost, heal, steward_id),
    )


async def _apply_chronic_course(
    conn: aiosqlite.Connection,
    steward_id: int,
    ailment: dict[str, Any],
    *,
    cost_mult: float = 1.0,
    cost_add: int = 0,
    wait_halve: bool = False,
    free: bool = False,
) -> str:
    key = ailment["key"]
    meta = AILMENTS[key]
    wait = int(ailment.get("treat_wait") or 0)
    if wait_halve and wait > 0:
        now = db.now()
        last = int(ailment.get("last_treat_at") or 0)
        half_ready = last + int(config.INFECTION_TREAT_COOLDOWN) // 2
        if now >= half_ready:
            wait = 0
    if wait > 0:
        raise ValueError(
            f"桥桥大夫摇头：「菌还压着，{fmt_wait(wait)}后再来。"
            "一次清不干净，别连号。」"
        )
    cost = 0 if free else _bill_cost(meta["cost"], cost_mult=cost_mult, cost_add=cost_add)
    heal = meta.get("health_restore", 8)
    if not free:
        await _pay_and_heal(conn, steward_id, cost, heal)
    else:
        await conn.execute(
            "UPDATE stewards SET health=MIN(100, health+?) WHERE id=?",
            (heal, steward_id),
        )
    now = db.now()
    stage = int(ailment.get("stage") or 1)
    name = f"{meta['emoji']}{meta['name']}"
    if stage <= 1:
        await conn.execute(
            "DELETE FROM steward_ailments WHERE steward_id=? AND ailment_key=?",
            (steward_id, key),
        )
        return (
            (f"桥桥大夫把{name}余菌压住了（身体 +{heal}）。" if free else
             f"桥桥大夫收 {cost} 票，把{name}余菌压住了（身体 +{heal}）。")
            + "这次算清了——别再生吃。"
        )
    new_stage = stage - 1
    await conn.execute(
        """
        UPDATE steward_ailments
        SET stage=?, last_treat_at=?
        WHERE steward_id=? AND ailment_key=?
        """,
        (new_stage, now, steward_id, key),
    )
    left_name = _stage_name(key, new_stage) or f"还剩{new_stage}档"
    return (
        (f"桥桥大夫给{name}压了一档" if free else f"桥桥大夫收 {cost} 票，给{name}压了一档")
        + f"（现为{left_name}，疗程还剩 {new_stage} 次，身体 +{heal}）。"
        + "菌没清干净，隔几小时再来，别指望一次根治。"
    ) + flavor.maybe_suffix(flavor.CLINIC_TREAT_LINES)


async def treat_one(
    conn: aiosqlite.Connection,
    steward_id: int,
    ailment_key: str,
    *,
    cost_mult: float = 1.0,
    cost_add: int = 0,
    allow_pit: bool = False,
) -> str:
    resolved = resolve_ailment_key(ailment_key) or ailment_key
    if resolved not in AILMENTS:
        raise ValueError("未知病症，visit_ops clinic 查看")
    ailments = await list_ailments(conn, steward_id)
    hit = next((a for a in ailments if a["key"] == resolved), None)
    if not hit:
        raise ValueError(f"你没有 {AILMENTS[resolved]['name']}")
    if bridge_refuses(hit) and not allow_pit:
        raise ValueError(_pit_refuse())
    if hit["chronic"]:
        return await _apply_chronic_course(
            conn, steward_id, hit,
            cost_mult=cost_mult, cost_add=cost_add,
        )
    meta = AILMENTS[resolved]
    cost = _bill_cost(meta["cost"], cost_mult=cost_mult, cost_add=cost_add)
    heal = meta.get("health_restore", 12)
    await _pay_and_heal(conn, steward_id, cost, heal)
    await conn.execute(
        "DELETE FROM steward_ailments WHERE steward_id=? AND ailment_key=?",
        (steward_id, resolved),
    )
    return (
        f"桥桥大夫收 {cost} 票，治好 {meta['emoji']}{meta['name']} "
        f"（身体 +{heal}）"
    ) + flavor.maybe_suffix(flavor.CLINIC_TREAT_LINES)


async def treat_all(
    conn: aiosqlite.Connection,
    steward_id: int,
    *,
    cost_mult: float = 1.0,
    cost_add: int = 0,
    allow_pit: bool = False,
) -> str:
    ailments = await list_ailments(conn, steward_id)
    if not ailments:
        return "身体倍儿棒——没病别占桥桥大夫的号"
    simple = [
        a for a in ailments
        if not a["chronic"] and not bridge_refuses(a) and (allow_pit or not a["pit"])
    ]
    chronic = [a for a in ailments if a["chronic"]]
    pit = [a for a in ailments if bridge_refuses(a)]
    course_target = None
    skipped_wait = None
    for a in chronic:
        wait = int(a.get("treat_wait") or 0)
        if wait > 0:
            skipped_wait = (a, wait)
            continue
        course_target = a
        break
    if not simple and course_target is None:
        if skipped_wait:
            a, wait = skipped_wait
            raise ValueError(
                f"桥桥大夫摇头：「{a['emoji']}{a['name']}菌还压着，"
                f"{fmt_wait(wait)}后再来。一次清不干净，别连号。」"
            )
        if pit:
            raise ValueError(_pit_refuse())
        return "身体倍儿棒——没病别占桥桥大夫的号"

    cost = sum(_bill_cost(AILMENTS[a["key"]]["cost"], cost_mult=cost_mult, cost_add=0) for a in simple)
    if cost_add and simple:
        cost += cost_add * len(simple)
    heal_total = sum(AILMENTS[a["key"]].get("health_restore", 12) for a in simple)
    if course_target is not None:
        cost += _bill_cost(course_target["cost"], cost_mult=cost_mult, cost_add=cost_add)
        heal_total += AILMENTS[course_target["key"]].get("health_restore", 8)
    await _pay_and_heal(conn, steward_id, cost, heal_total)

    names: list[str] = []
    for a in simple:
        names.append(f"{a['emoji']}{a['name']}")
        await conn.execute(
            "DELETE FROM steward_ailments WHERE steward_id=? AND ailment_key=?",
            (steward_id, a["key"]),
        )

    extra = ""
    if course_target is not None:
        # 付过账，直接落档，避免 _apply_chronic_course 再扣一次票
        now = db.now()
        stage = int(course_target.get("stage") or 1)
        meta = AILMENTS[course_target["key"]]
        label = f"{meta['emoji']}{meta['name']}"
        if stage <= 1:
            await conn.execute(
                "DELETE FROM steward_ailments WHERE steward_id=? AND ailment_key=?",
                (steward_id, course_target["key"]),
            )
            names.append(f"{label}（余菌压住）")
        else:
            new_stage = stage - 1
            await conn.execute(
                """
                UPDATE steward_ailments
                SET stage=?, last_treat_at=?
                WHERE steward_id=? AND ailment_key=?
                """,
                (new_stage, now, steward_id, course_target["key"]),
            )
            left = _stage_name(course_target["key"], new_stage) or f"还剩{new_stage}档"
            extra = (
                f" {label}只压了一档（现为{left}），打包也一次清不干净，"
                f"{fmt_wait(config.INFECTION_TREAT_COOLDOWN)}后再来。"
            )
            names.append(f"{label}·{left}")

    if skipped_wait and course_target is None:
        a, wait = skipped_wait
        extra += (
            f" {a['emoji']}{a['name']}还在疗程间隔（{fmt_wait(wait)}后再看），"
            "打包清不掉。"
        )
    if pit:
        extra += " 井下伤请回 undertide_ops medic（晏安医务间），桥桥不接。"

    cleared = "、".join(names) if names else "（普通伤已空）"
    return (
        f"桥桥大夫收 {cost} 票，处理：{cleared}"
        f"（身体 +{min(100, heal_total)}）"
        f"{extra}"
    )

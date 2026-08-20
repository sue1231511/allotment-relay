"""滨海酒吧 — 暮夜上工赚票，票紧时有穷人补贴。老板：荔梔。"""

from __future__ import annotations

import random

import aiosqlite

from . import config, db, energy, flavor, survival, world
from .catalog import COASTAL_BAR, NPC_FIXED
from .game import require_steward


def _day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


def _owner_lines() -> list[str]:
    npc = next((n for n in NPC_FIXED if n["key"] == COASTAL_BAR["owner"]), None)
    return npc["lines"] if npc else ["今晚营业，缺人手"]


def _is_open() -> bool:
    return world.current_day_phase() in COASTAL_BAR["open_phases"]


def _poor_bonus(tickets: int) -> tuple[float, str]:
    if tickets <= config.BAR_POOR_THRESHOLD:
        return config.BAR_POOR_PAY_MULT, flavor.pick(config.BAR_POOR_LABELS)
    if tickets <= config.BAR_POOR_THRESHOLD * 2:
        return 1.25, "票不多，荔梔多塞了两张"
    return 1.0, ""


async def bar_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=1)
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        phase = world.current_day_phase()
        open_now = _is_open()
        lines = [
            f"{COASTAL_BAR['emoji']}{COASTAL_BAR['name']} — 老板 {COASTAL_BAR['owner_name']}",
            f"营业: {'开' if open_now else '歇'}（{world.day_phase_label(phase)}，暮/夜开门）",
            f"你的票: {s['tickets']}（≤{config.BAR_POOR_THRESHOLD} 有穷人补贴）",
            f"上工: bar_ops shift（-{config.BAR_SHIFT_ENERGY} 精力，日限 {config.BAR_SHIFT_DAILY}）",
            "chat — 跟荔梔唠唠",
        ]
        if not open_now:
            lines.append("白天别摸鱼，去份地或赶海；酒吧晚上见")
        return "\n".join(lines)

    if verb == "chat":
        line = random.choice(_owner_lines())
        tail = flavor.pick([
            "——荔梔擦着杯子，眼神像在看 KPI",
            "——说罢往你领口别了一枚塑料领针：工牌，别扔",
            "——背后调酒声叮当，像给你打节拍",
        ])
        return f"荔梔：{line}{tail}"

    if verb == "shift":
        if not _is_open():
            raise ValueError(
                f"{COASTAL_BAR['name']} 暮/夜才营业，现在 {world.day_phase_label(world.current_day_phase())}"
            )
        day = _day_id()
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute(
                "SELECT count FROM bar_rolls WHERE steward_id=? AND day=?",
                (s["id"], day),
            )
            row = await cur.fetchone()
            used = row[0] if row else 0
            if used >= config.BAR_SHIFT_DAILY:
                raise ValueError(f"今日上工上限 {config.BAR_SHIFT_DAILY}，明天再来")
            await energy.spend(conn, s["id"], config.BAR_SHIFT_ENERGY, action="酒吧上工")

            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            tickets_before = (await cur.fetchone())[0]
            mult, poor_note = _poor_bonus(tickets_before)
            base = random.randint(config.BAR_PAY_MIN, config.BAR_PAY_MAX)
            tips = random.randint(0, config.BAR_TIP_MAX)
            if s.get("portrait"):
                tips += random.randint(0, 3)
            if world.current_weather() == "misty":
                tips += 2
            event_line = ""
            if random.random() < 0.22:
                tips += random.randint(4, 10)
                event_line = flavor.pick(config.BAR_TIP_EVENTS)
            elif random.random() < 0.12:
                tips = max(0, tips - random.randint(2, 6))
                event_line = flavor.pick(config.BAR_OOPS_EVENTS)

            gain = max(1, int((base + tips) * mult))
            await conn.execute(
                "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                (gain, s["id"]),
            )
            await survival.bump(conn, s["id"], mist_wit=-3, satiety=-2, standing=random.randint(-2, 4))
            await conn.execute(
                """
                INSERT INTO bar_rolls (steward_id, day, count) VALUES (?,?,1)
                ON CONFLICT(steward_id, day) DO UPDATE SET count = count + 1
                """,
                (s["id"], day),
            )
            await conn.commit()

        role = flavor.pick(config.BAR_ROLE_LINES)
        msg = f"{COASTAL_BAR['name']}上工：{role}，+{gain} 票（底{base}+小费{tips}）"
        if poor_note:
            msg += f"【{poor_note}】"
        if event_line:
            msg += f"\n{event_line}"
        msg += flavor.maybe_suffix(config.BAR_SHIFT_SUFFIX, chance=0.55)
        await db.add_chronicle(
            "bar",
            f"{s['name']} 在{COASTAL_BAR['name']}上工 +{gain}票",
            s["id"],
        )
        return msg

    raise ValueError(f"未知 bar 指令: {command}（status/shift/chat）")

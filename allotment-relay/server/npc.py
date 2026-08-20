"""NPC — 固定访客台词 + 偷菜贼名号。visit 给语境提示，每日首次有小回暖。"""

from __future__ import annotations

import random

import aiosqlite

from . import config, db, flavor, survival, world
from .catalog import KITCHEN_DISHES, NPC_FIXED, NPC_THIEVES
from .game import require_steward


def _day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


async def npc_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=1)
    verb = parts[0].lower() if parts else "list"

    if verb == "list":
        lines = ["固定 NPC（visit 名字）:"]
        for npc in NPC_FIXED:
            tag = ""
            if npc["key"] == "gugu_dove":
                tag = " · 昼间随机偷吃庄稼，不可伤害"
            elif npc["key"] == "qiaoqiao":
                tag = " · 诊所 NPC，治病用 clinic_ops treat"
            elif npc["key"] == "lili":
                tag = " · 流动贝壳商，lili_ops scan/trade"
            elif npc["key"] == "old_salt":
                tag = " · 赶海/潮汐提示"
            elif npc["key"] == "herb_aunt":
                tag = " · 厨房配方提示"
            elif npc["key"] == "market_fan":
                tag = " · 集市挂单"
            lines.append(f"  {npc['key']} — {npc['name']}{tag}")
        lines.append(f"偷菜贼名号: {', '.join(NPC_THIEVES[:3])}…")
        lines.append("  lizhi — 荔栀（滨海酒吧老板，也可 bar_ops chat）")
        lines.append("每日首次 visit 略回暖雾智/档信")
        return "\n".join(lines)

    if verb == "visit" and len(parts) >= 2:
        key = parts[1].lower()
        npc = next((n for n in NPC_FIXED if n["key"] == key), None)
        if not npc:
            raise ValueError(f"未知 NPC，list 查看")
        line = random.choice(npc["lines"])
        extra = await _visit_context(s, npc["key"])
        gift = await _daily_visit_gift(s["id"], npc["key"])
        return f"{npc['name']}：{line}{extra}{gift}"

    if verb == "thieves":
        return "偷菜贼名册:\n" + "\n".join(f"  · {t}" for t in NPC_THIEVES)

    raise ValueError(f"未知 npc 指令: {command}（list/visit/thieves）")


async def _visit_context(steward: dict, key: str) -> str:
    tide = world.current_tide()
    weather = world.current_weather()
    phase = world.current_day_phase()
    if key == "gugu_dove":
        return flavor.pick([
            "——咕咕咕咕咕咕，飞走了",
            "——伤不得，联盟牌子上写着呢",
            "——它看你不顺眼，但主要是看庄稼顺眼",
        ])
    if key == "lili":
        from . import lili as lili_mod
        async with aiosqlite.connect(db.DB_PATH) as conn:
            hint = await lili_mod.active_visit_hint(conn)
        if hint:
            return f"——{hint}"
        return "——驮包叮当远去了，lili_ops scan 蹲下一回"
    if key == "old_salt":
        bits = [
            f"现在 {world.tide_label(tide)} · {world.weather_label(weather)}",
        ]
        if tide == "ebb":
            bits.append("退潮赶海：beach_ops dig，贝壳权重高")
        elif tide == "slack":
            bits.append("平潮可 probe 掏洞，dig 也行")
        else:
            bits.append("涨潮别翻沙，坐钓 tide_ops cast 碰运气")
        if weather == "misty":
            bits.append("雾天珠砂/海玻璃略多")
        return "——" + "；".join(bits)
    if key == "herb_aunt":
        from .catalog import ITEM_NAMES
        dish_key, meta = random.choice(list(KITCHEN_DISHES.items()))
        ings = " + ".join(ITEM_NAMES.get(i, i) for i in meta["ings"])
        return f"——今儿提一嘴：kitchen_ops cook {dish_key}（{ings}）"
    if key == "market_fan":
        return "——缺料就 market_ops sell/buy，别跟建议价置气"
    if key == "lizhi":
        from . import bar as bar_mod
        open_now = bar_mod.is_open()
        duty = bar_mod.duty_line(steward)
        hours = "现在营业，shift 去" if open_now else f"酒吧暮/夜开，现在 {world.day_phase_label(phase)}"
        return f"——{hours}。{duty}"
    if key == "qiaoqiao":
        from . import health as health_mod
        async with aiosqlite.connect(db.DB_PATH) as conn:
            ailments = await health_mod.list_ailments(conn, steward["id"])
        if ailments:
            names = "、".join(a["name"] for a in ailments[:3])
            return f"——你挂着 {names}，clinic_ops treat，不赊账"
        return "——身子还行。别等病了再来聊天"
    return flavor.pick([
        "——说完就溜达走了",
        "——留下一股姜味",
        "——顺便看了眼你的份地",
    ])


async def _daily_visit_gift(steward_id: int, npc_key: str) -> str:
    if npc_key == "gugu_dove":
        return ""
    day = _day_id()
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT 1 FROM npc_visits WHERE steward_id=? AND npc_key=? AND day=?",
            (steward_id, npc_key, day),
        )
        if await cur.fetchone():
            return ""
        await conn.execute(
            "INSERT INTO npc_visits (steward_id, npc_key, day) VALUES (?,?,?)",
            (steward_id, npc_key, day),
        )
        if npc_key == "lizhi":
            await survival.bump(conn, steward_id, standing=2)
            note = "档信 +2（今日首次拜访）"
        elif npc_key == "qiaoqiao":
            await conn.execute(
                "UPDATE stewards SET health=MIN(100, health+2) WHERE id=?",
                (steward_id,),
            )
            note = "身体 +2（聊聊天也算复查，治病还是要花钱）"
        elif npc_key == "herb_aunt":
            await survival.bump(conn, steward_id, satiety=3)
            note = "饱食 +3（姜姨塞了块姜糖）"
        else:
            await survival.bump(conn, steward_id, mist_wit=2)
            note = "雾智 +2（今日首次拜访）"
        await conn.commit()
    return f"\n{note}"


def pick_thief_name(peer_name: str | None = None) -> str:
    if peer_name and random.random() < 0.55:
        return peer_name
    if random.random() < 0.35:
        return random.choice(NPC_THIEVES)
    return flavor.pick(["过路家伙", "无名之手", "篱笆外的影子"])

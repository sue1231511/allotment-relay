"""NPC — 固定访客台词 + 偷菜贼名号。"""

from __future__ import annotations

import random

import aiosqlite

from . import db, flavor
from .catalog import NPC_FIXED, NPC_THIEVES
from .game import require_steward


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
            lines.append(f"  {npc['key']} — {npc['name']}{tag}")
        lines.append(f"偷菜贼名号: {', '.join(NPC_THIEVES[:3])}…")
        lines.append("  lizhi — 荔栀（滨海酒吧老板娘，bar_ops tonight/chat）")
        lines.append("  wangfu — 我哪有旺夫命（固定驻唱，bar_ops song）")
        return "\n".join(lines)

    if verb == "visit" and len(parts) >= 2:
        key = parts[1].lower()
        npc = next((n for n in NPC_FIXED if n["key"] == key), None)
        if not npc:
            raise ValueError(f"未知 NPC，list 查看")
        line = random.choice(npc["lines"])
        if npc["key"] == "gugu_dove":
            extra = flavor.pick([
                "——咕咕咕咕咕咕，飞走了",
                "——伤不得，联盟牌子上写着呢",
                "——它看你不顺眼，但主要是看庄稼顺眼",
            ])
        elif npc["key"] == "lili":
            from . import lili as lili_mod
            async with aiosqlite.connect(db.DB_PATH) as conn:
                hint = await lili_mod.active_visit_hint(conn)
            if hint:
                extra = f"——{hint}"
            else:
                extra = "——驮包叮当远去了，lili_ops scan 蹲下一回"
        else:
            extra = flavor.pick([
                "——说完就溜达走了",
                "——留下一股姜味",
                "——顺便看了眼你的份地",
            ])
        return f"{npc['name']}：{line}{extra}"

    if verb == "thieves":
        return "偷菜贼名册:\n" + "\n".join(f"  · {t}" for t in NPC_THIEVES)

    raise ValueError(f"未知 npc 指令: {command}（list/visit/thieves）")


def pick_thief_name(peer_name: str | None = None) -> str:
    if peer_name and random.random() < 0.55:
        return peer_name
    if random.random() < 0.35:
        return random.choice(NPC_THIEVES)
    return flavor.pick(["过路家伙", "无名之手", "篱笆外的影子"])

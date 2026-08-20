"""诊所 — 桥桥大夫，花钱治病，不赊账。"""

from __future__ import annotations

import random

import aiosqlite

from . import db, flavor, health
from .catalog import AILMENTS
from .game import require_steward


async def clinic_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        async with db.connect() as conn:
            s = await db.get_steward_by_id(s["id"]) or s
            ailments = await health.list_ailments(conn, s["id"])
        lines = [
            "桥桥大夫诊所（必须花票，不赊账）",
            health.meter_line(s, ailments),
            "指令: treat 病症 / treat all / visit",
        ]
        if not ailments:
            lines.append("目前没挂号项——别装病")
            return "\n".join(lines)
        lines.append("待治:")
        total = 0
        for a in ailments:
            total += a["cost"]
            lines.append(
                f"  {a['key']} — {a['emoji']}{a['name']} "
                f"（{a['hint']} · 诊费 {a['cost']} 票）"
            )
        lines.append(f"全套合计 {total} 票 · clinic_ops treat all")
        return "\n".join(lines)

    if verb == "visit":
        line = random.choice([
            "桥桥大夫：「票不到位，药不到位。诊所不搞慈善。」",
            "桥桥大夫推推眼镜：「随机事件搞出来的病，找随机事件哭去——诊费照收。」",
            "桥桥大夫：「咕咕斑鸠伤不得，你扭了脚可得花钱。」",
            "桥桥大夫指价目表：「看清数字再开口，我不还价。」",
            "桥桥大夫：「宿醉也是病，酒吧赚的票别全花在下一顿酒上。」",
        ])
        async with db.connect() as conn:
            ailments = await health.list_ailments(conn, s["id"])
        if ailments:
            total = sum(a["cost"] for a in ailments)
            line += f"\n当前 {len(ailments)} 项待治，合计 {total} 票。"
        else:
            line += "\n你看上去暂时不用破费。"
        return line + flavor.maybe_suffix([
            "——诊所里消毒水味很诚实",
            "——墙上有字：必须花钱",
        ])

    if verb == "treat" and len(parts) >= 2:
        target = parts[1].lower()
        async with db.connect() as conn:
            if target == "all":
                msg = await health.treat_all(conn, s["id"])
            else:
                msg = await health.treat_one(conn, s["id"], target)
            await db.add_chronicle("clinic", f"{s['name']} {msg}", s["id"], conn=conn)
            await conn.commit()
        return msg

    if verb == "catalog":
        lines = ["病症价目（clinic_ops treat 键名）:"]
        for key, meta in AILMENTS.items():
            lines.append(
                f"  {key} — {meta['emoji']}{meta['name']} "
                f"{meta['cost']}票 · {meta.get('hint', '')}"
            )
        return "\n".join(lines)

    raise ValueError(
        f"未知 clinic 指令: {command}（status/treat 病症|all/visit/catalog）"
    )

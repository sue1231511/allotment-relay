"""lore_ops — 查阅沿海联盟背景，不改数值。"""

from __future__ import annotations

from .game import require_steward
from .lore import LORE_TOPIC_LABELS, LORE_TOPICS, lore_topic_text


async def lore_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    parts = command.strip().split(maxsplit=1)
    verb = parts[0].lower() if parts else "scan"
    arg = parts[1].strip() if len(parts) > 1 else ""

    if verb in ("scan", "read", "topic"):
        import random
        topic = (arg or "").strip().lower()
        if not topic:
            topic = random.choice(list(LORE_TOPICS.keys()))
        text = lore_topic_text(topic)
        if topic in LORE_TOPICS:
            from . import bond as bond_mod
            from . import db
            async with db.connect() as conn:
                gained = await bond_mod.grant(
                    conn, s["id"], bond_mod.LORE_TOPIC, "story", once=f"lore:{topic}"
                )
                await conn.commit()
            if gained:
                text += f"\n岛缘 +{gained}"
        return text

    if verb in ("topics", "list", "help"):
        return lore_topic_text("topics")

    if verb == "hedge":
        from .lore import hedge_note_hint
        return f"篱笆条灵感（可直接复制改）：\n「{hedge_note_hint()}」"

    raise ValueError(
        f"未知 lore 指令: {command}\n"
        "用法: lore_ops scan [主题] · topics · hedge\n"
        f"主题: {', '.join(LORE_TOPIC_LABELS.keys())}"
    )

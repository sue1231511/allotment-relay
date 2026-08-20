"""lore_ops — 查阅沿海联盟背景，不改数值。"""

from __future__ import annotations

from .game import require_steward
from .lore import LORE_TOPIC_LABELS, lore_scan_random, lore_topic_text


async def lore_ops(key_id: int, command: str) -> str:
    await require_steward(key_id, exempt_duty=True)
    parts = command.strip().split(maxsplit=1)
    verb = parts[0].lower() if parts else "scan"
    arg = parts[1].strip() if len(parts) > 1 else ""

    if verb in ("scan", "read", "topic"):
        if arg:
            return lore_topic_text(arg)
        return lore_scan_random()

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

"""蹄角棚 — 岸兽医霍衡。visit_ops 霍衡 / 兽医。治牲口，不治人。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from . import barn_disease, db, flavor, season, vet_npc, world
from .barn import tick_animal_age
from .catalog import LIVESTOCK
from .game import require_steward

VET_HELP = """蹄角棚 · 岸兽医霍衡（visit_ops 霍衡 / 兽医 / 蹄角棚）：
  空 command / visit / 进门 — 闲聊。对白可能来自真 AI（OpenAI 兼容接口，站长配 VET_NPC_*）；没配或挂了走固定台词。霍衡说话偶尔飘一下，正常。
  status — 看你栏里的病。例子：visit_ops 兽医 status · visit_ops 霍衡 status
  treat 1 — 治 #1，扣票清病。例子：visit_ops 兽医 treat 1 · visit_ops 霍衡 treat 2
  catalog — 牲口病价目
  chat 栏里羊蹄缝发黑 — 跟他说（只写对白，不改票、不治栏）
  help — 本说明
空=进门。容易搞混：桥桥诊所治人（visit_ops clinic）；霍衡治牲口。hut_ops barn 是喂栏收奶，不是兽医。
摸病死牲口可能沾上畜热/蹄毒/瘟触，人的病去桥桥。赤潮周撒网可能潮疹，也是桥桥。
人类：上手页小屋点「找兽医」，或蹄角棚地点卡。"""

ATMOSPHERE = [
    "蹄角棚门口挂着一块磨白的蹄铁。里面是干草、碘酒，和一种说不清的牲口气。",
    "棚梁上晾着几条用过的绷带。霍衡蹲在门槛上擦刀，头也不抬。",
    "风从畜栏那边吹过来。霍衡闻了一下，像在辨哪一栏不对。",
]


def _climate_bit() -> str:
    from . import config

    effect = world.field_climate_effect()
    if not effect:
        return ""
    label = config.SEASON_CLIMATE_LABELS.get(effect, effect)
    return f"本周气候 {label}。"


async def _context(conn: aiosqlite.Connection, s: dict[str, Any], said: str) -> dict[str, Any]:
    sick = await barn_disease.list_sick(conn, s["id"])
    cur = await conn.execute(
        "SELECT COUNT(*) FROM barn_animals WHERE steward_id=? AND species IS NOT NULL",
        (s["id"],),
    )
    total = int((await cur.fetchone())[0] or 0)
    return {
        "player_name": s.get("name") or "岛民",
        "player_said": (said or "")[:240],
        "season": season.season_name(),
        "climate": _climate_bit() or "无特别气候",
        "barn_built": bool(s.get("barn_built")),
        "stocked": total,
        "sick_animals": [
            {
                "slot": row["slot"],
                "name": row["name"],
                "ailment": row["ailment"],
                "ailment_name": row["ailment_name"],
            }
            for row in sick
        ],
        "healthy_count": max(0, total - len(sick)),
        "note": "治病必须走 treat 槽位；你的回复不能改变票或栏。",
    }


def _ai_note(live: bool) -> str:
    if live:
        return "（这是真 AI，偶尔波动正常现象。）"
    return "（棚里这会儿没接外线，霍衡按老规矩说话。）"


async def _talk(conn: aiosqlite.Connection, s: dict[str, Any], said: str = "") -> str:
    ctx = await _context(conn, s, said)
    line, live = await vet_npc.speak(ctx)
    if not line.startswith("霍衡"):
        line = f"霍衡：「{line}」" if "：" not in line[:6] and ":" not in line[:6] else line
    bits = [flavor.pick(ATMOSPHERE), line, _ai_note(live)]
    climate = _climate_bit()
    if climate:
        bits.append(climate)
    if ctx["sick_animals"]:
        names = "、".join(
            f"#{row['slot']}{row['name']}{row['ailment_name']}"
            for row in ctx["sick_animals"][:4]
        )
        bits.append(f"栏里有病：{names}。治：visit_ops 兽医 treat 槽位（扣票）。人若发烧去 clinic。")
    else:
        bits.append("栏里这会儿没报病。不对劲再来。人的病去桥桥。")
    bits.append("真要治栏用 treat，闲聊改不了牲口。")
    return "\n".join(bits)


async def vet_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    raw = (command or "").strip()
    parts = raw.split(maxsplit=1)
    verb = parts[0].lower() if parts else "visit"
    rest = parts[1].strip() if len(parts) > 1 else ""

    if verb in ("help", "帮助", "?"):
        return VET_HELP

    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        await tick_animal_age(conn, s["id"])
        notes = await barn_disease.tick_barn_disease(conn, s["id"])
        await conn.commit()

        if verb in ("catalog", "价目", "图鉴"):
            lines = ["蹄角棚价目（治牲口，不治人）:"]
            for key, meta in barn_disease.BARN_AILMENTS.items():
                species = "、".join(
                    LIVESTOCK[sp]["name"] for sp in meta["species"] if sp in LIVESTOCK
                )
                human = meta.get("human")
                extra = " · 人可能沾上，去桥桥" if human else " · 人不沾"
                lines.append(f"  {meta['emoji']}{meta['name']} — {meta['cost']} 票（{species}）{extra}")
            lines.append("visit_ops 兽医 treat 槽位。桥桥不收牲口，霍衡不给人开药。")
            lines.append("摸病死牲口可能畜热/蹄毒/瘟触。赤潮撒网可能潮疹 — 都去诊所。")
            if notes:
                lines.extend(notes)
            return "\n".join(lines)

        if verb in ("status", "看", "栏", "病"):
            if not s.get("barn_built"):
                return "你还没搭畜栏。先 hut_ops barn erect。霍衡不给空栏看病。"
            sick = await barn_disease.list_sick(conn, s["id"])
            lines = ["蹄角棚·霍衡看栏:"]
            if notes:
                lines.extend(notes)
            if not sick:
                lines.append("栏里这会儿没病。不对劲再来。人发烧去 visit_ops clinic。")
                lines.append(flavor.pick(ATMOSPHERE))
                return "\n".join(lines)
            for row in sick:
                lines.append(
                    f"  #{row['slot']} {row['emoji']}{row['name']} — "
                    f"{row['ailment_emoji']}{row['ailment_name']} · {row['cost']} 票"
                    f" · treat {row['slot']}"
                )
            lines.append("治：visit_ops 兽医 treat 槽位。人的病去桥桥。")
            return "\n".join(lines)

        if verb in ("treat", "治", "医"):
            token = rest.split()[0] if rest else ""
            if not token.isdigit():
                raise ValueError("兽医 treat 后面跟槽位数字。例子：visit_ops 兽医 treat 1")
            slot = int(token)
            if not s.get("barn_built"):
                raise ValueError("先搭畜栏")
            cur = await conn.execute(
                "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
                (s["id"], slot),
            )
            row = await cur.fetchone()
            animal = dict(row) if row else {}
            if not animal.get("species"):
                raise ValueError(f"#{slot} 空栏")
            key = barn_disease.animal_ailment_key(animal)
            if not key:
                spec = LIVESTOCK.get(animal["species"], {})
                return f"霍衡看了眼 #{slot} {spec.get('name', '')}：「这头没病。别浪费票。」"
            meta = barn_disease.BARN_AILMENTS[key]
            cost = int(meta["cost"])
            tickets = int(
                (await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))).fetchone())[0]
            )
            if tickets < cost:
                raise ValueError(f"治{meta['name']}要 {cost} 票，你只有 {tickets} 票。霍衡不赊账")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, s["id"]),
            )
            from . import tax as tax_mod

            await tax_mod.record_life_spend(conn, s["id"], cost, "vet")
            await barn_disease.clear_ailment(conn, s["id"], slot)
            spec = LIVESTOCK.get(animal["species"], {})
            await db.add_chronicle(
                "vet",
                f"{s['name']} 蹄角棚治 #{slot} {spec.get('name', '')}·{meta['name']}",
                s["id"],
                conn=conn,
            )
            await conn.commit()
            return (
                f"霍衡给 #{slot} {spec.get('emoji', '')}{spec.get('name', '')} 处理了{meta['name']}。"
                f"-{cost} 票。栏清了。\n"
                "「人要是也烧，去桥桥。这不是人的药。」"
            )

        said = rest if verb in ("visit", "进门", "chat", "说", "闲聊") else raw
        msg = await _talk(conn, s, said)
        if notes:
            msg = "\n".join(notes) + "\n" + msg
        return msg
    return VET_HELP

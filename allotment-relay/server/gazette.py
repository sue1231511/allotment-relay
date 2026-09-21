"""潮汐周报。根据本周真实 chronicle 写成一期，不另造地点。"""
from __future__ import annotations

from typing import Any

from . import db, world
from .disaster import cst_week_ordinal, cst_week_start

RARE_FISH = ("旗鱼", "金枪", "龙虾", "鲍鱼", "石斑", "马鲛", "真鲷")
OBJECT_MARKS = ("戒", "衣", "冠", "呢衣", "婚服", "标本", "雾银")


def week_start(ts: int | None = None) -> int:
    """东八区本周一 00:00。和岸税、周目标同一周界，不是 UTC 周四。"""
    return cst_week_start(ts)


def _pick_title(stats: dict[str, Any]) -> str:
    if stats.get("rare_fish"):
        return "本周最大的一条鱼差点把码头拽走"
    if stats.get("fails", 0) >= 3:
        return "本周出海九次有八次在喊修船"
    if stats.get("drinks", 0) >= 8:
        return "酒吧昨夜有人把杯子喝到见底"
    if stats.get("weddings"):
        return "连理所又多了一对本该再想想的人"
    if stats.get("gifts"):
        return "有东西从一只口袋漂到另一只"
    if stats.get("craft"):
        return "砧上火花比人话多"
    if stats.get("watches"):
        return "灯塔夜里有人没睡"
    if not stats.get("rows"):
        return "本周岛上安静得像账本没人翻"
    return "潮声把这周的事又说了一遍"


def _object_line(text: str) -> bool:
    return any(mark in (text or "") for mark in OBJECT_MARKS)


async def compile_week(conn, *, ts: int | None = None) -> dict[str, Any]:
    start = week_start(ts)
    rows = await (await conn.execute(
        """
        SELECT action, text, actor_id, created_at
        FROM chronicle
        WHERE created_at>=?
        ORDER BY id DESC
        LIMIT 500
        """,
        (start,),
    )).fetchall()
    stats: dict[str, Any] = {
        "rows": len(rows),
        "drinks": 0,
        "fails": 0,
        "weddings": [],
        "gifts": [],
        "craft": [],
        "watches": 0,
        "rare_fish": [],
        "objects": [],
        "voyages": 0,
        "songs": [],
    }
    for action, text, _actor, _at in rows:
        t = text or ""
        if action == "bar_order":
            stats["drinks"] += 1
        elif action == "voyage":
            stats["voyages"] += 1
            if "风暴折返" in t or "船损" in t:
                stats["fails"] += 1
        elif action == "marriage" and "成婚" in t:
            stats["weddings"].append(t.split("\n", 1)[0][:80])
        elif action == "gift":
            stats["gifts"].append(t[:80])
            if _object_line(t):
                stats["objects"].append(t[:80])
        elif action == "craft" and "取走" in t:
            stats["craft"].append(t[:80])
            if _object_line(t):
                stats["objects"].append(t[:80])
        elif action == "buxing" and "在灯塔守夜" in t:
            stats["watches"] += 1
        elif action == "bar_song":
            stats["songs"].append(t[:80])
        elif action in ("tide", "pen"):
            for name in RARE_FISH:
                if name in t:
                    stats["rare_fish"].append(t[:80])
                    break
    lines: list[str] = []
    if stats["rare_fish"]:
        lines.append(stats["rare_fish"][0])
    elif any(a == "tide" for a, *_ in rows):
        hit = next((t for a, t, *_ in rows if a == "tide"), "")
        if hit:
            lines.append(hit[:80])
    if stats["fails"]:
        lines.append(f"出航翻车 {stats['fails']} 回。修船的锤子这周没闲着。")
    if stats["drinks"]:
        lines.append(f"酒吧记了 {stats['drinks']} 杯。有人明天会后悔。")
    if stats["weddings"]:
        lines.append(stats["weddings"][0])
    if stats["objects"]:
        lines.append("物的履历：" + stats["objects"][0])
    elif stats["gifts"]:
        lines.append(stats["gifts"][0])
    from . import ledger as ledger_mod
    led = await ledger_mod.recent_lines(conn, since=start, limit=2)
    if led:
        lines = [ln for ln in lines if not ln.startswith("物的履历：")]
        lines.append("物的履历：" + led[0])
    if stats["craft"]:
        lines.append(stats["craft"][0])
    if stats["songs"]:
        lines.append("墙上还在哼：" + stats["songs"][0])
    if stats["watches"]:
        lines.append(f"灯塔守夜 {stats['watches']} 回。光还在。")
    climate = world.active_climate_effect()
    if climate:
        from . import config
        label = config.SEASON_CLIMATE_LABELS.get(climate, climate)
        lines.append(f"本周气候还是{label}。天气不是顶上那一句空话。")
    w = world.current_weather()
    lines.append(world.WEATHER_HINT.get(w, ""))
    lines = [ln for ln in lines if ln]
    if not lines:
        lines.append("没捞到大新闻。人还在，地还在。")
    from . import works as works_mod
    work = await works_mod.snapshot(conn)
    headline = (work or {}).get("headline") or ""
    if headline:
        lines = [ln for ln in lines if ln != headline][:6] + [headline]
    else:
        lines = lines[:8]
    title = _pick_title(stats)
    return {
        "week": cst_week_ordinal(ts),
        "title": title,
        "lines": lines[:8],
        "work": work,
    }


async def payload() -> dict[str, Any]:
    async with db.connect() as conn:
        data = await compile_week(conn)
        await conn.commit()
    return data


async def report_text() -> str:
    data = await payload()
    lines = [f"潮汐周报 · 《{data['title']}》", "根据本周岛上真事写成。不是周目标，也不是厅示。"]
    lines.extend(f"  · {ln}" for ln in data["lines"])
    lines.append("人类：广场点潮汐公告，或上手页潮生会点本周纪事。")
    return "\n".join(lines)

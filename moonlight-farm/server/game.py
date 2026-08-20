import hashlib
import random
import re
from typing import Any

import aiosqlite

from . import db
from .catalog import CROPS, FISH, ITEM_NAMES, ITEM_PRICES
from .config import (
    CATCH_FINE_MOON,
    CROP_GROW_SECONDS,
    DAILY_COOK_LIMIT,
    FISH_BAIT_COST,
    HOUSE_COST,
    SPECIES,
    START_MOON,
    STEAL_ACTIVE_WINDOW,
    STEAL_YIELD_RATIO,
    WORK_MOON,
)


def _crop_ready(plot: dict[str, Any], grow_seconds: int | None = None) -> bool:
    if not plot.get("crop") or not plot.get("planted_at"):
        return False
    grow = grow_seconds or CROPS.get(plot["crop"], {}).get("grow", CROP_GROW_SECONDS)
    return db.now() - plot["planted_at"] >= grow


def _crop_withered(plot: dict[str, Any], grow_seconds: int | None = None) -> bool:
    if not plot.get("crop") or not plot.get("planted_at"):
        return False
    grow = grow_seconds or CROPS.get(plot["crop"], {}).get("grow", CROP_GROW_SECONDS)
    return db.now() - plot["planted_at"] >= grow * 2


def _format_plot(plot: dict[str, Any]) -> str:
    slot = plot["slot"]
    if not plot.get("crop"):
        return f"  地块{slot}: 空"
    crop = plot["crop"]
    meta = CROPS.get(crop, {"name": crop, "emoji": "🌱"})
    if _crop_withered(plot, meta.get("grow")):
        return f"  地块{slot}: {meta['emoji']}{meta['name']}（已枯）"
    if _crop_ready(plot, meta.get("grow")):
        state = "可收"
    elif plot.get("watered"):
        state = "生长中"
    else:
        state = "需浇水"
    return f"  地块{slot}: {meta['emoji']}{meta['name']}（{state}）"


async def require_player(key_id: int) -> dict[str, Any]:
    player = await db.get_player_by_key_id(key_id)
    if not player or not player["registered"]:
        raise ValueError("请先调用 garden_register 注册角色")
    await db.touch_player(player["id"])
    return player


async def garden_guide() -> str:
    return "\n".join([
        "# 月光农场 MCP 指南",
        "",
        "1. garden_register(name, bio, species, appearance) — 首次注册",
        "2. garden_profile() / garden_whois(name) — 看资料",
        "3. farm(command) — plant/water/harvest/steal/note/neighbors/status/buy",
        "4. fish(command) — cast/status",
        "5. house(command) — build/name/visit/gift/status",
        "6. pet(command) — adopt/feed/play/status",
        "7. bottle(command) — throw/pick/reply/list",
        "8. inventory(command) — list/sell",
        "9. kitchen(command) — cook/recipes",
        "10. garden_work() — 打零工赚 moon",
        "",
        "命令可用 ; 连接，例如：farm(\"plant 1 cabbage; water\")",
        "时间均为 UTC。作物成熟后会继续生长直到枯萎，记得及时收获。",
        f"可选物种：{', '.join(SPECIES)}",
    ])


async def garden_profile(key_id: int) -> str:
    player = await require_player(key_id)
    plots = await db.get_plots(player["id"])
    inv = await db.get_inventory(player["id"])
    lines = [
        f"名字: {player['name']}",
        f"简介: {player['bio']}",
        f"物种: {player['species']}",
        f"外观: {player['appearance']}",
        f"moon: {player['moon']}",
        f"地块: {player['plot_count']}",
        f"小屋: {'已建「' + player['house_name'] + '」' if player['house_built'] else '未建'}",
    ]
    if player["pet_name"]:
        lines.append(f"宠物: {player['pet_name']}（{player['pet_species']}，心情 {player['pet_mood']}）")
    lines.append("地块状态:")
    lines.extend(_format_plot(p) for p in plots)
    if inv:
        lines.append("背包:")
        for item, qty in inv.items():
            lines.append(f"  {ITEM_NAMES.get(item, item)} x{qty}")
    return "\n".join(lines)


async def garden_profile_edit(key_id: int, bio: str = "", appearance: str = "") -> str:
    player = await require_player(key_id)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        if bio.strip():
            await conn.execute("UPDATE players SET bio = ? WHERE id = ?", (bio.strip()[:200], player["id"]))
        if appearance.strip():
            await conn.execute(
                "UPDATE players SET appearance = ? WHERE id = ?",
                (appearance.strip()[:120], player["id"]),
            )
        await conn.commit()
    return "资料已更新"


async def garden_whois(name: str) -> str:
    target = await db.get_player_by_name(name)
    if not target or not target["registered"]:
        raise ValueError(f"找不到园丁: {name}")
    plots = await db.get_plots(target["id"])
    lines = [
        f"名字: {target['name']}",
        f"简介: {target['bio']}",
        f"物种: {target['species']}",
        f"外观: {target['appearance']}",
        f"最近活跃: {target['last_active_at']} (UTC epoch)",
        f"小屋: {'「' + target['house_name'] + '」' if target['house_built'] else '无'}",
    ]
    if target["pet_name"]:
        lines.append(f"宠物: {target['pet_name']}（{target['pet_species']}）")
    lines.append("公开地块:")
    lines.extend(_format_plot(p) for p in plots)
    return "\n".join(lines)


async def garden_work(key_id: int) -> str:
    player = await require_player(key_id)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE players SET moon = moon + ? WHERE id = ?",
            (WORK_MOON, player["id"]),
        )
        await conn.commit()
    await db.add_feed("work", f"{player['name']} 打零工赚了 {WORK_MOON} moon", player["id"])
    return f"赚了 {WORK_MOON} moon"


async def _farm_one(player: dict[str, Any], cmd: str) -> str:
    cmd = cmd.strip()
    if not cmd:
        return "空命令"
    parts = cmd.split(maxsplit=2)
    verb = parts[0].lower()

    if verb == "status":
        plots = await db.get_plots(player["id"])
        return "农场状态\n" + "\n".join(_format_plot(p) for p in plots)

    if verb == "neighbors":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT name, species, last_active_at FROM players WHERE registered = 1 AND id != ? ORDER BY last_active_at DESC LIMIT 20",
                (player["id"],),
            )
            rows = await cur.fetchall()
        if not rows:
            return "附近还没有其他园丁"
        return "\n".join(
            f"- {r['name']}（{r['species']}，最近活跃 {r['last_active_at']}）" for r in rows
        )

    if verb == "buy" and len(parts) >= 3:
        qty = int(parts[1])
        crop = parts[2].lower()
        if crop not in CROPS:
            raise ValueError(f"未知作物: {crop}")
        seed = f"seed_{crop}"
        cost = CROPS[crop]["seed_price"] * qty
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute("SELECT moon FROM players WHERE id = ?", (player["id"],))
            moon = (await cur.fetchone())[0]
            if moon < cost:
                raise ValueError(f"moon 不足，需要 {cost}")
            await conn.execute("UPDATE players SET moon = moon - ? WHERE id = ?", (cost, player["id"]))
            await db.add_item(conn, player["id"], seed, qty)
            await conn.commit()
        return f"买了 {CROPS[crop]['name']}种子 x{qty}，花费 {cost} moon"

    if verb == "plant" and len(parts) >= 3:
        slot = int(parts[1])
        crop = parts[2].lower()
        if crop not in CROPS:
            raise ValueError(f"未知作物: {crop}")
        seed = f"seed_{crop}"
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute(
                "SELECT * FROM plots WHERE player_id = ? AND slot = ?",
                (player["id"], slot),
            )
            plot = await cur.fetchone()
            if not plot:
                raise ValueError(f"没有地块 {slot}")
            if plot[3]:
                raise ValueError(f"地块 {slot} 已有作物")
            if not await db.take_item(conn, player["id"], seed, 1):
                raise ValueError(f"缺少 {CROPS[crop]['name']}种子")
            await conn.execute(
                "UPDATE plots SET crop = ?, planted_at = ?, watered = 0 WHERE player_id = ? AND slot = ?",
                (crop, db.now(), player["id"], slot),
            )
            await conn.commit()
        return f"在地块 {slot} 种下了 {CROPS[crop]['emoji']}{CROPS[crop]['name']}"

    if verb == "water":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute(
                "SELECT slot, crop FROM plots WHERE player_id = ? AND crop IS NOT NULL AND watered = 0",
                (player["id"],),
            )
            rows = await cur.fetchall()
            if not rows:
                return "没有需要浇水的地"
            for slot, _ in rows:
                await conn.execute(
                    "UPDATE plots SET watered = 1 WHERE player_id = ? AND slot = ?",
                    (player["id"], slot),
                )
            await conn.commit()
        return f"浇了 {len(rows)} 块地"

    if verb == "harvest":
        harvested = []
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("SELECT * FROM plots WHERE player_id = ?", (player["id"],))
            plots = [dict(r) for r in await cur.fetchall()]
            for plot in plots:
                if not _crop_ready(plot):
                    continue
                crop = plot["crop"]
                item = f"crop_{crop}"
                await db.add_item(conn, player["id"], item, 1)
                await conn.execute(
                    "UPDATE plots SET crop = NULL, planted_at = NULL, watered = 0 WHERE id = ?",
                    (plot["id"],),
                )
                harvested.append(CROPS[crop]["name"])
            for plot in plots:
                if _crop_withered(plot):
                    await conn.execute(
                        "UPDATE plots SET crop = NULL, planted_at = NULL, watered = 0 WHERE id = ?",
                        (plot["id"],),
                    )
            await conn.commit()
        if not harvested:
            return "没有可收获的作物"
        await db.add_feed("harvest", f"{player['name']} 收获了 {', '.join(harvested)}", player["id"])
        return f"收获了: {', '.join(harvested)}"

    if verb == "steal" and len(parts) >= 3:
        target_name = parts[1]
        slot = int(parts[2])
        target = await db.get_player_by_name(target_name)
        if not target:
            raise ValueError(f"找不到 {target_name}")
        if target["id"] == player["id"]:
            raise ValueError("不能偷自己的菜")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM plots WHERE player_id = ? AND slot = ?",
                (target["id"], slot),
            )
            plot = dict(await cur.fetchone() or {})
            if not plot or not _crop_ready(plot):
                raise ValueError("那块地没有可偷的成熟作物")
            caught = db.now() - target["last_active_at"] <= STEAL_ACTIVE_WINDOW
            crop = plot["crop"]
            item = f"crop_{crop}"
            if caught:
                await conn.execute(
                    "UPDATE players SET moon = MAX(0, moon - ?) WHERE id = ?",
                    (CATCH_FINE_MOON, player["id"]),
                )
                await conn.execute(
                    "UPDATE plots SET crop = NULL, planted_at = NULL, watered = 0 WHERE id = ?",
                    (plot["id"],
                    ),
                )
                await conn.commit()
                msg = f"{player['name']} 偷 {target['name']} 的地 {slot} 被当场抓住，罚 {CATCH_FINE_MOON} moon"
                await db.add_feed("caught", msg, player["id"], target["id"])
                return msg
            qty = 1 if random.random() > 0.3 else 0
            if qty:
                await db.add_item(conn, player["id"], item, qty)
            await conn.execute(
                "UPDATE plots SET crop = NULL, planted_at = NULL, watered = 0 WHERE id = ?",
                (plot["id"],),
            )
            await conn.commit()
        msg = f"{player['name']} 从 {target['name']} 的地 {slot} 偷走 {CROPS[crop]['name']}"
        await db.add_feed("steal", msg, player["id"], target["id"])
        return msg + ("" if qty else "（空手而归）")

    if verb == "note" and len(parts) >= 3:
        target_name = parts[1]
        text = parts[2]
        target = await db.get_player_by_name(target_name)
        if not target:
            raise ValueError(f"找不到 {target_name}")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO notes (from_player_id, to_player_id, text, created_at) VALUES (?, ?, ?, ?)",
                (player["id"], target["id"], text[:200], db.now()),
            )
            await conn.commit()
        msg = f"{player['name']} 在 {target['name']} 的地里留了张条：「{text[:80]}」"
        await db.add_feed("note", msg, player["id"], target["id"])
        return "条子已留下"

    if verb == "apologize" and len(parts) >= 2:
        target_name = parts[1]
        target = await db.get_player_by_name(target_name)
        if not target:
            raise ValueError(f"找不到 {target_name}")
        msg = f"{player['name']} 向 {target['name']} 道歉了"
        await db.add_feed("apology", msg, player["id"], target["id"])
        return msg

    raise ValueError(f"未知 farm 命令: {cmd}")


async def farm(key_id: int, command: str) -> str:
    player = await require_player(key_id)
    chunks = [c.strip() for c in command.split(";") if c.strip()]
    results = []
    for chunk in chunks:
        results.append(await _farm_one(player, chunk))
    return "\n".join(results)


async def fish(key_id: int, command: str) -> str:
    player = await require_player(key_id)
    parts = command.strip().split()
    if not parts:
        raise ValueError("用法: cast [bait_cost] / status")
    verb = parts[0].lower()
    if verb == "status":
        inv = await db.get_inventory(player["id"])
        fish_items = {k: v for k, v in inv.items() if k.startswith("fish_")}
        if not fish_items:
            return "背包里没有鱼"
        return "\n".join(f"{ITEM_NAMES.get(k, k)} x{v}" for k, v in fish_items.items())
    if verb == "cast":
        bait_cost = int(parts[1]) if len(parts) > 1 else FISH_BAIT_COST
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute("SELECT moon FROM players WHERE id = ?", (player["id"],))
            moon = (await cur.fetchone())[0]
            if moon < bait_cost:
                raise ValueError(f"moon 不足，钓鱼需要 {bait_cost} moon")
            await conn.execute(
                "UPDATE players SET moon = moon - ? WHERE id = ?",
                (bait_cost, player["id"]),
            )
            await conn.commit()
        roll = random.random()
        if roll < 0.15:
            return "什么都没钓到"
        fish_key = random.choice(list(FISH.keys()))
        item = f"fish_{fish_key}"
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await db.add_item(conn, player["id"], item, 1)
            await conn.commit()
        meta = FISH[fish_key]
        msg = f"{player['name']} 钓到了 {meta['emoji']}{meta['name']}"
        await db.add_feed("fish", msg, player["id"])
        return msg
    raise ValueError(f"未知 fish 命令: {command}")


async def house(key_id: int, command: str) -> str:
    player = await require_player(key_id)
    chunks = [c.strip() for c in command.split(";") if c.strip()]
    results = []
    for chunk in chunks:
        results.append(await _house_one(player, chunk))
    return "\n".join(results)


async def _house_one(player: dict[str, Any], cmd: str) -> str:
    parts = cmd.split(maxsplit=2)
    verb = parts[0].lower()

    if verb == "status":
        if not player["house_built"]:
            return "还没有小屋"
        return f"小屋「{player['house_name']}」已建"

    if verb == "build":
        if player["house_built"]:
            return "已经有小屋了"
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute("SELECT moon, plot_count FROM players WHERE id = ?", (player["id"],))
            moon, plots = (await cur.fetchone())
            if moon < HOUSE_COST:
                raise ValueError(f"建小屋需要 {HOUSE_COST} moon")
            if plots <= 1:
                raise ValueError("至少需要 2 块地，建屋会占用 1 块")
            await conn.execute(
                "UPDATE players SET moon = moon - ?, house_built = 1, plot_count = plot_count - 1 WHERE id = ?",
                (HOUSE_COST, player["id"]),
            )
            cur = await conn.execute(
                "SELECT id FROM plots WHERE player_id = ? ORDER BY slot DESC LIMIT 1",
                (player["id"],),
            )
            row = await cur.fetchone()
            if row:
                await conn.execute("DELETE FROM plots WHERE id = ?", (row[0],))
            await conn.commit()
        msg = f"{player['name']} 盖好了小屋"
        await db.add_feed("house", msg, player["id"])
        return msg + f"，花费 {HOUSE_COST} moon，占用 1 块地"

    if verb == "name" and len(parts) >= 2:
        house_name = " ".join(parts[1:])[:40]
        if not player["house_built"]:
            raise ValueError("先 build 小屋")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "UPDATE players SET house_name = ? WHERE id = ?",
                (house_name, player["id"]),
            )
            await conn.commit()
        return f"小屋命名为「{house_name}」"

    if verb == "visit" and len(parts) >= 2:
        target = await db.get_player_by_name(parts[1])
        if not target:
            raise ValueError("找不到该园丁")
        online = db.now() - target["last_active_at"] <= STEAL_ACTIVE_WINDOW
        house = target["house_name"] or "未命名小屋"
        state = "在家" if online else "不在"
        return f"拜访 {target['name']}：{house}（{state}）"

    if verb == "gift" and len(parts) >= 3:
        m = re.match(r"(\S+)\s+(\S+)\s+(\d+)$", cmd)
        if not m:
            raise ValueError("用法: gift Alice crop_cabbage 3")
        target_name, item, qty_s = m.group(1), m.group(2), m.group(3)
        qty = int(qty_s)
        target = await db.get_player_by_name(target_name)
        if not target:
            raise ValueError("找不到该园丁")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            if not await db.take_item(conn, player["id"], item, qty):
                raise ValueError(f"背包里没有足够的 {item}")
            online = db.now() - target["last_active_at"] <= STEAL_ACTIVE_WINDOW
            if online:
                await db.add_item(conn, target["id"], item, qty)
                await conn.commit()
                msg = f"{player['name']} 当面送给 {target['name']} {ITEM_NAMES.get(item, item)} x{qty}"
                await db.add_feed("gift", msg, player["id"], target["id"])
                return msg
            await conn.execute(
                "INSERT INTO gifts (from_player_id, to_player_id, item, quantity, delivered, created_at) VALUES (?, ?, ?, ?, 0, ?)",
                (player["id"], target["id"], item, qty, db.now()),
            )
            await conn.commit()
            return f"把 {ITEM_NAMES.get(item, item)} x{qty} 放在了 {target['name']} 门口"

    raise ValueError(f"未知 house 命令: {cmd}")


async def pet(key_id: int, command: str) -> str:
    player = await require_player(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        if not player["pet_name"]:
            return "还没有宠物，用 pet adopt 名字 物种"
        return f"{player['pet_name']}（{player['pet_species']}）心情 {player['pet_mood']}/100"

    if verb == "adopt" and len(parts) >= 3:
        pet_name = parts[1][:20]
        pet_species = parts[2][:20]
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "UPDATE players SET pet_name = ?, pet_species = ?, pet_mood = 80 WHERE id = ?",
                (pet_name, pet_species, player["id"]),
            )
            await conn.commit()
        msg = f"{player['name']} 收养了宠物 {pet_name}（{pet_species}）"
        await db.add_feed("pet", msg, player["id"])
        return msg

    if verb == "feed":
        if not player["pet_name"]:
            raise ValueError("还没有宠物")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute("SELECT moon FROM players WHERE id = ?", (player["id"],))
            moon = (await cur.fetchone())[0]
            if moon < 5:
                raise ValueError("喂宠物需要 5 moon")
            await conn.execute(
                "UPDATE players SET moon = moon - 5, pet_mood = MIN(100, pet_mood + 15) WHERE id = ?",
                (player["id"],),
            )
            await conn.commit()
        return f"喂了 {player['pet_name']}，心情 +15"

    if verb == "play":
        if not player["pet_name"]:
            raise ValueError("还没有宠物")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "UPDATE players SET pet_mood = MIN(100, pet_mood + 10) WHERE id = ?",
                (player["id"],),
            )
            await conn.commit()
        return f"和 {player['pet_name']} 玩了一会儿"

    raise ValueError(f"未知 pet 命令: {command}")


async def bottle(key_id: int, command: str) -> str:
    player = await require_player(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "list"

    if verb == "list":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT id, text, mood, created_at FROM bottles WHERE picked_by IS NULL ORDER BY created_at DESC LIMIT 10"
            )
            rows = await cur.fetchall()
        if not rows:
            return "海上没有漂流瓶"
        return "\n".join(f"#{r['id']} [{r['mood']}] {r['text'][:60]}" for r in rows)

    if verb == "throw" and len(parts) >= 2:
        mood = parts[1] if len(parts) == 2 else parts[2] if len(parts) >= 3 else ""
        text = parts[2] if len(parts) >= 3 else parts[1]
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO bottles (author_id, text, mood, created_at) VALUES (?, ?, ?, ?)",
                (player["id"], text[:200], mood[:40], db.now()),
            )
            await conn.commit()
        return "瓶子已扔进海里"

    if verb == "pick" and len(parts) >= 2:
        bottle_id = int(parts[1])
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("SELECT * FROM bottles WHERE id = ?", (bottle_id,))
            row = await cur.fetchone()
            if not row:
                raise ValueError("没有这个瓶子")
            if row["picked_by"]:
                raise ValueError("瓶子已被捡走")
            await conn.execute(
                "UPDATE bottles SET picked_by = ? WHERE id = ?",
                (player["id"], bottle_id),
            )
            await conn.commit()
            author = await db.get_player_by_id(row["author_id"])
            author_name = author["name"] if author else "未知"
            return f"捡到的瓶子来自 {author_name}：{row['text']}"

    if verb == "reply" and len(parts) >= 3:
        bottle_id = int(parts[1])
        reply = parts[2]
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "UPDATE bottles SET reply = ? WHERE id = ? AND author_id = ?",
                (reply[:200], bottle_id, player["id"]),
            )
            await conn.commit()
        return "已回复"

    raise ValueError(f"未知 bottle 命令: {command}")


async def inventory(key_id: int, command: str) -> str:
    player = await require_player(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "list"
    if verb == "list":
        inv = await db.get_inventory(player["id"])
        if not inv:
            return "背包是空的"
        lines = [f"moon: {player['moon']}"]
        for item, qty in inv.items():
            price = ITEM_PRICES.get(item, 0)
            lines.append(f"  {ITEM_NAMES.get(item, item)} x{qty}（卖 {price}/个）")
        return "\n".join(lines)
    if verb == "sell" and len(parts) >= 3:
        item = parts[1]
        qty = int(parts[2])
        price = ITEM_PRICES.get(item)
        if not price:
            raise ValueError(f"不能卖 {item}")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            if not await db.take_item(conn, player["id"], item, qty):
                raise ValueError("数量不足")
            gain = price * qty
            await conn.execute(
                "UPDATE players SET moon = moon + ? WHERE id = ?",
                (gain, player["id"]),
            )
            await conn.commit()
        return f"卖出 {ITEM_NAMES.get(item, item)} x{qty}，获得 {gain} moon"
    raise ValueError(f"未知 inventory 命令: {command}")


async def kitchen(key_id: int, command: str) -> str:
    player = await require_player(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "recipes"
    if verb == "recipes":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT r.name, r.score, p.name AS inventor
                FROM recipes r JOIN players p ON p.id = r.inventor_id
                ORDER BY r.created_at DESC LIMIT 20
                """
            )
            rows = await cur.fetchall()
        if not rows:
            return "还没有人发明菜"
        return "\n".join(f"「{r['name']}」{r['score']}分 by {r['inventor']}" for r in rows)

    if verb == "cook":
        ingredients = parts[1:]
        if len(ingredients) < 2 or len(ingredients) > 3:
            raise ValueError("做菜需要 2~3 样食材，如 cook crop_potato crop_tomato")
        day = db.now() // 86400
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT cooks_today, cook_day FROM players WHERE id = ?",
                (player["id"],),
            )
            row = await cur.fetchone()
            cooks = row["cooks_today"] if row["cook_day"] == day else 0
            if cooks >= DAILY_COOK_LIMIT:
                raise ValueError(f"今天已做 {DAILY_COOK_LIMIT} 道菜")
            for item in ingredients:
                if not await db.take_item(conn, player["id"], item, 1):
                    raise ValueError(f"缺少 {item}")
            signature = "|".join(sorted(ingredients))
            cur = await conn.execute("SELECT * FROM recipes WHERE signature = ?", (signature,))
            existing = await cur.fetchone()
            if existing:
                dish_name = existing["name"]
                score = existing["score"]
                dish_item = f"dish_{existing['id']}"
            else:
                score = random.randint(2, 10)
                names = ["月下", "星光", "暗影", "暖炉", "晨露"]
                bases = ["烩", "汤", "卷", "串", "锅"]
                dish_name = random.choice(names) + random.choice(bases)
                await conn.execute(
                    "INSERT INTO recipes (signature, name, inventor_id, score, created_at) VALUES (?, ?, ?, ?, ?)",
                    (signature, dish_name, player["id"], score, db.now()),
                )
                cur = await conn.execute("SELECT last_insert_rowid()")
                rid = (await cur.fetchone())[0]
                dish_item = f"dish_{rid}"
                msg = f"{player['name']} 发明了「{dish_name}」（{score} 分）"
                await db.add_feed("cook", msg, player["id"])
            await db.add_item(conn, player["id"], dish_item, 1)
            new_cooks = (cooks + 1) if row["cook_day"] == day else 1
            await conn.execute(
                "UPDATE players SET cooks_today = ?, cook_day = ? WHERE id = ?",
                (new_cooks, day, player["id"]),
            )
            await conn.commit()
        return f"做出「{dish_name}」（{score} 分），入背包 {dish_item}"
    raise ValueError(f"未知 kitchen 命令: {command}")

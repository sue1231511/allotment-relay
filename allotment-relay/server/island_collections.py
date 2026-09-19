"""岛收集簿 — 里程碑点亮（持久化解锁）。"""
from __future__ import annotations

from . import db
from .catalog import ITEM_NAMES
from .game import require_steward

# (key, 标题, satchel/meal item 或 None, 里程碑键)
ENTRIES: list[tuple[str, str, str | None, str | None]] = [
    ("kale", "甘蓝入门", "crop_kale", None),
    ("beet", "甜菜一行", "crop_beet", None),
    ("fogpea", "雾豆初收", "crop_fogpea", None),
    ("ginger", "潮姜入袋", "crop_tide_ginger", None),
    ("herring", "鲱鳞闪光", "fish_herring", None),
    ("sardine", "沙丁一串", "fish_sardine", None),
    ("mackerel", "鲭鱼入网", "fish_mackerel", None),
    ("pickles", "腌坛开盖", "pickles", None),
    ("compost", "堆肥上手", "compost", None),
    ("quarry_copper", "铜脉初鸣", "quarry_copper", None),
    ("quarry_salt", "盐晶在手", "quarry_salt", None),
    ("quarry_iron_bar", "铁条出炉", "quarry_iron_bar", None),
    ("craft_copper_nails", "岸钉入包", "craft_copper_nails", None),
    ("ut_pit_silt", "坑底淤泥", "ut_pit_silt", None),
    ("ut_brine_crystal", "卤晶在手", "ut_brine_crystal", None),
    ("proc_black_salt", "岸黑盐成", "proc_black_salt", None),
    ("skiff", "第一艘船", None, "boat"),
    ("barn", "畜栏开张", None, "barn"),
    ("hut2", "小屋二档", None, "hut2"),
    ("hut4", "临海邸梦", None, "hut4"),
    ("greenhouse", "温室起架", None, "greenhouse"),
    ("eatery", "开过小馆", None, "eatery"),
    ("eatery_combo_dine", "套餐堂食", None, "eatery_combo_dine"),
    ("eatery_set_served", "齐柜出餐", None, "eatery_set_served"),
    ("tide_ginger_crab", "潮姜蟹盏", "meal:tide_ginger_crab", None),
    ("brine_clam_pot", "卤蟹锅香", "meal:brine_clam_pot", None),
    ("black_salt_fish", "黑盐炖鱼成", "meal:black_salt_fish", None),
    ("fog_mushroom_soup", "雾菇汤香", "meal:fog_mushroom_soup", None),
    ("lantern_sashimi", "灯笼鱼刺身", "meal:lantern_sashimi", None),
    ("undertide_enter", "潮下踏足", None, "undertide"),
    ("voyage_far", "远海归港", None, "voyage_far"),
    ("voyage_deep", "深漂归港", None, "voyage_deep"),
    ("drink_mist", "自泡雾豆茶", "drink_mist_pea_tea", None),
    ("drink_fog_port", "雾港热朗姆", "drink_fog_port", None),
    ("quarry_tide", "潮石入袋", "quarry_tide_stone", None),
    ("quarry_fog_lead", "雾铅在握", "quarry_fog_lead", None),
    ("fish_lantern", "灯笼鱼影", "fish_lanternfish", None),
    ("bar_work", "洗过酒吧碗", None, "bar_work"),
    ("boat_mod", "船改装上手", None, "boat_mod"),
    ("cofarm", "共耕之约", None, "cofarm"),
    ("assist_day", "帮邻居一天", None, "assist_log"),
    ("deep_echo_drink", "点过深海回声", None, "bar_deep_echo"),
    ("cutter_boat", "切波艇", None, "boat_cutter"),
    ("drifter_boat", "漂航船", None, "boat_drifter"),
    ("orchard", "首棵成树", None, "orchard"),
    ("hail_black", "黑旗照面", None, "hail_chronicle"),
    ("parley_ok", "海上谈成", None, "parley_win"),
    ("league_week", "周目标出力", None, "league_contrib"),
    ("hearth_brew", "灶台点亮", None, "hearth_disc"),
    ("marriage", "潮誓成婚", None, "married"),
    ("wall_post", "听潮亭钉牌", None, "wall_post"),
    ("star_tip", "小橘打赏", None, "star_tip"),
    ("fish_kingcrab", "石蟹王", "fish_kingcrab", None),
    ("quarry_marrow", "髓矿", "quarry_marrow", None),
    ("drink_sea_lime", "海涯青柠汽", "drink_sea_lime", None),
    ("watch_hoy", "守潮驳", None, "boat_watch"),
    ("longliner", "延绳船", None, "boat_longliner"),
    ("shed_plot", "温室首收", None, "greenhouse_harvest"),
    ("bar_order", "酒吧点单", None, "bar_order"),
    ("contract_fill", "完成悬赏", None, "contract_fill"),
    ("undertide_pit", "深坑一战", None, "pit_fight"),
    ("layer_link", "层间信使", None, "layer_msg"),
    ("craft_gyotaku", "第一幅鱼拓", "craft_gyotaku", None),
    ("craft_boat_model", "船模入柜", "craft_boat_model", None),
    ("crop_pomelo", "柚子入园", "crop_pomelo", None),
    ("crop_coffee", "咖啡豆熟", "crop_coffee", None),
]


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_collection_unlock (
            steward_id INTEGER NOT NULL REFERENCES stewards(id),
            coll_key TEXT NOT NULL,
            unlocked_at INTEGER NOT NULL,
            PRIMARY KEY (steward_id, coll_key)
        )
        """
    )


async def _has_item(conn, steward_id: int, item: str) -> bool:
    if item.startswith("meal:"):
        dish = item.split(":", 1)[1]
        cur = await conn.execute(
            """
            SELECT 1 FROM meal_storage
            WHERE steward_id=? AND dish_key=? AND quantity>0 LIMIT 1
            """,
            (steward_id, dish),
        )
        return (await cur.fetchone()) is not None
    cur = await conn.execute(
        "SELECT 1 FROM satchel WHERE steward_id=? AND item=? AND quantity>0 LIMIT 1",
        (steward_id, item),
    )
    return (await cur.fetchone()) is not None


async def _milestone(conn, steward_id: int, key: str | None) -> bool:
    if key == "boat":
        cur = await conn.execute(
            "SELECT boat_key FROM stewards WHERE id=?", (steward_id,)
        )
        row = await cur.fetchone()
        return bool(row and row[0])
    if key == "barn":
        cur = await conn.execute(
            "SELECT barn_built FROM stewards WHERE id=?", (steward_id,)
        )
        return bool(int((await cur.fetchone())[0] or 0))
    if key == "hut2":
        cur = await conn.execute(
            "SELECT hut_built, hut_level FROM stewards WHERE id=?",
            (steward_id,),
        )
        row = await cur.fetchone()
        return bool(row and int(row[0]) and int(row[1] or 0) >= 2)
    if key == "hut4":
        cur = await conn.execute(
            "SELECT hut_built, hut_level FROM stewards WHERE id=?",
            (steward_id,),
        )
        row = await cur.fetchone()
        return bool(row and int(row[0]) and int(row[1] or 0) >= 4)
    if key == "greenhouse":
        cur = await conn.execute(
            "SELECT 1 FROM parcels WHERE steward_id=? AND greenhouse=1 LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "eatery":
        cur = await conn.execute(
            "SELECT eatery_open FROM stewards WHERE id=?", (steward_id,)
        )
        return bool(int((await cur.fetchone())[0] or 0))
    if key == "eatery_combo_dine":
        cur = await conn.execute(
            """
            SELECT 1 FROM chronicle
            WHERE actor_id=? AND action='eatery' AND text LIKE '%吃套餐%' LIMIT 1
            """,
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "eatery_set_served":
        cur = await conn.execute(
            """
            SELECT 1 FROM chronicle
            WHERE target_id=? AND action='eatery' AND text LIKE '%吃套餐%' LIMIT 1
            """,
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "undertide":
        cur = await conn.execute(
            "SELECT access FROM steward_undertide WHERE steward_id=?",
            (steward_id,),
        )
        row = await cur.fetchone()
        return bool(row and int(row[0] or 0))
    if key == "voyage_far":
        cur = await conn.execute(
            "SELECT 1 FROM voyages WHERE steward_id=? AND route='far' LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "voyage_deep":
        cur = await conn.execute(
            "SELECT 1 FROM voyages WHERE steward_id=? AND route='deep' LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "bar_work":
        cur = await conn.execute(
            "SELECT 1 FROM bar_shifts WHERE steward_id=? LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "boat_mod":
        cur = await conn.execute(
            "SELECT 1 FROM steward_boat_mod WHERE steward_id=? LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "cofarm":
        cur = await conn.execute(
            "SELECT 1 FROM neighbor_cofarm WHERE steward_id=? LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "assist_log":
        cur = await conn.execute(
            "SELECT 1 FROM assist_log WHERE helper_id=? LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "bar_deep_echo":
        cur = await conn.execute(
            "SELECT 1 FROM bar_drink_orders WHERE patron_id=? AND drink_key='deep_echo' LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "boat_cutter":
        cur = await conn.execute(
            "SELECT boat_key FROM stewards WHERE id=?", (steward_id,),
        )
        row = await cur.fetchone()
        bk = row[0] if row else ""
        return bk in ("cutter", "drifter")
    if key == "boat_drifter":
        cur = await conn.execute(
            "SELECT boat_key FROM stewards WHERE id=?", (steward_id,),
        )
        row = await cur.fetchone()
        return row and row[0] == "drifter"
    if key == "orchard":
        cur = await conn.execute(
            "SELECT 1 FROM parcels WHERE steward_id=? AND orchard=1 AND crop IS NOT NULL LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "hail_chronicle":
        cur = await conn.execute(
            "SELECT 1 FROM chronicle WHERE actor_id=? AND text LIKE '%黑旗%' LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "parley_win":
        cur = await conn.execute(
            "SELECT 1 FROM chronicle WHERE actor_id=? AND text LIKE '%黑旗：parley%' LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "league_contrib":
        cur = await conn.execute(
            "SELECT 1 FROM league_contrib WHERE steward_id=? LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "hearth_disc":
        cur = await conn.execute(
            "SELECT 1 FROM hearth_discoveries WHERE discoverer_id=? LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "married":
        cur = await conn.execute(
            "SELECT 1 FROM marriages WHERE steward_id=? AND status='married' LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "wall_post":
        cur = await conn.execute(
            "SELECT 1 FROM wall_threads WHERE steward_id=? AND deleted=0 LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "star_tip":
        cur = await conn.execute(
            "SELECT 1 FROM star_tips WHERE steward_id=? LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "boat_watch":
        cur = await conn.execute("SELECT boat_key FROM stewards WHERE id=?", (steward_id,))
        row = await cur.fetchone()
        bk = row[0] if row else ""
        return bk in ("watch_hoy", "cutter", "smack", "drifter", "longliner")
    if key == "boat_longliner":
        cur = await conn.execute("SELECT boat_key FROM stewards WHERE id=?", (steward_id,))
        row = await cur.fetchone()
        return row and row[0] in ("longliner", "drifter")
    if key == "greenhouse_harvest":
        cur = await conn.execute(
            """
            SELECT 1 FROM parcels
            WHERE steward_id=? AND greenhouse=1 AND harvest_left=0 AND crop IS NOT NULL
            LIMIT 1
            """,
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "bar_order":
        cur = await conn.execute(
            "SELECT 1 FROM bar_drink_orders WHERE patron_id=? LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "contract_fill":
        cur = await conn.execute(
            "SELECT 1 FROM contracts WHERE filler_id=? AND status='filled' LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "pit_fight":
        cur = await conn.execute(
            "SELECT 1 FROM chronicle WHERE actor_id=? AND text LIKE '%深坑%' LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    if key == "layer_msg":
        cur = await conn.execute(
            "SELECT 1 FROM chronicle WHERE actor_id=? AND text LIKE '%潮返地面%' LIMIT 1",
            (steward_id,),
        )
        return (await cur.fetchone()) is not None
    return False


async def _entry_met(conn, steward_id: int, entry: tuple) -> bool:
    _key, _title, item, mile = entry
    if item:
        return await _has_item(conn, steward_id, item)
    return await _milestone(conn, steward_id, mile)


async def sync_unlocks(conn, steward_id: int) -> int:
    await ensure_table(conn)
    from . import boat_mods as bmods_mod
    await bmods_mod.ensure_table(conn)
    from . import neighbor_cofarm as cofarm_mod
    await cofarm_mod.ensure_table(conn)
    new = 0
    now = db.now()
    for entry in ENTRIES:
        key = entry[0]
        if not await _entry_met(conn, steward_id, entry):
            continue
        cur = await conn.execute(
            """
            INSERT OR IGNORE INTO steward_collection_unlock (steward_id, coll_key, unlocked_at)
            VALUES (?,?,?)
            """,
            (steward_id, key, now),
        )
        if cur.rowcount:
            new += 1
    s = await db.get_steward_by_id(steward_id)
    if s:
        from . import progress as progress_mod
        await progress_mod.scan_achievements(conn, s)
    return new


async def sheet(conn, steward_id: int) -> str:
    await sync_unlocks(conn, steward_id)
    cur = await conn.execute(
        "SELECT coll_key FROM steward_collection_unlock WHERE steward_id=?",
        (steward_id,),
    )
    unlocked = {r[0] for r in await cur.fetchall()}
    lines = [f"岛收集簿（{len(ENTRIES)} 项，点亮后永久记录；不是 lore scan）："]
    for key, title, item, mile in ENTRIES:
        ok = key in unlocked
        mark = "✓" if ok else "·"
        hint = ""
        if not ok:
            if item and not item.startswith("meal:"):
                hint = ITEM_NAMES.get(item, item)
            elif item:
                hint = item.split(":", 1)[-1]
            elif mile:
                hint = mile
        lines.append(f"  {mark} {title}" + (f"（{hint}）" if hint else ""))
    lines.append(f"进度 {len(unlocked)}/{len(ENTRIES)}。")
    return "\n".join(lines)


async def collection_ops(key_id: int, command: str = "") -> str:
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "status"
    read_ok = verb in ("", "status", "列表", "list", "help", "?", "帮助", "收集")
    s = await require_steward(key_id, exempt_duty=read_ok)
    if verb in ("help", "?", "帮助"):
        return "steward_ops 收集 — 岛收集簿（点亮永久保存；不是 lore scan）"
    async with db.connect() as conn:
        msg = await sheet(conn, s["id"])
        await conn.commit()
        return msg

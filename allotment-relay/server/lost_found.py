"""失物。酒吧/赶海偶尔捡到别人丢掉的东西。可留、问、交给潮生会、送给人。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db
from .catalog import ITEM_NAMES, item_label

ITEMS = {
    "lost_lighter": {
        "title": "银色打火机",
        "mark": "背面刻着一个已经模糊的「橘」",
        "owner": "小橘",
        "story": "lighter",
    },
    "lost_coat": {
        "title": "旧外套",
        "mark": "内袋有一张被水晕开的码头号牌",
        "owner": "",
        "story": "coat",
    },
    "lost_list": {
        "title": "湿了的购物单",
        "mark": "只认得「盐、灯油、不要再买酒」",
        "owner": "",
        "story": "list",
    },
    "lost_photo": {
        "title": "无名照片",
        "mark": "背面没有字。人的脸被潮气糊掉了",
        "owner": "",
        "story": "photo",
    },
    "lost_band": {
        "title": "模糊的银戒",
        "mark": "圈口磨平了，像在口袋里转过很多年",
        "owner": "",
        "story": "band",
    },
}

_BAR_EVENT_ITEM = {
    "ring": "lost_band",
    "lost_coat": "lost_coat",
}


async def maybe_from_bar(conn, steward: dict, event: dict) -> str | None:
    tags = event.get("tags") or []
    if "lost_item" not in tags:
        return None
    key = _BAR_EVENT_ITEM.get(str(event.get("id") or ""), "")
    if not key:
        return None
    return await spawn(conn, steward, key, source="bar")


async def try_wash(s: dict) -> str | None:
    if random.random() > 0.06:
        return None
    key = random.choice(list(ITEMS))
    async with db.connect() as conn:
        line = await spawn(conn, s, key, source="beach")
        await conn.commit()
    return line


async def spawn(conn, steward: dict, item: str, *, source: str) -> str:
    meta = ITEMS[item]
    sid = int(steward["id"])
    owner = meta["owner"]
    if not owner:
        row = await (await conn.execute(
            "SELECT name FROM stewards WHERE id!=? ORDER BY RANDOM() LIMIT 1",
            (sid,),
        )).fetchone()
        owner = (row[0] if row else "") or ""
    now = db.now()
    payload = {
        "title": meta["title"],
        "mark": meta["mark"],
        "owner": owner,
        "story": meta["story"],
        "source": source,
    }
    await conn.execute(
        """
        INSERT INTO lost_items (item, holder_id, owner_hint, mark, payload_json, source, created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            item, sid, owner, meta["mark"],
            json.dumps(payload, ensure_ascii=False),
            source, now,
        ),
    )
    await db.add_item(conn, sid, item, 1)
    from . import ledger as ledger_mod

    where = "酒吧排水口" if source == "bar" else "潮线"
    await ledger_mod.birth(
        conn,
        sid,
        item,
        [
            f"{meta['title']}在{where}被{steward['name']}捡到",
            meta["mark"],
        ],
        qty=1,
    )
    await db.add_chronicle("lost", f"{steward['name']} 捡到{meta['title']}", sid, conn=conn)
    return f"捡到{meta['title']}。{meta['mark']}。可以自己留、去潮生会问、交给潮生会，或送给谁。"


async def held(conn, steward_id: int) -> list[dict[str, Any]]:
    rows = await (await conn.execute(
        """
        SELECT id, item, owner_hint, mark, payload_json, source
        FROM lost_items
        WHERE holder_id=? AND resolved=0
        ORDER BY id DESC LIMIT 8
        """,
        (steward_id,),
    )).fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r[0],
            "item": r[1],
            "label": ITEM_NAMES.get(r[1], r[1]),
            "owner_hint": r[2] or "",
            "mark": r[3] or "",
            "source": r[5] or "",
        })
    return out


async def status_text(conn, steward: dict) -> str:
    rows = await held(conn, steward["id"])
    if not rows:
        return (
            "失物柜这会儿空着。酒吧洗碗、赶海翻沙偶尔会捡到别人丢掉的东西。"
            "捡到了可以自己留、问、交还，或送给谁。不是任务。"
        )
    lines = ["你口袋里的失物："]
    for row in rows:
        extra = f"。{row['mark']}" if row["mark"] else ""
        lines.append(f"  · {row['label']}{extra}")
    lines.append("交还：visit_ops 潮生会 失物 交 银色打火机。问：潮生会 失物 问")
    lines.append("也可以 tote_ops gift 名字 物品 1，送给对的人或送错人。")
    return "\n".join(lines)


async def ask(conn, steward: dict) -> str:
    rows = await held(conn, steward["id"])
    if not rows:
        return "阿簿翻了翻抽屉。「你口袋里没有失物。捡到了再来。」"
    row = rows[0]
    guesses = [
        f"阿簿看了一眼{row['label']}。「潮生会代收。交还就放下，不问你从哪来。」",
        f"「{row['mark']}」他念了一遍。「听潮亭寻人木牌也可以钉。别指望我破案。」",
    ]
    hint = row.get("owner_hint") or ""
    if hint and random.random() < 0.45:
        guesses.append(f"他停了一下。「有人叫{hint}。也可能不是。」")
    else:
        guesses.append("「大多数只是普通东西。少部分会自己开口。」")
    return random.choice(guesses)


async def turn_in(conn, steward: dict, token: str) -> str:
    from .catalog import resolve_item_key

    key = resolve_item_key(token) or token
    row = await (await conn.execute(
        """
        SELECT id, item, owner_hint, mark FROM lost_items
        WHERE holder_id=? AND resolved=0 AND item=?
        ORDER BY id DESC LIMIT 1
        """,
        (steward["id"], key),
    )).fetchone()
    if not row:
        return f"{item_label(key)}不在你的失物里。潮生会 失物 看口袋。"
    if not await db.take_item(conn, steward["id"], key, 1):
        raise ValueError("行囊里没有这件失物")
    from . import ledger as ledger_mod

    await ledger_mod.consume(
        conn, steward["id"], key, 1,
        extra=f"后交给潮生会，{ledger_mod.calendar_phrase()}。履历到此",
    )
    await conn.execute(
        "UPDATE lost_items SET resolved=1, resolution='hui', resolved_at=? WHERE id=?",
        (db.now(), row[0]),
    )
    await db.add_chronicle("lost", f"{steward['name']} 把失物交给潮生会", steward["id"], conn=conn)
    standing = 2 if row[2] else 1
    from . import survival

    await survival.bump(conn, steward["id"], standing=standing)
    label = ITEM_NAMES.get(key, key)
    if row[2]:
        return f"阿簿收下{label}。「记下了。」档信 +{standing}。他没说会不会找到人。"
    return f"阿簿把{label}丢进抽屉。「普通东西。你交了就算完。」档信 +{standing}"


async def note_gift(conn, giver: dict, peer: dict, item: str) -> str | None:
    if item not in ITEMS:
        return None
    row = await (await conn.execute(
        """
        SELECT id, owner_hint FROM lost_items
        WHERE holder_id=? AND resolved=0 AND item=?
        ORDER BY id DESC LIMIT 1
        """,
        (giver["id"], item),
    )).fetchone()
    if not row:
        return None
    owner = (row[1] or "").strip()
    peer_name = peer.get("name") or ""
    if owner and peer_name and owner == peer_name:
        resolution = "right"
        extra = f"{peer_name}盯着看了很久。「这是我的。」没说谢谢。"
    else:
        resolution = "wrong"
        extra = f"{peer_name}收下了。好像不是这份。也没有还回来。"
    await conn.execute(
        """
        UPDATE lost_items SET holder_id=?, resolved=1, resolution=?, resolved_at=?
        WHERE id=?
        """,
        (peer["id"], resolution, db.now(), row[0]),
    )
    await db.add_chronicle(
        "lost",
        f"{giver['name']} 把失物送给{peer_name}（{resolution}）",
        giver["id"],
        conn=conn,
    )
    return extra


async def player_items(conn, steward: dict) -> list[dict[str, Any]]:
    rows = await held(conn, steward["id"])
    items = []
    items.append({
        "sid": "lost-ask",
        "kind": "look",
        "name": "问失物",
        "emoji": "🔍",
        "note": "阿簿看一眼。不破案。",
        "detail": "不是任务。交还或送给谁都行。",
        "price": "问",
        "can": True,
        "target": "lost-ask",
    })
    if not rows:
        items.append({
            "sid": "lost-empty",
            "kind": "look",
            "name": "失物柜",
            "emoji": "🗄️",
            "note": "这会儿空着。酒吧洗碗、赶海翻沙偶尔会捡到。",
            "price": "看",
            "can": True,
            "target": "lost",
        })
        return items
    for row in rows:
        items.append({
            "sid": f"lost-{row['id']}",
            "kind": "lost_turn",
            "name": f"交还 {row['label']}",
            "emoji": "📦",
            "note": row["mark"] or "交给潮生会。",
            "detail": row["mark"],
            "price": "交",
            "can": True,
            "target": row["item"],
        })
    return items

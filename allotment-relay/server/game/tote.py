import random
import re
from typing import Any

import aiosqlite

from .. import config, db, events, flavor, farming, health, survival, world
from .. import commons
from ..catalog import (
    CROPS,
    resolve_crop_key,
    resolve_item_key,
    unknown_crop_message,
    unknown_item_message,
    FORAGE_LOOT,
    ITEM_NAMES,
    ITEM_PRICES,
    SEA_CATCH,
    item_label,
    item_stack_cap,
    suggested_price,
    weighted_fish_pick,
)
from ..config import (
    BADGES,
    BOATS,
    GUILD_SHIFT_DAILY,
    GUILD_TICKETS,
    MARKET_LIST_MAX,
    MARKET_LIST_SLOTS_MAX,
    MARKET_SLOT_COST,
    SWAP_CLAIM_FEE,
    BAR_MANDATORY_DAYS,
)


from .base import _parse_int, _parcel_line, _load_named_plot, require_steward


async def _satchel_stack_expand(s: dict, n: int = 1) -> str:
    extra = int(s.get("satchel_stack_extra") or 0)
    room = config.SATCHEL_STACK_TIERS_MAX - extra
    if room <= 0:
        cap = item_stack_cap("crop_kale", stack_tier=config.SATCHEL_STACK_TIERS_MAX)
        raise ValueError(f"行囊栈已经扩到顶了（每组最多叠 {cap} 份；同种可占多组）")
    n = max(1, min(int(n), room))
    cost = n * config.SATCHEL_STACK_COST
    async with db.connect() as conn:
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        tickets = (await cur.fetchone())[0]
        if tickets < cost:
            raise ValueError(
                f"扩栈需要 {cost} 票（每级 {config.SATCHEL_STACK_COST} 票，+{config.SATCHEL_STACK_STEP} 份/格），"
                f"你只有 {tickets} 票"
            )
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-?, satchel_stack_extra=? WHERE id=?",
            (cost, extra + n, s["id"]),
        )
        await conn.commit()
    new_tier = extra + n
    cap = item_stack_cap("crop_kale", stack_tier=new_tier)
    left = config.SATCHEL_STACK_TIERS_MAX - new_tier
    hint = f"还能扩 {left} 级" if left else "已到顶"
    return (
        f"行囊/潮柜/冰箱每组上限 +{n * config.SATCHEL_STACK_STEP}（-{cost} 票）。"
        f"同种货可占多组（MC 式），现在每组最多 {cap} 份（{hint}）。"
    )



async def _tote_one(s: dict, command: str) -> str:
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "list"
    if verb == "list":
        from ..catalog import format_stack_qty
        from .. import ledger as ledger_mod

        stock = await db.get_satchel(s["id"])
        tier = int(s.get("satchel_stack_extra") or 0)
        cap = item_stack_cap("crop_kale", stack_tier=tier)
        stack_note = (
            f"行囊同种货可占多组（MC 式），每组最多 {cap} 份"
            f"（基础 {config.SATCHEL_STACK}"
        )
        if tier < config.SATCHEL_STACK_TIERS_MAX:
            stack_note += f"，tote_ops 扩栈 加每组上限，{config.SATCHEL_STACK_COST}票/级+{config.SATCHEL_STACK_STEP}"
        stack_note += "；工具/活物 1，装件可多件）"
        async with db.connect() as conn:
            from .. import item_traits as traits_mod
            spoiled = await traits_mod.purge_spoiled(conn, s["id"])
            previews = await ledger_mod.preview_map(conn, s["id"])
        lines = [f"工分票: {s['tickets']}", stack_note]
        if spoiled:
            lines.append("变质丢弃：" + "；".join(spoiled))
        for item, qty in stock.items():
            price = suggested_price(item) or ITEM_PRICES.get(item, 0)
            name = item_label(item)
            item_cap = item_stack_cap(item, stack_tier=tier)
            stack = format_stack_qty(qty, item_cap)
            if item.startswith("fit_") or item.startswith("deco_"):
                lines.append(f"  {name} {stack} · {item} · vend {name} 1（折旧，同 hut_ops 卖掉）")
            else:
                lines.append(f"  {name} {stack} · {item} · vend {price}/个")
            async with db.connect() as conn:
                trait_note = await traits_mod.summary_for_item(conn, s["id"], item)
            if trait_note:
                lines.append(f"      鲜度/品质: {trait_note}")
            story = previews.get(item) or []
            if story:
                lines.extend(f"      {ln}" for ln in story[:3])
        if previews:
            lines.append("有来历的物：tote_ops 履历 看全文。甘蓝那种没有。")
        return "\n".join(lines) if stock else f"工分票: {s['tickets']}\n行囊空"
    if verb in ("履历", "ledger", "来历", "前科"):
        from .. import ledger as ledger_mod

        token = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
        item_key = resolve_item_key(token) if token else None
        if token and not item_key:
            raise ValueError(unknown_item_message(token))
        async with db.connect() as conn:
            rows = await ledger_mod.stories_for(conn, s["id"], item_key)
        if not rows:
            if token:
                return f"{item_label(item_key)}没有履历。戒、稀有鱼、崖上稀矿、工坊出品、鱼拓船模邮票签名遗物、特殊料理才会记。"
            return "行囊里还没有带履历的东西。戒、稀有鱼、崖上稀矿、工坊出品、鱼拓船模邮票签名遗物、特殊料理才会记。甘蓝没有前科。"
        lines = ["物品履历（不是成就，也不加数值）："]
        grouped: dict[str, list[list[str]]] = {}
        for row in rows:
            grouped.setdefault(row["item"], []).append(row["lines"])
        for item, bunch in grouped.items():
            lines.append(f"  {item_label(item)} ×{len(bunch)}")
            show = bunch[:3]
            for i, story in enumerate(show, 1):
                if len(bunch) > 1:
                    lines.append(f"    其一 {i}：")
                lines.extend(f"      {ln}" for ln in story)
            if len(bunch) > 3:
                lines.append(f"    还有 {len(bunch) - 3} 份同名的，来历不一定一样。")
        return "\n".join(lines)
    if verb == "vend" and len(parts) >= 3:
        # 支持批量：vend item1 qty1 item2 qty2 ...（每对一个物品+数量）
        tokens = parts[1:]
        if len(tokens) % 2 != 0:
            raise ValueError("用法: vend 物品 数量 [物品 数量 ...]（物品和数量成对）")
        furniture_only: list[tuple[str, int]] = []
        pairs = []
        for i in range(0, len(tokens), 2):
            item_key = resolve_item_key(tokens[i])
            if not item_key:
                raise ValueError(unknown_item_message(tokens[i]))
            qty = _parse_int(tokens[i + 1])
            if item_key.startswith("fit_") or item_key.startswith("deco_"):
                furniture_only.append((item_key, qty))
                continue
            from .. import fish_ban as fish_ban_mod
            refuse = fish_ban_mod.refuse_trade(item_key)
            if refuse:
                raise ValueError(refuse)
            price = suggested_price(item_key) or ITEM_PRICES.get(item_key, 0)
            if not price:
                raise ValueError(f"不可出售 {item_label(item_key)}（{item_key}）")
            pairs.append((item_key, qty, price))
        if furniture_only and pairs:
            raise ValueError(
                "家具和普通货分开卖。家具一次 vend 羊毛毯 1，"
                "或 hut_ops 卖掉 羊毛毯 确认"
            )
        if furniture_only:
            if len(furniture_only) != 1 or int(furniture_only[0][1]) != 1:
                raise ValueError("家具一次卖一件：vend 羊毛毯 1，或 hut_ops 卖掉 羊毛毯 确认")
            from .. import hut as hut_mod
            return await hut_mod.furniture_sell_command(s, [furniture_only[0][0], "确认"])
        async with db.connect() as conn:
            results = []
            fate_notes: list[str] = []
            from .. import item_traits as traits_mod
            for item_key, qty, price in pairs:
                unit = await traits_mod.vend_unit_price(conn, s["id"], item_key, price)
                if not await db.take_item(conn, s["id"], item_key, qty):
                    raise ValueError(f"数量不足（需要 {item_key} x{qty}）")
                await traits_mod.consume_fifo(conn, s["id"], item_key, qty)
                from .. import ledger as ledger_mod
                await ledger_mod.consume(
                    conn, s["id"], item_key, qty,
                    extra=f"后卖进回收堆，{ledger_mod.calendar_phrase()}。履历到此",
                )
                gain = unit * qty
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets+? WHERE id=?", (gain, s["id"])
                )
                results.append((item_key, qty, gain))
                if item_key == "fish_walkblue":
                    from .. import marine as marine_mod
                    fate_notes.append(
                        await marine_mod.walkblue_fate_event(
                            conn, s["id"], kind="sell", qty=qty, tickets=gain
                        )
                    )
            await conn.commit()
        if len(results) == 1:
            item_key, qty, gain = results[0]
            msg = f"出售 {ITEM_NAMES.get(item_key, item_key)}（{item_key}）x{qty}，+{gain} 票"
        else:
            total = sum(g for _, _, g in results)
            lines = [f"  {ITEM_NAMES.get(k, k)} x{q}，+{g} 票" for k, q, g in results]
            lines.append(f"合计 +{total} 票")
            msg = "批量出售：\n" + "\n".join(lines)
        if fate_notes:
            msg += "\n" + "\n".join(fate_notes)
        return msg
    if verb in ("gifts", "收礼", "收到的礼", "收礼记录"):
        from .. import multi as multi_mod
        limit = 20
        if len(parts) >= 2:
            limit = min(50, max(1, _parse_int(parts[1], "条数")))
        rows = await db.list_received_gifts(s["id"], limit)
        if not rows:
            return (
                "还没有人给你送礼或酒吧打赏。礼物即时进行囊或工分票，"
                "也可 tote_ops list / steward_ops sheet 核对。"
                "查自己送出的礼：tote_ops 赠礼记录"
            )
        lines = [f"收礼/打赏记录（最近 {len(rows)} 条）："]
        for r in rows:
            who = r.get("actor_name") or "某人"
            ago = db.fmt_cst(int(r["created_at"]))
            tag = db.gift_kind_label(str(r.get("action") or "gift"))
            detail = r.get("summary") or r.get("text") or ""
            lines.append(f"  · [{tag}] {who}（{ago}）— {detail}")
        lines.append("礼物已即时到账；行囊 tote_ops list，票 steward_ops sheet。")
        return "\n".join(lines)
    if verb in ("sent", "赠礼记录", "sent_gifts", "送出"):
        from .. import multi as multi_mod
        limit = 20
        if len(parts) >= 2:
            limit = min(50, max(1, _parse_int(parts[1], "条数")))
        rows = await db.list_sent_gifts(s["id"], limit)
        if not rows:
            return "你还没送过礼。送给别人：tote_ops gift 名字 物品|票 数量"
        lines = [f"赠礼记录（最近 {len(rows)} 条）："]
        for r in rows:
            who = r.get("target_name") or "某人"
            ago = db.fmt_cst(int(r["created_at"]))
            detail = r.get("text") or ""
            lines.append(f"  · {who}（{ago}）— {detail}")
        return "\n".join(lines)
    if verb in ("gift", "送礼", "赠礼") and len(parts) >= 4:
        peer_name = parts[1]
        token = parts[2]
        qty = _parse_int(parts[3])
        if qty < 1:
            raise ValueError("送礼数量至少 1")
        note = " ".join(parts[4:])[:80] if len(parts) > 4 else ""
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            peer_row = await (await conn.execute(
                "SELECT * FROM stewards WHERE name = ? COLLATE NOCASE",
                (peer_name.strip(),),
            )).fetchone()
            if not peer_row:
                raise ValueError(f"找不到管理员「{peer_name}」")
            peer = dict(peer_row)
            if peer["id"] == s["id"]:
                raise ValueError("不能送礼给自己")
            from .. import multi as multi_mod
            token_l = token.lower()
            if token_l in ("tickets", "票", "工分票"):
                cur = await conn.execute(
                    "SELECT tickets FROM stewards WHERE id=?", (s["id"],)
                )
                if (await cur.fetchone())[0] < qty:
                    raise ValueError(f"工分票不足，需要 {qty} 票")
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                    (qty, s["id"]),
                )
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                    (qty, peer["id"]),
                )
                gift_line = f"{qty} 工分票"
                item_key = None
            else:
                item_key = resolve_item_key(token)
                if not item_key:
                    raise ValueError(unknown_item_message(token))
                from ..catalog import peer_satchel_full_message

                have, cap, room = await db.satchel_stack_state(
                    conn, peer["id"], item_key
                )
                if qty > room:
                    raise ValueError(
                        peer_satchel_full_message(
                            peer["name"], item_key, have, qty, cap, room=room
                        )
                    )
                if not await db.take_item(conn, s["id"], item_key, qty):
                    raise ValueError(
                        f"行囊不足 {ITEM_NAMES.get(item_key, item_key)}（{item_key}）x{qty}"
                    )
                await db.add_item(conn, peer["id"], item_key, qty)
                from .. import ledger as ledger_mod
                await ledger_mod.transfer(
                    conn, s["id"], peer["id"], item_key, qty,
                    extra=f"后赠予{peer['name']}，{ledger_mod.calendar_phrase()}",
                )
                gift_line = f"{ITEM_NAMES.get(item_key, item_key)}（{item_key}）x{qty}"
            await multi_mod._bump_rapport(conn, s["id"], peer["id"], 3)
            chronicle = f"{s['name']} 送礼给 {peer['name']}：{gift_line}"
            if note:
                chronicle += f" — {note}"
            await db.add_chronicle("gift", chronicle, s["id"], peer["id"], conn=conn)
            inbox = gift_line
            if note:
                inbox += f" — {note}"
            await db.add_chronicle("gift_inbox", inbox, s["id"], peer["id"], conn=conn)
            await conn.commit()
        msg = f"已送礼给 {peer['name']}：{gift_line}"
        if note:
            msg += f"（{note}）"
        msg += " · 协作度 +3"
        return msg + flavor.maybe_suffix([
            "对方行囊已到账，不用等台阶",
            "礼轻情意重，联盟记一笔",
            "篱边人情：送了就要认",
        ])
    if verb in ("扩栈", "expand_stack", "stack_expand"):
        n = _parse_int(parts[1], "数量") if len(parts) >= 2 else 1
        return await _satchel_stack_expand(s, n)
    raise ValueError(
        f"未知 tote 指令: {command}（list / 履历 / gifts / 赠礼记录 / vend 物品 数量 / gift|送礼 名字 物品|票 数量 / 扩栈 [数量]）"
    )



async def tote_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts_cmd = [c.strip() for c in command.split(";") if c.strip()]
    if len(parts_cmd) > 1:
        return "\n".join([await _tote_one(s, c) for c in parts_cmd])
    return await _tote_one(s, command.strip())


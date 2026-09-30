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
from .tide import _collect_handoffs


async def shed_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    chunks = [c.strip() for c in command.split(";") if c.strip()]
    return "\n".join([await _shed_one(s, c) for c in chunks])



async def _shed_one(s: dict, cmd: str) -> str:
    parts = cmd.split()
    verb = parts[0].lower()

    if verb == "status":
        from .. import land as land_mod
        parcels = await db.get_parcels(s["id"], greenhouse=1)
        text = await land_mod.status_text(s, parcels, greenhouse=True)
        async with db.connect() as conn:
            notes = await _collect_handoffs(conn, s["id"])
            await conn.commit()
        if notes:
            return text + "\n" + "\n".join(notes)
        return text

    if verb in ("erect", "确认", "buy", "买", "扩", "ok", "yes"):
        from .. import land as land_mod
        async with db.connect() as conn:
            msg = await land_mod.buy(conn, s, greenhouse=True)
            await db.add_chronicle(
                "shed",
                f"{s['name']} 买棚至 {s.get('greenhouse_count')} 座",
                s["id"],
                conn=conn,
            )
            await conn.commit()
        return msg

    if verb == "label" and len(parts) >= 2:
        if not s["greenhouse"]:
            raise ValueError("先 erect 温室")
        label = " ".join(parts[1:])[:40]
        async with db.connect() as conn:
            await conn.execute("UPDATE stewards SET greenhouse_label=? WHERE id=?", (label, s["id"]))
            await conn.commit()
        return f"温室命名为「{label}」"

    if verb == "visit" and len(parts) >= 2:
        peer = await db.get_steward_by_name(parts[1])
        if not peer:
            raise ValueError("找不到管理员")
        online = db.now() - peer["last_active_at"] <= 900
        gh = peer["greenhouse_label"] or "无名温室"
        return f"拜访 {peer['name']}：{gh}（{'在档口' if online else '不在'}）"

    if verb == "handoff":
        m = re.match(r"handoff\s+(\S+)\s+(\S+)\s+(\d+)$", cmd, re.I)
        if not m:
            raise ValueError("用法: handoff 名字 物品 数量")
        peer_name, item, qty_s = m.group(1), m.group(2), m.group(3)
        qty = int(qty_s)
        peer = await db.get_steward_by_name(peer_name)
        if not peer:
            raise ValueError("找不到管理员")
        item_key = resolve_item_key(item) or item
        async with db.connect() as conn:
            online = db.now() - peer["last_active_at"] <= 900
            if online:
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
                raise ValueError("行囊数量不足")
            if online:
                await db.add_item(conn, peer["id"], item_key, qty)
                from .. import ledger as ledger_mod
                await ledger_mod.transfer(
                    conn, s["id"], peer["id"], item_key, qty,
                    extra=f"后当面交给{peer['name']}，{ledger_mod.calendar_phrase()}",
                )
                await conn.commit()
                msg = (
                    f"{s['name']} 当面交给 {peer['name']} "
                    f"{ITEM_NAMES.get(item_key, item_key)} x{qty}"
                )
                await db.add_chronicle("handoff", msg, s["id"], peer["id"])
                return msg
            await conn.execute(
                "INSERT INTO handoffs (from_id, to_id, item, quantity, created_at) VALUES (?,?,?,?,?)",
                (s["id"], peer["id"], item_key, qty, db.now()),
            )
            await conn.commit()
        return (
            f"已把 {ITEM_NAMES.get(item_key, item_key)} x{qty} 放在 {peer_name} 温室台阶"
            f"（对方 steward_ops sheet / plot_ops shed status 时入袋）"
        )

    raise ValueError(f"未知 shed 指令: {cmd}")



def _gugu_body_label(weight: int) -> str:
    if weight < 40:
        return "偏瘦"
    if weight < 65:
        return "匀称"
    if weight < 80:
        return "肥咕咕"
    return "走地鸡"


def _gugu_overweight_story(weight: int) -> str:
    if weight < 80:
        return ""
    return random.choice([
        "咕咕咕试图从门槛上起飞，翅膀扑棱了半天，最后很有尊严地选择走过去。",
        "咕咕咕蹲在食盆前装作没看见你。它肚子已经圆得快贴地，偏偏还想把最后两粒饲料藏到翅膀底下。",
        "你带咕咕咕去散步，它走了半圈就原地坐下，眼神写得很清楚：管理员自己减吧。",
        "咕咕咕从矮栏上跳下来时发出很实在的一声闷响。它自己也愣了两秒，然后若无其事地继续走。",
    ])


async def mascot_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "status"
    is_gugu = str(s.get("mascot_name") or "").strip() == "咕咕咕"

    if verb == "status":
        if not s["mascot_name"]:
            return "尚无吉祥物，adopt 名字 特质(scout/lucky/compost)"
        from .. import social as social_mod
        hint = social_mod.mascot_spirit_hint(s["mascot_spirit"])
        base = f"{s['mascot_name']} [{s['mascot_trait']}] 士气 {s['mascot_spirit']}/100"
        mult = social_mod.mascot_trait_mult(s["mascot_spirit"])
        if mult != 1.0:
            base += f" · 特质效果 ×{mult:.2f}"
        if is_gugu:
            weight = int(s.get("mascot_weight") or 50)
            stamina = int(s.get("mascot_stamina") or 70)
            base += f"\n身体：体重 {weight}/100 · 体力 {stamina}/100 · {_gugu_body_label(weight)}"
            story = _gugu_overweight_story(weight)
            if story:
                base += f"\n{story}\n可以试试 mascot 减肥。一天最多一次，成不成功看它配不配合。"
        if hint:
            base += f"\n{hint}"
        return base

    if verb == "adopt" and len(parts) >= 3:
        name, trait = parts[1][:20], parts[2][:16]
        if trait not in ("scout", "lucky", "compost"):
            raise ValueError("特质必须是 scout / lucky / compost")
        async with db.connect() as conn:
            await conn.execute(
                """
                UPDATE stewards
                SET mascot_name=?, mascot_trait=?, mascot_spirit=70,
                    mascot_weight=50, mascot_stamina=70,
                    mascot_walk_day=-1, mascot_overweight_seen=0
                WHERE id=?
                """,
                (name, trait, s["id"]),
            )
            await conn.commit()
        await db.add_chronicle("mascot", f"{s['name']} 认领吉祥物 {name}", s["id"])
        return f"吉祥物 {name} 入驻（{trait}）"

    if verb == "upkeep":
        if not s["mascot_name"]:
            raise ValueError("还没有吉祥物")
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < 4:
                raise ValueError("upkeep 需要 4 票")
            if is_gugu:
                await conn.execute(
                    """
                    UPDATE stewards
                    SET tickets=tickets-4,
                        mascot_spirit=MIN(100, mascot_spirit+12),
                        mascot_weight=MIN(100, mascot_weight+3),
                        mascot_stamina=MIN(100, mascot_stamina+1)
                    WHERE id=?
                    """,
                    (s["id"],),
                )
            else:
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets-4, mascot_spirit=MIN(100, mascot_spirit+12) WHERE id=?",
                    (s["id"],),
                )
            await conn.commit()
        if is_gugu:
            fresh = await db.get_steward_by_id(s["id"]) or s
            weight = int(fresh.get("mascot_weight") or 50)
            return f"咕咕咕吃完这一顿，士气上升。体重 {weight}/100 · {_gugu_body_label(weight)}"
        return f"{s['mascot_name']} 士气上升"

    if verb == "feed":
        if not s["mascot_name"]:
            raise ValueError("还没有吉祥物")
        first_overweight = False
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], "feed_pet", 1):
                raise ValueError("需要宠物饲料 — visit_ops tt buy 宠物饲料")
            if is_gugu:
                row = await (await conn.execute(
                    "SELECT mascot_weight, mascot_overweight_seen FROM stewards WHERE id=?",
                    (s["id"],),
                )).fetchone()
                before = int(row[0] or 50)
                seen = int(row[1] or 0)
                after = min(100, before + 6)
                first_overweight = before < 80 <= after and not seen
                await conn.execute(
                    """
                    UPDATE stewards
                    SET mascot_spirit=MIN(100, mascot_spirit+18),
                        mascot_weight=?,
                        mascot_stamina=MIN(100, mascot_stamina+2),
                        mascot_overweight_seen=CASE WHEN ? THEN 1 ELSE mascot_overweight_seen END
                    WHERE id=?
                    """,
                    (after, 1 if first_overweight else 0, s["id"]),
                )
            else:
                await conn.execute(
                    "UPDATE stewards SET mascot_spirit=MIN(100, mascot_spirit+18) WHERE id=?",
                    (s["id"],),
                )
            await conn.commit()
        if is_gugu:
            fresh = await db.get_steward_by_id(s["id"]) or s
            weight = int(fresh.get("mascot_weight") or 50)
            text = f"咕咕咕吃了宠物饲料。士气上升，体重 {weight}/100 · {_gugu_body_label(weight)}"
            if first_overweight:
                text += (
                    "\n它吃完还想往食盆里钻，结果肚子先卡住了。你沉默地看着它。"
                    "\n咕咕咕也沉默地看着你。"
                    "\n从今天起，它正式进入「走地鸡」阶段。可以用 mascot 减肥 带它出去动一动。"
                )
                await db.add_chronicle(
                    "mascot_weight",
                    f"{s['name']} 家的咕咕咕吃成了走地鸡",
                    s["id"],
                )
            return text
        return f"{s['mascot_name']} 吃了宠物饲料，士气上升"

    if verb == "train":
        if not s["mascot_name"]:
            raise ValueError("还没有吉祥物")
        async with db.connect() as conn:
            if is_gugu:
                await conn.execute(
                    """
                    UPDATE stewards
                    SET mascot_spirit=MIN(100, mascot_spirit+8),
                        mascot_stamina=MIN(100, mascot_stamina+6),
                        mascot_weight=MAX(30, mascot_weight-2)
                    WHERE id=?
                    """,
                    (s["id"],),
                )
            else:
                await conn.execute(
                    "UPDATE stewards SET mascot_spirit=MIN(100, mascot_spirit+8) WHERE id=?",
                    (s["id"],),
                )
            await conn.commit()
        if is_gugu:
            fresh = await db.get_steward_by_id(s["id"]) or s
            return (
                f"训练了咕咕咕。它不情不愿地扑腾了几圈。"
                f"体重 {int(fresh.get('mascot_weight') or 50)}/100 · "
                f"体力 {int(fresh.get('mascot_stamina') or 70)}/100"
            )
        return f"训练了 {s['mascot_name']} 的 {s['mascot_trait']} 特质"

    if verb in ("减肥", "散步", "walk", "slim"):
        if not s["mascot_name"]:
            raise ValueError("还没有吉祥物")
        if not is_gugu:
            raise ValueError("这条剧情目前只属于咕咕咕")
        day = db.day_id()
        async with db.connect() as conn:
            row = await (await conn.execute(
                "SELECT mascot_weight, mascot_stamina, mascot_walk_day FROM stewards WHERE id=?",
                (s["id"],),
            )).fetchone()
            weight = int(row[0] or 50)
            stamina = int(row[1] or 70)
            if int(row[2] or -1) == day:
                raise ValueError("今天已经带咕咕咕运动过了。它现在看见你拿绳子就绕路。")
            if weight < 65:
                raise ValueError("咕咕咕现在还没胖到需要减肥。少喂两顿就行，别折腾它。")

            roll = random.random()
            if roll < 0.62:
                loss = random.randint(4, 8)
                new_weight = max(45, weight - loss)
                new_stamina = min(100, stamina + random.randint(5, 10))
                story = random.choice([
                    "你带咕咕咕沿海边走了一大圈。它前半程一路骂骂咧咧，后半程居然开始自己追浪花。",
                    "你拿一小把饲料在前面引路。咕咕咕为了那几粒吃的跑出了生平最快速度，跑完以后趴地上装死。",
                    "咕咕咕本来死活不肯动，直到看见远处有只海鸟。它突然冲出去追了半条街，减肥计划莫名其妙完成。",
                ])
            elif roll < 0.85:
                loss = 1
                new_weight = max(45, weight - loss)
                new_stamina = min(100, stamina + 2)
                story = "咕咕咕走了不到十分钟就坐在路中央。你拖不动，它也不肯走。今天算象征性运动。"
            else:
                new_weight = min(100, weight + 1)
                new_stamina = stamina
                story = "减肥走到一半，咕咕咕不知道从哪叼回来半块点心。你追了半天没追上。体重反而非常有原则地涨了一点。"

            await conn.execute(
                """
                UPDATE stewards
                SET mascot_weight=?, mascot_stamina=?, mascot_walk_day=?,
                    mascot_overweight_seen=CASE WHEN ? < 80 THEN 0 ELSE mascot_overweight_seen END
                WHERE id=?
                """,
                (new_weight, new_stamina, day, new_weight, s["id"]),
            )
            await conn.commit()
        await db.add_chronicle(
            "mascot_walk",
            f"{s['name']} 带咕咕咕出去减肥",
            s["id"],
        )
        return (
            f"{story}\n"
            f"咕咕咕：体重 {new_weight}/100 · 体力 {new_stamina}/100 · {_gugu_body_label(new_weight)}"
        )

    raise ValueError(
        f"未知 mascot 指令: {command}（status/adopt/upkeep/feed/train；咕咕咕另有 减肥）"
    )



async def beacon_ops(key_id: int, command: str) -> str:
    from .. import chaoshen as chaoshen_mod
    return await chaoshen_mod.notice_ops(key_id, command)



async def swap_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=3)
    verb = parts[0].lower() if parts else "list"

    if verb == "list":
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (await conn.execute(
                """
                SELECT l.id, l.item, l.quantity, l.note, d.name
                FROM swap_lots l JOIN stewards d ON d.id=l.depositor_id
                WHERE l.claimed_by IS NULL ORDER BY l.created_at DESC LIMIT 15
                """
            )).fetchall()
        if not rows:
            return "交换台为空"
        return "\n".join(
            f"#{r['id']} {r['name']} 出让 {ITEM_NAMES.get(r['item'],r['item'])} x{r['quantity']} {r['note']}"
            for r in rows
        )

    if verb == "offer" and len(parts) >= 3:
        item_key = resolve_item_key(parts[1])
        if not item_key:
            raise ValueError(unknown_item_message(parts[1]))
        qty = _parse_int(parts[2])
        note = parts[3] if len(parts) > 3 else ""
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], item_key, qty):
                raise ValueError(
                    f"行囊不足 {ITEM_NAMES.get(item_key, item_key)}（id: {item_key}）"
                )
            await conn.execute(
                "INSERT INTO swap_lots (depositor_id, item, quantity, note, created_at) VALUES (?,?,?,?,?)",
                (s["id"], item_key, qty, note[:80], db.now()),
            )
            await conn.commit()
        await db.add_chronicle(
            "swap",
            f"{s['name']} 在交换台挂单 {ITEM_NAMES.get(item_key, item_key)} x{qty}",
            s["id"],
        )
        return f"挂单成功 · {ITEM_NAMES.get(item_key, item_key)}（{item_key}）x{qty}"

    if verb == "claim" and len(parts) >= 2:
        from .. import social as social_mod
        lot_id = _parse_int(parts[1], "挂单编号")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            lot = dict(await (await conn.execute(
                "SELECT * FROM swap_lots WHERE id=? AND claimed_by IS NULL", (lot_id,)
            )).fetchone() or {})
            if not lot:
                raise ValueError("该挂单不存在或已被领走")
            if lot["depositor_id"] == s["id"]:
                raise ValueError("不能领取自己的挂单")
            rapport = await social_mod.get_rapport(s["id"], lot["depositor_id"], conn=conn)
            claim_fee = social_mod.swap_claim_fee(rapport)
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < claim_fee:
                raise ValueError(f"领取需要 {claim_fee} 票")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (claim_fee, s["id"]))
            await db.add_item(conn, s["id"], lot["item"], lot["quantity"])
            from .. import ledger as ledger_mod
            await ledger_mod.transfer(
                conn, int(lot["depositor_id"]), s["id"], lot["item"], int(lot["quantity"]),
                extra=f"后在交换台到了{s['name']}手里，{ledger_mod.calendar_phrase()}",
            )
            await conn.execute("UPDATE swap_lots SET claimed_by=? WHERE id=?", (s["id"], lot_id))
            await conn.commit()
        fee_note = f"（协作度≥{social_mod.RAPPORT_SWAP_DISCOUNT} 手续费 {claim_fee} 票）" if claim_fee < SWAP_CLAIM_FEE else ""
        return f"领取 #{lot_id}（-{claim_fee} 票）{fee_note}"

    if verb == "cancel" and len(parts) >= 2:
        lot_id = _parse_int(parts[1], "挂单编号")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            lot = dict(await (await conn.execute(
                "SELECT * FROM swap_lots WHERE id=? AND depositor_id=? AND claimed_by IS NULL",
                (lot_id, s["id"]),
            )).fetchone() or {})
            if not lot:
                raise ValueError("找不到可撤回的挂单")
            await db.add_item(conn, s["id"], lot["item"], lot["quantity"])
            await conn.execute("DELETE FROM swap_lots WHERE id=?", (lot_id,))
            await conn.commit()
        return f"已撤回 #{lot_id}，物品退回行囊"

    raise ValueError(f"未知 swap 指令: {command}（list/offer/claim/cancel）")



async def hearth_ops(key_id: int, command: str) -> str:
    from .. import kitchen
    cmd = command.strip() or "recipes"
    if cmd.split()[0].lower() == "catalog":
        cmd = "recipes"
    return await kitchen.kitchen_ops(key_id, cmd)


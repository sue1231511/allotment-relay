"""实付批次账：系统商店卖给玩家的货，每一批记住「当时实付单价」，退货按这个价 × 0.9。

为什么要有：Tt酱的买入价随好感浮动（满心七五折）。如果退货只看「退货人此刻的买入价」，
高好感号买货、送给 0 心小号，小号按 0 心价退，两头合起来赚钱。实付价跟着货走，
退货价永远是「最初那一笔系统收款」的 0.9 倍，货怎么转手都赚不到。

账的规则：
  * 记账的货 = 价格簿里挂 Tt 渠道的买入类物品（种子、饲料、工具、渔具……）。
  * 买入时记一批 (件数, 实付单价)。Tt酱、杂货铺（plot_ops buy）、工具店（tool buy）都记。
  * 取走物品时 (db.take_item) 先按先进先出扣批次，再把「批次总量 > 背包数量」的多余批次削掉，
    所以批次总量任何时候都 ≤ 背包数量，不会留下幽灵批次。
  * 转手（送礼、当面交接、集市、交换台、公仓、悬赏）时批次随货走：
    take_item_carry 取走并带出批次，stash/unstash 在挂单里暂存，give 在收货人那边落账。
  * 没有批次的件（掉落、旧存档里没补到账的、转手时丢了批次的）退货价取保守价：
    pricing.ref_value = 全岛最低买入价 × 0.9，任何人买都不会比它低。
"""
from __future__ import annotations

import logging
import aiosqlite

from . import price_book, pricing

_log = logging.getLogger(__name__)

STEWARD = "steward"
FLAG_BACKFILL = "paid_batch_backfill_v1"

Slices = list[tuple[int, int]]   # [(件数, 实付单价), ...]

_TRACKED: frozenset[str] | None = None


def tracked_items() -> frozenset[str]:
    """记账的货：价格簿里买入类、且挂了 Tt 渠道的物品。"""
    global _TRACKED
    if _TRACKED is None:
        _TRACKED = frozenset(
            item for item, entry in price_book.BOOK.items()
            if entry.get("cls") == "buy" and "tt" in (entry.get("ch") or ())
        )
    return _TRACKED


def is_tracked(item: str) -> bool:
    return item in tracked_items()


def _clean_slices(slices: Slices | None) -> Slices:
    out: Slices = []
    for q, p in slices or []:
        q, p = int(q), int(p)
        if q > 0 and p > 0:
            out.append((q, p))
    return out


async def _pop_fifo(
    conn: aiosqlite.Connection, kind: str, owner: int, item: str, qty: int,
) -> Slices:
    """按先进先出取走至多 qty 件批次，返回取走的切片；批次不够就返回少的（余下是无批次件）。"""
    if qty <= 0:
        return []
    cur = await conn.execute(
        "SELECT id, qty, paid_unit FROM paid_batches "
        "WHERE owner_kind=? AND owner_id=? AND item=? ORDER BY id ASC",
        (kind, owner, item),
    )
    rows = await cur.fetchall()
    left = qty
    out: Slices = []
    for bid, have, paid in rows:
        if left <= 0:
            break
        have = int(have)
        take = min(have, left)
        left -= take
        out.append((take, int(paid)))
        if take >= have:
            await conn.execute("DELETE FROM paid_batches WHERE id=?", (bid,))
        else:
            await conn.execute(
                "UPDATE paid_batches SET qty=qty-? WHERE id=?", (take, bid),
            )
    return out


async def _insert(
    conn: aiosqlite.Connection, kind: str, owner: int, item: str, slices: Slices,
) -> None:
    for q, p in slices:
        await conn.execute(
            "INSERT INTO paid_batches (owner_kind, owner_id, item, qty, paid_unit) VALUES (?,?,?,?,?)",
            (kind, owner, item, q, p),
        )


async def batch_total(
    conn: aiosqlite.Connection, steward_id: int, item: str, *, kind: str = STEWARD,
) -> int:
    cur = await conn.execute(
        "SELECT COALESCE(SUM(qty),0) FROM paid_batches WHERE owner_kind=? AND owner_id=? AND item=?",
        (kind, steward_id, item),
    )
    return int((await cur.fetchone())[0] or 0)


async def _satchel_qty(conn: aiosqlite.Connection, steward_id: int, item: str) -> int:
    cur = await conn.execute(
        "SELECT quantity FROM satchel WHERE steward_id=? AND item=?", (steward_id, item),
    )
    row = await cur.fetchone()
    return int(row[0]) if row else 0


async def trim_to_satchel(conn: aiosqlite.Connection, steward_id: int, item: str) -> int:
    """批次总量 > 背包数量时，削掉最老的多余批次。返回削掉的件数。"""
    if not is_tracked(item):
        return 0
    try:
        total = await batch_total(conn, steward_id, item)
        if total <= 0:
            return 0
        have = await _satchel_qty(conn, steward_id, item)
        extra = total - have
        if extra <= 0:
            return 0
        _log.info(
            "paid_ledger.trim: 批次 %d 件 > 背包 %d 件，削掉最老 %d 件 steward=%s item=%s",
            total, have, extra, steward_id, item,
        )
        cut = await _pop_fifo(conn, STEWARD, steward_id, item, extra)
        return sum(q for q, _ in cut)
    except Exception:
        _log.exception("paid_ledger.trim_to_satchel 失败 steward=%s item=%s", steward_id, item)
        raise


async def consume(
    conn: aiosqlite.Connection, steward_id: int, item: str, qty: int,
) -> Slices:
    """db.take_item 扣完背包后调用：先扣 qty 件批次（先进先出），再削多余。返回扣掉的切片。"""
    if not is_tracked(item) or qty <= 0:
        return []
    try:
        slices = await _pop_fifo(conn, STEWARD, steward_id, item, qty)
        await trim_to_satchel(conn, steward_id, item)
        return slices
    except Exception:
        _log.exception("paid_ledger.consume 失败 steward=%s item=%s qty=%s", steward_id, item, qty)
        raise


async def record_purchase(
    conn: aiosqlite.Connection, steward_id: int, item: str, qty: int, paid_unit: int,
) -> None:
    """系统商店卖出时记一批。调用方已经 db.add_item 过。"""
    if not is_tracked(item) or qty <= 0 or paid_unit <= 0:
        return
    try:
        await _insert(conn, STEWARD, steward_id, item, [(int(qty), int(paid_unit))])
        await trim_to_satchel(conn, steward_id, item)
    except Exception:
        _log.exception(
            "paid_ledger.record_purchase 失败 steward=%s item=%s qty=%s paid=%s",
            steward_id, item, qty, paid_unit,
        )
        raise


async def give(
    conn: aiosqlite.Connection, steward_id: int, item: str, slices: Slices | None,
) -> None:
    """收货人落账。调用方已经 db.add_item 过；批次总量不会超过背包数量。"""
    clean = _clean_slices(slices)
    if not clean or not is_tracked(item):
        return
    try:
        await _insert(conn, STEWARD, steward_id, item, clean)
        await trim_to_satchel(conn, steward_id, item)
    except Exception:
        _log.exception("paid_ledger.give 失败 steward=%s item=%s slices=%s", steward_id, item, clean)
        raise


async def stash(
    conn: aiosqlite.Connection, kind: str, ref: int, item: str, slices: Slices | None,
) -> None:
    """挂单暂存：集市/交换台/当面交接/公仓。ref 是挂单编号（公仓用 0）。"""
    clean = _clean_slices(slices)
    if not clean or not is_tracked(item):
        return
    try:
        await _insert(conn, kind, ref, item, clean)
    except Exception:
        _log.exception("paid_ledger.stash 失败 kind=%s ref=%s item=%s", kind, ref, item)
        raise


async def unstash(
    conn: aiosqlite.Connection, kind: str, ref: int, item: str, qty: int,
) -> Slices:
    """从挂单里取出 qty 件的批次（先进先出）。"""
    if not is_tracked(item) or qty <= 0:
        return []
    try:
        return await _pop_fifo(conn, kind, ref, item, qty)
    except Exception:
        _log.exception("paid_ledger.unstash 失败 kind=%s ref=%s item=%s qty=%s", kind, ref, item, qty)
        raise


async def discard(
    conn: aiosqlite.Connection, kind: str, ref: int, item: str | None = None,
) -> None:
    """挂单作废（被风刮没了等）：批次一起清掉。"""
    try:
        if item is None:
            await conn.execute(
                "DELETE FROM paid_batches WHERE owner_kind=? AND owner_id=?", (kind, ref),
            )
        else:
            await conn.execute(
                "DELETE FROM paid_batches WHERE owner_kind=? AND owner_id=? AND item=?",
                (kind, ref, item),
            )
    except Exception:
        _log.exception("paid_ledger.discard 失败 kind=%s ref=%s item=%s", kind, ref, item)
        raise


async def refund_plan(
    conn: aiosqlite.Connection, steward_id: int, item: str, qty: int,
) -> Slices:
    """vend 用：这次卖 qty 件，每一段的实付单价。实付单价 0 = 无批次件（走保守价）。只读。"""
    if qty <= 0:
        return []
    if not is_tracked(item):
        return [(int(qty), 0)]
    cur = await conn.execute(
        "SELECT qty, paid_unit FROM paid_batches "
        "WHERE owner_kind=? AND owner_id=? AND item=? ORDER BY id ASC",
        (STEWARD, steward_id, item),
    )
    rows = await cur.fetchall()
    left = int(qty)
    out: Slices = []
    for have, paid in rows:
        if left <= 0:
            break
        take = min(int(have), left)
        left -= take
        out.append((take, int(paid)))
    if left > 0:
        out.append((left, 0))
    return out


async def backfill_legacy(conn: aiosqlite.Connection) -> int:
    """一次性补账（init_db 里跑）。

    上线前买的货没有批次。给每个玩家背包里「没有批次的记账货」补一批，实付单价取
    **持有人此刻在 Tt 的买入价**——也就是改版前退货会给他的那个价，所以对老实人退货金额不变。
    这一步只加批次行，不动任何人的物品和票。挂在集市/交换台/公仓/交接里的旧货不补，
    取回或被领走后按无批次件算（保守价）。补数据和「已补」标记在同一个保存点里（db.run_flagged_migration）。
    """
    from . import db

    return await db.run_flagged_migration(conn, FLAG_BACKFILL, "实付批次补账", _backfill_work)


async def _backfill_work(conn: aiosqlite.Connection, stats: dict[str, int]) -> int:
    from . import tt as tt_mod

    added = 0
    rows = await (await conn.execute(
        "SELECT steward_id, item, quantity FROM satchel WHERE quantity>0"
    )).fetchall()
    hearts_cache: dict[int, int] = {}
    for sid, item, qty in rows:
        if not is_tracked(item):
            continue
        missing = int(qty) - await batch_total(conn, int(sid), item)
        if missing <= 0:
            continue
        if int(sid) not in hearts_cache:
            score = await tt_mod._affinity(conn, int(sid))  # noqa: SLF001
            hearts_cache[int(sid)] = tt_mod.hearts(score)
        paid = pricing.tt_buy_price(pricing.base_price(item), hearts_cache[int(sid)])
        if paid <= 0:
            continue
        await _insert(conn, STEWARD, int(sid), item, [(missing, paid)])
        added += missing
        stats["processed"] += 1
    return added


def _now() -> int:
    import time

    return int(time.time())


def unit_refund(item: str, paid_unit: int) -> int:
    """一件货的退货价：有实付价 = floor(实付 × 0.9)，再受固定回收价/加工封顶约束；无批次 = 保守价。"""
    return pricing.refund_from_paid(item, paid_unit)

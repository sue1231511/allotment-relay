"""回收（vend）计价：tote_ops vend / kitchen_ops vend 共用。

价格规则见 pricing.py 顶部说明。这里负责「读库」的部分：
好感（Tt 退货价）、品质批次、渔市流量。

保证：一次卖 N 件的总价 == 逐件卖 N 次的总价（路径无关）。
  - 每一段按自己那一批的品质/重量/冰箱系数计价；
  - 渔市行情逐件滑动：每卖一件，下一件就按「已多卖一件」的流量算。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import aiosqlite

from . import paid_ledger, pricing

_log = logging.getLogger(__name__)

TOKEN_REFUSE = (
    "手作信物（订婚戒、潮誓戒、潮信贝、潮誓砂）不能卖给商店回收。"
    "可以送给别人（tote_ops gift）、交换台交换，或挂集市。"
)


@dataclass
class VendPlan:
    item: str
    qty: int
    total: int
    sea_note: str = ""
    flow_units: int = 0     # 要记进渔市流量的件数
    first_unit: int = 0     # 第一件的单价（给提示用）


async def tt_hearts(conn: aiosqlite.Connection, steward_id: int) -> int:
    """玩家在 Tt酱那儿的心数；没记录算 0。"""
    from . import tt as tt_mod

    try:
        score = await tt_mod._affinity(conn, steward_id)  # noqa: SLF001
    except Exception:
        _log.exception("tt_hearts 读好感失败 steward=%s", steward_id)
        raise
    return tt_mod.hearts(score)


def _flat_price(item: str) -> int:
    """熟菜 / 混搭菜 / 其他不吃修正的货：价格只取决于物品本身。"""
    from .catalog import suggested_price

    return int(suggested_price(item) or 0)


async def unit_preview(conn: aiosqlite.Connection, steward_id: int, item: str) -> int:
    """列表展示用：这件货此刻一件大约回收多少（不含品质批次与行情）。0 = 不可回收。"""
    if pricing.is_token(item):
        return 0
    entry = pricing.book_entry(item)
    if entry is None or entry.get("notote"):
        return _flat_price(item)
    if entry.get("cls") == "buy":
        slices = await paid_ledger.refund_plan(conn, steward_id, item, 1)
        return pricing.refund_from_paid(item, slices[0][1]) if slices else pricing.ref_value(item)
    return pricing.ref_value(item)


async def plan(conn: aiosqlite.Connection, steward_id: int, item: str, qty: int) -> VendPlan:
    """算这次卖 qty 件的总价。只读（会顺手对账品质批次），不扣物品、不加票。"""
    if qty < 1:
        raise ValueError(f"数量必须 ≥1，收到 {qty}")
    if pricing.is_token(item):
        raise ValueError(TOKEN_REFUSE)
    entry = pricing.book_entry(item)

    # 熟菜 / 混搭菜 / 没进簿的动态物品：一口价
    if entry is None or entry.get("notote"):
        unit = _flat_price(item)
        if unit <= 0:
            raise ValueError("这件东西卖不出价")
        return VendPlan(item, qty, unit * qty, first_unit=unit)

    # 可买品：每一批按它当初的实付单价 × 0.9 退；没有实付记录的件走保守价
    if entry.get("cls") == "buy":
        total = 0
        first = 0
        for count, paid in await paid_ledger.refund_plan(conn, steward_id, item, qty):
            unit = pricing.refund_from_paid(item, paid)
            if unit <= 0:
                raise ValueError("这件东西卖不出价")
            total += unit * count
            first = first or unit
        return VendPlan(item, qty, total, first_unit=first)

    # 产出品：逐批、逐件
    from . import fish_market
    from . import item_traits as traits_mod

    ref = pricing.ref_value(item)
    if ref <= 0:
        raise ValueError("这件东西卖不出价")
    segments = await traits_mod.vend_segments(conn, steward_id, item, qty)
    market_fish = fish_market.is_market_fish(item)
    flow = await fish_market.window_flow(conn, item) if market_fish else 0
    total = 0
    first = 0
    sold = 0
    for count, mod, spoiled in segments:
        if spoiled:
            unit = max(1, ref // 5)
            total += unit * count
            first = first or unit
            sold += count
            flow += count if market_fish else 0
            continue
        if not market_fish:
            unit = pricing.made_unit_price(item, mod)
            total += unit * count
            first = first or unit
            sold += count
            continue
        remaining = count
        while remaining > 0:
            sea = fish_market.sea_mult_at(ref, flow)
            unit = pricing.made_unit_price(item, mod * sea)
            first = first or unit
            if sea <= fish_market.MULT_FLOOR:
                # 行情已跌停，后面每件都一个价
                total += unit * remaining
                flow += remaining
                sold += remaining
                remaining = 0
                break
            total += unit
            flow += 1
            sold += 1
            remaining -= 1
    note = ""
    if market_fish:
        final_flow = (await fish_market.window_flow(conn, item)) + sold
        note = fish_market.mult_note(fish_market.sea_mult_at(ref, final_flow))
    return VendPlan(
        item, qty, int(total), sea_note=note,
        flow_units=sold if market_fish else 0, first_unit=first,
    )

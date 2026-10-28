"""统一定价：价格簿 + 全游戏共用的定价规则。

规则一句话版（细则见 docs/pricing.md）：

* 每个物品在价格簿 `price_book.BOOK` 里只有一个基础价 B。
* 买入（系统卖给玩家）：`ceil(B × 渠道系数 × 折扣)`，折扣总下限 0.75。
* 回收（系统从玩家手里收）：
    - 产出品（作物、鱼、蛋、矿……）：`floor(0.70 × B × 修正)`，修正夹在 [0.50, 1.50]。
      B 取 `ceil(现行回收价 / 0.70)`，所以修正为 1 时回收价与改版前完全一致。
    - 可买品：**回收价 = 每批当初的实付单价 × 0.9**（实付价跟着货走，见 paid_ledger）；
      没有付款记录的件取保守价 ref_value（全岛最低买入价 × 0.9）。
    - 手作信物（订婚戒、潮誓戒等）：不进价格簿，不可卖给任何商店回收；
      玩家之间可以送礼、交换、挂集市。
* 加工（做饭、手工……）：成品回收价 ≤ 2.0 × 材料回收价合计。
* 玩家之间的渠道（集市、小馆、打赏、送礼、合约、交换台）不碰价格，只守恒。

本模块不碰数据库；需要读库的部分（好感、品质批次、渔市流量）由调用方传值进来，
或放在 item_traits / fish_market 里调用本模块的纯函数。
"""
from __future__ import annotations

import logging
from typing import Any

from . import price_book

_log = logging.getLogger(__name__)

# ── 参数（全部在这里，改一处全局生效）──────────────────────────────
R_SELL_PCT = 70          # 产出品回收基础系数 0.70（百分数，整数运算避免浮点误差）
REFUND_PCT = 90          # 可买品回收 = 当前买入价 × 0.90
BUY_FLOOR_PERMILLE = 750  # 买入折扣总下限 0.75
MOD_LO = 0.50            # 产出品回收修正下限
MOD_HI = 1.50            # 产出品回收修正上限
P_MAX = 2.0              # 加工：成品回收价 ≤ P_MAX × 材料回收价合计
MARKET_PRICE_MAX_MULT = 100   # 集市单价上限 = 100 × B（有 B 才限）

# Tt 好感折扣：每两心 −5%，共 5 档 → 满 10 心 ×0.75（千分数）
HEARTS_MAX = 10
_HEARTS_PERMILLE = {0: 1000, 2: 950, 4: 900, 6: 850, 8: 800, 10: 750}

# 手作信物：不进价格簿，不可回收，玩家之间照常送礼/交换/挂集市
TOKEN_ITEMS = frozenset({
    "betroth_ring",    # 订婚戒
    "tide_vow_ring",   # 潮誓戒
    "betroth_shell",   # 潮信贝（订婚信物材料）
    "tide_vow_sand",   # 潮誓砂（成婚信物材料）
})

# 潮下销赃（后室铺）
#   店货（后室铺货架/强卖买来的 ut_ 货）：出货价必须低于最低买入价，不赚钱。
#   赃物（强买抢来的 utl_ 货）：任何商店都买不到，另开高价通道，保持原有玩法。
FENCE_SHOP_LO = 0.60
FENCE_SHOP_HI = 0.85
FENCE_SHOP_TIDE_LO = 0.85
FENCE_SHOP_TIDE_HI = 1.15
FENCE_SHOP_LUCKY = 1.15
FENCE_SHOP_LUCKY_CHANCE = 0.05
FENCE_SUB_MULT = 0.45
FENCE_LOOT_LO = 1.5
FENCE_LOOT_HI = 1.9
FENCE_LOOT_LUCKY = 2.0
LOOT_PREFIX = "utl_"
# 这两样是「井底材料」：坑里捡、铺子也卖，是炼制配方的原料，保持 ut_ 键，按店货算
LOOT_EXCLUDE = frozenset({"pit_silt", "brine_crystal"})

# 酒吧打赏加成：协作度够了，对方实收多 15%，但由当日营业额池出，并有每对号日上限
TIP_BONUS_PCT = 15
TIP_PAIR_DAILY_COUNT = 10
TIP_PAIR_DAILY_AMOUNT = 1000


# 加工封顶表：{产出物品: 单件回收价上限}。由 catalog 导入末尾按配方算好登记。
_CAPS: dict[str, int] = {}


def register_cap(item: str, cap: int) -> None:
    _CAPS[item] = int(cap)


def cap_for(item: str) -> int | None:
    return _CAPS.get(item)


# ── 价格簿读取 ─────────────────────────────────────────────────────
def book_entry(item: str) -> dict[str, Any] | None:
    return price_book.BOOK.get(item)


def is_token(item: str) -> bool:
    return item in TOKEN_ITEMS


def base_price(item: str) -> int:
    """基础价 B；不在簿里（含信物）返回 0。"""
    entry = price_book.BOOK.get(item)
    return int(entry["B"]) if entry else 0


def has_buy_channel(item: str) -> bool:
    entry = price_book.BOOK.get(item)
    return bool(entry and entry.get("cls") == "buy")


# ── 买入 ──────────────────────────────────────────────────────────
def hearts_permille(hearts: int) -> int:
    h = max(0, min(HEARTS_MAX, int(hearts)))
    return _HEARTS_PERMILLE[h - (h % 2)]


def tt_buy_price(list_price: int, hearts: int, *, flat: bool = False) -> int:
    """Tt酱买入价：ceil(标价 × 折扣)。flat=True 是嫁妆柜，不打折。纯整数运算。"""
    if list_price <= 0:
        return 0
    if flat:
        return int(list_price)
    permille = max(hearts_permille(hearts), BUY_FLOOR_PERMILLE)
    return max(1, -(-int(list_price) * permille // 1000))


def min_buy_price(item: str) -> int:
    """所有玩家、所有渠道里这件货的理论最低买入价（0 = 买不到）。"""
    entry = price_book.BOOK.get(item)
    if not entry or entry.get("cls") != "buy":
        return 0
    channels = entry.get("ch") or ()
    b = int(entry["B"])
    best: list[int] = []
    if "tt" in channels:
        best.append(tt_buy_price(b, HEARTS_MAX))
    if "tt_flat" in channels:
        best.append(b)
    if "florist" in channels:
        best.append(max(1, b - FLORIST_MAX_DISCOUNT))
    for tag in ("plot", "tool_ops", "hut", "barn"):
        if tag in channels:
            best.append(b)
    if "clinic" in channels:
        best.append(max(1, round(b * CLINIC_MIN_MULT)))
    if "ut_shelf" in channels:
        best.append(ut_shelf_min_price(b, entry.get("layer", "common")))
    return min(best) if best else 0


CLINIC_MIN_MULT = 0.9        # 诊所九折（clinic.CLINIC_DISCOUNT_MULT）
FLORIST_MAX_DISCOUNT = 8     # 四域等级最多减 8 票（lili_catalog.ticket_cost_for_steward）
UT_LAYER_MULT = {"common": 1.4, "linked": 1.6, "rare": 1.8}
UT_REP_MULT_MIN = 0.90       # 影信最高档的价格系数


def ut_shelf_min_price(base: int, layer: str) -> int:
    return max(1, int(base * UT_LAYER_MULT.get(layer, 1.5) * UT_REP_MULT_MIN))


# ── 回收：不依赖玩家的参考价（用于展示、集市建议价、估值）───────────
def ref_value(item: str) -> int:
    """玩家无关的回收参考价。信物、没进簿的返回 0（调用方当不可回收）。

    产出品 = floor(0.70B)；可买品 = 最低买入价 × 0.9（对任何玩家都不会比实际回收价高）。
    """
    if item in TOKEN_ITEMS:
        return 0
    entry = price_book.BOOK.get(item)
    if not entry:
        return 0
    fixed = entry.get("sell")
    if fixed is not None:
        value = int(fixed)
    else:
        b = int(entry["B"])
        if entry.get("cls") == "made":
            value = b * R_SELL_PCT // 100
        else:
            value = min_buy_price(item) * REFUND_PCT // 100
    cap = _CAPS.get(item)
    return min(value, cap) if cap is not None else value


def refund_for_player(item: str, hearts: int) -> int:
    """可买品的回收价：该玩家此刻在店里的买入价 × 0.9（向下取整）。

    只有挂在 Tt 上的货吃好感折扣；其他可买品按固定标价。有固定回收价的（花、茶包）取较小者。
    """
    entry = price_book.BOOK.get(item)
    if not entry or item in TOKEN_ITEMS:
        return 0
    if entry.get("cls") != "buy":
        return ref_value(item)
    channels = entry.get("ch") or ()
    b = int(entry["B"])
    if "tt" in channels:
        buy_now = tt_buy_price(b, hearts)
    elif "tt_flat" in channels:
        buy_now = b
    else:
        buy_now = min_buy_price(item)
    value = buy_now * REFUND_PCT // 100
    fixed = entry.get("sell")
    if fixed is not None:
        value = min(value, int(fixed))
    cap = _CAPS.get(item)
    if cap is not None:
        value = min(value, cap)
    return value


def refund_from_paid(item: str, paid_unit: int) -> int:
    """可买品一件的退货价。paid_unit>0：最初那笔系统收款（实付单价）× 0.9 向下取整；
    paid_unit=0：这件没有实付记录，取保守价 ref_value（全岛最低买入价 × 0.9）。
    固定回收价（花、茶包）和加工封顶照样约束。信物不退。"""
    if item in TOKEN_ITEMS:
        return 0
    entry = price_book.BOOK.get(item)
    if not entry:
        return 0
    if int(paid_unit) <= 0:
        return ref_value(item)
    value = int(paid_unit) * REFUND_PCT // 100
    fixed = entry.get("sell")
    if fixed is not None:
        value = min(value, int(fixed))
    cap = _CAPS.get(item)
    if cap is not None:
        value = min(value, cap)
    return value


# ── 加工封顶 ──────────────────────────────────────────────────────
def proc_cap(input_value_sum: int, out_qty: int = 1) -> int:
    """成品单件回收价上限 = P_MAX × 材料回收价合计 / 产出数量（向下取整）。"""
    return int(P_MAX * max(0, int(input_value_sum)) / max(1, int(out_qty)))


def mix_cap_from_tier(tier: int) -> int:
    """自由组合：混搭菜的 key 里只留了档位（材料身价 // 20），封顶按档位下界算。

    档位下界 = 20×档位；档位 0 的搭配材料至少两样、每样至少 6 票，下界取 12。
    """
    return int(P_MAX * max(20 * max(0, int(tier)), 12))


# ── 渔获/作物回收修正 ──────────────────────────────────────────────
def clamp_mod(product: float) -> float:
    return max(MOD_LO, min(MOD_HI, float(product)))


def made_unit_price(item: str, mod_product: float = 1.0) -> int:
    """产出品单件回收价：floor(ref × clamp(修正乘积))，至少 1（ref>0 时）。"""
    ref = ref_value(item)
    if ref <= 0:
        return 0
    return max(1, int(ref * clamp_mod(mod_product)))


# ── 潮下销赃 ──────────────────────────────────────────────────────
def loot_key(shop_key: str) -> str:
    """ut_xxx → utl_xxx（赃物）。井底材料保持 ut_ 键。"""
    if not shop_key.startswith("ut_") or shop_key.endswith("_s"):
        return shop_key
    base = shop_key[3:]
    if base in LOOT_EXCLUDE:
        return shop_key
    return LOOT_PREFIX + base


def is_loot(item: str) -> bool:
    return item.startswith(LOOT_PREFIX)


def fence_shop_payout(base: int, *, u: float, tide: float, lucky: bool, substandard: bool = False) -> int:
    """店货销赃：base × U(0.60,0.85) × 景气(夹 0.85~1.15) × 幸运 1.15；次品再 ×0.45。

    最高 = base × 0.85 × 1.15 × 1.15 ≈ 1.124×base，低于最低买入 1.26×base。
    """
    u = max(FENCE_SHOP_LO, min(FENCE_SHOP_HI, u))
    tide = max(FENCE_SHOP_TIDE_LO, min(FENCE_SHOP_TIDE_HI, tide))
    value = base * u * tide * (FENCE_SHOP_LUCKY if lucky else 1.0)
    if substandard:
        value *= FENCE_SUB_MULT
    return max(0, int(value))


def fence_shop_max(base: int) -> int:
    return fence_shop_payout(base, u=FENCE_SHOP_HI, tide=FENCE_SHOP_TIDE_HI, lucky=True)


def fence_loot_payout(vend: int, *, u: float, tide: float, lucky: bool) -> int:
    """赃物销赃：沿用改版前的高价通道 vend × U(1.5,1.9) × 景气 × 幸运 ×2。"""
    value = vend * u * tide
    if lucky:
        value *= FENCE_LOOT_LUCKY
    return max(0, int(value))


# ── 酒吧打赏加成 ──────────────────────────────────────────────────
def tip_bonus_wanted(amount: int, rapport_ok: bool) -> int:
    if not rapport_ok or amount <= 0:
        return 0
    return max(1, amount * TIP_BONUS_PCT // 100)

"""小屋写操作。睡 / 升级 / 潮柜 / 堆肥桶 / 畜栏仍走 hut_ops；做饭走 kitchen_ops cook，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import barn, db, game, hut, kitchen
from .. import mcp_dispatch as mux
from ..catalog import HUT_HARD, HUT_SOFT, LILI_DECOR, is_bed_key
from ..florist_catalog import FLORIST_DECOR
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "look": "看屋",
    "sleep": "睡觉",
    "cook": "出锅了",
    "upgrade": "升级",
    "buy_install": "装上了",
    "install": "装上了",
    "put": "存进去了",
    "take": "取出来了",
    "expand": "加了格",
    "compost_put": "沤进去了",
    "compost_take": "取出了堆肥",
    "barn_erect": "搭了畜栏",
    "barn_buy": "买进栏了",
    "barn_feed": "喂过了",
    "barn_collect": "收过了",
    "barn_harvest": "大收了",
    "barn_shear": "剪过毛",
    "barn_churn": "搅成奶酪了",
    "barn_breed": "配种了",
    "barn_recover": "寻回牲口了",
    "barn_pedigree": "畜栏履历",
    "repair_appliance": "修好了",
    "repair_roof": "修好了",
    "bath": "泡过了",
    "read": "读过了",
    "sell_fit": "卖掉了",
    "pickle": "腌好了",
    "dry": "晾好了",
    "chore_pay": "交了家维",
    "chore_task": "杂务处置了",
    "mascot_adopt": "领养了吉祥物",
    "mascot_status": "吉祥物",
    "mascot_upkeep": "喂养吉祥物",
    "mascot_train": "陪练",
    "mascot_feed": "喂了饲料",
    "mascot_diet": "减肥",
    "mascot_walk": "散步",
    "barn_name": "起了名",
    "barn_fuss": "栏里的事处置了",
    "vet_treat": "请了兽医",
    "vet_fumes": "棚里呛处置了",
    "vet_catalog": "兽医价目",
    "vet_status": "栏里的病",
}

_TRAITS = {"scout", "lucky", "compost"}
_CHORES = {"自修", "请匠", "不管"}
_FUSS = {"哄", "关栏", "不管", "隔离", "兽医", "拖着"}
_FUMES = {"通风", "换草", "硬留"}


def _one_line(value: str, label: str, limit: int) -> str:
    text = (value or "").strip()
    if not text or len(text) > limit or any(ch in text for ch in "\r\n;"):
        raise ApiError("BAD_REQUEST", f"{label}写一行，不超过 {limit} 个字。")
    return text

_FIT_KIND = {
    "bed": "hard",
    "cabinet": "soft",
    "fridge": "soft",
    "compost_bin": "soft",
    "pickle_crock": "hard",
    "fish_rack": "soft",
    "bath_tub": "hard",
    "bookshelf": "soft",
}


def _qty_tail(target: str, default: int | None = 1) -> tuple[str, str]:
    raw = (target or "").strip()
    if not raw:
        return "", "" if default is None else str(default)
    parts = raw.split()
    if parts and parts[-1].isdigit():
        return " ".join(parts[:-1]), parts[-1]
    if default is None:
        return raw, ""
    return raw, str(default)


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await hut.player_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["hut"] = shelf
    return snap


_UNIQUE_FIT = {"bed", "cabinet", "fridge", "compost_bin", "hammock", "pickle_crock", "fish_rack", "bath_tub", "bookshelf"}


def _kind_for(key: str) -> str:
    bare = hut._fitting_bare(key)
    if bare in HUT_HARD or is_bed_key(bare) or bare == "hammock":
        return "hard"
    if bare in HUT_SOFT or bare in LILI_DECOR or bare in FLORIST_DECOR:
        return "soft"
    if str(key).startswith("deco_"):
        return "soft"
    raise ApiError("BAD_REQUEST", "小屋里装不了这一件。")


def _is_unique_fitting(key: str) -> bool:
    bare = hut._fitting_bare(key)
    return is_bed_key(bare) or bare in _UNIQUE_FIT


async def _empty_for(s: dict[str, Any], key: str) -> str:
    kind = _kind_for(key)
    async with db.connect() as conn:
        fittings = await hut._fittings(conn, s["id"])
    lvl = int(s.get("hut_level") or 1)
    slot = hut.first_empty_slot(lvl, fittings, kind)
    if not slot:
        raise ApiError("BAD_REQUEST", "没有空槽。先升级小屋，或卖掉一件腾位置。")
    return slot


def _already_in(fittings: dict[str, str], key: str) -> bool:
    for item in fittings.values():
        bare = hut._fitting_bare(item)
        if key == "bed" and (is_bed_key(bare) or bare == "hammock"):
            return True
        if bare == key:
            return True
    return False


async def _buy_install(key_id: int, key: str) -> str:
    if key not in _FIT_KIND:
        raise ApiError("BAD_REQUEST", "小屋里装不了这一件。")
    try:
        s = await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        fittings = await hut._fittings(conn, s["id"])
        stock = await db.get_satchel(s["id"])
    if _already_in(fittings, key):
        raise ApiError("BAD_REQUEST", "已经装上了。")
    bits: list[str] = []
    fit_item = f"fit_{key}"
    if int(stock.get(fit_item) or 0) < 1:
        bits.append(await hut.hut_ops(key_id, f"buy {key}"))
        s = await game.require_steward(key_id)
    try:
        slot = await _empty_for(s, key)
    except ApiError:
        if bits:
            return "\n".join(bits) + "\n买到了，但没有空槽。先升级小屋再装。"
        raise
    bits.append(await hut.hut_ops(key_id, f"install {slot} {key}"))
    return "\n".join(bits)


async def _install(key_id: int, key: str) -> str:
    try:
        s = await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    _kind_for(key)
    async with db.connect() as conn:
        fittings = await hut._fittings(conn, s["id"])
    if _is_unique_fitting(key) and _already_in(fittings, hut._fitting_bare(key)):
        raise ApiError("BAD_REQUEST", "已经装上了。")
    slot = await _empty_for(s, key)
    return await hut.hut_ops(key_id, f"install {slot} {key}")


def _command(kind: str, target: str) -> tuple[str, str]:
    """返回 (channel, command)。hut 走 hut_ops，barn 走 barn_ops，kitchen 走 kitchen_ops cook。"""
    extra = (target or "").strip()
    if kind == "look":
        return "hut", "status"
    if kind == "sleep":
        return "hut", "睡"
    if kind == "upgrade":
        return "hut", "upgrade"
    if kind == "put":
        name, qty = _qty_tail(extra, 1)
        if not name:
            raise ApiError("BAD_REQUEST", "先点要存的那一件。")
        return "hut", f"冰柜 存 {name} {qty}"
    if kind == "take":
        name, qty = _qty_tail(extra, 1)
        if not name:
            raise ApiError("BAD_REQUEST", "先点要取的那一件。")
        return "hut", f"冰柜 取 {name} {qty}"
    if kind == "expand":
        _, n = _qty_tail(extra, 1)
        return "hut", f"潮柜 扩 {n}"
    if kind == "compost_put":
        name, qty = _qty_tail(extra, 1)
        if not name:
            raise ApiError("BAD_REQUEST", "先点要沤的粪便。")
        return "hut", f"堆肥桶 存 {name} {qty}"
    if kind == "compost_take":
        _, qty = _qty_tail(extra, None)
        return "hut", f"堆肥桶 取 堆肥 {qty}".strip()
    if kind == "barn_erect":
        return "barn", "erect"
    if kind == "barn_buy":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点要买进栏的那一只。")
        return "barn", f"buy {extra}"
    if kind == "barn_feed":
        if not extra.isdigit():
            raise ApiError("BAD_REQUEST", "先点要喂的那一栏。")
        return "barn", f"feed {extra}"
    if kind == "barn_collect":
        if not extra.isdigit():
            raise ApiError("BAD_REQUEST", "先点要收的那一栏。")
        return "barn", f"collect {extra}"
    if kind == "barn_harvest":
        if not extra.isdigit():
            raise ApiError("BAD_REQUEST", "先点要大收的那一栏。")
        return "barn", f"harvest {extra}"
    if kind == "barn_shear":
        if not extra.isdigit():
            raise ApiError("BAD_REQUEST", "先点要剪毛的那一栏。")
        return "barn", f"shear {extra}"
    if kind == "barn_churn":
        _, n = _qty_tail(extra, 2)
        return "barn", f"churn {n}"
    if kind == "barn_breed":
        if not extra.isdigit():
            raise ApiError("BAD_REQUEST", "先点要配种的那一栏。")
        return "barn", f"breed {extra}"
    if kind == "barn_recover":
        if not extra.isdigit():
            raise ApiError("BAD_REQUEST", "先点要寻回的那一栏。")
        return "barn", f"recover {extra}"
    if kind == "barn_pedigree":
        return "barn", "履历"
    if kind == "barn_rescue":
        slot, _, action = extra.partition("|")
        if not slot.isdigit() or not action:
            raise ApiError("BAD_REQUEST", "先选诱回、围栏或急追。")
        return "barn", f"惊逃 {slot} {action}"
    if kind == "repair_appliance":
        key = (extra or "").strip().lower()
        if key == "fridge":
            return "hut", "修冰箱"
        if key == "stove":
            return "hut", "修灶"
        raise ApiError("BAD_REQUEST", "只能修冰箱或灶台。")
    if kind == "repair_roof":
        return "hut", "修屋顶"
    if kind == "bath":
        return "hut", "泡澡"
    if kind == "read":
        return "hut", "读书"
    if kind == "cook":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点要煮的菜，或点 2～5 样材料再下锅。")
        return "kitchen", f"cook {extra}"
    if kind == "sell_fit":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点要卖掉的那一件。")
        return "hut", f"卖掉 {extra} 确认"
    if kind == "pickle":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点要腌的蔬菜。")
        return "hut", f"腌 {extra}"
    if kind == "dry":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点要晾的生鱼。")
        return "hut", f"晾 {extra}"
    if kind == "chore_pay":
        return "hut", "家维 交"
    if kind == "chore_task":
        if extra not in _CHORES:
            raise ApiError("BAD_REQUEST", "杂务只能自修、请匠或不管。")
        return "hut", f"杂务 {extra}"
    if kind == "mascot_adopt":
        trait, _, name = extra.partition("|")
        if trait.strip() not in _TRAITS:
            raise ApiError("BAD_REQUEST", "特质只能是探路、好运或沤肥。")
        name = _one_line(name, "吉祥物的名字", 20)
        if " " in name:
            raise ApiError("BAD_REQUEST", "吉祥物的名字不能带空格。")
        return "bundle", f"mascot adopt {name} {trait.strip()}"
    if kind in ("mascot_status", "mascot_upkeep", "mascot_train", "mascot_feed"):
        return "bundle", f"mascot {kind.split('_', 1)[1]}"
    if kind == "mascot_diet":
        return "bundle", "mascot 减肥"
    if kind == "mascot_walk":
        return "bundle", "mascot 散步"
    if kind == "barn_name":
        slot, _, name = extra.partition("|")
        if not slot.strip().isdigit():
            raise ApiError("BAD_REQUEST", "先点要起名的那一栏。")
        name = _one_line(name, "名字", 12)
        if " " in name:
            raise ApiError("BAD_REQUEST", "名字不能带空格。")
        return "barn", f"起名 {int(slot)} {name}"
    if kind == "barn_fuss":
        if extra not in _FUSS:
            raise ApiError("BAD_REQUEST", "先选一路。")
        return "barn", f"闹脾气 {extra}"
    if kind == "vet_treat":
        if not extra.isdigit():
            raise ApiError("BAD_REQUEST", "先点要看的那一栏。")
        return "visit", f"兽医 treat {extra}"
    if kind == "vet_fumes":
        if extra not in _FUMES:
            raise ApiError("BAD_REQUEST", "棚险只能通风、换草或硬留。")
        return "visit", f"兽医 棚险 {extra}"
    if kind == "vet_catalog":
        return "visit", "兽医 catalog"
    if kind == "vet_status":
        return "visit", "兽医 status"
    raise ApiError("BAD_REQUEST", "小屋里没有这一下。")


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    verb = (kind or "").strip()
    if verb == "buy_install":
        key = (target or "").strip()
        if key not in _FIT_KIND:
            raise ApiError("BAD_REQUEST", "小屋里装不了这一件。")
        try:
            narrative = await _buy_install(key_id, key)
        except ApiError:
            raise
        except ValueError as exc:
            raise classify(exc) from exc
    elif verb == "install":
        key = (target or "").strip()
        if not key:
            raise ApiError("BAD_REQUEST", "先点要装的那一件。")
        try:
            narrative = await _install(key_id, key)
        except ApiError:
            raise
        except ValueError as exc:
            raise classify(exc) from exc
    else:
        channel, command = _command(verb, target)
        try:
            if channel == "barn":
                await game.require_steward(key_id)
                narrative = await barn.barn_ops(key_id, command)
            elif channel == "bundle":
                await game.require_steward(key_id)
                narrative = await mux.hut_bundle(key_id, command)
            elif channel == "visit":
                await game.require_steward(key_id)
                narrative = await mux.visit_bundle(key_id, command)
            elif channel == "kitchen":
                await game.require_steward(key_id)
                narrative = await kitchen.kitchen_ops(key_id, command)
            else:
                await game.require_steward(key_id)
                narrative = await hut.hut_ops(key_id, command)
        except ValueError as exc:
            raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(verb, "小屋"),
        "narrative": humanize(narrative),
        "kind": "hut",
    }
    return snap

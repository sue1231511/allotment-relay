"""小屋写操作。睡 / 升级 / 潮柜 / 堆肥桶 / 畜栏仍走 hut_ops，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import barn, db, game, hut
from ..catalog import is_bed_key
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "look": "看屋",
    "sleep": "睡觉",
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
}

_FIT_KIND = {
    "bed": "hard",
    "cabinet": "soft",
    "fridge": "soft",
    "compost_bin": "soft",
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


async def _empty_for(s: dict[str, Any], key: str) -> str:
    kind = _FIT_KIND.get(key)
    if not kind:
        raise ApiError("BAD_REQUEST", "小屋里装不了这一件。")
    async with db.connect() as conn:
        fittings = await hut._fittings(conn, s["id"])
    lvl = int(s.get("hut_level") or 1)
    slot = hut.first_empty_slot(lvl, fittings, kind)
    if not slot:
        raise ApiError("BAD_REQUEST", "没有空槽。先升级小屋。")
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
    if key not in _FIT_KIND:
        raise ApiError("BAD_REQUEST", "小屋里装不了这一件。")
    try:
        s = await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    slot = await _empty_for(s, key)
    return await hut.hut_ops(key_id, f"install {slot} {key}")


def _command(kind: str, target: str) -> tuple[str, str]:
    """返回 (channel, command)。channel=hut 走 hut_ops，barn 走 barn_ops。"""
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
        n = extra if extra.isdigit() else "1"
        return "hut", f"潮柜 扩 {n}"
    if kind == "compost_put":
        name, qty = _qty_tail(extra, 1)
        if not name:
            raise ApiError("BAD_REQUEST", "先点要沤的粪便。")
        return "hut", f"堆肥桶 存 {name} {qty}"
    if kind == "compost_take":
        qty = extra if extra.isdigit() else ""
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
        n = extra if extra.isdigit() else "2"
        return "barn", f"churn {n}"
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
        if key not in _FIT_KIND:
            raise ApiError("BAD_REQUEST", "小屋里装不了这一件。")
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

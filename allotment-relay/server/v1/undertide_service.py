"""潮下钱庄与赌场的移动端适配层。

数值、债务、限额和随机结算全部仍走 ``undertide_ops``；这里仅把手机上可点的
有限动作翻成既有命令，避免前端另算一套钱。
"""
from __future__ import annotations

from typing import Any

from .. import undertide
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "bank_debt": "恶猫钱庄",
    "bank_save": "存进账本",
    "bank_take": "从账本取出",
    "bank_borrow": "借款",
    "bank_repay": "还款",
    "casino_desk": "死人赌场",
    "casino_dice": "黑潮骰",
    "casino_lantern": "最后一盏灯",
    "casino_draw": "死人抽牌",
}


def _amount(target: str, *, allow_all: bool = False) -> str:
    value = (target or "").strip().lower()
    if allow_all and value == "all":
        return value
    if not value.isdigit() or int(value) <= 0:
        raise ApiError("BAD_REQUEST", "票数要填正整数。")
    return value


def _command(kind: str, target: str) -> str:
    kind = (kind or "").strip()
    target = (target or "").strip()
    if kind == "bank_debt":
        return "bank debt"
    if kind == "bank_save":
        return f"bank save {_amount(target)}"
    if kind == "bank_take":
        return f"bank take {_amount(target, allow_all=True)}"
    if kind == "bank_borrow":
        return f"bank borrow {_amount(target)}"
    if kind == "bank_repay":
        return f"bank repay {_amount(target, allow_all=True)}"
    if kind == "casino_desk":
        return "casino"
    if kind == "casino_dice":
        bits = target.split()
        if len(bits) != 2 or bits[0] not in {"small", "big", "black"}:
            raise ApiError("BAD_REQUEST", "骰桌要选小、 大或黑潮，再下注。")
        return f"dice {bits[0]} {_amount(bits[1])}"
    if kind == "casino_lantern":
        value = target.lower()
        if value in {"continue", "cash"}:
            return f"lantern {value}"
        return f"lantern {_amount(value)}"
    if kind == "casino_draw":
        bits = target.split()
        if len(bits) != 2:
            raise ApiError("BAD_REQUEST", "抽牌要填下注和停牌点。")
        try:
            stand = int(bits[1])
        except ValueError as exc:
            raise ApiError("BAD_REQUEST", "停牌点要填 12 到 20。") from exc
        if not 12 <= stand <= 20:
            raise ApiError("BAD_REQUEST", "停牌点只能在 12 到 20。")
        return f"draw {_amount(bits[0])} {stand}"
    raise ApiError("BAD_REQUEST", "这里没有这一下。")


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    """读取两个桌面的原始说明；未下井时赌场保留锁定提示。"""
    try:
        bank = await undertide.undertide_ops(key_id, "bank debt")
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        casino = await undertide.undertide_ops(key_id, "casino")
        casino_open = True
    except ValueError as exc:
        casino = str(exc)
        casino_open = False
    snap = await farm_service.snapshot(api_key, key_id)
    snap["undertide"] = {
        "bank": humanize(bank),
        "casino": humanize(casino),
        "casino_open": casino_open,
    }
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    command = _command(kind, target)
    try:
        narrative = await undertide.undertide_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(kind, "潮下"),
        "narrative": humanize(narrative),
        "kind": "undertide",
    }
    return snap

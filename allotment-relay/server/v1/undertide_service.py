"""潮下钱庄、赌场、后室铺、恩怨墙、医务间的移动端适配层。

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
    "well_crack": "井险处置",
    "market_desk": "后室铺",
    "market_buy": "按编号买",
    "market_repair": "找掌柜修",
    "racket_accept": "认栽成交",
    "racket_refuse": "硬扛",
    "bounty_desk": "恩怨墙",
    "bounty_take": "接单",
    "bounty_post": "挂单",
    "medic": "晏安医务间",
    "pit_drug": "体质药",
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
    if kind == "well_crack":
        if not target:
            raise ApiError("BAD_REQUEST", "先选清井、绑索或硬闯。")
        return f"井险 {target}"
    if kind == "market_desk":
        return "market"
    if kind == "market_buy":
        if not target:
            raise ApiError("BAD_REQUEST", "先写下货架编号。")
        return f"buy {target}"
    if kind == "market_repair":
        return "repair"
    if kind == "racket_accept":
        return "racket accept"
    if kind == "racket_refuse":
        return "racket refuse"
    if kind == "bounty_desk":
        return "bounty"
    if kind == "bounty_take":
        if not target:
            raise ApiError("BAD_REQUEST", "先写下悬赏编号。")
        return f"bounty take {target}"
    if kind == "bounty_post":
        bits = target.split()
        if len(bits) < 3 or bits[0] not in {"steal", "beat"}:
            raise ApiError("BAD_REQUEST", "挂单要写 steal 或 beat、名字和赏金。")
        return f"bounty post {target}"
    if kind == "medic":
        if not target:
            raise ApiError("BAD_REQUEST", "先选要治的井下伤。")
        return f"medic {target}"
    if kind == "pit_drug":
        return f"pit drug {target}".strip() if target else "pit drug list"
    raise ApiError("BAD_REQUEST", "这里没有这一下。")


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    """读取两个桌面的原始说明；未下井时赌场保留锁定提示。"""
    from .. import db
    from .. import undertide_well_crack as crack_mod

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

    async def _desk(command: str) -> str:
        try:
            return humanize(await undertide.undertide_ops(key_id, command))
        except ValueError as exc:
            return humanize(str(exc))

    market = await _desk("market")
    bounty = await _desk("bounty")
    medic = await _desk("pit")
    s = await db.get_steward_by_key_id(key_id)
    async with db.connect() as conn:
        well = await crack_mod.player_snippet(conn, s or {"id": 0, "tickets": 0})
    snap = await farm_service.snapshot(api_key, key_id)
    snap["undertide"] = {
        "bank": humanize(bank),
        "casino": humanize(casino),
        "casino_open": casino_open,
        "market": market,
        "bounty": bounty,
        "medic": medic,
        "well": well,
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

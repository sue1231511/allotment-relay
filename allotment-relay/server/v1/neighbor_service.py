"""邻居与互助：名册、帮忙打理、偷菜与致歉、借船、合伙、托养、菜篮、共耕、周目标、合约、联盟储藏室。

全部翻成已有的 steward_ops / alliance_ops / plot_ops 子命令，不新增玩法和数值。名字、物品、编号在适配层校验。
"""
from __future__ import annotations

import logging
import re
from typing import Any

from .. import db, game, multi
from .. import mcp_dispatch as mux
from . import farm_service
from .errors import ApiError, classify, humanize

log = logging.getLogger(__name__)

TITLES = {
    "peer": "公开档",
    "rapport": "协作度",
    "assist": "帮忙打理",
    "steal": "偷菜",
    "amends": "致歉",
    "loan_give": "借船",
    "loan_status": "借船状态",
    "share_open": "合伙开船",
    "share_join": "合伙入伙",
    "share_status": "合伙状态",
    "share_end": "合伙散伙",
    "foster_out": "托养送出",
    "foster_back": "托养接回",
    "foster_list": "托养列表",
    "basket_open": "开菜篮",
    "basket_order": "订菜篮",
    "basket_claim": "领菜篮",
    "cofarm_order": "订共耕",
    "cofarm_status": "共耕状态",
    "cofarm_end": "解共耕",
    "league_status": "周目标",
    "league_board": "贡献榜",
    "league_contribute": "贡献周目标",
    "larder_list": "联盟储藏室",
    "larder_donate": "存进储藏室",
    "larder_draw": "从储藏室领",
    "contract_list": "合约",
    "contract_mine": "我挂的合约",
    "contract_take": "接合约",
    "contract_fill": "交合约",
    "contract_cancel": "撤合约",
    "contract_post": "挂合约",
    "contract_post_labor": "挂看护委托",
}
BOATS = ("切波艇", "近海帆撬", "漂航船", "延绳船")
_NAME = re.compile(r"^[^\s;\r\n]{1,24}$")
_ITEM = re.compile(r"^[^\s;\r\n]{1,40}$")
_SLOT = re.compile(r"^(?:[0-9]{1,3}|[园棚][0-9]{1,3})$")
_NO_ARG = {
    "loan_status": ("alliance", "借船 状态"),
    "share_status": ("alliance", "合伙 状态"),
    "share_end": ("alliance", "合伙 散"),
    "foster_list": ("alliance", "托养 列表"),
    "basket_open": ("alliance", "菜篮 开"),
    "basket_claim": ("alliance", "菜篮 领"),
    "cofarm_status": ("alliance", "共耕 状态"),
    "league_status": ("alliance", "league status"),
    "league_board": ("alliance", "league board"),
    "larder_list": ("alliance", "larder"),
    "contract_list": ("alliance", "contract list"),
    "contract_mine": ("alliance", "contract mine"),
}
_ONE_NAME = {
    "peer": ("steward", "peer {}"),
    "rapport": ("alliance", "rapport {}"),
    "assist": ("alliance", "assist {}"),
    "amends": ("plot", "amends {}"),
    "loan_give": ("alliance", "借船 给 {}"),
    "share_join": ("alliance", "合伙 入 {}"),
    "basket_order": ("alliance", "菜篮 订 {}"),
    "cofarm_order": ("alliance", "共耕 订 {}"),
    "cofarm_end": ("alliance", "共耕 解 {}"),
}


def _name(value: str, label: str = "名字") -> str:
    text = (value or "").strip()
    if not _NAME.match(text):
        raise ApiError("BAD_REQUEST", f"先选{label}。")
    return text


def _item(value: str, label: str = "物品") -> str:
    text = (value or "").strip()
    if not _ITEM.match(text):
        raise ApiError("BAD_REQUEST", f"{label}填一个词。")
    return text


def _int(value: str, label: str) -> int:
    text = (value or "").strip()
    if not text.isdigit() or int(text) <= 0 or int(text) > 1_000_000_000:
        raise ApiError("BAD_REQUEST", f"{label}要正整数。")
    return int(text)


def _command(kind: str, target: str) -> tuple[str, str]:
    kind = (kind or "").strip()
    target = (target or "").strip()
    if kind in _NO_ARG:
        return _NO_ARG[kind]
    if kind in _ONE_NAME:
        tool, tmpl = _ONE_NAME[kind]
        return tool, tmpl.format(_name(target))
    bits = target.split()
    if kind == "steal":
        if not bits or len(bits) > 2:
            raise ApiError("BAD_REQUEST", "先选邻居，再选地块（不选就让游戏挑）。")
        if len(bits) == 2 and not _SLOT.match(bits[1]):
            raise ApiError("BAD_REQUEST", "地块写数字，或 园1、棚1。")
        return "plot", f"偷菜 {_name(bits[0])}" + (f" {bits[1]}" if len(bits) == 2 else "")
    if kind == "share_open":
        if target not in BOATS:
            raise ApiError("BAD_REQUEST", "合伙只能买切波艇、近海帆撬、漂航船、延绳船。")
        return "alliance", f"合伙 开 {target}"
    if kind in ("foster_out", "foster_back"):
        if len(bits) != 2 or not bits[1].isdigit() or int(bits[1]) <= 0:
            raise ApiError("BAD_REQUEST", "写邻居名和栏位号。")
        verb = "送出" if kind == "foster_out" else "接回"
        return "alliance", f"托养 {verb} {_name(bits[0])} {int(bits[1])}"
    if kind == "league_contribute":
        if len(bits) != 2:
            raise ApiError("BAD_REQUEST", "写物品和数量。")
        return "alliance", f"league contribute {_item(bits[0])} {_int(bits[1], '数量')}"
    if kind in ("larder_donate", "larder_draw"):
        if len(bits) != 2:
            raise ApiError("BAD_REQUEST", "写物品和数量。")
        verb = "donate" if kind == "larder_donate" else "draw"
        return "alliance", f"{verb} {_item(bits[0])} {_int(bits[1], '数量')}"
    if kind in ("contract_take", "contract_fill", "contract_cancel"):
        return "alliance", f"contract {kind.split('_', 1)[1]} {_int(target, '合约编号')}"
    if kind == "contract_post":
        if len(bits) != 3:
            raise ApiError("BAD_REQUEST", "写要的物品、数量、酬票。")
        return "alliance", f"contract post {_item(bits[0])} {_int(bits[1], '数量')} {_int(bits[2], '酬票')}"
    if kind == "contract_post_labor":
        if len(bits) != 2:
            raise ApiError("BAD_REQUEST", "写天数和酬票。")
        return "alliance", f"contract post 看护 {_int(bits[0], '天数')} {_int(bits[1], '酬票')}"
    raise ApiError("BAD_REQUEST", "这里没有这一下。")


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        steward = await game.require_steward(key_id, exempt_duty=True)
        roster = await multi.neighbor_roster(steward, online_only=False)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await farm_service.snapshot(api_key, key_id)
    snap["neighbors"] = {
        "total": roster["total"],
        "listed": roster["listed"],
        "online": roster["online"],
        "window_min": roster["window_min"],
        "people": roster["people"],
        "boats": list(BOATS),
    }
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    tool, command = _command(kind, target)
    runner = {"steward": mux.steward_ops, "alliance": mux.alliance_bundle, "plot": mux.plot_bundle}[tool]
    try:
        narrative = await runner(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {"title": TITLES.get(kind, "邻居"), "narrative": humanize(narrative), "kind": "neighbor"}
    return snap

"""潮下的移动端适配层：井口、钱庄、赌场、后室铺、恩怨墙、医务间、深坑、凯斯酒馆、监牢、K 室。

数值、债务、限额和随机结算全部仍走 ``undertide_ops``；这里仅把手机上可点的
有限动作翻成既有命令，避免前端另算一套钱。
"""
from __future__ import annotations

import logging
from typing import Any

from .. import undertide
from . import farm_service
from .errors import ApiError, classify, humanize

log = logging.getLogger(__name__)


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
    "well_look": "井口",
    "well_descend": "下井",
    "well_enter": "进入潮下",
    "well_guide": "井下指南",
    "well_clean": "清井",
    "well_status": "潮下档案",
    "pit_list": "深坑",
    "pit_board": "井壁胜场榜",
    "pit_fight": "下坑",
    "tavern_visit": "凯斯酒馆",
    "tavern_chat": "跟荔栀说话",
    "tavern_whisper": "耳语人",
    "tavern_spy": "查雇主",
    "tavern_ai": "别人的动态",
    "tavern_ruby": "红宝石",
    "tavern_bleed": "卖血",
    "jail_status": "地下监牢",
    "jail_ransom": "赎身",
    "jail_serve": "服刑",
    "jail_work": "苦力",
    "kroom_status": "K 室",
    "kroom_settle": "K 室结算",
    "kroom_vr": "价值回收",
    "street": "帘外街",
    "muscle": "强买",
    "push": "强卖",
    "hijack": "劫持",
    "grudge": "寻仇应对",
    "lottery": "潮汐博彩",
    "refine_list": "潮下炼制",
    "refine": "炼",
    "sell": "出货",
    "cheer": "哄猫猫",
}

_STRATEGIES = {"attack", "guard", "feint"}
_NO_ARG = {
    "well_look": "well",
    "well_descend": "descend",
    "well_enter": "enter",
    "well_guide": "guide",
    "well_clean": "清井",
    "well_status": "status",
    "pit_list": "pit",
    "pit_board": "pit board",
    "tavern_visit": "tavern",
    "tavern_chat": "tavern chat",
    "tavern_whisper": "tavern whisper",
    "tavern_spy": "tavern spy",
    "tavern_ai": "tavern ai",
    "jail_status": "jail status",
    "jail_ransom": "jail ransom",
    "jail_serve": "jail serve",
    "jail_work": "jail work",
    "kroom_status": "kroom status",
    "kroom_settle": "kroom settle",
    "kroom_vr": "kroom vr",
    "street": "street",
    "lottery": "lottery",
    "refine_list": "炼 list",
}


def _token(value: str, label: str, *, limit: int = 40) -> str:
    """名字、物品、炼制 key 这类单个词：不许空、不许换行、不许太长。"""
    text = (value or "").strip()
    if not text or len(text) > limit or any(ch in text for ch in "\r\n;"):
        raise ApiError("BAD_REQUEST", f"{label}填一个词，别带换行或分号。")
    return text


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
    if kind in _NO_ARG:
        return _NO_ARG[kind]
    if kind == "pit_fight":
        bits = target.split()
        if not bits or len(bits) > 2:
            raise ApiError("BAD_REQUEST", "先选斗士，再选攻、守或虚晃（不选就随机）。")
        if len(bits) == 2 and bits[1].lower() not in _STRATEGIES:
            raise ApiError("BAD_REQUEST", "打法只能是 attack、guard 或 feint。")
        return f"fight {_token(bits[0], '斗士名')}" + (f" {bits[1].lower()}" if len(bits) == 2 else "")
    if kind in ("tavern_ruby", "tavern_bleed"):
        verb = kind.split("_", 1)[1]
        if target and target not in ("confirm", "确认"):
            raise ApiError("BAD_REQUEST", "只能先问价，再确认。")
        return f"tavern {verb}" + (" 确认" if target else "")
    if kind == "muscle":
        return f"muscle {_token(target, '名号')}"
    if kind == "push":
        bits = target.split()
        if len(bits) != 2:
            raise ApiError("BAD_REQUEST", "强卖要写名号和物品。")
        return f"push {_token(bits[0], '名号')} {_token(bits[1], '物品')}"
    if kind == "hijack":
        return f"hijack {_token(target, '对象')}"
    if kind == "grudge":
        if target not in ("pay", "fight", "run"):
            raise ApiError("BAD_REQUEST", "寻仇只能 pay、fight 或 run。")
        return f"grudge {target}"
    if kind == "refine":
        return f"炼 {_token(target, '炼制名')}"
    if kind == "sell":
        bits = target.split()
        if not bits or len(bits) > 2 or (len(bits) == 2 and (not bits[1].isdigit() or int(bits[1]) <= 0)):
            raise ApiError("BAD_REQUEST", "出货写物品，数量要正整数（不写就一件）。")
        return f"sell {_token(bits[0], '物品')}" + (f" {bits[1]}" if len(bits) == 2 else "")
    if kind == "cheer":
        return f"cheer {_token(target, '好话', limit=60)}"
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


_DESK_COMMANDS = {
    "well": "well",
    "tavern": "tavern",
    "jail": "jail status",
    "kroom": "kroom status",
}


async def snapshot(api_key: str, key_id: int, desk: str = "", *, text: bool = True) -> dict[str, Any]:
    """读取各柜台的说明。

    不带 desk：钱庄、赌场、后室铺、恩怨墙、医务间（老接口，手机地图原样用）。
    带 desk=well|pit|tavern|jail|kroom：只多取那一处。柜台每看一次都会掷井下随机事件，
    所以不一股脑全取。text=False 时（动作回包）不重读柜台说明，只带状态和斗士名册。
    """
    from .. import db
    from .. import undertide_well_crack as crack_mod

    desk = (desk or "").strip()
    if desk and desk not in {"well", "pit", "tavern", "jail", "kroom"}:
        raise ApiError("BAD_REQUEST", "没有这个柜台。")

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
    medic = await _desk("pit drug list")
    s = await db.get_steward_by_key_id(key_id)
    async with db.connect() as conn:
        well = await crack_mod.player_snippet(conn, s or {"id": 0, "tickets": 0})
        ut = await undertide._ensure_ut(conn, int(s["id"])) if s else {}
    snap = await farm_service.snapshot(api_key, key_id)
    under: dict[str, Any] = {
        "bank": humanize(bank),
        "casino": humanize(casino),
        "casino_open": casino_open,
        "market": market,
        "bounty": bounty,
        "medic": medic,
        "well": well,
        "access": bool(ut.get("access")),
        "well_hint": bool(ut.get("well_hint")),
        "jailed": ut.get("jail_state") == "serving",
    }
    if text and desk in _DESK_COMMANDS:
        under[desk + "_text"] = await _desk(_DESK_COMMANDS[desk])
    if desk == "pit":
        from .. import undertide_pit

        if text:
            under["pit_text"] = await _desk("pit")
        fighters: list[dict[str, Any]] = []
        if under["access"]:
            try:
                async with db.connect() as conn:
                    fighters = await undertide_pit.fighters_view(conn)
                    await conn.commit()
            except Exception:
                log.exception("深坑斗士名册读取失败 key_id=%s desk=%s", key_id, desk)
        under["pit"] = fighters
    snap["undertide"] = under
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    command = _command(kind, target)
    try:
        narrative = await undertide.undertide_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    desk = kind.split("_", 1)[0] if kind.split("_", 1)[0] in {"well", "pit", "tavern", "jail", "kroom"} else ""
    snap = await snapshot(api_key, key_id, desk, text=False)
    snap["event"] = {
        "title": TITLES.get(kind, "潮下"),
        "narrative": humanize(narrative),
        "kind": "undertide",
    }
    return snap

"""每事件多选 — 点名册里每条至少两路，不全是扣票。

已有入口（帆撕/虫害/惊逃/杂务/塌方等）只登记；缺档的事记待选，steward_ops 灾选 处理。
"""
from __future__ import annotations

import json
from typing import Any

from . import bad_event_tiers as tiers_mod
from . import db

CHOICES: dict[str, dict[str, Any]] = {
    "bird_peck": {"via": "份地田间事件", "opts": ("不管", "补种"), "owned": False},
    "line_slip": {"via": "海边再钓", "opts": ("再钓", "换饵"), "owned": False},
    "humid_soft": {"via": "小屋杂务", "opts": ("晾晒", "不管", "请匠"), "owned": False},
    "stove_stubborn": {"via": "小屋灶台", "opts": ("清灰", "硬烧", "不管"), "owned": False},
    "barn_fuss": {"via": "畜栏闹脾气", "opts": ("哄", "关栏", "不管"), "owned": False},
    "line_tangle": {"via": "渔具栏", "opts": ("解开", "剪断", "不管"), "owned": False},
    "net_weed": {"via": "港口撒网", "opts": ("理网", "不管"), "owned": True},
    "shovel_dull": {"via": "赶海再翻", "opts": ("磨刃", "硬挖", "不管"), "owned": False},
    "probe_sand": {"via": "赶海探沙", "opts": ("再探", "不管"), "owned": True},
    "frost_chore": {"via": "小屋杂务", "opts": ("自修", "请匠", "不管"), "owned": True},
    "door_hinge": {"via": "小屋杂务", "opts": ("自修", "请匠", "不管"), "owned": True},
    "roof_drip": {"via": "小屋修屋顶", "opts": ("自修", "请匠", "不管"), "owned": True},
    "lamp_out": {"via": "小屋杂务", "opts": ("自修", "请匠", "不管"), "owned": True},
    "fridge_break": {"via": "小屋修冰箱", "opts": ("修冰箱", "用盐冰", "不管"), "owned": False},
    "sheep_escape": {"via": "畜栏惊逃", "opts": ("诱回", "围栏", "急追"), "owned": True},
    "pest": {"via": "份地田间事件", "opts": ("手工", "施药", "拔除", "不管"), "owned": True},
    "sail_tear": {"via": "港口出海栏", "opts": ("补", "返航", "硬撑"), "owned": True},
    "gh_leak": {"via": "份地田间事件", "opts": ("补网", "通风", "不管"), "owned": True},
    "rats": {"via": "份地田间事件", "opts": ("手工", "施药", "拔除"), "owned": True},
    "wind_scorch": {"via": "份地田间事件", "opts": ("手工", "施药", "拔除"), "owned": True},
    "woodworm": {"via": "小屋杂务", "opts": ("自修", "请匠", "不管"), "owned": True},
    "stove_clog": {"via": "小屋杂务", "opts": ("自修", "请匠", "不管"), "owned": True},
    "mold_soft": {"via": "小屋杂务", "opts": ("自修", "请匠", "不管"), "owned": True},
    "hold_leak": {"via": "港口修舱", "opts": ("修", "返航", "硬撑"), "owned": False},
    "bilge": {"via": "港口修船", "opts": ("修泵", "返航", "硬撑"), "owned": True},
    "murrain": {"via": "小屋找兽医", "opts": ("兽医", "自己处理", "拖着"), "owned": False},
    "quarry_collapse": {"via": "盐风崖塌方", "opts": ("撑柱", "撤人", "硬挖"), "owned": True},
    "roof_leak_bad": {"via": "小屋修屋顶", "opts": ("修屋顶", "接盆", "不管"), "owned": False},
    "hold_break": {"via": "港口修舱", "opts": ("修", "返航", "硬撑"), "owned": False},
    "well_crack": {"via": "井下井险", "opts": ("清井", "绑索", "硬闯"), "owned": True},
    "dystocia": {"via": "小屋找兽医", "opts": ("兽医", "自己处理", "拖着"), "owned": False},
    "storm_wreck": {"via": "港口修船", "opts": ("修船", "捞残骸", "不管"), "owned": False},
    "epidemic": {"via": "畜栏灾选", "opts": ("绔离", "兽医", "拖着"), "owned": False},
    "tide_press": {"via": "潮生会工程", "opts": ("捐排水", "不管"), "owned": True},
    "sinkhole": {"via": "份地田间事件", "opts": ("填土", "围起来", "不管"), "owned": True},
    "crop_wipe": {"via": "份地田间事件", "opts": ("手工", "施药", "拔除"), "owned": True},
    "rabbit": {"via": "份地稻草人", "opts": ("扎稻草人", "不管"), "owned": True},
    "deer": {"via": "份地稻草人", "opts": ("扎稻草人", "不管"), "owned": True},
    "boar": {"via": "份地田间事件", "opts": ("不管", "补种"), "owned": True},
    "gull": {"via": "份地田间事件", "opts": ("不管", "补种"), "owned": True},
    "slug": {"via": "份地田间事件", "opts": ("手工", "施药", "不管"), "owned": True},
    "crow": {"via": "份地田间事件", "opts": ("不管", "补种"), "owned": True},
    "dove": {"via": "份地田间事件", "opts": ("忽略", "驱赶"), "owned": True},
    "woodpecker": {"via": "果园", "opts": ("不管", "补种"), "owned": True},
    "dry_spell": {"via": "份地浇水", "opts": ("浇水", "不管"), "owned": True},
    "canker": {"via": "份地田间事件", "opts": ("拔除", "施药", "不管"), "owned": True},
    "squirrel": {"via": "果园", "opts": ("不管", "补种"), "owned": True},
    "hail": {"via": "港口出海栏", "opts": ("fight", "flee", "parley", "bribe"), "owned": True},
    "clinic_queue": {"via": "广场诊所", "opts": ("排队", "改天"), "owned": True},
    "barn_choke": {"via": "小屋找兽医", "opts": ("通风", "不管"), "owned": False},
    "bar_sink": {"via": "酒吧洗碗", "opts": ("擦干", "不管"), "owned": True},
    "eatery_smoke": {"via": "小馆后厨", "opts": ("开窗", "不管"), "owned": True},
    "stall_gust": {"via": "集市看摊", "opts": ("压货", "不管"), "owned": True},
    "salt_blot": {"via": "份地田间事件", "opts": ("施药", "拔除", "不管"), "owned": True},
    "well_return": {"via": "潮生会工程", "opts": ("捐排水", "不管"), "owned": True},
    "home_wick": {"via": "小屋杂务", "opts": ("自修", "请匠", "不管"), "owned": True},
    "home_roof": {"via": "小屋修屋顶", "opts": ("自修", "请匠", "不管"), "owned": True},
    "leg_fish": {"via": "广场诊所", "opts": ("treat", "不管"), "owned": True},
    "red_tide": {"via": "广场诊所", "opts": ("treat", "不管"), "owned": True},
    "hull_leak": {"via": "港口修船", "opts": ("修船体", "硬撑", "返航"), "owned": True},
    "line_snap": {"via": "渔具栏", "opts": ("修线", "换线", "不管"), "owned": True},
    "snag": {"via": "港口解挂", "opts": ("解挂", "切线"), "owned": True},
    "big_fight": {"via": "港口搏鱼", "opts": ("硬拉", "放走", "切线"), "owned": True},
    "aphid": {"via": "份地田间事件", "opts": ("手工", "施药", "拔除"), "owned": True},
    "root_rot": {"via": "份地田间事件", "opts": ("手工", "施药", "拔除"), "owned": True},
    "blight": {"via": "份地田间事件", "opts": ("手工", "施药", "拔除"), "owned": True},
    "peach_worm": {"via": "份地田间事件", "opts": ("手工", "施药", "拔除"), "owned": True},
    "grape_rot": {"via": "份地田间事件", "opts": ("手工", "施药", "拔除"), "owned": True},
    "storm_wreck_part": {"via": "港口出海栏", "opts": ("补", "返航", "硬撑"), "owned": True},
    "murrain_week": {"via": "小屋找兽医", "opts": ("兽医", "绔离", "拖着"), "owned": False},
    "quarry_dust": {"via": "广场诊所", "opts": ("treat", "不管"), "owned": True},
    "well_fall": {"via": "井下井险", "opts": ("清井", "绑索", "硬闯"), "owned": True},
    "fish_ban": {"via": "潮生会禁捕", "opts": ("放生", "认罚"), "owned": True},
    "escape_cache": {"via": "畜栏惊逃", "opts": ("诱回", "急追"), "owned": True},
    "blight_ash": {"via": "份地田间事件", "opts": ("烧灰", "不管"), "owned": True},
    "wreck_scrap": {"via": "港口打捞", "opts": ("捞残骸", "不管"), "owned": True},
}

TICKET_COSTS = {
    "哄": 6,
    "清灰": 4,
    "晒晒": 3,
    "磨刃": 5,
    "修": 16,
    "修冰箱": 18,
    "修屋顶": 20,
    "修船": 22,
    "兽医": 28,
    "绔离": 10,
    "自己处理": 8,
    "用盐冰": 6,
    "接盆": 4,
    "补种": 0,
    "捞残骸": 0,
}


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_event_choices (
            steward_id INTEGER NOT NULL REFERENCES stewards(id),
            event_key TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL,
            PRIMARY KEY (steward_id, event_key)
        )
        """
    )


def spec_for(event_key: str) -> dict[str, Any] | None:
    return CHOICES.get(event_key)


def cover_ok() -> bool:
    from . import event_catalog

    for ev in event_catalog.NAMED_EVENTS:
        spec = CHOICES.get(ev["key"])
        if not spec or len(spec.get("opts") or ()) < 2:
            return False
    return True


def covered_count() -> int:
    return sum(1 for spec in CHOICES.values() if len(spec.get("opts") or ()) >= 2)


def catalog_line(event_key: str) -> str:
    spec = CHOICES.get(event_key) or {}
    opts = "｜".join(spec.get("opts") or ())
    via = spec.get("via") or "管家档灾选"
    return f"{event_key}：{opts}（{via}）"


async def offer(conn, steward_id: int, event_key: str, **payload: Any) -> str | None:
    spec = CHOICES.get(event_key)
    if not spec:
        return None
    if spec.get("owned"):
        return None
    await ensure_table(conn)
    now = db.now()
    blob = json.dumps(payload, ensure_ascii=False)
    await conn.execute(
        """
        INSERT OR REPLACE INTO steward_event_choices
        (steward_id, event_key, payload_json, created_at)
        VALUES (?,?,?,?)
        """,
        (int(steward_id), event_key, blob, now),
    )
    opts = "｜".join(spec["opts"])
    return f"待选 {spec.get('via') or event_key}：{opts}（上手页管家档点灾选）"

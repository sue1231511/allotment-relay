"""栗栗摊麻烦档：换货后摊车倾斜，三选一（压货 / 唤铃 / 硬绑）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_TILT = "tilt"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN lili_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN lili_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT lili_hazard FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


async def maybe_after_trade(conn, steward_id: int) -> str | None:
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > 0.12:
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET lili_hazard=?, lili_hazard_json=?
        WHERE id=?
        """,
        (
            HAZARD_TILT,
            json.dumps({"kind": "cart_tilt"}, ensure_ascii=False),
            steward_id,
        ),
    )
    return (
        "铃鹿一蹦，摊车歪了，货要滑！"
        " visit_ops lili 栗险 压货|唤铃|硬绑"
        "（压货=黑麦×1或6票；唤铃=5精力；硬绑=10精力）"
        "人类 /island 栗栗摊也能点。"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_TILT:
        raise ValueError(
            "摊车还歪着，先 visit_ops lili 栗险 压货|唤铃|硬绑。"
            "人类 /island 栗栗摊也能点。"
        )


def ui_actions(*, tickets: int, stock: dict[str, int], energy_now: int) -> list[dict[str, Any]]:
    rye = int(stock.get("crop_rye") or 0)
    return [
        {
            "action": "压货",
            "label": "压货",
            "hint": "黑麦×1 或 6 票",
            "can": rye >= 1 or tickets >= 6,
            "disabled_reason": "缺黑麦且票不够 6",
        },
        {
            "action": "唤铃",
            "label": "唤铃",
            "hint": "5 精力",
            "can": energy_now >= 5,
            "disabled_reason": "精力不够 5",
        },
        {
            "action": "硬绑",
            "label": "硬绑",
            "hint": "10 精力",
            "can": energy_now >= 10,
            "disabled_reason": "精力不够 10",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_TILT:
        raise ValueError("没有栗险待决。visit_ops lili scan 看摊")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("压货", "weight"), ("唤铃", "bell"), ("硬绑", "bind")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("栗险处置：压货 · 唤铃 · 硬绑（例 visit_ops lili 栗险 压货）")
    sid = steward["id"]

    if norm == "压货":
        paid = ""
        if not await db.take_item(conn, sid, "crop_rye", 1):
            cost = 6
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("压货要黑麦×1 或 6 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "黑麦×1"
        await _clear(conn, sid)
        return f"压稳货箱，铃鹿不闹了。（{paid}）"

    if norm == "唤铃":
        await energy.spend(conn, sid, 5, action="栗栗唤铃")
        await _clear(conn, sid)
        return "摇响铃铛，夜栖把摊脚顶住了。"

    await energy.spend(conn, sid, 10, action="栗栗硬绑")
    lost = ""
    if random.random() < 0.22:
        for shell in ("shell_catseye", "shell_rough_white", "shell_rough_brown"):
            if await db.take_item(conn, sid, shell, 1):
                lost = "绑绳时滑走一枚贝壳。"
                break
    await _clear(conn, sid)
    return f"硬绑好摊绳，继续换货。{lost}"


async def _clear(conn, steward_id: int) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET lili_hazard=NULL, lili_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )

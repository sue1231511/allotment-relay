"""引航 — 邀请关系、多信号风控、分阶段奖励。

不封号。单一 IP / 设备 / VPN 信号不能单独定罪。
奖励资格只由后端判断；玩家接口不返回风险分、权重或阈值。
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import re
import secrets
from typing import Any

import aiosqlite
from fastapi import Request

from . import config, db

_SETTLING: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "invite_settling", default=False
)

STATUS_PENDING = "pending"
STATUS_QUALIFIED = "qualified"
STATUS_RISK_REVIEW = "risk_review"
STATUS_REWARDED = "rewarded"
STATUS_INVALID = "invalid"

TIER_MEMENTO = "memento"
TIER_QUALIFIED = "qualified"
TIER_FINAL = "final"

TIER_LABEL = {
    TIER_MEMENTO: "纪念礼",
    TIER_QUALIFIED: "正式邀请",
    TIER_FINAL: "深缘礼",
}

ACTIVITY_TYPES = (
    "npc",
    "tale",
    "story",
    "encounter",
    "eatery",
    "donate",
    "plot",
    "explore",
)

ACTIVITY_LABEL = {
    "npc": "NPC 好感",
    "tale": "潮闻",
    "story": "故事",
    "encounter": "相遇",
    "eatery": "小馆",
    "donate": "捐赠",
    "plot": "份地",
    "explore": "探索",
}

STATUS_LABEL = {
    STATUS_PENDING: "等岛缘结上",
    STATUS_QUALIFIED: "已是岛民",
    STATUS_RISK_REVIEW: "核验中",
    STATUS_REWARDED: "已致谢",
    STATUS_INVALID: "暂未计入",
}

KEEPSAKES: dict[str, dict[str, str]] = {
    "landing_note": {"name": "登岛笺", "emoji": "✉", "who": "invitee", "tier": TIER_MEMENTO},
    "guide_wick": {"name": "引航灯芯", "emoji": "🕯️", "who": "inviter", "tier": TIER_MEMENTO},
    "shore_lamp": {"name": "岸灯", "emoji": "🏮", "who": "inviter", "tier": TIER_QUALIFIED},
    "twin_tide": {"name": "双人潮纹", "emoji": "〰", "who": "inviter", "tier": TIER_FINAL},
    "deep_shell": {"name": "深缘贝", "emoji": "🐚", "who": "invitee", "tier": TIER_FINAL},
}

ENERGY_ACTIVITY = {
    "撒网": "explore",
    "坐钓": "explore",
    "赶海": "explore",
    "掏洞": "explore",
    "捞怪鱼": "explore",
    "探脉": "explore",
    "崖矿": "explore",
    "洗矿": "explore",
    "工坊": "explore",
    "灌盐田": "explore",
    "收盐": "explore",
    "打捞": "explore",
    "酒吧上工": "encounter",
    "小剧场试镜": "encounter",
    "小剧场对戏": "encounter",
    "小剧场演出": "encounter",
    "star_watch": "encounter",
    "tale_explore": "tale",
    "讨伐": "explore",
    "砍缆跑路": "explore",
    "黑旗接舷": "explore",
    "出海": "explore",
}

_CODE_RE = re.compile(r"[^A-Z2-9]")
_DEVICE_RE = re.compile(r"^[0-9a-fA-F-]{16,80}$")


def make_invite_code(n: int | None = None) -> str:
    length = int(n or config.INVITE_CODE_LEN)
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(max(4, length)))


def normalize_code(raw: str) -> str:
    text = (raw or "").strip().upper().replace("-", "").replace(" ", "")
    if text.startswith("INVITE"):
        text = text[6:]
    return _CODE_RE.sub("", text)


def normalize_device_id(raw: str) -> str:
    text = (raw or "").strip()
    if not text or not _DEVICE_RE.match(text):
        return ""
    return text[:80]


def hash_ip(ip: str) -> str:
    raw = (ip or "").strip()
    if not raw:
        return ""
    salt = config.INVITE_IP_SALT
    return hashlib.sha256(f"{salt}|{raw}".encode("utf-8")).hexdigest()[:32]


def client_ip_and_hops(request: Request | None) -> tuple[str, int]:
    if request is None:
        return "", 1
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    hops = 1
    ip = ""
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        hops = max(1, len(parts))
        ip = parts[0] if parts else ""
    if not ip and request.client:
        ip = request.client.host or ""
    return ip, hops


def device_from_cookie(request: Request | None) -> str:
    if request is None:
        return ""
    return normalize_device_id(request.cookies.get("tidal_did") or "")


def public_status(status: str) -> str:
    return STATUS_LABEL.get(status, "未绑定")


def risk_band(score: int) -> str:
    n = int(score or 0)
    if n <= config.INVITE_RISK_LOW_MAX:
        return "low"
    if n <= config.INVITE_RISK_MID_MAX:
        return "mid"
    return "high"


async def ensure_schema(conn: aiosqlite.Connection) -> None:
    """幂等建表。init_db 也会跑一遍，这里给单测/热路径兜底。"""
    for ddl in _SCHEMA_DDL:
        try:
            await conn.execute(ddl)
        except aiosqlite.OperationalError:
            pass


_SCHEMA_DDL = (
    "ALTER TABLE stewards ADD COLUMN invite_code TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE stewards ADD COLUMN invited_by INTEGER",
    "ALTER TABLE stewards ADD COLUMN invite_bound_at INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE stewards ADD COLUMN invite_status TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE stewards ADD COLUMN invite_lantern INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE api_keys ADD COLUMN pending_invite_code TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE api_keys ADD COLUMN register_device_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE api_keys ADD COLUMN register_ip_hash TEXT NOT NULL DEFAULT ''",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_stewards_invite_code
    ON stewards(invite_code) WHERE invite_code != ''
    """,
    """
    CREATE TABLE IF NOT EXISTS invite_devices (
        device_id TEXT NOT NULL,
        key_id INTEGER NOT NULL,
        first_seen_at INTEGER NOT NULL,
        last_seen_at INTEGER NOT NULL,
        PRIMARY KEY (device_id, key_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invite_ip_log (
        ip_hash TEXT NOT NULL,
        key_id INTEGER NOT NULL,
        first_seen_at INTEGER NOT NULL,
        last_seen_at INTEGER NOT NULL,
        hops INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (ip_hash, key_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invite_activity (
        steward_id INTEGER NOT NULL,
        activity_type TEXT NOT NULL,
        first_at INTEGER NOT NULL,
        count INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (steward_id, activity_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invite_rewards (
        invitee_id INTEGER NOT NULL,
        tier TEXT NOT NULL,
        granted_at INTEGER NOT NULL,
        PRIMARY KEY (invitee_id, tier)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invite_keepsakes (
        steward_id INTEGER NOT NULL,
        item_key TEXT NOT NULL,
        granted_at INTEGER NOT NULL,
        PRIMARY KEY (steward_id, item_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invite_risk_log (
        invitee_id INTEGER PRIMARY KEY,
        inviter_id INTEGER NOT NULL,
        bound_at INTEGER NOT NULL,
        island_bond INTEGER NOT NULL DEFAULT 0,
        active_days INTEGER NOT NULL DEFAULT 0,
        activity_types INTEGER NOT NULL DEFAULT 0,
        device_account_count INTEGER NOT NULL DEFAULT 0,
        risk_score INTEGER NOT NULL DEFAULT 0,
        hit_rules TEXT NOT NULL DEFAULT '[]',
        invite_status TEXT NOT NULL DEFAULT 'pending',
        rewards_json TEXT NOT NULL DEFAULT '[]',
        note TEXT NOT NULL DEFAULT '',
        cleared_at INTEGER NOT NULL DEFAULT 0,
        updated_at INTEGER NOT NULL
    )
    """,
)


async def backfill_invite_codes(conn: aiosqlite.Connection) -> None:
    await ensure_schema(conn)
    rows = await (await conn.execute(
        "SELECT id FROM stewards WHERE COALESCE(invite_code,'')=''"
    )).fetchall()
    for (sid,) in rows:
        await assign_invite_code(conn, int(sid))


async def assign_invite_code(conn: aiosqlite.Connection, steward_id: int) -> str:
    row = await (await conn.execute(
        "SELECT invite_code FROM stewards WHERE id=?", (steward_id,)
    )).fetchone()
    if row and (row[0] or "").strip():
        return str(row[0])
    for _ in range(12):
        code = make_invite_code()
        try:
            await conn.execute(
                "UPDATE stewards SET invite_code=? WHERE id=? AND COALESCE(invite_code,'')=''",
                (code, steward_id),
            )
        except aiosqlite.IntegrityError:
            continue
        got = await (await conn.execute(
            "SELECT invite_code FROM stewards WHERE id=?", (steward_id,)
        )).fetchone()
        if got and got[0]:
            return str(got[0])
    raise ValueError("发不出引航码，请稍后再试")


async def lookup_inviter(conn: aiosqlite.Connection, code: str) -> dict[str, Any] | None:
    norm = normalize_code(code)
    if not norm:
        return None
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM stewards WHERE invite_code=? AND enrolled=1", (norm,)
    )).fetchone()
    return dict(row) if row else None


async def set_pending_invite(
    conn: aiosqlite.Connection,
    key_id: int,
    invite_code: str,
    device_id: str = "",
    ip: str = "",
) -> dict[str, Any]:
    """登记凭证时记下邀请码。码无效不挡签发，只是不挂 pending。"""
    await ensure_schema(conn)
    norm = normalize_code(invite_code)
    did = normalize_device_id(device_id)
    iph = hash_ip(ip)
    ok = False
    err = ""
    if norm:
        inviter = await lookup_inviter(conn, norm)
        if not inviter:
            err = "邀请码无效，或邀请人还没上岛"
        else:
            ok = True
    await conn.execute(
        """
        UPDATE api_keys SET pending_invite_code=?, register_device_id=?, register_ip_hash=?
        WHERE id=?
        """,
        (norm if ok else "", did, iph, key_id),
    )
    return {"ok": ok, "error": err, "code": norm if ok else ""}


async def observe(
    key_id: int,
    device_id: str = "",
    ip: str = "",
    hops: int = 1,
    *,
    now: int | None = None,
    conn: aiosqlite.Connection | None = None,
) -> None:
    if not key_id:
        return
    ts = db.now() if now is None else int(now)
    did = normalize_device_id(device_id)
    iph = hash_ip(ip)

    async def _write(c: aiosqlite.Connection) -> None:
        await ensure_schema(c)
        if did:
            await c.execute(
                """
                INSERT INTO invite_devices (device_id, key_id, first_seen_at, last_seen_at)
                VALUES (?,?,?,?)
                ON CONFLICT(device_id, key_id) DO UPDATE SET last_seen_at=excluded.last_seen_at
                """,
                (did, key_id, ts, ts),
            )
        if iph:
            await c.execute(
                """
                INSERT INTO invite_ip_log (ip_hash, key_id, first_seen_at, last_seen_at, hops)
                VALUES (?,?,?,?,?)
                ON CONFLICT(ip_hash, key_id) DO UPDATE SET
                    last_seen_at=excluded.last_seen_at,
                    hops=MAX(invite_ip_log.hops, excluded.hops)
                """,
                (iph, key_id, ts, ts, max(1, int(hops))),
            )

    if conn is not None:
        await _write(conn)
        return
    async with db.connect() as owned:
        await _write(owned)
        await owned.commit()


def activity_from_bond(
    cat: str,
    once: str | None = None,
    daily: str | None = None,
    activity: str | None = None,
) -> str:
    if activity and activity in ACTIVITY_TYPES:
        return activity
    key = (once or daily or "").strip()
    if key.startswith("invite:"):
        return ""
    if key.startswith("tale:"):
        return "tale"
    if key.startswith("story:"):
        return "story"
    if key.startswith("lore:"):
        return "encounter"
    if key.startswith("visit:"):
        return "npc"
    if "eatery" in key or "dine" in key or "cook" in key:
        return "eatery"
    if cat == "people":
        return "npc"
    if cat == "story":
        return "story"
    if cat == "give":
        return "donate"
    if cat == "life":
        return "eatery"
    if cat == "labor":
        return "plot"
    return ""


async def note_activity(
    conn: aiosqlite.Connection,
    steward_id: int,
    activity_type: str,
    *,
    now: int | None = None,
) -> None:
    kind = (activity_type or "").strip()
    if not steward_id or kind not in ACTIVITY_TYPES:
        return
    await ensure_schema(conn)
    ts = db.now() if now is None else int(now)
    await conn.execute(
        """
        INSERT INTO invite_activity (steward_id, activity_type, first_at, count)
        VALUES (?,?,?,1)
        ON CONFLICT(steward_id, activity_type) DO UPDATE SET count = count + 1
        """,
        (steward_id, kind, ts),
    )


async def note_from_bond(
    conn: aiosqlite.Connection,
    steward_id: int,
    cat: str,
    *,
    once: str | None = None,
    daily: str | None = None,
    activity: str | None = None,
) -> None:
    if _SETTLING.get():
        return
    kind = activity_from_bond(cat, once, daily, activity)
    if not kind:
        return
    await note_activity(conn, steward_id, kind)


async def activity_snapshot(
    conn: aiosqlite.Connection, steward_id: int
) -> dict[str, Any]:
    await ensure_schema(conn)
    rows = await (await conn.execute(
        "SELECT activity_type, count FROM invite_activity WHERE steward_id=?",
        (steward_id,),
    )).fetchall()
    counts = {str(r[0]): int(r[1] or 0) for r in rows}
    total = sum(counts.values())
    types = [k for k, n in counts.items() if n > 0]
    ratio = 0.0
    top = ""
    if total > 0:
        top, n = max(counts.items(), key=lambda kv: kv[1])
        ratio = n / total
    dominated = bool(
        total > 0 and ratio >= float(config.INVITE_MAX_SINGLE_TYPE_RATIO)
    )
    return {
        "counts": counts,
        "types": types,
        "type_count": len(types),
        "total": total,
        "top": top,
        "ratio": ratio,
        "dominated": dominated,
    }


def active_days(created_at: int, *, now: int | None = None) -> int:
    ts = db.now() if now is None else int(now)
    return max(1, db.day_id(ts) - db.day_id(int(created_at or ts)) + 1)


async def device_account_count(conn: aiosqlite.Connection, key_id: int) -> int:
    row = await (await conn.execute(
        """
        SELECT COUNT(DISTINCT d2.key_id)
        FROM invite_devices d1
        JOIN invite_devices d2 ON d2.device_id = d1.device_id
        WHERE d1.key_id=?
        """,
        (key_id,),
    )).fetchone()
    return int(row[0] or 0) if row else 0


async def _key_ids_for_steward(conn: aiosqlite.Connection, steward_id: int) -> list[int]:
    row = await (await conn.execute(
        "SELECT key_id FROM stewards WHERE id=?", (steward_id,)
    )).fetchone()
    return [int(row[0])] if row and row[0] else []


async def risk_score(
    conn: aiosqlite.Connection,
    invitee: dict[str, Any],
    inviter: dict[str, Any],
    *,
    now: int | None = None,
) -> tuple[int, list[str]]:
    """返回 (分数, 命中规则内部名)。不要把这个结构发给玩家前端。"""
    await ensure_schema(conn)
    ts = db.now() if now is None else int(now)
    weights = config.INVITE_RISK_WEIGHTS
    hits: list[str] = []
    score = 0
    invitee_key = int(invitee.get("key_id") or 0)
    inviter_key = int(inviter.get("key_id") or 0)

    shared_device = await (await conn.execute(
        """
        SELECT 1 FROM invite_devices a
        JOIN invite_devices b ON a.device_id=b.device_id
        WHERE a.key_id=? AND b.key_id=?
        LIMIT 1
        """,
        (invitee_key, inviter_key),
    )).fetchone()
    if shared_device:
        hits.append("same_device")
        score += int(weights.get("same_device") or 0)

    burst_cut = ts - int(config.INVITE_DEVICE_BURST_WINDOW)
    row = await (await conn.execute(
        """
        SELECT COUNT(DISTINCT d2.key_id)
        FROM invite_devices d1
        JOIN invite_devices d2 ON d2.device_id=d1.device_id
        JOIN api_keys k ON k.id=d2.key_id
        WHERE d1.key_id=? AND k.created_at>=?
        """,
        (invitee_key, burst_cut),
    )).fetchone()
    if int(row[0] or 0) >= int(config.INVITE_DEVICE_BURST_COUNT):
        hits.append("device_burst")
        score += int(weights.get("device_burst") or 0)

    ip_cut = ts - int(config.INVITE_IP_BURST_WINDOW)
    row = await (await conn.execute(
        """
        SELECT COUNT(DISTINCT i2.key_id)
        FROM invite_ip_log i1
        JOIN invite_ip_log i2 ON i2.ip_hash=i1.ip_hash
        JOIN api_keys k ON k.id=i2.key_id
        JOIN stewards s ON s.key_id=i2.key_id
        WHERE i1.key_id=? AND k.created_at>=? AND COALESCE(s.invited_by,0)>0
        """,
        (invitee_key, ip_cut),
    )).fetchone()
    if int(row[0] or 0) >= int(config.INVITE_IP_BURST_COUNT):
        hits.append("ip_burst")
        score += int(weights.get("ip_burst") or 0)

    overlap_cut = ts - int(config.INVITE_IP_OVERLAP_DAYS) * config.FORAGE_COOLDOWN_DAY
    row = await (await conn.execute(
        """
        SELECT COUNT(*) FROM invite_ip_log a
        JOIN invite_ip_log b ON a.ip_hash=b.ip_hash
        WHERE a.key_id=? AND b.key_id=?
          AND a.last_seen_at>=? AND b.last_seen_at>=?
        """,
        (invitee_key, inviter_key, overlap_cut, overlap_cut),
    )).fetchone()
    if int(row[0] or 0) >= 1:
        hits.append("ip_overlap")
        score += int(weights.get("ip_overlap") or 0)

    snap = await activity_snapshot(conn, int(invitee["id"]))
    if snap["total"] >= 6 and snap["dominated"]:
        hits.append("behavior_anomaly")
        score += int(weights.get("behavior_anomaly") or 0)

    inv_cut = ts - int(config.INVITE_INVITER_BURST_WINDOW)
    row = await (await conn.execute(
        """
        SELECT COUNT(*) FROM stewards
        WHERE invited_by=? AND invite_bound_at>=?
        """,
        (int(inviter["id"]), inv_cut),
    )).fetchone()
    if int(row[0] or 0) >= int(config.INVITE_INVITER_BURST_COUNT):
        hits.append("inviter_burst")
        score += int(weights.get("inviter_burst") or 0)

    hops_row = await (await conn.execute(
        "SELECT MAX(hops) FROM invite_ip_log WHERE key_id=?",
        (invitee_key,),
    )).fetchone()
    hops = int(hops_row[0] or 1) if hops_row else 1
    devices_on_ip = await (await conn.execute(
        """
        SELECT COUNT(DISTINCT d.device_id)
        FROM invite_ip_log i
        JOIN invite_devices d ON d.key_id=i.key_id
        WHERE i.ip_hash IN (SELECT ip_hash FROM invite_ip_log WHERE key_id=?)
        """,
        (invitee_key,),
    )).fetchone()
    many_devices = int(devices_on_ip[0] or 0) if devices_on_ip else 0
    if hops >= int(config.INVITE_PROXY_HOPS) or many_devices >= int(
        config.INVITE_PROXY_DEVICES_ON_IP
    ):
        hits.append("proxy_hint")
        score += int(weights.get("proxy_hint") or 0)

    return score, hits


def qualifies(invitee: dict[str, Any], snap: dict[str, Any], *, now: int | None = None) -> bool:
    days = active_days(int(invitee.get("created_at") or 0), now=now)
    bond = int(invitee.get("island_bond") or 0)
    if days < int(config.INVITE_VALID_DAYS):
        return False
    if bond < int(config.INVITE_VALID_ISLAND_BOND):
        return False
    if int(snap.get("type_count") or 0) < int(config.INVITE_MIN_ACTIVITY_TYPES):
        return False
    if snap.get("dominated"):
        return False
    return True


async def _granted_tiers(conn: aiosqlite.Connection, invitee_id: int) -> set[str]:
    rows = await (await conn.execute(
        "SELECT tier FROM invite_rewards WHERE invitee_id=?", (invitee_id,)
    )).fetchall()
    return {str(r[0]) for r in rows}


async def _claim_tier(conn: aiosqlite.Connection, invitee_id: int, tier: str) -> bool:
    """数据库层幂等。插入成功才允许发奖。"""
    ts = db.now()
    try:
        await conn.execute(
            "INSERT INTO invite_rewards (invitee_id, tier, granted_at) VALUES (?,?,?)",
            (invitee_id, tier, ts),
        )
    except aiosqlite.IntegrityError:
        return False
    return True


async def _give_keepsake(conn: aiosqlite.Connection, steward_id: int, item_key: str) -> None:
    ts = db.now()
    await conn.execute(
        """
        INSERT OR IGNORE INTO invite_keepsakes (steward_id, item_key, granted_at)
        VALUES (?,?,?)
        """,
        (steward_id, item_key, ts),
    )


async def _grant_bond(
    conn: aiosqlite.Connection, steward_id: int, amount: int, once: str
) -> None:
    from . import bond as bond_mod

    n = int(amount or 0)
    if n <= 0:
        return
    await bond_mod.grant(conn, steward_id, n, "give", once=once)


async def _grant_tickets(conn: aiosqlite.Connection, steward_id: int, amount: int) -> None:
    n = int(amount or 0)
    if n <= 0:
        return
    await conn.execute(
        "UPDATE stewards SET tickets=tickets+? WHERE id=?",
        (n, steward_id),
    )


async def _grant_title(conn: aiosqlite.Connection, steward_id: int, key: str) -> None:
    from . import progress as progress_mod

    conn.row_factory = aiosqlite.Row
    fresh = await (await conn.execute(
        "SELECT * FROM stewards WHERE id=?", (steward_id,)
    )).fetchone()
    if not fresh:
        return
    await progress_mod.grant_title(conn, dict(fresh), key)


async def settle_rewards(
    conn: aiosqlite.Connection,
    invitee: dict[str, Any],
    inviter: dict[str, Any],
    status: str,
) -> list[str]:
    """按档发奖。中/高风险不结算；已发过的档不会再发。"""
    if status in (STATUS_RISK_REVIEW, STATUS_INVALID):
        return []
    if _SETTLING.get():
        return []
    token = _SETTLING.set(True)
    granted: list[str] = []
    try:
        await ensure_schema(conn)
        bond = int(invitee.get("island_bond") or 0)
        invitee_id = int(invitee["id"])
        inviter_id = int(inviter["id"])

        if bond >= int(config.INVITE_TIER_MEMENTO_BOND):
            if await _claim_tier(conn, invitee_id, TIER_MEMENTO):
                await _give_keepsake(conn, invitee_id, "landing_note")
                await _give_keepsake(conn, inviter_id, "guide_wick")
                await _grant_bond(
                    conn, inviter_id, config.INVITE_REWARD_MEMENTO_BOND,
                    f"invite:{TIER_MEMENTO}:{invitee_id}:inviter",
                )
                granted.append(TIER_MEMENTO)

        ready_official = status in (STATUS_QUALIFIED, STATUS_REWARDED)
        if ready_official:
            if await _claim_tier(conn, invitee_id, TIER_QUALIFIED):
                await _give_keepsake(conn, inviter_id, "shore_lamp")
                await conn.execute(
                    "UPDATE stewards SET invite_lantern=1 WHERE id=?", (inviter_id,)
                )
                await _grant_tickets(
                    conn, inviter_id, config.INVITE_REWARD_QUALIFIED_TICKETS,
                )
                await _grant_bond(
                    conn, inviter_id, config.INVITE_REWARD_QUALIFIED_BOND,
                    f"invite:{TIER_QUALIFIED}:{invitee_id}:inviter",
                )
                await _grant_bond(
                    conn, invitee_id, config.INVITE_REWARD_QUALIFIED_INVITEE_BOND,
                    f"invite:{TIER_QUALIFIED}:{invitee_id}:invitee",
                )
                await _grant_title(conn, inviter_id, "navigator")
                await _grant_title(conn, invitee_id, "same_tide")
                granted.append(TIER_QUALIFIED)

        if ready_official and bond >= int(config.INVITE_TIER_FINAL_BOND):
            if await _claim_tier(conn, invitee_id, TIER_FINAL):
                await _give_keepsake(conn, inviter_id, "twin_tide")
                await _give_keepsake(conn, invitee_id, "deep_shell")
                await _grant_bond(
                    conn, inviter_id, config.INVITE_REWARD_FINAL_BOND,
                    f"invite:{TIER_FINAL}:{invitee_id}:inviter",
                )
                granted.append(TIER_FINAL)
    finally:
        _SETTLING.reset(token)
    return granted


async def _upsert_risk_log(
    conn: aiosqlite.Connection,
    invitee: dict[str, Any],
    inviter: dict[str, Any],
    *,
    score: int,
    hits: list[str],
    status: str,
    snap: dict[str, Any],
    device_accounts: int,
    note: str = "",
) -> None:
    tiers = sorted(await _granted_tiers(conn, int(invitee["id"])))
    existing_note = ""
    if note == "":
        old = await (await conn.execute(
            "SELECT note FROM invite_risk_log WHERE invitee_id=?",
            (int(invitee["id"]),),
        )).fetchone()
        existing_note = str(old[0] or "") if old else ""
    else:
        existing_note = note
    await conn.execute(
        """
        INSERT INTO invite_risk_log (
            invitee_id, inviter_id, bound_at, island_bond, active_days,
            activity_types, device_account_count, risk_score, hit_rules,
            invite_status, rewards_json, note, cleared_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,?)
        ON CONFLICT(invitee_id) DO UPDATE SET
            inviter_id=excluded.inviter_id,
            bound_at=excluded.bound_at,
            island_bond=excluded.island_bond,
            active_days=excluded.active_days,
            activity_types=excluded.activity_types,
            device_account_count=excluded.device_account_count,
            risk_score=excluded.risk_score,
            hit_rules=excluded.hit_rules,
            invite_status=excluded.invite_status,
            rewards_json=excluded.rewards_json,
            note=excluded.note,
            updated_at=excluded.updated_at
        """,
        (
            int(invitee["id"]),
            int(inviter["id"]),
            int(invitee.get("invite_bound_at") or 0),
            int(invitee.get("island_bond") or 0),
            active_days(int(invitee.get("created_at") or 0)),
            int(snap.get("type_count") or 0),
            int(device_accounts),
            int(score),
            json.dumps(hits, ensure_ascii=False),
            status,
            json.dumps(tiers, ensure_ascii=False),
            existing_note,
            db.now(),
        ),
    )


async def evaluate_and_settle(
    conn: aiosqlite.Connection,
    steward_id: int,
    *,
    force: bool = False,
    now: int | None = None,
) -> dict[str, Any] | None:
    if not steward_id or _SETTLING.get():
        return None
    await ensure_schema(conn)
    conn.row_factory = aiosqlite.Row
    invitee_row = await (await conn.execute(
        "SELECT * FROM stewards WHERE id=?", (steward_id,)
    )).fetchone()
    if not invitee_row:
        return None
    invitee = dict(invitee_row)
    inviter_id = int(invitee.get("invited_by") or 0)
    if not inviter_id:
        return None
    inviter_row = await (await conn.execute(
        "SELECT * FROM stewards WHERE id=?", (inviter_id,)
    )).fetchone()
    if not inviter_row:
        return None
    inviter = dict(inviter_row)
    current = (invitee.get("invite_status") or STATUS_PENDING).strip() or STATUS_PENDING
    snap = await activity_snapshot(conn, steward_id)
    score, hits = await risk_score(conn, invitee, inviter, now=now)
    band = risk_band(score)
    ok = qualifies(invitee, snap, now=now)
    cleared_row = await (await conn.execute(
        "SELECT COALESCE(cleared_at,0) FROM invite_risk_log WHERE invitee_id=?",
        (steward_id,),
    )).fetchone()
    manually_cleared = bool(cleared_row and int(cleared_row[0] or 0) > 0)
    next_status = current
    if current != STATUS_REWARDED:
        if band == "high" and not force and not manually_cleared:
            next_status = STATUS_INVALID
        elif band == "mid" and not force and not manually_cleared:
            next_status = STATUS_RISK_REVIEW
        elif ok:
            next_status = STATUS_QUALIFIED
        else:
            next_status = STATUS_PENDING
    device_accounts = await device_account_count(conn, int(invitee.get("key_id") or 0))
    await _upsert_risk_log(
        conn, invitee, inviter, score=score, hits=hits, status=next_status,
        snap=snap, device_accounts=device_accounts,
    )
    granted = await settle_rewards(conn, invitee, inviter, next_status)
    if next_status == STATUS_QUALIFIED:
        tiers = set(granted) | await _granted_tiers(conn, steward_id)
        if TIER_QUALIFIED in tiers:
            next_status = STATUS_REWARDED
    if next_status != current:
        await conn.execute(
            "UPDATE stewards SET invite_status=? WHERE id=?",
            (next_status, steward_id),
        )
        invitee["invite_status"] = next_status
    else:
        await conn.execute(
            "UPDATE stewards SET invite_status=? WHERE id=? AND COALESCE(invite_status,'')=''",
            (next_status, steward_id),
        )
    await conn.execute(
        "UPDATE invite_risk_log SET invite_status=?, rewards_json=? WHERE invitee_id=?",
        (
            next_status,
            json.dumps(sorted(await _granted_tiers(conn, steward_id)), ensure_ascii=False),
            steward_id,
        ),
    )
    return {
        "status": next_status,
        "score": score,
        "hits": hits,
        "granted": granted,
        "qualified": ok,
        "band": band,
    }


async def bind_invite(
    conn: aiosqlite.Connection,
    invitee: dict[str, Any],
    code: str,
    *,
    now: int | None = None,
) -> dict[str, Any]:
    await ensure_schema(conn)
    if int(invitee.get("invited_by") or 0):
        raise ValueError("引航关系已经结过，不能改绑别人。")
    inviter = await lookup_inviter(conn, code)
    if not inviter:
        raise ValueError("邀请码无效，或邀请人还没上岛。")
    if int(inviter["id"]) == int(invitee["id"]):
        raise ValueError("不能自己引自己。")
    if int(inviter.get("key_id") or 0) == int(invitee.get("key_id") or 0):
        raise ValueError("不能自己引自己。")
    ts = db.now() if now is None else int(now)
    cur = await conn.execute(
        """
        UPDATE stewards
        SET invited_by=?, invite_bound_at=?, invite_status=?
        WHERE id=? AND COALESCE(invited_by,0)=0
        """,
        (int(inviter["id"]), ts, STATUS_PENDING, int(invitee["id"])),
    )
    if cur.rowcount != 1:
        raise ValueError("引航关系已经结过，不能改绑别人。")
    invitee["invited_by"] = int(inviter["id"])
    invitee["invite_bound_at"] = ts
    invitee["invite_status"] = STATUS_PENDING
    await _upsert_risk_log(
        conn, invitee, inviter, score=0, hits=[], status=STATUS_PENDING,
        snap=await activity_snapshot(conn, int(invitee["id"])),
        device_accounts=await device_account_count(conn, int(invitee.get("key_id") or 0)),
    )
    await evaluate_and_settle(conn, int(invitee["id"]), now=now)
    return inviter


async def bind_from_pending(conn: aiosqlite.Connection, invitee: dict[str, Any]) -> None:
    key_id = int(invitee.get("key_id") or 0)
    if not key_id:
        return
    row = await (await conn.execute(
        "SELECT pending_invite_code FROM api_keys WHERE id=?", (key_id,)
    )).fetchone()
    code = (row[0] if row else "") or ""
    if not normalize_code(code):
        return
    try:
        await bind_invite(conn, invitee, code)
    except ValueError:
        return


async def keepsakes_of(conn: aiosqlite.Connection, steward_id: int) -> list[dict[str, str]]:
    await ensure_schema(conn)
    rows = await (await conn.execute(
        "SELECT item_key FROM invite_keepsakes WHERE steward_id=? ORDER BY granted_at",
        (steward_id,),
    )).fetchall()
    out = []
    for (key,) in rows:
        meta = KEEPSAKES.get(str(key)) or {"name": str(key), "emoji": "◌"}
        out.append({"key": str(key), "name": meta["name"], "emoji": meta.get("emoji", "◌")})
    return out


def invite_link(code: str, base: str = "") -> str:
    origin = (base or "").rstrip("/")
    path = f"/register?invite={code}"
    return f"{origin}{path}" if origin else path


async def player_view(
    steward: dict[str, Any],
    *,
    base: str = "",
    conn: aiosqlite.Connection | None = None,
) -> dict[str, Any]:
    """给网页 / MCP 的公开结果。不含风险分、权重、阈值。"""
    owned = conn is None
    if owned:
        ctx = db.connect()
        conn = await ctx.__aenter__()
    assert conn is not None
    try:
        await ensure_schema(conn)
        conn.row_factory = aiosqlite.Row
        sid = int(steward["id"])
        await assign_invite_code(conn, sid)
        await evaluate_and_settle(conn, sid)
        fresh = await (await conn.execute(
            "SELECT * FROM stewards WHERE id=?", (sid,)
        )).fetchone()
        s = dict(fresh) if fresh else dict(steward)
        code = str(s.get("invite_code") or "")
        invited_by = int(s.get("invited_by") or 0)
        host = None
        if invited_by:
            row = await (await conn.execute(
                "SELECT id, name FROM stewards WHERE id=?", (invited_by,)
            )).fetchone()
            if row:
                host = {"id": int(row["id"]), "name": row["name"]}
        guests = []
        rows = await (await conn.execute(
            """
            SELECT id, name, invite_status, invite_bound_at, COALESCE(island_bond,0)
            FROM stewards WHERE invited_by=? ORDER BY invite_bound_at DESC
            """,
            (sid,),
        )).fetchall()
        guest_ids = [int(r["id"]) for r in rows]
        reward_map: dict[int, set[str]] = {gid: set() for gid in guest_ids}
        if guest_ids:
            q = ",".join("?" * len(guest_ids))
            for r in await (await conn.execute(
                f"SELECT invitee_id, tier FROM invite_rewards WHERE invitee_id IN ({q})",
                guest_ids,
            )).fetchall():
                reward_map.setdefault(int(r[0]), set()).add(str(r[1]))
        counted = 0
        for r in rows:
            st = str(r["invite_status"] or STATUS_PENDING)
            if st in (STATUS_QUALIFIED, STATUS_REWARDED):
                counted += 1
            guests.append({
                "name": r["name"],
                "status": public_status(st),
                "status_key": st if st in (
                    STATUS_PENDING, STATUS_QUALIFIED, STATUS_RISK_REVIEW,
                    STATUS_REWARDED, STATUS_INVALID,
                ) else STATUS_PENDING,
                "bound_at": int(r["invite_bound_at"] or 0),
                "rewards": sorted(reward_map.get(int(r["id"]), set())),
            })
        mine_status = str(s.get("invite_status") or "")
        keeps = await keepsakes_of(conn, sid)
        if owned:
            await conn.commit()
        return {
            "code": code,
            "link": invite_link(code, base),
            "bound": bool(invited_by),
            "can_bind": not invited_by,
            "inviter": host,
            "my_status": public_status(mine_status) if invited_by else "",
            "my_status_key": mine_status if invited_by else "",
            "invited": guests,
            "valid_count": counted,
            "keepsakes": keeps,
            "lantern": bool(s.get("invite_lantern")),
            "official_reward_tickets": int(config.INVITE_REWARD_QUALIFIED_TICKETS),
            "official_reward_bond": int(config.INVITE_REWARD_QUALIFIED_BOND),
        }
    finally:
        if owned:
            await ctx.__aexit__(None, None, None)


async def player_text(steward: dict[str, Any], *, base: str = "") -> str:
    view = await player_view(steward, base=base)
    lines = [
        "引航",
        f"你的邀请码：{view['code']}",
        f"邀请链接：{view['link']}",
        "把码或链接给新岛民。登记或首次绑定后关系就定了，不能改绑。",
        "自己不能引自己。注册当时不算有效邀请；对方真正在岛上过日子才会致谢。",
        f"正式谢礼：邀请人 {config.INVITE_REWARD_QUALIFIED_TICKETS} 工分票 + {config.INVITE_REWARD_QUALIFIED_BOND} 岛缘（达标后自动入账）。还有称呼和收藏，不要发明领邀请奖。",
    ]
    if view["bound"] and view.get("inviter"):
        lines.append(
            f"你由「{view['inviter']['name']}」引来 · {view['my_status'] or '已绑定'}"
        )
    elif view["can_bind"]:
        lines.append("还没绑过引航人。steward_ops 绑定 邀请码 只能用一次。")
    lines.append(f"你引来的岛民 {len(view['invited'])} 人，其中计入有效 {view['valid_count']} 人。")
    if view["invited"]:
        for g in view["invited"][:20]:
            extra = "、".join(TIER_LABEL.get(x, x) for x in g["rewards"]) if g["rewards"] else "尚未致谢"
            lines.append(f"  · {g['name']} · {g['status']} · {extra}")
    if view["keepsakes"]:
        bits = "、".join(f"{k['emoji']}{k['name']}" for k in view["keepsakes"])
        lines.append(f"引航收藏：{bits}（不占行囊，不能卖不能送）")
    if view["lantern"]:
        lines.append("岸灯已在小屋亮着。")
    lines.extend([
        "",
        "例子：steward_ops 引航 · steward_ops 绑定 AB12CD34 · steward_ops invite",
        "容易搞混：引航是请人上岛；alliance_ops assist 是帮邻居打理；tote_ops gift 是送礼。",
        "空 command 的 sheet 也会写一行引航码。不要发明 invite_ops / 领邀请奖。",
    ])
    return "\n".join(lines)


def sheet_line(steward: dict[str, Any]) -> str | None:
    code = (steward.get("invite_code") or "").strip()
    if not code:
        return None
    if int(steward.get("invited_by") or 0):
        label = public_status(str(steward.get("invite_status") or STATUS_PENDING))
        return f"引航码 {code} · 已被引来（{label}）· steward_ops 引航"
    return f"引航码 {code} · steward_ops 引航 看邀请与绑定"


async def admin_rows() -> list[dict[str, Any]]:
    async with db.connect() as conn:
        await ensure_schema(conn)
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """
            SELECT
                l.invitee_id, l.inviter_id, l.bound_at, l.island_bond,
                l.active_days, l.activity_types, l.device_account_count,
                l.risk_score, l.hit_rules, l.invite_status, l.rewards_json,
                l.note, l.cleared_at, l.updated_at,
                a.name AS invitee_name, b.name AS inviter_name
            FROM invite_risk_log l
            JOIN stewards a ON a.id=l.invitee_id
            JOIN stewards b ON b.id=l.inviter_id
            ORDER BY l.updated_at DESC
            LIMIT 300
            """
        )).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["hit_rules"] = json.loads(item.get("hit_rules") or "[]")
            except json.JSONDecodeError:
                item["hit_rules"] = []
            try:
                item["rewards"] = json.loads(item.get("rewards_json") or "[]")
            except json.JSONDecodeError:
                item["rewards"] = []
            item["risk_band"] = risk_band(int(item.get("risk_score") or 0))
            out.append(item)
        return out


async def admin_clear(invitee_id: int, note: str = "") -> str:
    async with db.connect() as conn:
        await ensure_schema(conn)
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM stewards WHERE id=?", (int(invitee_id),)
        )).fetchone()
        if not row or not int(row["invited_by"] or 0):
            raise ValueError("没有这条引航关系")
        await conn.execute(
            """
            UPDATE stewards SET invite_status=? WHERE id=?
            """,
            (STATUS_PENDING, int(invitee_id)),
        )
        await conn.execute(
            """
            UPDATE invite_risk_log
            SET invite_status=?, cleared_at=?, note=?, updated_at=?
            WHERE invitee_id=?
            """,
            (STATUS_PENDING, db.now(), (note or "人工解除风险").strip()[:200], db.now(), int(invitee_id)),
        )
        result = await evaluate_and_settle(conn, int(invitee_id), force=True)
        await conn.commit()
    st = (result or {}).get("status") or STATUS_PENDING
    return f"已解除风险并重算：现在状态 {st}"


async def invite_ops(key_id: int, command: str = "", *, base: str = "") -> str:
    from . import game

    s = await game.require_steward(key_id, exempt_duty=True)
    verb, rest = _head(command)
    if verb in ("绑定", "bind", "结引"):
        code = normalize_code(rest)
        if not code:
            raise ValueError("用法：steward_ops 绑定 邀请码")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            fresh = await (await conn.execute(
                "SELECT * FROM stewards WHERE id=?", (s["id"],)
            )).fetchone()
            inviter = await bind_invite(conn, dict(fresh) if fresh else s, code)
            await conn.commit()
        return (
            f"引航关系已结：你由「{inviter['name']}」引来。"
            "关系永久，不能改绑。对方真正在岛上过日子后才会致谢。"
        )
    return await player_text(s, base=base)


def _head(command: str) -> tuple[str, str]:
    parts = (command or "").strip().split(None, 1)
    if not parts:
        return "", ""
    return parts[0], parts[1] if len(parts) > 1 else ""

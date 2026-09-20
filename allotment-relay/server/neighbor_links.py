"""玩家连接 — §五十七：借船、托养、菜篮订阅。"""
from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import db
from .catalog import ITEM_NAMES
from .game import require_steward

RAPPORT_FOSTER = 40
RAPPORT_BASKET = 30
RAPPORT_BOAT = 60
FOSTER_DAYS = 7
BASKET_DAYS = 7
BASKET_FEE = 25
BOAT_LOAN_SEC = 3 * 86400
LOAN_REMINDER_SEC = 86400

BASKET_POOL = (
    "egg", "duck_egg", "crop_kale", "crop_beet", "crop_fogpea",
    "fish_herring", "fish_sardine", "pickles", "compost",
)


async def ensure_tables(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS neighbor_boat_loan (
            borrower_id INTEGER NOT NULL PRIMARY KEY,
            lender_id INTEGER NOT NULL,
            boat_key TEXT NOT NULL,
            until_ts INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS neighbor_basket_offer (
            steward_id INTEGER NOT NULL PRIMARY KEY,
            active INTEGER NOT NULL DEFAULT 1,
            updated_at INTEGER NOT NULL
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS neighbor_basket_sub (
            buyer_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            until_day INTEGER NOT NULL,
            last_claim_day INTEGER NOT NULL DEFAULT 0,
            paid_tickets INTEGER NOT NULL,
            PRIMARY KEY (buyer_id, seller_id)
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS neighbor_loan_reminder (
            loan_key TEXT PRIMARY KEY,
            steward_id INTEGER NOT NULL,
            ping_day INTEGER NOT NULL
        )
        """
    )
    try:
        await conn.execute(
            "ALTER TABLE barn_animals ADD COLUMN real_owner_id INTEGER NOT NULL DEFAULT 0"
        )
    except Exception:
        pass


async def _rapport(conn, a: int, b: int) -> int:
    from . import social as social_mod
    return await social_mod.get_rapport(a, b, conn=conn)


async def _peer(name: str) -> dict[str, Any]:
    p = await db.get_steward_by_name(name)
    if not p:
        raise ValueError("找不到该岛民")
    return p


# ── 借船 ─────────────────────────────────────────────


async def boat_loan_give(conn, lender: dict, borrower_name: str) -> str:
    await ensure_tables(conn)
    if not lender.get("boat_key"):
        raise ValueError("你还没有船，无法借出")
    borrower = await _peer(borrower_name)
    if borrower["id"] == lender["id"]:
        raise ValueError("不能借给自己")
    r = await _rapport(conn, lender["id"], borrower["id"])
    if r < RAPPORT_BOAT:
        raise ValueError(f"借船需要协作度 ≥{RAPPORT_BOAT}（当前 {r}）")
    cur = await conn.execute(
        "SELECT lender_id FROM neighbor_boat_loan WHERE borrower_id=?",
        (borrower["id"],),
    )
    if await cur.fetchone():
        raise ValueError(f"{borrower['name']} 已在借别人的船，先等到期")
    until = db.now() + BOAT_LOAN_SEC
    await conn.execute(
        """
        INSERT OR REPLACE INTO neighbor_boat_loan
        (borrower_id, lender_id, boat_key, until_ts, created_at)
        VALUES (?,?,?,?,?)
        """,
        (borrower["id"], lender["id"], lender["boat_key"], until, db.now()),
    )
    await db.add_chronicle(
        "sea",
        f"{lender['name']} 把 {lender['boat_key']} 借给 {borrower['name']}（3 日）",
        lender["id"],
        conn=conn,
    )
    return (
        f"已借出船给 {borrower['name']}，约 3 日内可用。"
        f"对方出海磨损算在你账上（部件/船体）。"
    )


async def boat_loan_status(conn, steward_id: int) -> str | None:
    await ensure_tables(conn)
    cur = await conn.execute(
        """
        SELECT l.lender_id, l.boat_key, l.until_ts, s.name
        FROM neighbor_boat_loan l JOIN stewards s ON s.id=l.lender_id
        WHERE l.borrower_id=?
        """,
        (steward_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    if db.now() >= int(row[2]):
        await conn.execute(
            "DELETE FROM neighbor_boat_loan WHERE borrower_id=?", (steward_id,)
        )
        return None
    left = int(row[2]) - db.now()
    extra = ""
    if left <= LOAN_REMINDER_SEC:
        extra = f" · 约 {max(1, left // 3600)} 小时内到期"
    return f"借船中：{row[3]} 的 {row[1]}（到期 {db.fmt_cst(row[2])}{extra}）"


async def _reminder_ping(conn, loan_key: str, steward_id: int) -> bool:
    day = db.day_id()
    cur = await conn.execute(
        """
        INSERT OR IGNORE INTO neighbor_loan_reminder (loan_key, steward_id, ping_day)
        VALUES (?,?,?)
        """,
        (loan_key, steward_id, day),
    )
    return cur.rowcount > 0


async def loan_reminder_notices(conn, steward_id: int, *, ping: bool = True) -> list[str]:
    """借船临期提醒：sheet 每次可见；站内纪事（loan_reminder）每日每笔最多一条。"""
    await ensure_tables(conn)
    now = db.now()
    out: list[str] = []
    cur = await conn.execute(
        """
        SELECT lender_id, boat_key, until_ts FROM neighbor_boat_loan WHERE borrower_id=?
        """,
        (steward_id,),
    )
    row = await cur.fetchone()
    if row and int(row[2]) > now:
        left = int(row[2]) - now
        if left <= LOAN_REMINDER_SEC:
            lender = await db.get_steward_by_id(int(row[0]))
            lname = lender["name"] if lender else "?"
            hrs = max(1, left // 3600)
            line = (
                f"借船提醒：{lname} 的 {row[1]} 约 {hrs} 小时内到期"
                " → tide_ops voyage return · alliance_ops 借船 状态"
            )
            out.append(line)
            if ping:
                key = f"br:{steward_id}:{row[2]}"
                if await _reminder_ping(conn, key, steward_id):
                    await db.add_chronicle(
                        "loan_reminder", line, steward_id, int(row[0]), conn=conn,
                    )
    cur = await conn.execute(
        """
        SELECT borrower_id, boat_key, until_ts FROM neighbor_boat_loan
        WHERE lender_id=? AND until_ts>?
        """,
        (steward_id, now),
    )
    for bid, bk, until in await cur.fetchall():
        left = int(until) - now
        if left > LOAN_REMINDER_SEC:
            continue
        borrower = await db.get_steward_by_id(int(bid))
        bname = borrower["name"] if borrower else "?"
        hrs = max(1, left // 3600)
        line = (
            f"借出提醒：{bname} 仍借你的 {bk}，约 {hrs} 小时内到期"
            "（磨损仍记你账）"
        )
        out.append(line)
        if ping:
            key = f"ln:{steward_id}:{bid}:{until}"
            if await _reminder_ping(conn, key, steward_id):
                await db.add_chronicle(
                    "loan_reminder", line, steward_id, int(bid), conn=conn,
                )
    return out


async def boat_loan_status_report(conn, steward_id: int) -> str:
    """借船 状态：在借 / 借出 + 临期行。"""
    lines: list[str] = []
    br = await boat_loan_status(conn, steward_id)
    if br:
        lines.append(br)
    now = db.now()
    cur = await conn.execute(
        """
        SELECT b.name, l.boat_key, l.until_ts FROM neighbor_boat_loan l
        JOIN stewards b ON b.id=l.borrower_id
        WHERE l.lender_id=? AND l.until_ts>?
        """,
        (steward_id, now),
    )
    for bname, bk, until in await cur.fetchall():
        left = int(until) - now
        extra = ""
        if left <= LOAN_REMINDER_SEC:
            extra = f" · 约 {max(1, left // 3600)} 小时内到期"
        lines.append(f"借出中：{bname} 用 {bk}（到期 {db.fmt_cst(until)}{extra}）")
    if not lines:
        return "当前没有在借的船，也没有借出中的船。"
    for note in await loan_reminder_notices(conn, steward_id, ping=False):
        if note not in lines:
            lines.append(note)
    return "\n".join(lines)


async def effective_boat_key(conn, steward: dict) -> str | None:
    """自有船、合伙大船（档位不低于自有）、借来的船。"""
    from . import neighbor_boat_share as share_mod
    from .config import BOATS

    personal = steward.get("boat_key") or ""
    share = await share_mod.share_boat_key(conn, steward["id"])
    pers_rank = int((BOATS.get(personal) or {}).get("rank") or 0) if personal else 0
    share_rank = int((BOATS.get(share) or {}).get("rank") or 0) if share else 0
    if share and share_rank >= pers_rank:
        return share
    if personal:
        return personal
    await ensure_tables(conn)
    cur = await conn.execute(
        "SELECT boat_key, until_ts FROM neighbor_boat_loan WHERE borrower_id=?",
        (steward["id"],),
    )
    row = await cur.fetchone()
    if not row or db.now() >= int(row[1]):
        return None
    return row[0]


async def boat_loan_lender(conn, borrower_id: int) -> int | None:
    await ensure_tables(conn)
    cur = await conn.execute(
        "SELECT lender_id, until_ts FROM neighbor_boat_loan WHERE borrower_id=?",
        (borrower_id,),
    )
    row = await cur.fetchone()
    if not row or db.now() >= int(row[1]):
        return None
    return int(row[0])


async def boat_loan_after_voyage(conn, borrower_id: int, *, storm: bool) -> str | None:
    lender_id = await boat_loan_lender(conn, borrower_id)
    if not lender_id:
        return None
    from . import boat_parts as parts_mod
    from . import boat_hull as hull_mod

    await parts_mod.wear_voyage(conn, lender_id, "near", storm=storm)
    note = await hull_mod.wear_after_voyage(conn, lender_id, "near", storm=storm)
    if storm and random.random() < 0.25:
        await conn.execute(
            "UPDATE stewards SET boat_damaged=1 WHERE id=?", (lender_id,)
        )
        return f"借出的船在风浪里受了损（船主需 voyage repair）。{note}"
    return f"借出的船磨损记在船主身上。{note}" if note else "借出的船磨损记在船主身上。"


# ── 托养 ─────────────────────────────────────────────


async def _host_has_slot(conn, host_id: int) -> int | None:
    cur = await conn.execute(
        "SELECT slot FROM barn_animals WHERE steward_id=? AND (species IS NULL OR species='') ORDER BY slot LIMIT 1",
        (host_id,),
    )
    row = await cur.fetchone()
    if row:
        return int(row[0])
    cur = await conn.execute(
        "SELECT MAX(slot) FROM barn_animals WHERE steward_id=?", (host_id,)
    )
    mx = int((await cur.fetchone())[0] or 0)
    return mx + 1 if mx < 8 else None


async def foster_send(conn, owner: dict, host_name: str, slot: int) -> str:
    await ensure_tables(conn)
    host = await _peer(host_name)
    if host["id"] == owner["id"]:
        raise ValueError("不能托养给自己")
    r = await _rapport(conn, owner["id"], host["id"])
    if r < RAPPORT_FOSTER:
        raise ValueError(f"托养需要协作度 ≥{RAPPORT_FOSTER}（当前 {r}）")
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute(
        """
        SELECT * FROM barn_animals WHERE steward_id=? AND slot=? AND species IS NOT NULL AND species != ''
        """,
        (owner["id"], slot),
    )
    row = await cur.fetchone()
    if not row:
        raise ValueError(f"#{slot} 没有可托养的牲口")
    animal = dict(row)
    if int(animal.get("real_owner_id") or 0):
        raise ValueError("这栏已在托管中")
    host_slot = await _host_has_slot(conn, host["id"])
    if host_slot is None:
        raise ValueError(f"{host['name']} 畜栏已满")
    await conn.execute(
        "DELETE FROM barn_animals WHERE steward_id=? AND slot=?",
        (owner["id"], slot),
    )
    cols = [k for k in animal.keys() if k not in ("id", "steward_id", "slot")]
    animal["real_owner_id"] = owner["id"]
    animal["steward_id"] = host["id"]
    animal["slot"] = host_slot
    # rebuild insert
    keys = ["steward_id", "slot", "species", "stocked_at", "fed", "guard", "real_owner_id"]
    vals = [
        host["id"], host_slot, animal.get("species"), animal.get("stocked_at"),
        animal.get("fed"), animal.get("guard", 0), owner["id"],
    ]
    extra_cols = [
        "born_at", "ailment", "ailment_at", "pedigree_label", "temper",
        "escaped_at", "custom_name",
    ]
    for c in extra_cols:
        if c in animal:
            keys.append(c)
            vals.append(animal[c])
    placeholders = ",".join("?" * len(keys))
    await conn.execute(
        f"INSERT INTO barn_animals ({','.join(keys)}) VALUES ({placeholders})",
        vals,
    )
    await db.add_chronicle(
        "barn",
        f"{owner['name']} 把 #{slot} 托给 {host['name']}（#{host_slot}）",
        owner["id"],
        conn=conn,
    )
    return (
        f"已托养至 {host['name']} 畜栏 #{host_slot}，"
        f"接回：alliance_ops 托养 接回 {host['name']} {host_slot}"
    )


async def foster_reclaim(conn, owner: dict, host_name: str, host_slot: int) -> str:
    await ensure_tables(conn)
    host = await _peer(host_name)
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute(
        """
        SELECT * FROM barn_animals
        WHERE real_owner_id=? AND steward_id=? AND slot=?
        """,
        (owner["id"], host["id"], host_slot),
    )
    row = await cur.fetchone()
    if not row:
        raise ValueError(f"没有在 {host['name']} #{host_slot} 托管的牲口")
    animal = dict(row)
    host_id = animal["steward_id"]
    await conn.execute(
        "DELETE FROM barn_animals WHERE steward_id=? AND slot=?",
        (host_id, host_slot),
    )
    owner_slot = await _host_has_slot(conn, owner["id"]) or 1
    animal["real_owner_id"] = 0
    keys = ["steward_id", "slot", "species", "stocked_at", "fed", "guard", "real_owner_id"]
    vals = [
        owner["id"], owner_slot, animal.get("species"), animal.get("stocked_at"),
        animal.get("fed"), animal.get("guard", 0), 0,
    ]
    for c in ("born_at", "ailment", "temper", "custom_name", "pedigree_label"):
        if c in animal and animal[c]:
            keys.append(c)
            vals.append(animal[c])
    ph = ",".join("?" * len(keys))
    await conn.execute(
        f"INSERT INTO barn_animals ({','.join(keys)}) VALUES ({ph})",
        vals,
    )
    return f"已从邻居栏 #{host_slot} 接回，在你栏 #{owner_slot}。"


async def foster_list(conn, steward_id: int) -> str:
    await ensure_tables(conn)
    cur = await conn.execute(
        """
        SELECT slot, species, steward_id FROM barn_animals WHERE real_owner_id=?
        """,
        (steward_id,),
    )
    out = await cur.fetchall()
    if not out:
        return "没有在邻居处的托管牲口。"
    lines = ["托管中（接回：托养 接回 邻居名 栏位）："]
    for slot, species, hid in out:
        h = await db.get_steward_by_id(int(hid))
        nm = h["name"] if h else "?"
        lines.append(f"  {nm} #{slot} {species}")
    return "\n".join(lines)


# ── 菜篮 ─────────────────────────────────────────────


async def basket_open(conn, seller: dict) -> str:
    await ensure_tables(conn)
    await conn.execute(
        """
        INSERT OR REPLACE INTO neighbor_basket_offer (steward_id, active, updated_at)
        VALUES (?, 1, ?)
        """,
        (seller["id"], db.now()),
    )
    return "已开通菜篮供应（邻居可 alliance_ops 菜篮 订 你的名字 25）。"


async def basket_subscribe(conn, buyer: dict, seller_name: str) -> str:
    await ensure_tables(conn)
    seller = await _peer(seller_name)
    if seller["id"] == buyer["id"]:
        raise ValueError("不能订自己的菜篮")
    r = await _rapport(conn, buyer["id"], seller["id"])
    if r < RAPPORT_BASKET:
        raise ValueError(f"菜篮订阅需要协作度 ≥{RAPPORT_BASKET}（当前 {r}）")
    cur = await conn.execute(
        "SELECT active FROM neighbor_basket_offer WHERE steward_id=?",
        (seller["id"],),
    )
    row = await cur.fetchone()
    if not row or not int(row[0]):
        raise ValueError(f"{seller['name']} 还没开通菜篮（让对方 alliance_ops 菜篮 开）")
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (buyer["id"],))
    tickets = int((await cur.fetchone())[0])
    if tickets < BASKET_FEE:
        raise ValueError(f"订阅要 {BASKET_FEE} 票")
    until = db.day_id() + BASKET_DAYS
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (BASKET_FEE, buyer["id"]),
    )
    await conn.execute(
        """
        INSERT OR REPLACE INTO neighbor_basket_sub
        (buyer_id, seller_id, until_day, last_claim_day, paid_tickets)
        VALUES (?,?,?,0,?)
        """,
        (buyer["id"], seller["id"], until, BASKET_FEE),
    )
    await _bump_rapport(conn, buyer["id"], seller["id"], 2)
    await db.add_chronicle(
        "market",
        f"{buyer['name']} 订阅 {seller['name']} 菜篮 {BASKET_DAYS} 天",
        buyer["id"],
        conn=conn,
    )
    return f"已订阅 {seller['name']} 菜篮 {BASKET_DAYS} 天（-{BASKET_FEE} 票）。每日：菜篮 领"


async def basket_claim(conn, buyer: dict) -> str:
    await ensure_tables(conn)
    day = db.day_id()
    cur = await conn.execute(
        """
        SELECT seller_id, until_day, last_claim_day FROM neighbor_basket_sub
        WHERE buyer_id=? ORDER BY until_day DESC LIMIT 1
        """,
        (buyer["id"],),
    )
    row = await cur.fetchone()
    if not row:
        raise ValueError("没有有效菜篮订阅。alliance_ops 菜篮 订 邻居名")
    seller_id, until, last = int(row[0]), int(row[1]), int(row[2])
    if day > until:
        raise ValueError("订阅已过期，重新 菜篮 订")
    if last >= day:
        raise ValueError("今天已领过菜篮")
    item = random.choice(BASKET_POOL)
    # 邻居若 satchel 有该物，象征性「从邻居分一截」
    cur = await conn.execute(
        "SELECT quantity FROM satchel WHERE steward_id=? AND item=? AND quantity>0",
        (seller_id, item),
    )
    if await cur.fetchone():
        await db.take_item(conn, seller_id, item, 1)
    await db.add_item(conn, buyer["id"], item, 1)
    await conn.execute(
        """
        UPDATE neighbor_basket_sub SET last_claim_day=?
        WHERE buyer_id=? AND seller_id=?
        """,
        (day, buyer["id"], seller_id),
    )
    seller = await db.get_steward_by_id(seller_id)
    sn = seller["name"] if seller else "邻居"
    return f"菜篮领取 {ITEM_NAMES.get(item, item)} x1（来自 {sn}）"


async def _bump_rapport(conn, a: int, b: int, n: int) -> None:
    from . import multi as multi_mod
    await multi_mod._bump_rapport(conn, a, b, n)


async def dispatch(conn, steward: dict, parts: list[str]) -> str:
    await ensure_tables(conn)
    if not parts:
        return (
            "菜篮：开 · 订 名字 · 领\n"
            "托养：送出 名字 槽位 · 接回 邻居名 栏位 · 列表\n"
            "借船：给 名字 · 状态"
        )
    sub = parts[0].lower()
    if sub in ("借船", "loan", "boat"):
        if len(parts) == 1:
            return "借船 给 名字（协作≥60）· 借船 状态"
        if len(parts) >= 3 and parts[1] in ("给", "lend", "出"):
            return await boat_loan_give(conn, steward, parts[2])
        if len(parts) >= 2 and parts[1] in ("状态", "status"):
            return await boat_loan_status_report(conn, steward["id"])
        raise ValueError("借船 给 名字 · 借船 状态")
    if sub in ("托养", "foster"):
        if parts[1] in ("送出", "出") and len(parts) >= 4:
            return await foster_send(conn, steward, parts[2], int(parts[3]))
        if parts[1] in ("接回", "back") and len(parts) >= 4:
            return await foster_reclaim(conn, steward, parts[2], int(parts[3]))
        if parts[1] in ("接回", "back") and len(parts) == 3:
            raise ValueError("托养 接回 邻居名 栏位（不是你自己家的槽位号）")
        if parts[1] in ("列表", "list", "status"):
            return await foster_list(conn, steward["id"])
        raise ValueError("托养 送出 名字 槽位 · 托养 接回 邻居名 栏位 · 托养 列表")
    if sub in ("菜篮", "basket"):
        if parts[1] in ("开", "open"):
            return await basket_open(conn, steward)
        if parts[1] in ("订", "sub") and len(parts) >= 3:
            return await basket_subscribe(conn, steward, parts[2])
        if parts[1] in ("领", "claim"):
            return await basket_claim(conn, steward)
        raise ValueError("菜篮 开 · 菜篮 订 名字 · 菜篮 领")
    raise ValueError(f"未知邻居连接指令: {' '.join(parts)}")


async def neighbor_links_ops(key_id: int, command: str) -> str:
    parts = command.strip().split()
    head = parts[0].lower() if parts else ""
    read_only = head in ("借船", "loan", "boat", "托养", "foster", "菜篮", "basket") and (
        len(parts) <= 1
        or (len(parts) >= 2 and parts[1] in ("状态", "status", "列表", "list"))
    )
    s = await require_steward(key_id, exempt_duty=read_only)
    async with db.connect() as conn:
        msg = await dispatch(conn, s, parts)
        await conn.commit()
    return msg

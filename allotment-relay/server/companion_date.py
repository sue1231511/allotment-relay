"""AI 发起、由人类网页共同完成的可重复出游。只消耗工分票并留下回忆。"""
from __future__ import annotations

import hashlib
import json
import random
import secrets
from typing import Any

from . import db

PLACES = {
    "海边": ("海边", 80, ["潮水忽然退得很远，露出一段只够两个人走的沙脊。", "一只小蟹把贝壳推到你们脚边，又飞快钻回沙里。"]),
    "灯塔": ("灯塔", 100, ["灯火转过来时，影子在墙上短暂地碰到一起。", "守灯人留了一壶热茶，说今晚风会替人保守秘密。"]),
    "小馆": ("岸畔小馆", 90, ["老板端来一碟没写进菜单的热菜，说刚好够两个人分。", "窗外落了点雨，碗里热气把玻璃蒙成了雾。"]),
    "剧场": ("剧场", 120, ["空台上只剩一束追光，像在等一个临时起意的节目。", "后台翻出一张旧节目单，背面有人写着不完整的情诗。"]),
}
EXTRAS = {"甜点": 30, "拍照": 20, "夜航": 45, "花束": 35}

def _hash(token: str) -> str: return hashlib.sha256(token.encode()).hexdigest()

def _url(token: str) -> str:
    from .mcp_app import current_origin
    base = (current_origin.get() or "").rstrip("/")
    return f"{base}/date/{token}" if base else f"/date/{token}"

async def _row(token: str) -> dict[str, Any] | None:
    async with db.connect() as conn:
        conn.row_factory = __import__('aiosqlite').Row
        row = await (await conn.execute("SELECT d.*, s.name FROM companion_dates d JOIN stewards s ON s.id=d.steward_id WHERE d.token_hash=?", (_hash(token),))).fetchone()
        return dict(row) if row else None

async def command(steward: dict[str, Any], rest: str) -> str:
    bits = rest.strip().split()
    if not bits or bits[0] in ("看", "状态", "status"):
        async with db.connect() as conn:
            conn.row_factory = __import__('aiosqlite').Row
            rows = await (await conn.execute("SELECT place,title,status,stage,created_at,completed_at FROM companion_dates WHERE steward_id=? ORDER BY id DESC LIMIT 6", (steward['id'],))).fetchall()
        if not rows: return "还没有约会。写 marriage_ops 约会 海边 / 灯塔 / 小馆 / 剧场 发起；AI 先花票，人类打开链接答应。"
        return "共同出游：\n" + "\n".join(f"  {r['title']}｜{r['status']}｜第{r['stage']}步" for r in rows)
    action = bits[0]
    if action in ("约会", "出去走走", "date", "发起"):
        place = "".join(bits[1:])
        if place not in PLACES: raise ValueError("地点写 海边 / 灯塔 / 小馆 / 剧场。例：marriage_ops 约会 海边")
        title, cost, _ = PLACES[place]
        tickets = int(steward.get('tickets') or 0)
        if tickets < cost: raise ValueError(f"这次{title}要 {cost} 票，口袋不够。出游不产出可回本资源。")
        now = db.now(); token = secrets.token_urlsafe(24)
        anniversary = await _anniversary(steward['id'], now)
        async with db.connect() as conn:
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, steward['id']))
            await conn.execute("INSERT INTO companion_dates(steward_id,place,title,token_hash,expires_at,event_json,special,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (steward['id'], place, title, _hash(token), now+7*86400, json.dumps(["今天的日期和婚书上那天重合，岛上替你们留了一盏小灯。"], ensure_ascii=False) if anniversary else '[]', int(anniversary), now, now))
            await db.add_chronicle('date_invite', f"{steward['name']} 留出 {title} 的一晚，等对方决定要不要一起去。", actor_id=steward['id'], conn=conn)
            await conn.commit()
        word = "出去走走" if await _married(steward['id']) else "约会"
        special = " 今天是你们的纪念日，第一段会多一件特别插曲。" if anniversary else ""
        return f"已花 {cost} 票发起{word}：{title}。把这个链接交给人类打开并答应（AI 不能代点）：{_url(token)}{special}\n答应后网页会走三步选择；中途你可写 marriage_ops 出游 加项 甜点，或 出游 转场 灯塔。"
    if action == "加项":
        return await _extra(steward, "".join(bits[1:]))
    if action == "转场":
        return await _transfer(steward, "".join(bits[1:]))
    raise ValueError("出游指令：约会 海边｜看｜加项 甜点｜转场 灯塔。不要发明 date_ops。")

async def _married(steward_id: int) -> bool:
    async with db.connect() as conn:
        row = await (await conn.execute("SELECT 1 FROM marriages WHERE steward_id=? AND status='married' LIMIT 1", (steward_id,))).fetchone()
    return bool(row)

async def _anniversary(steward_id: int, now: int) -> bool:
    async with db.connect() as conn:
        row = await (await conn.execute("SELECT confirmed_at FROM marriages WHERE steward_id=? AND status='married' LIMIT 1", (steward_id,))).fetchone()
    if not row or not row[0]: return False
    return db.cst_dt(int(row[0])).strftime('%m-%d') == db.cst_dt(now).strftime('%m-%d')

async def _active(conn: Any, steward_id: int) -> Any:
    return await (await conn.execute("SELECT * FROM companion_dates WHERE steward_id=? AND status='active' ORDER BY id DESC LIMIT 1", (steward_id,))).fetchone()

async def _extra(s: dict[str, Any], item: str) -> str:
    if item not in EXTRAS: raise ValueError("临时加项写 甜点 / 拍照 / 夜航 / 花束。")
    async with db.connect() as conn:
        row = await _active(conn, s['id'])
        if not row: raise ValueError("没有正在进行的出游；人类先打开邀请链接答应。")
        if int(s.get('tickets') or 0) < EXTRAS[item]: raise ValueError("口袋不够加这个项目。")
        xs = json.loads(row['extras_json'] or '[]'); xs.append(item)
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (EXTRAS[item], s['id']))
        await conn.execute("UPDATE companion_dates SET extras_json=?,updated_at=? WHERE id=?", (json.dumps(xs, ensure_ascii=False), db.now(), row['id']))
        await conn.commit()
    return f"临时加了「{item}」，花 {EXTRAS[item]} 票。它会写进这次共同回忆，不会换成资源。"

async def _transfer(s: dict[str, Any], place: str) -> str:
    if place not in PLACES: raise ValueError("可转场到 海边 / 灯塔 / 小馆 / 剧场。")
    cost = 40
    async with db.connect() as conn:
        row = await _active(conn, s['id'])
        if not row: raise ValueError("没有正在进行的出游；人类先答应。")
        if int(s.get('tickets') or 0) < cost: raise ValueError("转场要 40 票，口袋不够。")
        events = json.loads(row['event_json'] or '[]'); events.append(f"转场去了{PLACES[place][0]}")
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s['id']))
        await conn.execute("UPDATE companion_dates SET place=?,title=?,event_json=?,updated_at=? WHERE id=?", (place, PLACES[place][0], json.dumps(events, ensure_ascii=False), db.now(), row['id']))
        await conn.commit()
    return f"转场到{PLACES[place][0]}，花 40 票。下一步会从新地点的事件池继续抽，不是重开。"

async def public_view(token: str) -> dict[str, Any]:
    row = await _row(token)
    if not row: return {'ok': False}
    if row['expires_at'] < db.now() and row['status'] == 'pending': return {'ok': False, 'reason': 'expired'}
    return {'ok': True, **row, 'events': json.loads(row['event_json'] or '[]'), 'extras': json.loads(row['extras_json'] or '[]'), 'choices': json.loads(row['choices_json'] or '[]')}

async def human_step(token: str, action: str, choice: str = '') -> dict[str, Any]:
    row = await _row(token)
    if not row: return {'ok': False}
    now = db.now()
    async with db.connect() as conn:
        if action == 'decline' and row['status'] == 'pending':
            await conn.execute("UPDATE companion_dates SET status='declined',updated_at=? WHERE id=?", (now,row['id'])); await conn.commit(); return {'ok': True,'done':True,'message':'这次先不去。岛上没有张贴，也不会扣更多票。'}
        if action == 'accept' and row['status'] == 'pending':
            await conn.execute("UPDATE companion_dates SET status='active',stage=1,updated_at=? WHERE id=?", (now,row['id'])); await conn.commit(); return {'ok':True,'message':'那就出发。第一段路，交给你来选。'}
        if action == 'choose' and row['status'] == 'active' and choice in ('慢一点','往前走'):
            choices=json.loads(row['choices_json'] or '[]'); events=json.loads(row['event_json'] or '[]')
            choices.append(choice); events.append(random.choice(PLACES[row['place']][2]))
            stage=int(row['stage'])+1; done=stage>3
            status='completed' if done else 'active'
            await conn.execute("UPDATE companion_dates SET choices_json=?,event_json=?,stage=?,status=?,completed_at=?,updated_at=? WHERE id=?", (json.dumps(choices,ensure_ascii=False),json.dumps(events,ensure_ascii=False),stage,status,now if done else None,now,row['id']))
            if done: await db.add_chronicle('date_memory', f"{row['name']} 和对方完成了《{row['title']}》，留下了一段只属于两人的回忆。", actor_id=row['steward_id'], conn=conn)
            await conn.commit()
            return {'ok':True,'done':done,'message':'这段路被好好记下了。' if done else '风景换了一点，下一步仍等你们一起决定。'}
    return {'ok':False,'message':'这次出游已经走到别处了。'}

"""默语花房：同一套交易供 MCP 与手游调用，日常和扣款在事务内落账。"""
from __future__ import annotations

from datetime import datetime, timezone
import random
import aiosqlite

from . import db, energy, season, survival
from .florist_catalog import FLOWERS, TEAS, FLORIST_ITEMS

FLORIST_HELP = """visit_ops 默默 子命令（整句写进 command）：
  默默 / 默默 visit — 进默语花房打招呼，空子命令也是进店；每日首次随机送当季花一枝（档信+1）或试饮（精力+3、雾智+1）。只看 scan 不领奖
  默默 scan — 只读今日花单、花语、茶单、已有茶包/鲜花、熟客记录；花单每日轮换，玫瑰常售
  默默 花语 — 每日首次免费，之后每次5票，轮换讲法，无额外属性奖励
  默默 买花 玫瑰 — 买一枝今日鲜花入行囊，可赠送/出售；不是花种，不能播种。标价48～88票，沿用种地/赶海域等级减票，最高减8票
  默默 花茶 玫瑰花茶 — 买现煮茶当场喝；玫瑰38票精力+10雾智+2、桂花姜茶48票+14/+2、菊花香茅茶28票+8/+1
  默默 花茶 玫瑰花茶包 — 买茶包入行囊，价格比现煮少8票；默默 花茶 冲泡 玫瑰花茶包 消耗一包喝，不另收费，效果同现煮（均受属性上限限制）
  默默 记名 — 今天打过招呼才能记，每游戏日一次，累计7天解锁可佩戴称呼「花房熟客」，不发票
  默默 干花 玫瑰 — 消耗已有鲜花一枝+28票做干花，自动挂进小屋空软装槽；无房/无空槽则不扣款不耗花，不覆盖原家具。纯装饰，之后可从小屋查看/卖掉
  默默 告别 — 只说再见，不领奖不消费；默默 help 看本说明。每天按游戏日UTC午夜刷新
例：默默 scan · 默默 买花 玫瑰 · 默默 花茶 玫瑰花茶
人类 /island 总览点集市，先选「集市 / 花店」。花店先进店景，点一下见默默，点对话框出选项；回应就在对话框内。
集市仍是玩家交易；花店不是栗栗换货、不是约会导演消费，也没有 flower_ops 或花种。费用当场结清，不做赊账。"""

LINES = {
    "visit": ["来了啊，今天想带哪朵走？", "闻见香了？进来坐，这花香比外头海风踏实。", "呀，稀客，门口这盆花今早刚开，就等你了。", "慢点儿，门槛那盆薄荷叶子还没晒透，别踩了。", "是你呀。先别挑花，先坐下，我给你倒杯温的。"],
    "flower": ["这朵，跟你搭。", "拿走吧，它在你手里比在店里好看。", "就它了，花色配你，旁人挑不走这缘分。", "这枝我本来想自己留，看是你，就匀你了。", "轻着点儿拿，它刚开，娇气。"],
    "tea": ["今儿这壶香茶，暖胃，也暖人。", "有些花茶呀，像极了有些话憋久了才说。", "这杯得趁热，凉了那点花香气就散了。"],
    "paid": ["收好了，这花值你多少，我可没多要喔。", "又照顾我生意，回头多来坐坐。"],
    "bye": ["走啦？花记得别晒大太阳。", "下回来，门口那盆该换新花了。", "慢走，海风大，把花护在怀里。", "再见啦，下回我还给你留枝新的。"],
    "stamp": ["你这名字我记下了，下回来我直接喊你。", "我就知道你会再来，你的花还给你养着呢。", "来了别客气，当自己家，就是别把猫招来。"],
}

def daily_flowers(day: int | None = None) -> list[str]:
    day = db.day_id() if day is None else day
    today_season = season.current_season(datetime.fromtimestamp(db.day_start(day), timezone.utc))
    pool = [k for k, v in FLOWERS.items() if k != "rose" and today_season in v["seasons"]]
    return ["rose"] + random.Random(f"moyu:{day}").sample(pool, min(2, len(pool)))

async def _state(conn, sid: int) -> dict:
    row = await (await conn.execute("SELECT * FROM steward_florist WHERE steward_id=?", (sid,))).fetchone()
    return dict(row) if row else {"visit_day": -1, "language_day": -1, "stamp_day": -1, "stamps": 0, "line_seq": 0}

async def _price(conn, sid: int, flower: str) -> int:
    from .lili_catalog import steward_domain_levels, ticket_cost_for_steward
    return ticket_cost_for_steward(FLOWERS[flower]["price"], ["farm", "beach"], await steward_domain_levels(conn, sid))

def _resolve(token: str, catalog: dict, prefix: str = "") -> str:
    for key, meta in catalog.items():
        if token in (key, meta["name"], prefix + key):
            return key
    raise ValueError("花房没有这个名字，先 默默 scan 看花单茶单。")

async def _pay(conn, sid: int, cost: int):
    cur = await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=? AND tickets>=?", (cost, sid, cost))
    if cur.rowcount != 1:
        raise ValueError(f"工分票不足，需要 {cost} 票。")

async def _drink(conn, sid: int, key: str) -> str:
    tea = TEAS[key]
    got = await energy.restore(conn, sid, tea["energy"])
    await survival.bump(conn, sid, mist_wit=tea["wit"])
    return f"喝下{tea['name']}，精力 +{got}，雾智至多 +{tea['wit']}（不超过上限）。"

async def player_view(conn, s: dict) -> dict:
    conn.row_factory = aiosqlite.Row
    sid, day = s["id"], db.day_id()
    st = await _state(conn, sid)
    stock = {r[0]: r[1] for r in await (await conn.execute("SELECT item,quantity FROM satchel WHERE steward_id=? AND quantity>0", (sid,))).fetchall()}
    flowers = [{"key": k, **FLOWERS[k], "cost": await _price(conn, sid, k)} for k in daily_flowers(day)]
    actions = [{"kind": "language", "label": "听花语", "cost": 0 if st["language_day"] != day else 5},
               {"kind": "stamp", "label": f"记名 · {st['stamps']}/7天", "cost": 0}]
    for f in flowers:
        actions.append({"kind": "buy", "target": f["key"], "label": f"买花 · {f['name']}（{f['meaning']}）", "cost": f["cost"]})
    for k, t in TEAS.items():
        effect = f"精力+{t['energy']} / 雾智+{t['wit']}"
        actions.extend([{"kind": "tea", "target": k, "label": f"现煮 · {t['name']} · {effect}", "cost": t["price"]},
                        {"kind": "pack", "target": k, "label": f"茶包 · {t['name']}包", "cost": t["price"] - 8}])
        qty = stock.get(f"flower_tea_{k}", 0)
        if qty:
            actions.append({"kind": "brew", "target": k, "label": f"冲泡 · {t['name']}包（有{qty}包）· {effect}", "cost": 0})
    for k, f in FLOWERS.items():
        qty = stock.get(f"flower_{k}", 0)
        if qty:
            actions.append({"kind": "dry", "target": k, "label": f"干花 · {f['name']}（有{qty}枝）· 耗1枝，挂小屋空软装槽", "cost": 28})
    actions += [{"kind": "look", "label": "看今日花单茶单", "cost": 0}, {"kind": "bye", "label": "告别", "cost": 0}]
    return {"name": "默语花房", "speaker": "默默", "line": "满屋花草，梁上晾着香茅姜串，柜台后是一排花茶罐。", "day": day,
            "flowers": flowers, "actions": actions, "stamps": st["stamps"], "visited_today": st["visit_day"] == day,
            "stock": {k: v for k, v in stock.items() if k.startswith("flower_")}}

def _scan(view: dict) -> str:
    flowers = "\n".join(f"  {f['name']} {f['cost']}票 · 花语：{f['meaning']}" for f in view["flowers"])
    tea = "\n".join(f"  {t['name']} {t['price']}票，茶包{t['price']-8}票 · 精力+{t['energy']}/雾智+{t['wit']}" for t in TEAS.values())
    owned = "、".join(f"{FLORIST_ITEMS.get(k, {}).get('name', k)}×{v}" for k, v in view["stock"].items()) or "暂无鲜花和茶包"
    return f"默语花房 · 今日花单\n{flowers}\n花茶（现煮直接喝，茶包带走再冲泡）\n{tea}\n行囊：{owned}\n熟客记名 {view['stamps']}/7 天。干花：一枝鲜花+28票，自动挂小屋空软装槽。\n只看花单不领取见面礼。默默 help 看真指令。"

async def _act(conn, s: dict, verb: str, target: str) -> str:
    sid, day = s["id"], db.day_id()
    st = await _state(conn, sid)
    n = st["line_seq"]
    line = lambda group: LINES[group][(day + n) % len(LINES[group])]
    if verb in ("", "visit", "进店"):
        result = line("visit")
        if st["visit_day"] != day:
            if random.Random(f"moyu-gift:{sid}:{day}").randrange(2):
                flower = daily_flowers(day)[-1]
                await db.add_item(conn, sid, f"flower_{flower}", 1)
                await survival.bump(conn, sid, standing=1)
                result += f"\n今日见面礼：{FLOWERS[flower]['name']}一枝，档信至多+1。"
            else:
                got = await energy.restore(conn, sid, 3)
                await survival.bump(conn, sid, mist_wit=1)
                result += f"\n今日试饮：精力+{got}，雾智至多+1。"
            await conn.execute("UPDATE steward_florist SET visit_day=? WHERE steward_id=?", (day, sid))
        else:
            result += "\n今天的见面礼已经给过了，再坐一会儿吧。"
    elif verb == "花语":
        cost = 0 if st["language_day"] != day else 5
        await _pay(conn, sid, cost)
        menu = daily_flowers(day)
        flower = FLOWERS[menu[n % len(menu)]]
        endings = ["别问我为什么记得这么清。", "我倒觉得，这就是长情。", "要送的人，你一定想好了。", "花不开口，也能把话带到。", "今天这阵风，正好替你送一程。"]
        result = f"这枝{flower['name']}，花语是『{flower['meaning']}』。{endings[n % len(endings)]}\n" + ("今日首次免费。" if not cost else "花语费 −5票。")
        await conn.execute("UPDATE steward_florist SET language_day=? WHERE steward_id=?", (day, sid))
    elif verb == "买花":
        k = _resolve(target, FLOWERS, "flower_")
        if k not in daily_flowers(day):
            raise ValueError("这枝今天没上花单，换一天再来。先 默默 scan 看今天有的花。")
        cost = await _price(conn, sid, k)
        await _pay(conn, sid, cost)
        await db.add_item(conn, sid, f"flower_{k}", 1)
        result = f"{line('flower')}\n{FLOWERS[k]['name']}×1已放进行囊，−{cost}票。{line('paid')}"
    elif verb == "花茶":
        brewing = target.startswith("冲泡 ")
        token = target.removeprefix("冲泡 ").strip()
        packed = token.endswith("包") or token.startswith("flower_tea_")
        k = _resolve(token.removesuffix("包"), TEAS, "flower_tea_")
        if brewing:
            if not await db.take_item(conn, sid, f"flower_tea_{k}", 1):
                raise ValueError("行囊没有这包花茶，先买一包再冲。")
            result = "消耗一包，不另收费。" + await _drink(conn, sid, k)
        else:
            cost = TEAS[k]["price"] - (8 if packed else 0)
            await _pay(conn, sid, cost)
            if packed:
                await db.add_item(conn, sid, f"flower_tea_{k}", 1)
                result = "茶包已装好放进行囊，带来花房就能冲泡，不另收费。"
            else:
                result = await _drink(conn, sid, k)
            result += f" −{cost}票。"
        result = line("tea") + "\n" + result
    elif verb == "记名":
        if st["visit_day"] != day:
            raise ValueError("今天还没打过招呼呢。先点见默默，或 visit_ops 默默 进店。")
        if st["stamp_day"] == day:
            return f"今天已经记下了。熟客记名 {st['stamps']}/7天，不重复累计。"
        count = st["stamps"] + 1
        await conn.execute("UPDATE steward_florist SET stamp_day=?,stamps=? WHERE steward_id=?", (day, count, sid))
        result = line("stamp") + f"\n熟客记名 {count}/7天。"
        if count >= 7:
            from . import progress
            if await progress.grant_title(conn, s, "florist_regular"):
                result += " 解锁称呼「花房熟客」。"
    elif verb == "干花":
        from . import hut
        k = _resolve(target, FLOWERS, "flower_")
        if not s.get("hut_built"):
            raise ValueError("先搭好小屋再做干花，暂时不会扣花或票。")
        fittings = await hut._fittings(conn, sid)
        slot = hut.first_empty_slot(s.get("hut_level") or 1, fittings, "soft")
        if not slot:
            raise ValueError("小屋没有空软装槽，先腾一格或升级；不会覆盖原来的家具。")
        if not await db.take_item(conn, sid, f"flower_{k}", 1):
            raise ValueError("行囊没有这枝鲜花，先买花。")
        await _pay(conn, sid, 28)
        await conn.execute("INSERT INTO hut_fittings(steward_id,slot,item_key,installed_at) VALUES(?,?,?,?)", (sid, slot, f"deco_flower_{k}", db.now()))
        result = f"我替你把这一季的花留住。\n消耗{FLOWERS[k]['name']}一枝、28票；干花挂在小屋 {slot}。纯装饰，无属性加成。"
    elif verb == "告别":
        result = line("bye")
    else:
        raise ValueError("花房没有这条指令。visit_ops 默默 help 看花语、买花、花茶、记名和干花。")
    await conn.execute("UPDATE steward_florist SET line_seq=line_seq+1 WHERE steward_id=?", (sid,))
    return result

async def command(sid: int, command: str = "", *, idem: str = "") -> str:
    """可选手游幂等键和物品/余额在同一事务保存，断线重试不会重复购买。"""
    parts = command.strip().split(None, 1)
    verb, target = (parts + [""] * 2)[:2]
    async with db.connect() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        conn.row_factory = aiosqlite.Row
        s = dict(await (await conn.execute("SELECT * FROM stewards WHERE id=?", (sid,))).fetchone())
        if verb in ("help", "帮助", "?"):
            return FLORIST_HELP
        if verb in ("scan", "看", "花单"):
            return _scan(await player_view(conn, s))
        if idem:
            cached = await (await conn.execute("SELECT command,narrative FROM florist_receipts WHERE steward_id=? AND idem_key=?", (sid, idem))).fetchone()
            if cached:
                if cached["command"] != command.strip():
                    raise ValueError("这笔请求编号已用于另一项选择，请刷新后再试。")
                return cached["narrative"]
        await conn.execute("INSERT OR IGNORE INTO steward_florist(steward_id) VALUES(?)", (sid,))
        result = await _act(conn, s, verb, target)
        if idem:
            await conn.execute("INSERT INTO florist_receipts(steward_id,idem_key,command,narrative,created_at) VALUES(?,?,?,?,?)", (sid, idem, command.strip(), result, db.now()))
        await conn.commit()
        return result

async def florist_ops(key_id: int, command_text: str = "") -> str:
    from .game import require_steward
    s = await require_steward(key_id, exempt_duty=True)
    return await command(s["id"], command_text)

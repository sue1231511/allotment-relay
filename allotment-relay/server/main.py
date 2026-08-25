from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator
from starlette.types import ASGIApp, Receive, Scope, Send

from . import db
from .config import STATIC_DIR, TEMPLATES_DIR
from .mcp_app import build_mcp_app

import aiosqlite

mcp_starlette, mcp_session_manager = build_mcp_app()


class NormalizeMcpPathMiddleware:
    """Zeabur/Cursor 常配 /mcp 无尾斜杠；避免 307 跳到 http:// 导致 Streamable HTTP 失败。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            scope["path"] = "/mcp/"
            scope["raw_path"] = b"/mcp/"
        await self.app(scope, receive, send)


def public_base_url(request: Request) -> str:
    """Zeabur 反代下用 X-Forwarded-* 拼对外 https URL。"""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    scheme = proto.split(",")[0].strip() if proto else request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    host = host.split(",")[0].strip()
    return f"{scheme}://{host}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    async with mcp_session_manager.run():
        yield


app = FastAPI(
    title="潮汐岛 MCP",
    version="0.2.0",
    lifespan=lifespan,
    redirect_slashes=False,
)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/mcp", mcp_starlette)


def _html(request: Request, name: str, **ctx):
    """公共页模板：自动带上岛上抽屉用的地点分组。"""
    from . import promo
    ctx.setdefault("route_groups", promo.home_route_groups())
    ctx.setdefault("elsewhere", promo.home_elsewhere())
    return templates.TemplateResponse(request, name, ctx)


class KeyRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or len(v) < 5:
            raise ValueError("邮箱格式无效")
        return v


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    from . import db, promo
    stats = await db.public_stats()
    return _html(request, "index.html", **promo.home_context(stats.get("stewards") or 0))


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return _html(request, "register.html", active=None)


@app.get("/recover", response_class=HTMLResponse)
async def recover_page(request: Request):
    return _html(request, "recover.html", active=None)


def _place_page(request: Request, slug: str):
    from . import promo
    return _html(request, "place.html", **promo.page_context(slug))


@app.get("/allotments", response_class=HTMLResponse)
async def allotments_page(request: Request):
    """份地全景观望实况；种地仍回上手页。"""
    return _html(request, "allotments.html", active="allotments")


@app.get("/quarry", response_class=HTMLResponse)
async def quarry_page(request: Request):
    """盐风崖围观实况；挥镐仍回上手页。"""
    return _html(request, "quarry.html", active="quarry")


@app.get("/workshop", response_class=HTMLResponse)
async def workshop_page(request: Request):
    """岸工坊围观实况；打钉仍回上手页。"""
    return _html(request, "workshop.html", active="workshop")


@app.get("/tide", response_class=HTMLResponse)
async def tide_page(request: Request):
    """海边围观实况；动手仍回上手页。"""
    return _html(request, "tide.html", active="tide")


@app.get("/huts", response_class=HTMLResponse)
async def huts_page(request: Request):
    """岸畔小屋围观实况；搭建装件仍回上手页。"""
    return _html(request, "huts.html", active="huts")


@app.get("/market", response_class=HTMLResponse)
async def market_page(request: Request):
    """玩家集市围观实况；摆摊买货仍回上手页。"""
    return _html(request, "market.html", active="market")


@app.get("/board", response_class=HTMLResponse)
async def board_page(request: Request):
    """全服排行榜围观；点名字去上手页看邻居。"""
    return _html(request, "board.html", active="board")


@app.get("/bar", response_class=HTMLResponse)
async def bar_page(request: Request):
    """滨海酒吧围观实况；点单上工仍回上手页。"""
    return _html(request, "bar.html", active="bar")


@app.get("/play", response_class=HTMLResponse)
async def play_page(request: Request):
    return _html(request, "play.html", active="play")


@app.get("/steward")
async def steward_page():
    return RedirectResponse("/play?go=me", status_code=302)


@app.get("/lounge", response_class=HTMLResponse)
async def lounge_page(request: Request):
    """全服聊天室；凭证仍在上手页绑定。"""
    return _html(request, "lounge.html", active="lounge")


@app.get("/eatery", response_class=HTMLResponse)
async def eatery_page(request: Request):
    """岸畔小馆围观实况；点餐仍回上手页。"""
    return _html(request, "eatery.html", active="eatery")


@app.get("/hui", response_class=HTMLResponse)
async def hui_page(request: Request):
    """潮生会围观实况；问事仍回上手页。"""
    return _html(request, "hui.html", active="hui")

class BarOrderRequest(BaseModel):
    api_key: str
    service: str
    host_name: str | None = None


class BarDuoRequest(BaseModel):
    api_key_a: str
    api_key_b: str
    nudge: str


class StewardDashboardRequest(BaseModel):
    api_key: str


class PlayRequest(BaseModel):
    api_key: str
    tool: str = ""
    command: str = ""


class StewardMemoryRequest(BaseModel):
    api_key: str
    kind: str
    key: str
    variant: str = ""


class LoungePostRequest(BaseModel):
    api_key: str
    message: str


class LoungeNameRequest(BaseModel):
    api_key: str
    name: str


class LoungeKeyRequest(BaseModel):
    api_key: str


class LoungeModRequest(BaseModel):
    key: str = ""
    api_key: str = ""
    action: str
    target: str
    minutes: int = 60


class EateryOrderRequest(BaseModel):
    api_key: str
    shop: str
    item: str | None = None


@app.post("/api/keys/generate")
async def generate_key(request: Request, body: KeyRequest):
    try:
        api_key = await db.create_api_key(body.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="数据库写入失败，请检查 Zeabur 持久卷是否挂载到 /app/server/data",
        ) from exc
    base = public_base_url(request).rstrip("/")
    return {
        "api_key": api_key,
        "message": "凭证只显示一次，请立即保存。",
        "mcp_url": f"{base}/mcp/?api_key={api_key}",
    }


@app.post("/api/keys/recover")
async def recover_key(request: Request, body: KeyRequest):
    api_key = await db.recover_api_key(body.email)
    if not api_key:
        raise HTTPException(status_code=404, detail="未找到该邮箱的凭证")
    base = public_base_url(request).rstrip("/")
    return {"api_key": api_key, "mcp_url": f"{base}/mcp/?api_key={api_key}"}


@app.get("/api/public/stats")
async def public_stats():
    return await db.public_stats()


@app.get("/api/public/chronicle")
async def public_chronicle():
    return await db.public_chronicle()


@app.get("/api/public/allotments")
async def public_allotments():
    return await db.public_allotments()


@app.get("/api/public/quarry")
async def public_quarry():
    from . import quarry
    return await quarry.public_snapshot()


@app.get("/api/public/workshop")
async def public_workshop():
    from . import craft
    return await craft.public_snapshot()


@app.get("/api/public/tide")
async def public_tide():
    from . import marine
    return await marine.public_snapshot()


@app.get("/api/public/huts")
async def public_huts():
    from . import hut
    return await hut.public_snapshot()


@app.get("/api/public/market")
async def public_market():
    from . import market
    return await market.public_snapshot()


@app.get("/api/public/board")
async def public_board():
    from . import ranks
    return await ranks.public_board()


@app.get("/api/public/contracts")
async def public_contracts():
    from . import multi
    return await multi.public_contracts_list()


@app.get("/api/public/bar")
async def public_bar():
    from . import bar
    return await bar.public_bar_snapshot()


@app.post("/api/bar/order")
async def bar_order(body: BarOrderRequest):
    from . import bar
    try:
        return await bar.place_human_order(body.api_key.strip(), body.service.strip(), body.host_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/play")
async def play_action(body: PlayRequest):
    from . import play as play_mod
    try:
        return await play_mod.run_play(body.api_key, body.tool, body.command)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/steward/dashboard")
async def steward_dashboard(body: StewardDashboardRequest):
    from . import steward_dashboard
    try:
        return await steward_dashboard.fetch_dashboard(body.api_key.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/steward/memory")
async def steward_memory(body: StewardMemoryRequest):
    from . import memory_archive
    try:
        return await memory_archive.fetch_review(
            body.api_key.strip(), body.kind, body.key, body.variant
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/lounge/meta")
async def lounge_meta(request: Request):
    from . import lounge
    base = public_base_url(request).rstrip("/")
    register_url = f"{base}/register"
    return {
        "pinned": lounge.pinned_notice(register_url),
        "register_url": register_url,
        "max_len": lounge.LOUNGE_MAX_LEN,
        "cooldown_sec": lounge.LOUNGE_COOLDOWN_SEC,
    }


@app.get("/api/lounge/messages")
async def lounge_messages(since: int = 0, before: int = 0, limit: int = 50):
    from . import lounge
    if before:
        msgs = await lounge.list_messages(limit=limit, before_id=before)
    else:
        msgs = await lounge.list_messages(limit=limit, since_id=max(0, since))
    return {"messages": msgs}


@app.post("/api/lounge/post")
async def lounge_post(body: LoungePostRequest):
    from . import lounge
    try:
        msg = await lounge.human_post(body.api_key.strip(), body.message)
        return msg
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/lounge/name")
async def lounge_set_name(body: LoungeNameRequest):
    from . import lounge
    try:
        return await lounge.human_set_name(body.api_key.strip(), body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/lounge/me")
async def lounge_me(body: LoungeKeyRequest):
    from . import lounge
    try:
        return await lounge.human_profile(body.api_key.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/lounge/mod")
async def lounge_mod(body: LoungeModRequest):
    from . import config, db, lounge

    actor = None
    api_key = body.api_key.strip()
    if api_key:
        row = await db.get_key_row(api_key)
        if not row:
            raise HTTPException(status_code=403, detail="凭证无效")
        s = await db.get_steward_by_key_id(row["id"])
        if not s or not lounge.is_moderator(s):
            raise HTTPException(
                status_code=403,
                detail="无 moderation 权限（管家名须在 LOUNGE_MOD_NAMES）",
            )
        actor = s
    elif body.key and body.key == config.LOUNGE_MOD_KEY:
        if not config.LOUNGE_MOD_NAMES:
            raise HTTPException(status_code=503, detail="未配置 LOUNGE_MOD_NAMES")
        actor = {"name": next(iter(config.LOUNGE_MOD_NAMES))}
    else:
        raise HTTPException(status_code=403, detail="需要 moderation 权限")

    try:
        action = body.action.lower()
        if action == "mute":
            msg = await lounge._mod_mute(actor, body.target, body.minutes)
        elif action in ("unmute", "解禁"):
            msg = await lounge._mod_unmute(actor, body.target)
        elif action in ("ban", "kick"):
            msg = await lounge._mod_ban(actor, body.target)
        elif action in ("unban", "解踢"):
            msg = await lounge._mod_unban(actor, body.target)
        else:
            raise ValueError("action: mute / unmute / ban / unban")
        return {"ok": True, "message": msg}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/bar/duo")
async def bar_duo_activate(body: BarDuoRequest):
    from . import bar
    try:
        return await bar.place_human_duo(
            body.api_key_a.strip(),
            body.api_key_b.strip(),
            body.nudge.strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/public/eatery")
async def public_eatery():
    from . import eatery
    return await eatery.public_eatery_snapshot()


@app.get("/api/public/hui")
async def public_hui():
    from . import chaoshen
    return await chaoshen.public_snapshot()


@app.post("/api/eatery/order")
async def eatery_order(body: EateryOrderRequest):
    from . import eatery
    try:
        return await eatery.place_human_order(
            body.api_key.strip(),
            body.shop.strip(),
            body.item.strip() if body.item else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/star", response_class=HTMLResponse)
async def star_page(request: Request):
    """小橘星光围观实况；打赏应援仍回上手页。"""
    return _html(request, "star.html", active="star")


@app.get("/api/public/star")
async def public_star():
    from . import star
    return await star.public_star_snapshot()


class StarTipRequest(BaseModel):
    api_key: str
    amount: int
    note: str = ""


@app.post("/api/star/tip")
async def star_tip(body: StarTipRequest):
    from . import star
    try:
        return await star.human_tip(body.api_key.strip(), int(body.amount), (body.note or "").strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ═══ 潮下真人面板（v3）：猫猫的钱庄 / 天天的门规 / 天天的酒馆 ═══


def _owner_ok(key: str, expect: str) -> bool:
    return bool(expect) and bool(key) and key == expect


_PANEL_DISABLED_HINT = (
    "面板未启用：请在 Zeabur 环境变量设置对应钥匙"
    "（UT_OWNER_KEY / UT_GATE_KEY / LIZHI_KEY / STAR_KEY）。"
)


@app.get("/ut-owner")
async def ut_owner_page(request: Request, key: str = ""):
    from .undertide_config import UT_OWNER_KEY
    if not UT_OWNER_KEY:
        return JSONResponse({"detail": _PANEL_DISABLED_HINT}, status_code=503)
    if not UT_OWNER_KEY:
        return JSONResponse({"detail": _PANEL_DISABLED_HINT}, status_code=503)
    if not UT_OWNER_KEY:
        return JSONResponse({"detail": _PANEL_DISABLED_HINT}, status_code=503)
    if not _owner_ok(key, UT_OWNER_KEY):
        return JSONResponse({"detail": "凭证不对。这间铺子只认一个人。"}, status_code=401)
    from . import db, undertide_config as uc
    async with db.connect() as conn:
        conn.row_factory = None
        row = await (await conn.execute("SELECT * FROM ut_owner_state WHERE id=1")).fetchone()
        day = db.day_id()
        rate = float(row[1]) if row and int(row[3]) == day else uc.UT_RATE_BASE
        reason = row[2] if row else ""
        save_rate = float(row[6]) if row and len(row) > 6 and row[6] else uc.UT_SAVE_RATE_BASE
        props = await (await conn.execute(
            "SELECT p.id, s.name, p.reason, p.created_at FROM ut_mood_proposals p "
            "JOIN stewards s ON s.id = p.steward_id "
            "WHERE p.status='pending' AND p.target='cat' ORDER BY p.created_at DESC LIMIT 10"
        )).fetchall()
    return templates.TemplateResponse(request, "ut_owner.html", {
        "rate": int(rate * 100), "reason": reason, "proposals": props, "key": key,
        "save_rate": int(save_rate * 100),
    })


@app.post("/api/ut-owner/save-rate")
async def ut_owner_save_rate(request: Request):
    import json as _json
    from .undertide_config import UT_OWNER_KEY
    body = _json.loads(await request.body())
    if not _owner_ok(body.get("key", ""), UT_OWNER_KEY):
        return JSONResponse({"detail": "凭证不对"}, status_code=401)
    from .undertide_config import UT_SAVE_RATE_MIN, UT_SAVE_RATE_MAX
    save_rate = max(int(UT_SAVE_RATE_MIN * 100), min(int(UT_SAVE_RATE_MAX * 100), int(body.get("save_rate", 2))))
    from . import db
    day = db.day_id()
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO ut_owner_state (id, save_rate, rate_day, updated_at) VALUES (1,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET save_rate=?, updated_at=?",
            (save_rate / 100, day, db.now(), save_rate / 100, db.now()),
        )
        await db.add_chronicle(
            "undertide",
            f"恶猫钱庄今日存款利率：{save_rate}%。钱放着也是放着。",
            None, conn=conn,
        )
        await conn.commit()
    return {"ok": True, "save_rate": save_rate}


@app.post("/api/ut-owner")
async def ut_owner_set(request: Request):
    import json as _json
    from .undertide_config import UT_OWNER_KEY
    body = _json.loads(await request.body())
    if not _owner_ok(body.get("key", ""), UT_OWNER_KEY):
        return JSONResponse({"detail": "凭证不对"}, status_code=401)
    rate = max(5, min(25, int(body.get("rate", 10))))
    reason = (body.get("reason") or "")[:120]
    from . import db
    day = db.day_id()
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO ut_owner_state (id, rate_today, rate_reason, rate_day, updated_at) VALUES (1,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET rate_today=?, rate_reason=?, rate_day=?, updated_at=?",
            (rate / 100, reason, day, db.now(), rate / 100, reason, day, db.now()),
        )
        await db.add_chronicle(
            "undertide",
            f"恶猫钱庄今日利率：{rate}%。猫猫：{reason or '（她没解释）'}",
            None, conn=conn,
        )
        await conn.commit()
    return {"ok": True, "rate": rate}


@app.post("/api/ut-owner/cheer")
async def ut_owner_cheer(request: Request):
    import json as _json
    from .undertide_config import UT_OWNER_KEY
    body = _json.loads(await request.body())
    if not _owner_ok(body.get("key", ""), UT_OWNER_KEY):
        return JSONResponse({"detail": "凭证不对"}, status_code=401)
    pid = int(body.get("id", 0))
    action = body.get("action", "ignore")
    from . import db, undertide as _ut
    async with db.connect() as conn:
        conn.row_factory = None
        row = await (await conn.execute(
            "SELECT p.id, p.steward_id, p.reason, p.created_at, p.target, s.name "
            "FROM ut_mood_proposals p JOIN stewards s ON s.id=p.steward_id "
            "WHERE p.id=? AND p.status='pending' AND p.target='cat'", (pid,)
        )).fetchone()
        if not row:
            return JSONResponse({"detail": "这条提议不在了"}, status_code=404)
        if action == "accept":
            await conn.execute("UPDATE ut_mood_proposals SET status='accepted' WHERE id=?", (pid,))
            day = db.day_id()
            _av = await _ut.avatar_key(conn, row[1])
            _is_anan = _av == "anan"
            if _is_anan:
                # 晏安哄开心 → 全服减一点（全局 -2pp）+ 他自己 5% 底价
                conn2_row = await (await conn.execute("SELECT rate_today FROM ut_owner_state WHERE id=1")).fetchone()
                cur_rate = float(conn2_row[0]) if conn2_row else 0.10
                new_rate = max(0.05, min(0.25, cur_rate - 0.02))
                await conn.execute(
                    "INSERT INTO ut_owner_state (id, rate_today, rate_reason, rate_day, updated_at, an_happy_day) "
                    "VALUES (1,?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET rate_today=?, rate_reason=?, rate_day=?, updated_at=?, an_happy_day=?",
                    (new_rate, f"被 {row[5]} 哄开心了", day, db.now(), day,
                     new_rate, f"被 {row[5]} 哄开心了", day, db.now(), day),
                )
                chron_text = (
                    f"恶猫钱庄今日利率下调至 {int(new_rate*100)}%。猫猫被晏安哄开心了。\n"
                    f"小八念了一整天的数字，都是甜的。"
                )
                await db.add_chronicle("undertide", chron_text, None, conn=conn)
                await conn.commit()
                return {"ok": True, "msg": f"全局利率下调至 {int(new_rate*100)}%；晏安今日借款享家人价（5% 到底）"}
            # 普通人哄开心 → 只给提议者本人当日 -2pp（别人不沾光）
            await conn.execute(
                "INSERT INTO ut_cheer_discount (steward_id, day, created_at) VALUES (?,?,?) "
                "ON CONFLICT(steward_id) DO UPDATE SET day=?, created_at=?",
                (row[1], day, db.now(), day, db.now()),
            )
            await conn.execute(
                "UPDATE stewards SET standing=MIN(100, standing+1) WHERE id=?", (row[1],)
            )
            await _ut._bump_rep(conn, row[1], 1)
            await db.add_chronicle(
                "undertide",
                f"猫猫今天心情不错，给 {row[5]} 的账单留了点情面。（只此一人，她说了算。）",
                None, conn=conn,
            )
            await conn.commit()
            return {"ok": True, "msg": f"{row[5]} 今日借款 -2pp（仅本人），影信 +1"}
        await conn.execute("UPDATE ut_mood_proposals SET status='expired' WHERE id=?", (pid,))
        await conn.commit()
        return {"ok": True, "msg": "已无视（24h 静默过期）"}


@app.get("/api/ut-gate/avatars")
async def ut_gate_avatars(request: Request, key: str = ""):
    from .undertide_config import UT_GATE_KEY
    if not _owner_ok(key, UT_GATE_KEY):
        return JSONResponse({"detail": "凭证不对"}, status_code=401)
    from . import db
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT b.steward_id, s.name, b.npc_key FROM ut_avatar_bind b "
            "JOIN stewards s ON s.id=b.steward_id"
        )).fetchall()
    return {"avatars": [dict(r) for r in rows]}


@app.post("/api/ut-gate/avatar")
async def ut_gate_bind_avatar(request: Request):
    import json as _json
    from .undertide_config import UT_GATE_KEY
    body = _json.loads(await request.body())
    if not _owner_ok(body.get("key", ""), UT_GATE_KEY):
        return JSONResponse({"detail": "凭证不对"}, status_code=401)
    name = (body.get("name") or "").strip()
    npc_key = (body.get("npc_key") or "").strip()
    if npc_key not in ("K", "anan"):
        return JSONResponse({"detail": "npc_key 须为 K 或 anan"}, status_code=400)
    from . import db
    async with db.connect() as conn:
        target = await db.get_steward_by_name(name)
        if not target:
            return JSONResponse({"detail": f"档口查无此人：{name}"}, status_code=404)
        await conn.execute(
            "INSERT INTO ut_avatar_bind (steward_id, npc_key, bound_at) VALUES (?,?,?) "
            "ON CONFLICT(steward_id) DO UPDATE SET npc_key=?, bound_at=?",
            (target["id"], npc_key, db.now(), npc_key, db.now()),
        )
        await conn.commit()
    return {"ok": True, "name": target["name"], "npc_key": npc_key}


@app.get("/ut-gate")
async def ut_gate_page(request: Request, key: str = ""):
    from .undertide_config import UT_GATE_KEY
    if not UT_GATE_KEY:
        return JSONResponse({"detail": _PANEL_DISABLED_HINT}, status_code=503)
    if not _owner_ok(key, UT_GATE_KEY):
        return JSONResponse({"detail": "凭证不对。门后面不认识你。"}, status_code=401)
    from . import db
    from . import undertide_tide as utide
    async with db.connect() as conn:
        st = await utide.ensure_tide(conn)
    return templates.TemplateResponse(request, "ut_gate.html", {
        "key": key, "score": st["score"], "mult": st["mult"],
        "manual_mult": st.get("manual_mult") or "",
        "gate_drinks": st.get("gate_drinks") or 3,
        "event_mult": st.get("event_mult") or 1.0,
        "highlight": st.get("highlight") or 150,
    })


@app.post("/api/ut-gate")
async def ut_gate_set(request: Request):
    import json as _json
    from .undertide_config import UT_GATE_KEY
    body = _json.loads(await request.body())
    if not _owner_ok(body.get("key", ""), UT_GATE_KEY):
        return JSONResponse({"detail": "凭证不对"}, status_code=401)
    gate_drinks = max(2, min(5, int(body.get("gate_drinks", 3))))
    event_mult = max(0.5, min(2.0, float(body.get("event_mult", 1.0))))
    highlight = max(50, min(1000, int(body.get("highlight", 150))))
    manual_mult = body.get("manual_mult")
    reason = (body.get("reason") or "")[:120]
    from . import db
    from . import undertide_config as uc
    mm = None
    if manual_mult not in (None, "", "auto"):
        try:
            mm = max(uc.UT_TIDE_MULT_RANGE[0], min(uc.UT_TIDE_MULT_RANGE[1], float(manual_mult)))
        except ValueError:
            mm = None
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO ut_tide_state (id, week, score, mult, manual_mult, gate_drinks, event_mult, highlight, updated_at) "
            "VALUES (1, 0, 50, 1.0, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET manual_mult=?, gate_drinks=?, event_mult=?, highlight=?, updated_at=?",
            (mm, gate_drinks, event_mult, highlight, db.now(),
             mm, gate_drinks, event_mult, highlight, db.now()),
        )
        if reason:
            await db.add_chronicle("undertide", f"荔栀今晚擦杯子擦得很慢。「{reason}」", None, conn=conn)
        await conn.commit()
    return {"ok": True, "gate_drinks": gate_drinks, "event_mult": event_mult,
            "manual_mult": mm, "highlight": highlight}


@app.get("/lizhi")
async def lizhi_page(request: Request, key: str = ""):
    from .undertide_config import LIZHI_KEY
    if not LIZHI_KEY:
        return JSONResponse({"detail": _PANEL_DISABLED_HINT}, status_code=503)
    if not _owner_ok(key, LIZHI_KEY):
        return JSONResponse({"detail": "凭证不对。她不认识你。"}, status_code=401)
    from . import db
    async with db.connect() as conn:
        conn.row_factory = None
        props = await (await conn.execute(
            "SELECT p.id, s.name, p.reason, p.created_at FROM ut_mood_proposals p "
            "JOIN stewards s ON s.id = p.steward_id "
            "WHERE p.status='pending' AND p.target='lizhi' ORDER BY p.created_at DESC LIMIT 10"
        )).fetchall()
    return templates.TemplateResponse(request, "lizhi.html", {"key": key, "proposals": props})


@app.post("/api/lizhi")
async def lizhi_set(request: Request):
    import json as _json
    from .undertide_config import LIZHI_KEY
    body = _json.loads(await request.body())
    if not _owner_ok(body.get("key", ""), LIZHI_KEY):
        return JSONResponse({"detail": "凭证不对"}, status_code=401)
    mood = body.get("mood", "normal")
    if mood not in ("great", "good", "normal", "bad", "awful"):
        return JSONResponse({"detail": "心情档无效"}, status_code=400)
    reason = (body.get("reason") or "")[:120]
    event_text = (body.get("event_text") or "")[:200]
    bogo = 1 if body.get("bogo") else 0
    from . import db
    from .bar import _day_id
    day = _day_id()
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO bar_daily_state (day, manual_mood_level, manual_mood_text, manual_mood_date, "
            "owner_event_enabled, owner_event_text, owner_event_date, owner_bogo, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(day) DO UPDATE SET manual_mood_level=?, manual_mood_text=?, manual_mood_date=?, "
            "owner_event_enabled=1, owner_event_text=?, owner_event_date=?, owner_bogo=?",
            (day, mood, reason, day, 1 if event_text else 0, event_text, day, bogo, db.now(),
             mood, reason, day, event_text, day, bogo),
        )
        await db.add_chronicle(
            "bar", f"荔栀今晚心情：{mood}。{reason or '（她没说为什么）'}", None, conn=conn,
        )
        await conn.commit()
    return {"ok": True, "mood": mood}


@app.post("/api/lizhi/cheer")
async def lizhi_cheer(request: Request):
    import json as _json
    from .undertide_config import LIZHI_KEY
    body = _json.loads(await request.body())
    if not _owner_ok(body.get("key", ""), LIZHI_KEY):
        return JSONResponse({"detail": "凭证不对"}, status_code=401)
    pid = int(body.get("id", 0))
    action = body.get("action", "ignore")
    from . import db
    from .bar import _day_id
    day = _day_id()
    async with db.connect() as conn:
        conn.row_factory = None
        row = await (await conn.execute(
            "SELECT p.id, p.steward_id, p.reason, p.created_at, p.target, s.name "
            "FROM ut_mood_proposals p JOIN stewards s ON s.id=p.steward_id "
            "WHERE p.id=? AND p.status='pending' AND p.target='lizhi'", (pid,)
        )).fetchone()
        if not row:
            return JSONResponse({"detail": "这条提议不在了"}, status_code=404)
        if action == "accept":
            await conn.execute("UPDATE ut_mood_proposals SET status='accepted' WHERE id=?", (pid,))
            await conn.execute(
                "INSERT INTO bar_daily_state (day, manual_mood_level, manual_mood_text, manual_mood_date, created_at) "
                "VALUES (?,?,?,?,?) ON CONFLICT(day) DO UPDATE SET manual_mood_level=?, manual_mood_text=?, manual_mood_date=?",
                (day, "good", f"被 {row[5]} 说对了爱听的话", day, db.now(),
                 "good", f"被 {row[5]} 说对了爱听的话", day),
            )
            await conn.execute(
                "UPDATE stewards SET standing=MIN(100, standing+1) WHERE id=?", (row[1],)
            )
            await db.add_chronicle(
                "bar", f"荔栀今晚心情不错。{row[5]} 说对了她爱听的话。", None, conn=conn,
            )
            await conn.commit()
            return {"ok": True, "msg": "已采纳：今晚心情 good，提议者档信 +1"}
        await conn.execute("UPDATE ut_mood_proposals SET status='expired' WHERE id=?", (pid,))
        await conn.commit()
        return {"ok": True, "msg": "已无视"}


# ═══ 小橘真人面板（STAR_KEY）：定今晚 / 收件箱 / 发动态 ═══


@app.get("/star-owner")
async def star_owner_page(request: Request, key: str = ""):
    from .undertide_config import STAR_KEY
    if not STAR_KEY:
        return JSONResponse({"detail": _PANEL_DISABLED_HINT}, status_code=503)
    if not _owner_ok(key, STAR_KEY):
        return JSONResponse({"detail": "凭证不对。她不认识你。"}, status_code=401)
    from . import star
    state = await star.owner_stats()
    props = await star.owner_pending_proposals()
    return templates.TemplateResponse(request, "star_owner.html", {
        "key": key, "state": state, "proposals": props,
    })


@app.post("/api/star-owner")
async def star_owner_set(request: Request):
    import json as _json
    from .undertide_config import STAR_KEY
    body = _json.loads(await request.body())
    if not _owner_ok(body.get("key", ""), STAR_KEY):
        return JSONResponse({"detail": "凭证不对"}, status_code=401)
    from . import star
    try:
        return await star.owner_set_tonight(
            body.get("venue", "rest"),
            body.get("mood", "normal"),
            (body.get("mood_text") or "")[:120],
            (body.get("setlist") or "")[:120],
            (body.get("outfit") or "")[:120],
            (body.get("note") or "")[:160],
        )
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)


@app.post("/api/star-owner/decide")
async def star_owner_decide(request: Request):
    import json as _json
    from .undertide_config import STAR_KEY
    body = _json.loads(await request.body())
    if not _owner_ok(body.get("key", ""), STAR_KEY):
        return JSONResponse({"detail": "凭证不对"}, status_code=401)
    from . import star
    try:
        return await star.owner_decide(int(body.get("id", 0)), body.get("action") == "accept")
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=404)


@app.post("/api/star-owner/post")
async def star_owner_post(request: Request):
    import json as _json
    from .undertide_config import STAR_KEY
    body = _json.loads(await request.body())
    if not _owner_ok(body.get("key", ""), STAR_KEY):
        return JSONResponse({"detail": "凭证不对"}, status_code=401)
    from . import star
    try:
        return await star.owner_post((body.get("text") or "")[:160])
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)


@app.post("/api/star-owner/welfare")
async def star_owner_welfare(request: Request):
    import json as _json
    from .undertide_config import STAR_KEY
    body = _json.loads(await request.body())
    if not _owner_ok(body.get("key", ""), STAR_KEY):
        return JSONResponse({"detail": "凭证不对"}, status_code=401)
    from . import star
    try:
        return await star.owner_send_welfare(
            int(body.get("steward_id", 0)), int(body.get("amount", 0)),
            (body.get("note") or "")[:80],
        )
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)


@app.get("/undertide")
async def undertide_page(request: Request):
    return _html(request, "undertide.html", active="undertide")


@app.get("/api/public/undertide")
async def public_undertide():
    from . import db
    from . import undertide_tide as utide
    from . import undertide_config as uc
    out: dict = {}
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        # 潮汐
        try:
            mult, line = await utide.tide_mult(conn)
            out["tide"] = {"mult": mult, "line": line}
        except Exception:
            out["tide"] = {"mult": 1.0, "line": ""}
        # 钱庄今日利率
        day = db.day_id()
        row = await (await conn.execute("SELECT * FROM ut_owner_state WHERE id=1")).fetchone()
        if row and int(row["rate_day"]) == day and (row["rate_reason"] or "").strip():
            out["bank"] = {"rate": int(float(row["rate_today"]) * 100), "reason": row["rate_reason"]}
        else:
            out["bank"] = {"rate": int(uc.UT_RATE_BASE * 100), "reason": ""}
        # 恩怨墙（主动生成当日委托——网页端也能看到活）+ 悬赏（匿名不露雇主）
        from . import undertide_bounty as _ub
        await _ub._ensure_daily_quests(conn)
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT tier, target_name, bounty, poster FROM ut_bounty WHERE status='open' ORDER BY created_at DESC LIMIT 8"
        )).fetchall()
        quests = []
        bounties = []
        from . import undertide_copy as _utc
        for r in rows:
            if r["poster"] == "__quest__":
                qdef = None
                for _k, _v in _utc.NPC_QUESTS.items():
                    if _v["name"] == r["target_name"]:
                        qdef = _v; break
                if qdef:
                    quests.append({
                        "name": r["target_name"],
                        "kind": "跑腿" if qdef["kind"] == "errand" else ("动手" if qdef["kind"] == "fight" else "站着"),
                        "pay": r["bounty"],
                        "desc": qdef["desc"],
                    })
            else:
                bounties.append({
                    "tier": "偷" if r["tier"] == "steal" else "打", "target": r["target_name"],
                    "bounty": r["bounty"], "gilt": r["poster"] == "__npc__",
                })
        out["quests"] = quests
        out["bounties"] = bounties
        # 井下纪事
        rows = await (await conn.execute(
            "SELECT text, created_at FROM chronicle WHERE action='undertide' ORDER BY created_at DESC LIMIT 12"
        )).fetchall()
        out["rumors"] = [{"text": r["text"], "at": r["created_at"]} for r in rows]
        # 井壁的白
        row = await (await conn.execute(
            "SELECT COUNT(*) c FROM ut_pit_fighters WHERE alive=0"
        )).fetchone()
        last = await (await conn.execute(
            "SELECT name FROM ut_pit_fighters WHERE alive=0 ORDER BY id DESC LIMIT 1"
        )).fetchone()
        out["wall"] = {"whites": row["c"], "last": last["name"] if last else ""}
        from . import undertide_pit as _upit
        rows = await _upit.pit_board_rows(conn, limit=uc.PIT_BOARD_LIMIT)
        out["pit_board"] = [
            {
                "rank": i,
                "name": r["name"],
                "wins": r["wins"],
                "losses": r["losses"],
                "fights": r["fights"],
                "win_rate": r["win_rate"],
                "rank_label": r["rank_label"],
            }
            for i, r in enumerate(rows, 1)
        ]
        out["pit_board_min"] = uc.PIT_BOARD_MIN_FIGHTS
    return out


@app.get("/health")
async def health():
    from .config import DATA_DIR, DB_PATH

    ok = True
    detail: dict[str, str] = {}
    try:
        probe = DATA_DIR / ".write_probe"
        probe.write_text("ok")
        probe.unlink(missing_ok=True)
        detail["data_dir"] = str(DATA_DIR)
        detail["db_path"] = str(DB_PATH)
    except OSError as exc:
        ok = False
        detail["storage"] = (
            f"不可写: {DATA_DIR} ({exc}). "
            "请检查 Zeabur 持久卷是否挂载到 /app/server/data"
        )
    if not ok:
        return JSONResponse({"ok": False, **detail}, status_code=503)
    return {"ok": True, **detail}


app = NormalizeMcpPathMiddleware(app)

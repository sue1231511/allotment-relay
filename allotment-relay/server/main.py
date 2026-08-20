from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

from . import db
from .config import STATIC_DIR, TEMPLATES_DIR
from .mcp_app import build_mcp_app

mcp_starlette, mcp_session_manager = build_mcp_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    async with mcp_session_manager.run():
        yield


app = FastAPI(title="Allotment Relay MCP", version="0.2.0", lifespan=lifespan)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/mcp", mcp_starlette)


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
    return templates.TemplateResponse(request, "index.html", {"active": None})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"active": None})


@app.get("/recover", response_class=HTMLResponse)
async def recover_page(request: Request):
    return templates.TemplateResponse(request, "recover.html", {"active": None})


@app.get("/allotments", response_class=HTMLResponse)
async def allotments_page(request: Request):
    return templates.TemplateResponse(request, "allotments.html", {"active": "allotments"})


@app.get("/bar", response_class=HTMLResponse)
async def bar_page(request: Request):
    return templates.TemplateResponse(request, "bar.html", {"active": "bar"})


@app.get("/eatery", response_class=HTMLResponse)
async def eatery_page(request: Request):
    return templates.TemplateResponse(request, "eatery.html", {"active": "eatery"})


class BarOrderRequest(BaseModel):
    api_key: str
    service: str
    host_name: str | None = None


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
    base = str(request.base_url).rstrip("/")
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
    base = str(request.base_url).rstrip("/")
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


@app.get("/api/public/eatery")
async def public_eatery():
    from . import eatery
    return await eatery.public_eatery_snapshot()


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


@app.get("/health")
async def health():
    return {"ok": True}

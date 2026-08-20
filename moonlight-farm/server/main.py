from contextlib import asynccontextmanager
from pathlib import Path

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


app = FastAPI(title="Moonlight Farm MCP", version="0.1.0", lifespan=lifespan)
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
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/recover", response_class=HTMLResponse)
async def recover_page(request: Request):
    return templates.TemplateResponse("recover.html", {"request": request})


@app.get("/garden", response_class=HTMLResponse)
async def garden_page(request: Request):
    return templates.TemplateResponse("garden.html", {"request": request})


@app.post("/api/keys/generate")
async def generate_key(body: KeyRequest):
    try:
        api_key = await db.create_api_key(body.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "api_key": api_key,
        "message": "钥匙只显示一次，请立即保存。",
        "mcp_url": f"/mcp/?api_key={api_key}",
        "curl_example": f'curl -H "Authorization: Bearer {api_key}" $BASE/mcp/',
    }


@app.post("/api/keys/recover")
async def recover_key(body: KeyRequest):
    api_key = await db.recover_api_key(body.email)
    if not api_key:
        raise HTTPException(status_code=404, detail="未找到该邮箱的钥匙")
    return {"api_key": api_key, "mcp_url": f"/mcp/?api_key={api_key}"}


@app.get("/api/public/stats")
async def public_stats():
    return await db.public_stats()


@app.get("/api/public/feed")
async def public_feed():
    return await db.public_feed()


@app.get("/api/public/gardens")
async def public_gardens():
    return await db.public_gardens()


@app.get("/health")
async def health():
    return {"ok": True}

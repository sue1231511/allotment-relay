"""聊天室表情包 — 仅人类网页；AI scan / say 不可见、不可发。"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import aiosqlite

from . import config, db

STICKER_DIR = config.DATA_DIR / "lounge_stickers"
STICKER_MAX_BYTES = 512 * 1024
STICKER_MAX_PER_STEWARD = 64
STICKER_MAX_BATCH = 12
STICKER_ALLOWED_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def sticker_dir_for(steward_id: int) -> Path:
    path = STICKER_DIR / str(int(steward_id))
    path.mkdir(parents=True, exist_ok=True)
    return path


def sticker_file_url(sticker_id: int) -> str:
    return f"/api/lounge/stickers/{int(sticker_id)}/file"


def _sticker_view(row: dict[str, Any]) -> dict[str, Any]:
    sid = int(row["id"])
    return {
        "id": sid,
        "url": sticker_file_url(sid),
        "created_at": int(row.get("created_at") or 0),
    }


async def list_stickers(steward_id: int) -> list[dict[str, Any]]:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (
            await conn.execute(
                """
                SELECT id, created_at FROM lounge_stickers
                WHERE steward_id=?
                ORDER BY id DESC
                """,
                (int(steward_id),),
            )
        ).fetchall()
    return [_sticker_view(dict(r)) for r in rows]


async def get_sticker_row(sticker_id: int) -> dict[str, Any] | None:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        row = await (
            await conn.execute(
                "SELECT * FROM lounge_stickers WHERE id=?",
                (int(sticker_id),),
            )
        ).fetchone()
    return dict(row) if row else None


async def sticker_file_path(sticker_id: int) -> Path:
    row = await get_sticker_row(sticker_id)
    if not row:
        raise ValueError("表情包不存在")
    path = STICKER_DIR / str(int(row["steward_id"])) / str(row["filename"])
    if not path.is_file():
        raise ValueError("表情包文件丢失")
    return path


def _ext_for(content_type: str, filename: str) -> str:
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype in STICKER_ALLOWED_EXT:
        return STICKER_ALLOWED_EXT[ctype]
    lower = (filename or "").lower()
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        if lower.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    raise ValueError("只支持 png / jpg / webp / gif 图片")


async def save_uploaded_stickers(
    steward_id: int,
    files: list[tuple[str, str, bytes]],
) -> list[dict[str, Any]]:
    """files: list of (filename, content_type, raw_bytes)."""
    if not files:
        raise ValueError("请选择要添加的表情包图片")
    if len(files) > STICKER_MAX_BATCH:
        raise ValueError(f"一次最多添加 {STICKER_MAX_BATCH} 张")

    existing = await list_stickers(steward_id)
    if len(existing) + len(files) > STICKER_MAX_PER_STEWARD:
        raise ValueError(
            f"表情包最多 {STICKER_MAX_PER_STEWARD} 张（已有 {len(existing)}）"
        )

    prepared: list[tuple[str, bytes]] = []
    for name, ctype, raw in files:
        data = raw or b""
        if not data:
            raise ValueError(f"{name or '图片'}是空文件")
        if len(data) > STICKER_MAX_BYTES:
            raise ValueError(f"单张不能超过 {STICKER_MAX_BYTES // 1024}KB")
        ext = _ext_for(ctype, name)
        prepared.append((f"{uuid.uuid4().hex}{ext}", data))

    folder = sticker_dir_for(steward_id)
    now = db.now()
    created: list[dict[str, Any]] = []
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        for filename, data in prepared:
            (folder / filename).write_bytes(data)
            cur = await conn.execute(
                """
                INSERT INTO lounge_stickers (steward_id, filename, created_at)
                VALUES (?, ?, ?)
                """,
                (int(steward_id), filename, now),
            )
            created.append(
                _sticker_view({"id": int(cur.lastrowid), "created_at": now})
            )
        await conn.commit()
    return created


async def delete_sticker(steward_id: int, sticker_id: int) -> None:
    row = await get_sticker_row(sticker_id)
    if not row or int(row["steward_id"]) != int(steward_id):
        raise ValueError("表情包不存在")
    path = STICKER_DIR / str(int(steward_id)) / str(row["filename"])
    async with db.connect() as conn:
        await conn.execute(
            "DELETE FROM lounge_stickers WHERE id=? AND steward_id=?",
            (int(sticker_id), int(steward_id)),
        )
        await conn.commit()
    path.unlink(missing_ok=True)

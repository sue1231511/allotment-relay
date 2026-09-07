"""聊天室表情包 — 仅人类网页；AI scan / say 不可见、不可发。"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import aiosqlite

from . import config, db

STICKER_DIR = config.DATA_DIR / "lounge_stickers"
STICKER_MAX_BYTES = 3 * 1024 * 1024
STICKER_MAX_PER_STEWARD = 64
STICKER_MAX_BATCH = 12
STICKER_MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def sticker_dir_for(steward_id: int) -> Path:
    path = STICKER_DIR / str(int(steward_id))
    path.mkdir(parents=True, exist_ok=True)
    return path


def sticker_file_url(sticker_id: int) -> str:
    return f"/api/lounge/stickers/{int(sticker_id)}/file"


def sticker_media_type(path: Path) -> str:
    return STICKER_MEDIA.get(path.suffix.lower(), "application/octet-stream")


def _kb(n: int) -> int:
    return max(1, int(n) // 1024)


def _sniff_image(data: bytes, filename: str) -> tuple[str, str]:
    """Return (ext, media_type) from magic bytes. Ignore claimed MIME / suffix."""
    label = filename or "图片"
    if not data:
        raise ValueError(f"{label}是空文件")
    head = data[:16]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return ".gif", "image/gif"
    if len(data) >= 12 and head.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp", "image/webp"
    if head[4:8] == b"ftyp" or b"ftypheic" in data[:24] or b"ftypheif" in data[:24]:
        raise ValueError(
            f"{label}是 iPhone 实况/HEIC，网页加不进去。请另存为 JPG、PNG 或 GIF 再添加。"
        )
    raise ValueError(
        f"{label}不是 png / jpg / gif / webp（当前文件头无法识别）。"
        "请换一张，或用相册里「导出图片」后再试。"
    )


def _sticker_view(row: dict[str, Any]) -> dict[str, Any]:
    sid = int(row["id"])
    name = str(row.get("filename") or "")
    ext = Path(name).suffix.lower()
    return {
        "id": sid,
        "url": sticker_file_url(sid),
        "created_at": int(row.get("created_at") or 0),
        "kind": "gif" if ext == ".gif" else "image",
        "mime": STICKER_MEDIA.get(ext, "application/octet-stream"),
    }


async def list_stickers(steward_id: int) -> list[dict[str, Any]]:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (
            await conn.execute(
                """
                SELECT id, filename, created_at FROM lounge_stickers
                WHERE steward_id=? AND COALESCE(deleted_at, 0)=0
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


async def save_uploaded_stickers(
    steward_id: int,
    files: list[tuple[str, str, bytes]],
) -> list[dict[str, Any]]:
    """files: list of (filename, content_type, raw_bytes)."""
    if not files:
        raise ValueError("请选择要添加的表情包图片（png / jpg / gif）")
    if len(files) > STICKER_MAX_BATCH:
        raise ValueError(f"一次最多添加 {STICKER_MAX_BATCH} 张")

    existing = await list_stickers(steward_id)
    if len(existing) + len(files) > STICKER_MAX_PER_STEWARD:
        raise ValueError(
            f"表情包最多 {STICKER_MAX_PER_STEWARD} 张（已有 {len(existing)}）。"
            "先删掉不用的再添加。"
        )

    prepared: list[tuple[str, bytes, str]] = []
    for name, _ctype, raw in files:
        data = raw or b""
        if not data:
            raise ValueError(f"{name or '图片'}是空文件")
        if len(data) > STICKER_MAX_BYTES:
            raise ValueError(
                f"{name or '图片'}太大了（{_kb(len(data))}KB，上限 {_kb(STICKER_MAX_BYTES)}KB）。"
                "动图请先压缩，静态图另存为较小的 jpg/png。"
            )
        ext, _mime = _sniff_image(data, name or "图片")
        prepared.append((f"{uuid.uuid4().hex}{ext}", data, ext))

    folder = sticker_dir_for(steward_id)
    now = db.now()
    created: list[dict[str, Any]] = []
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        for filename, data, _ext in prepared:
            (folder / filename).write_bytes(data)
            cur = await conn.execute(
                """
                INSERT INTO lounge_stickers (steward_id, filename, created_at)
                VALUES (?, ?, ?)
                """,
                (int(steward_id), filename, now),
            )
            created.append(
                _sticker_view(
                    {"id": int(cur.lastrowid), "filename": filename, "created_at": now}
                )
            )
        await conn.commit()
    return created


async def delete_sticker(steward_id: int, sticker_id: int) -> None:
    row = await get_sticker_row(sticker_id)
    if not row or int(row["steward_id"]) != int(steward_id):
        raise ValueError("表情包不存在")
    if int(row.get("deleted_at") or 0):
        raise ValueError("表情包不存在")
    now = db.now()
    async with db.connect() as conn:
        await conn.execute(
            """
            UPDATE lounge_stickers
            SET deleted_at=?
            WHERE id=? AND steward_id=? AND COALESCE(deleted_at, 0)=0
            """,
            (now, int(sticker_id), int(steward_id)),
        )
        await conn.commit()

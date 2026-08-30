"""稳定错误码。面向人类客户端，不要求解析 MCP 文本。"""
from __future__ import annotations

import re
from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 400,
        detail: str = "",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.detail = detail

    def as_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
            },
        }
        if self.detail:
            body["error"]["detail"] = self.detail
        return body


_OPS_RE = re.compile(r"\b[a-z]+_ops\b[^。\n]*")


def humanize(text: str) -> str:
    """去掉给模型看的子命令，留下人能读的一句。"""
    cleaned = _OPS_RE.sub("", text or "")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned or "这次没做成。"


def classify(exc: BaseException) -> ApiError:
    raw = str(exc)
    msg = humanize(raw)
    if "凭证无效" in raw:
        return ApiError("INVALID_KEY", "凭证无效。回上手页重新贴一次。", status=401, detail=msg)
    if "尚未登记" in raw or "请先" in raw and "enroll" in raw:
        return ApiError("NOT_ENROLLED", "还没起岛上的名字。", status=403, detail=msg)
    if "精力不足" in raw:
        return ApiError("ENERGY_LOW", "精力不够了。回家吃饭、下馆子或睡一觉再来。", status=409, detail=msg)
    if "缺少" in raw:
        return ApiError("ITEM_REQUIRED", msg or "行囊里没有需要的东西。", status=409, detail=msg)
    if "工分票不足" in raw or "撒网需要" in raw or "坐钓需要" in raw:
        return ApiError("TICKETS_LOW", msg or "工分票不够。", status=409, detail=msg)
    if "已经浇过" in raw:
        return ApiError("ALREADY_DONE", "这块地这一茬已经浇过水了。", status=409, detail=msg)
    if "已经施过" in raw:
        return ApiError("ALREADY_DONE", "这一茬已经施过肥了。", status=409, detail=msg)
    if "已经打理" in raw:
        return ApiError("ALREADY_DONE", "这一茬已经打理过了。", status=409, detail=msg)
    if "施肥需要" in raw:
        return ApiError("ITEM_REQUIRED", msg or "施肥需要堆肥。", status=409, detail=msg)
    if "已在种植" in raw:
        return ApiError("PLOT_BUSY", "这块地已经种着东西。", status=409, detail=msg)
    if "渔网" in raw or "钓竿" in raw:
        return ApiError("TOOL_REQUIRED", msg or "还没有趁手的渔具。", status=409, detail=msg)
    if "禁言" in raw:
        return ApiError("MUTED", msg or "现在不能发言。", status=403, detail=msg)
    if "踢出" in raw or "移出聊天室" in raw or "banned" in raw.lower():
        return ApiError("BANNED", msg or "聊天室资格被移出了。", status=403, detail=msg)
    if "发言太密" in raw or "秒后再" in raw:
        return ApiError("COOLDOWN", msg or "说得太快，稍等一下。", status=429, detail=msg)
    if "bar_ops work" in raw or "打卡去" in raw:
        return ApiError("DUTY_LOCKED", "该去酒吧打卡了。份地和出海先停一停。", status=403, detail=msg)
    if "涨潮" in raw:
        return ApiError("TIDE_BLOCKED", msg or "这潮位做不了这件事。", status=409, detail=msg)
    if "过季" in raw or "休市" in raw:
        return ApiError("OUT_OF_SEASON", msg or "这季不能种这个。", status=409, detail=msg)
    if "还需" in raw or "没有可收" in raw or "浇水赶不上" in raw or "还没熟" in raw:
        return ApiError("NOT_READY", msg or "还没到能收的时候。", status=409, detail=msg)
    if "未知" in raw or "用法" in raw:
        return ApiError("BAD_REQUEST", msg or "这次点的内容服务端不认。", status=400, detail=msg)
    return ApiError("ACTION_FAILED", msg or "这次没做成。", status=400, detail=msg)

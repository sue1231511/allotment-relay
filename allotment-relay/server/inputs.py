"""用户输入的数量 / 单价 / 票数解析。

所有来自 MCP command、HTTP body 的数量与金额都先过这里：必须是整数、≥1、
不超过 INPUT_MAX。负数和 0 一律拒绝——负数会让「扣票」变成「加票」、
让「取走物品」变成「凭空发物品」。
"""
from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)

# 合理性上限：远低于 SQLite 64 位整数，只用来挡「写个 99999999999999」的怪输入
INPUT_MAX = 10**9


def parse_positive_int(
    token: Any,
    label: str = "数量",
    *,
    maximum: int = INPUT_MAX,
) -> int:
    """把用户写的数字解析成 1..maximum 的整数，否则抛 ValueError（中文提示）。"""
    raw = str(token if token is not None else "").strip().rstrip(";,").lstrip("#")
    if raw[:1] in ("x", "X", "×") and len(raw) > 1:
        raw = raw[1:]
    try:
        value = int(raw)
    except (TypeError, ValueError):
        _log.info("parse_positive_int: 非整数 label=%s token=%r", label, token)
        raise ValueError(f"{label}须为整数，收到: {token!r}") from None
    if value < 1:
        _log.warning(
            "parse_positive_int: 拒绝 ≤0 label=%s token=%r value=%s",
            label, token, value, stack_info=True,
        )
        raise ValueError(f"{label}至少为 1，收到: {token!r}")
    if value > maximum:
        _log.warning(
            "parse_positive_int: 拒绝超大数 label=%s token=%r value=%s max=%s",
            label, token, value, maximum,
        )
        raise ValueError(f"{label}最多 {maximum}，收到: {token!r}")
    return value


def require_positive(value: Any, label: str = "数量") -> int:
    """已经是 int 的内部值再校验一次（DB 里读出来的旧数据也走这里）。"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label}不是整数: {value!r}") from None
    if n < 1:
        raise ValueError(f"{label}必须 ≥1，当前 {n}")
    return n

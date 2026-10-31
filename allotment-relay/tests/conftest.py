"""每个用例换一把新的数据库互斥锁。

``db._DB_MUTEX`` 是模块级 asyncio.Lock，一旦在某个事件循环里发生过争用就绑定到那个循环。
测试里 pytest-asyncio、``asyncio.run`` 会反复新建循环，不重置就会在后面的用例报
``Lock ... is bound to a different event loop``。线上只有一个循环，不受影响。
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _fresh_db_mutex():
    from server import db

    db._DB_MUTEX = asyncio.Lock()
    yield


@pytest.fixture
def pin_random(monkeypatch):
    """把某个模块里的 random.random() 钉成固定值，只影响那一个模块（别的 random 调用照旧）。

    用法：pin_random(server.some_module, 1.0)。1.0 表示「概率事件一律不发生」。
    直接 monkeypatch 模块里的 ``random.random`` 会改到全局 random 模块，连带别处的随机一起变。
    """
    import random as real_random

    class _Pinned:
        def __init__(self, value: float) -> None:
            self._value = value

        def random(self) -> float:
            return self._value

        def __getattr__(self, name: str):
            return getattr(real_random, name)

    def _pin(module, value: float = 1.0) -> None:
        monkeypatch.setattr(module, "random", _Pinned(value))

    return _pin

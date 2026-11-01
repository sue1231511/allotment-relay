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

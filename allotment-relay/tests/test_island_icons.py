#!/usr/bin/env python3
"""/island 不用 emoji 当图标：对照表是最新的，引用到的图标都画了，静态模板里没有 emoji。"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿]")
TEXT_SYMBOLS = set("★☆♡♥✓✔✗✘✕✖✦✧•·")


def test_emoji_map_is_up_to_date() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/gen_emoji_icons.py"), "--check"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_mapped_icon_is_drawn() -> None:
    icons_js = (ROOT / "server/static/island/ui/icons.js").read_text(encoding="utf-8")
    drawn = set(re.findall(r"^  ([a-z]+): `", icons_js, re.M))
    used = set(re.findall(r'"\S": "([a-z]+)"', (ROOT / "server/static/island/ui/emoji-map.js").read_text(encoding="utf-8")))
    assert used <= drawn, used - drawn
    assert "dot" in drawn


def test_static_templates_have_no_emoji() -> None:
    for rel in ("server/templates/island.html", "server/templates/partials/island-lounge.html"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        found = {ch for ch in EMOJI.findall(text) if ch not in TEXT_SYMBOLS}
        assert not found, (rel, found)


def test_app_starts_the_converter() -> None:
    app = (ROOT / "server/static/island/app.js").read_text(encoding="utf-8")
    assert "startEmojiSvg();" in app
    css = (ROOT / "server/static/island/island.css").read_text(encoding="utf-8")
    assert ".island-ico" in css

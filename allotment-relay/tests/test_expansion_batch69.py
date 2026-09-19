"""batch69：闭环强耦合、事件多选全覆盖、稀有履历扩册。"""
from __future__ import annotations


def test_event_choice_covers_named():
    from server import event_catalog, event_choice

    assert event_choice.cover_ok()
    assert event_choice.covered_count() >= event_catalog.named_count()
    for key in ("sail_tear", "pest", "sinkhole", "barn_fuss", "hold_leak", "epidemic"):
        spec = event_choice.CHOICES[key]
        assert len(spec["opts"]) >= 2, key


def test_loop_couple_and_ledger_rare():
    from server import loop_couple, play_cascade
    from server.ledger import is_notable

    assert loop_couple.couple_ok()
    assert callable(play_cascade.hint)
    for key in (
        "craft_gyotaku",
        "craft_boat_model",
        "craft_tide_stamp",
        "craft_npc_sign",
        "wreck_scrap",
        "craft_relic",
        "proc_black_salt",
        "dish_black_salt_fish_s3",
        "fish_lanternfish",
    ):
        assert is_notable(key), key
    assert not is_notable("crop_kale")
    assert not is_notable("fish_herring")


def test_docs_batch69():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    help_txt = (root / "server/mcp_dispatch.py").read_text(encoding="utf-8")
    assert "灾选" in help_txt
    assert "闭环" in (root / "server/game.py").read_text(encoding="utf-8")
    track = (root.parent / "docs/TIDE_FULL_EXPANSION.md").read_text(encoding="utf-8")
    assert "追踪清单已于" in track
    assert "## 追踪清单" not in track
    agents = (root.parent / "AGENTS.md").read_text(encoding="utf-8")
    assert "整岛扩展方案要边做边标" not in agents
    manual = (root / "server/templates/partials/island-manual-content.html").read_text(
        encoding="utf-8"
    )
    assert "看屋会提下一步" in manual
    assert "鱼拓船模邮票签名遗物" in manual

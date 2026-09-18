"""Batch 8: /api/v1/farm/events pests + treat."""
from __future__ import annotations


def test_pest_ui_actions_outdoor():
    from server import plot_pests

    plot = {"slot": 1, "orchard": 0, "greenhouse": 0, "pest_key": "aphid", "pest_level": 2}
    acts = plot_pests.ui_actions(plot, tickets=5, stock={})
    assert any(a["action"] == "施药" and not a["can"] for a in acts)
    acts_ok = plot_pests.ui_actions(plot, tickets=20, stock={})
    assert any(a["action"] == "施药" and a["can"] for a in acts_ok)


def test_pest_ui_actions_greenhouse_leak():
    from server import plot_pests

    plot = {"slot": 1, "greenhouse": 1, "pest_key": "gh_leak", "pest_level": 1}
    acts = plot_pests.ui_actions(plot, tickets=100, stock={})
    assert not any(a["action"] == "补网" and a["can"] for a in acts)
    acts2 = plot_pests.ui_actions(plot, tickets=100, stock={"drift_twine": 2})
    assert any(a["action"] == "补网" and a["can"] for a in acts2)


def test_pest_row_for_api_shape():
    from server import plot_pests

    row = plot_pests.pest_row_for_api(
        {"slot": 2, "orchard": 0, "greenhouse": 0, "pest_key": "weed", "pest_level": 1, "crop": "cabbage"},
        tickets=50,
        stock={},
    )
    assert row["slot"] == "#2"
    assert row["pest_name"]
    assert len(row["actions"]) >= 3

"""Tests for the engineering catalog shown in startup/status displays."""

import hermes_cli.banner as banner


def test_get_available_skills_returns_approved_engineering_catalog():
    catalog = banner.get_available_skills()

    assert catalog["dynamics"] == ["modal_frf_compute"]
    assert "sol103_deck_build" in catalog["nastran"]
    assert "sol111_deck_build" in catalog["nastran"]
    assert "srs_compute" in catalog["signals"]
    assert "hdf5_channel_summary" in catalog["data"]


def test_get_available_skills_returns_copy():
    catalog = banner.get_available_skills()
    catalog["signals"].append("mutated")

    assert "mutated" not in banner.get_available_skills()["signals"]


def test_get_available_skills_hides_stock_and_legacy_names():
    all_names = {
        name
        for tool_names in banner.get_available_skills().values()
        for name in tool_names
    }

    assert "github-auth" not in all_names
    assert "claude-code" not in all_names
    assert "codebase-inspection" not in all_names
    assert "ava_build_modal_deck" not in all_names
    assert "ava_run_shock_delta" not in all_names
    assert "modal_deck_builder" not in all_names

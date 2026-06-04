"""Tests for the AVA skills shown in startup/status displays."""

import hermes_cli.banner as banner


def test_get_available_skills_returns_curated_ava_skills():
    skills = banner.get_available_skills()

    assert skills == {
        "modal": ["modal_deck_builder", "modal_frf"],
        "nastran": ["bdf_model_summary", "op2_inspection"],
        "shock": ["shock_delta_v1", "shock_response_spectrum"],
    }


def test_get_available_skills_returns_copy():
    skills = banner.get_available_skills()
    skills["shock"].append("mutated")

    assert "mutated" not in banner.get_available_skills()["shock"]


def test_get_available_skills_hides_stock_catalog_names():
    all_names = {
        name
        for skill_names in banner.get_available_skills().values()
        for name in skill_names
    }

    assert "github-auth" not in all_names
    assert "claude-code" not in all_names
    assert "codebase-inspection" not in all_names

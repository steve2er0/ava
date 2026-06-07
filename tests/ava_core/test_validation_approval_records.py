"""Validation gate tests for approved AVA engineering skills."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATION_ROOT = REPO_ROOT / "ava_core" / "validation"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_validation_layer_directories_exist():
    for name in ("golden_cases", "expected_outputs", "regression_tests", "approval_records"):
        assert (VALIDATION_ROOT / name).is_dir(), f"missing validation/{name}"


def test_approved_engineering_skills_have_validation_evidence():
    records = sorted((VALIDATION_ROOT / "approval_records").glob("*.json"))
    assert records, "at least one approval record should exist"

    for record_path in records:
        record = _load_json(record_path)
        if record.get("status") != "approved":
            continue
        if record.get("skill_type") != "engineering":
            continue

        skill = record["skill"]
        skill_path = REPO_ROOT / record["skill_path"]
        golden_path = REPO_ROOT / record["golden_cases"]
        expected_path = REPO_ROOT / record["expected_outputs"]
        regression_path = REPO_ROOT / record["regression_tests"]

        assert skill_path.exists(), f"{skill}: approved skill path does not exist"
        assert golden_path.exists(), f"{skill}: golden case manifest missing"
        assert expected_path.exists(), f"{skill}: expected output manifest missing"
        assert regression_path.exists(), f"{skill}: regression procedure missing"

        golden = _load_json(golden_path)
        expected = _load_json(expected_path)
        golden_case_ids = {case["id"] for case in golden.get("cases", [])}
        expected_case_ids = {
            item["case_id"] for item in expected.get("expected_outputs", [])
        }
        validated_on = set(record.get("validated_on", []))

        assert golden.get("skill") == skill
        assert expected.get("skill") == skill
        assert golden_case_ids, f"{skill}: approved skills require golden cases"
        assert validated_on, f"{skill}: approved skills require validated_on cases"
        assert validated_on <= golden_case_ids, (
            f"{skill}: approval record references unknown golden cases "
            f"{sorted(validated_on - golden_case_ids)}"
        )
        assert validated_on <= expected_case_ids, (
            f"{skill}: approval record references cases without expected outputs "
            f"{sorted(validated_on - expected_case_ids)}"
        )
        assert golden_case_ids <= expected_case_ids, (
            f"{skill}: every golden case needs an expected output"
        )

        regression_text = regression_path.read_text(encoding="utf-8")
        for case_id in validated_on:
            assert case_id in regression_text, (
                f"{skill}: regression procedure does not mention {case_id}"
            )

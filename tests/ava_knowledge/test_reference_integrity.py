import json
import re
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_ROOT = REPO_ROOT / "ava_knowledge"
REFERENCE_INDEX = KNOWLEDGE_ROOT / "references" / "reference_index.json"
REF_ID_RE = re.compile(r"\bREF-[A-Z0-9][A-Z0-9-]*\b")
RELEASED_STATUS_RE = re.compile(
    r"(?im)^(status|knowledge_status):\s*(approved|released)\b"
)


def _reference_index() -> dict[str, dict[str, object]]:
    data = json.loads(REFERENCE_INDEX.read_text(encoding="utf-8"))
    references = data["references"]
    return {str(ref["id"]): ref for ref in references}


def _is_placeholder(ref: dict[str, object]) -> bool:
    kind = str(ref.get("kind", "")).lower()
    status = str(ref.get("status", "")).lower()
    return "placeholder" in kind or "placeholder" in status


def _markdown_ref_ids(path: Path) -> set[str]:
    return set(REF_ID_RE.findall(path.read_text(encoding="utf-8")))


def _yaml_ref_ids(value: object) -> set[str]:
    if isinstance(value, dict):
        found: set[str] = set()
        for key, item in value.items():
            if key == "source_refs" and isinstance(item, list):
                found.update(str(ref_id) for ref_id in item)
            else:
                found.update(_yaml_ref_ids(item))
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for item in value:
            found.update(_yaml_ref_ids(item))
        return found
    return set()


def test_reference_index_ids_are_unique_and_complete() -> None:
    data = json.loads(REFERENCE_INDEX.read_text(encoding="utf-8"))
    references = data["references"]
    ids = [ref["id"] for ref in references]

    assert len(ids) == len(set(ids))
    for ref in references:
        assert ref["id"].startswith("REF-")
        assert ref.get("title")
        assert ref.get("kind")
        assert ref.get("status")
        assert ref.get("citation")
        if not _is_placeholder(ref):
            assert ref.get("source_url")


def test_markdown_theory_artifacts_have_references_sections() -> None:
    checked_roots = [
        KNOWLEDGE_ROOT / "concepts",
        KNOWLEDGE_ROOT / "extracts",
    ]

    missing = []
    for root in checked_roots:
        for path in root.rglob("*.md"):
            if path.name == "README.md":
                continue
            text = path.read_text(encoding="utf-8")
            if "## References" not in text or not _markdown_ref_ids(path):
                missing.append(path.relative_to(REPO_ROOT).as_posix())

    assert missing == []


def test_all_markdown_reference_ids_exist_in_index() -> None:
    known_refs = _reference_index()
    unknown: dict[str, list[str]] = {}

    for path in KNOWLEDGE_ROOT.rglob("*.md"):
        missing = sorted(_markdown_ref_ids(path) - known_refs.keys())
        if missing:
            unknown[path.relative_to(REPO_ROOT).as_posix()] = missing

    assert unknown == {}


def test_rule_yaml_has_source_refs_and_uses_known_references() -> None:
    known_refs = _reference_index()
    missing_source_refs = []
    unknown_refs: dict[str, list[str]] = {}

    for path in (KNOWLEDGE_ROOT / "rules").rglob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        ref_ids = _yaml_ref_ids(data)
        if not ref_ids:
            missing_source_refs.append(path.relative_to(REPO_ROOT).as_posix())
        missing = sorted(ref_ids - known_refs.keys())
        if missing:
            unknown_refs[path.relative_to(REPO_ROOT).as_posix()] = missing

    assert missing_source_refs == []
    assert unknown_refs == {}


def test_approved_or_released_knowledge_does_not_use_placeholders() -> None:
    known_refs = _reference_index()
    placeholder_refs = {
        ref_id for ref_id, ref in known_refs.items() if _is_placeholder(ref)
    }
    violations: dict[str, list[str]] = {}

    for path in KNOWLEDGE_ROOT.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if RELEASED_STATUS_RE.search(text):
            placeholders_used = sorted(_markdown_ref_ids(path) & placeholder_refs)
            if placeholders_used:
                violations[path.relative_to(REPO_ROOT).as_posix()] = placeholders_used

    for path in (KNOWLEDGE_ROOT / "rules").rglob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        status = str(data.get("status", "")).lower()
        knowledge_status = str(data.get("knowledge_status", "")).lower()
        if status in {"approved", "released"} or knowledge_status in {
            "approved",
            "released",
        }:
            placeholders_used = sorted(_yaml_ref_ids(data) & placeholder_refs)
            if placeholders_used:
                violations[path.relative_to(REPO_ROOT).as_posix()] = placeholders_used

    assert violations == {}

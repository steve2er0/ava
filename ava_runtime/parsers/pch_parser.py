"""Small NASTRAN PCH summary parser for approved AVA tools."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


RESPONSE_KEYWORDS = (
    "DISPLACEMENT",
    "VELOCITY",
    "ACCELERATION",
    "SPCFORCES",
    "OLOAD",
    "FORCE",
    "STRESS",
    "STRAIN",
)
_NUMBER_RE = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[EeDd][-+]?\d+)?")


@dataclass(frozen=True)
class PchRecord:
    """A compact numeric PCH row."""

    response_type: str
    entity_id: int | None
    abscissa: float | None
    values: tuple[float, ...]


@dataclass(frozen=True)
class PchSummary:
    """Summary of parsed PCH blocks."""

    path: Path
    response_counts: dict[str, int]
    record_count: int
    entity_ids: tuple[int, ...] = field(default_factory=tuple)
    metadata_lines: tuple[str, ...] = field(default_factory=tuple)


def _numbers_from_line(line: str) -> list[float]:
    return [float(match.group(0).replace("D", "E").replace("d", "e")) for match in _NUMBER_RE.finditer(line)]


def _response_type_from_line(line: str) -> str | None:
    upper = line.upper()
    for keyword in RESPONSE_KEYWORDS:
        if keyword in upper:
            return keyword
    return None


def parse_pch_records(path: str | Path) -> list[PchRecord]:
    """Parse numeric PCH records using a conservative block-state heuristic."""

    pch_path = Path(path)
    current_response = "UNKNOWN"
    records: list[PchRecord] = []
    for raw_line in pch_path.read_text(encoding="utf-8", errors="replace").splitlines():
        response_type = _response_type_from_line(raw_line)
        if response_type is not None:
            current_response = response_type
            continue
        if raw_line.lstrip().startswith("$"):
            continue
        values = _numbers_from_line(raw_line)
        if len(values) < 2:
            continue
        first = values[0]
        entity_id = int(first) if abs(first - int(first)) < 1.0e-9 and abs(first) > 1.0 else None
        abscissa = values[1] if entity_id is not None and len(values) > 1 else values[0]
        payload = tuple(values[2:] if entity_id is not None else values[1:])
        records.append(
            PchRecord(
                response_type=current_response,
                entity_id=entity_id,
                abscissa=abscissa,
                values=payload,
            )
        )
    return records


def summarize_pch(path: str | Path, *, metadata_limit: int = 40) -> PchSummary:
    """Summarize a PCH file without exposing full response data to the LLM."""

    pch_path = Path(path)
    records = parse_pch_records(pch_path)
    counts = Counter(record.response_type for record in records)
    entity_ids = sorted({record.entity_id for record in records if record.entity_id is not None})
    metadata_lines: list[str] = []
    for raw_line in pch_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("$"):
            metadata_lines.append(stripped[:160])
            if len(metadata_lines) >= metadata_limit:
                break
    return PchSummary(
        path=pch_path,
        response_counts=dict(sorted(counts.items())),
        record_count=len(records),
        entity_ids=tuple(entity_ids),
        metadata_lines=tuple(metadata_lines),
    )


def pch_summary_dict(summary: PchSummary) -> dict:
    """Return a JSON-serializable PCH summary."""

    return {
        "path": str(summary.path),
        "response_counts": summary.response_counts,
        "record_count": summary.record_count,
        "entity_count": len(summary.entity_ids),
        "entity_ids": list(summary.entity_ids),
        "metadata_lines": list(summary.metadata_lines),
    }


def records_to_rows(records: Iterable[PchRecord]) -> list[dict]:
    """Serialize selected parsed records for optional findings artifacts."""

    return [
        {
            "response_type": record.response_type,
            "entity_id": record.entity_id,
            "abscissa": record.abscissa,
            "values": list(record.values),
        }
        for record in records
    ]

"""NASTRAN F06 health scanning helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


FATAL_MARKERS = (
    "USER FATAL MESSAGE",
    "SYSTEM FATAL MESSAGE",
    "FATAL",
)
ERROR_MARKERS = (
    "USER INFORMATION MESSAGE 9999",
    "ERROR",
)
WARNING_MARKERS = (
    "WARNING",
    "USER WARNING MESSAGE",
)


@dataclass(frozen=True)
class F06Finding:
    """One health finding from an F06 file."""

    severity: str
    line_number: int
    text: str


def scan_f06(path: str | Path, *, context_chars: int = 220) -> dict:
    """Scan an F06 file for fatal, error, and warning indicators."""

    f06_path = Path(path)
    findings: list[F06Finding] = []
    for line_number, raw_line in enumerate(
        f06_path.read_text(encoding="utf-8", errors="replace").splitlines(),
        start=1,
    ):
        upper = raw_line.upper()
        severity = None
        if any(marker in upper for marker in FATAL_MARKERS):
            severity = "fatal"
        elif any(marker in upper for marker in ERROR_MARKERS):
            severity = "error"
        elif any(marker in upper for marker in WARNING_MARKERS):
            severity = "warning"
        if severity is None:
            continue
        findings.append(
            F06Finding(
                severity=severity,
                line_number=line_number,
                text=raw_line.strip()[:context_chars],
            )
        )

    severity_counts = {"fatal": 0, "error": 0, "warning": 0}
    for finding in findings:
        severity_counts[finding.severity] += 1
    status = "failed" if severity_counts["fatal"] else "warnings" if severity_counts["warning"] else "ok"
    if severity_counts["error"] and status == "ok":
        status = "errors"
    return {
        "path": str(f06_path),
        "status": status,
        "severity_counts": severity_counts,
        "finding_count": len(findings),
        "findings": [
            {
                "severity": finding.severity,
                "line_number": finding.line_number,
                "text": finding.text,
            }
            for finding in findings
        ],
    }

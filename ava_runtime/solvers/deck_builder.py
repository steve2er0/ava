"""NASTRAN deck construction helpers for the AVA runtime.

The runtime should generate repeatable solver inputs without spreading deck
syntax through workflow code. This module provides a small set of builders for
common analysis setups while leaving advanced bulk-data authoring to the caller
or to future specialized builders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class ModalDeckRequest:
    """Inputs required to build a basic SOL 103 modal deck."""

    title: str
    spc_id: int
    method_id: int
    mode_count: int
    frequency_upper_hz: float
    bulk_data_lines: Sequence[str] = field(default_factory=tuple)
    case_control_overrides: Sequence[str] = field(default_factory=tuple)


def build_modal_case_control(request: ModalDeckRequest) -> List[str]:
    """Return case-control lines for a standard modal extraction run."""

    lines = [
        f"TITLE = {request.title}",
        "ECHO = NONE",
        f"SPC = {request.spc_id}",
        f"METHOD = {request.method_id}",
        "DISPLACEMENT(PLOT) = ALL",
    ]
    lines.extend(request.case_control_overrides)
    return lines


def build_modal_bulk_data(request: ModalDeckRequest) -> List[str]:
    """Return the minimal bulk-data statements for a modal run.

    The `EIGRL` card is kept intentionally narrow: mode count and upper
    frequency bound are usually sufficient for starter workflow runs.
    """

    lines = [
        "PARAM,POST,-1",
        f"EIGRL,{request.method_id},,{request.frequency_upper_hz:.3f},{request.mode_count}",
    ]
    lines.extend(request.bulk_data_lines)
    return lines


def render_deck(
    solution_sequence: int,
    case_control_lines: Iterable[str],
    bulk_data_lines: Iterable[str],
) -> str:
    """Render a complete NASTRAN deck from prebuilt sections."""

    deck_lines = [f"SOL {solution_sequence}", "CEND"]
    deck_lines.extend(case_control_lines)
    deck_lines.append("BEGIN BULK")
    deck_lines.extend(bulk_data_lines)
    deck_lines.append("ENDDATA")
    return "\n".join(deck_lines) + "\n"


def build_modal_deck(request: ModalDeckRequest) -> str:
    """Build a complete SOL 103 deck."""

    return render_deck(
        solution_sequence=103,
        case_control_lines=build_modal_case_control(request),
        bulk_data_lines=build_modal_bulk_data(request),
    )


def write_deck(path: str | Path, text: str) -> Path:
    """Write a deck to disk and return the normalized path."""

    deck_path = Path(path)
    deck_path.write_text(text, encoding="utf-8")
    return deck_path

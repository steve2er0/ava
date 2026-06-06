"""NASTRAN deck construction helpers for the AVA runtime.

The runtime should generate repeatable solver inputs without spreading deck
syntax through workflow code. This module provides a small set of builders for
common analysis setups while leaving advanced bulk-data authoring to the caller
or to future specialized builders.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Mapping, Sequence


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


@dataclass(frozen=True)
class Sol111DeckRequest:
    """Inputs required to build a basic SOL 111 frequency-response deck."""

    title: str
    spc_id: int
    method_id: int
    frequency_set_id: int
    load_set_id: int
    damping_table_id: int | None = None
    frequencies_hz: Sequence[float] = field(default_factory=tuple)
    output_requests: Sequence[str] = field(default_factory=lambda: ("DISPLACEMENT(PUNCH)=ALL",))
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


def build_sol111_case_control(request: Sol111DeckRequest) -> List[str]:
    """Return case-control lines for a standard SOL 111 deck."""

    lines = [
        f"TITLE = {request.title}",
        "ECHO = NONE",
        f"SPC = {request.spc_id}",
        f"METHOD = {request.method_id}",
        f"FREQUENCY = {request.frequency_set_id}",
        f"DLOAD = {request.load_set_id}",
    ]
    if request.damping_table_id is not None:
        lines.append(f"SDAMPING = {request.damping_table_id}")
    lines.extend(request.output_requests)
    lines.extend(request.case_control_overrides)
    return lines


def _freq1_lines(set_id: int, frequencies_hz: Sequence[float]) -> List[str]:
    if not frequencies_hz:
        return []
    if len(frequencies_hz) >= 2:
        sorted_freqs = sorted(float(freq) for freq in frequencies_hz)
        deltas = [round(sorted_freqs[index + 1] - sorted_freqs[index], 9) for index in range(len(sorted_freqs) - 1)]
        if len(set(deltas)) == 1 and deltas[0] > 0.0:
            return [f"FREQ1,{set_id},{sorted_freqs[0]:.9g},{deltas[0]:.9g},{len(sorted_freqs) - 1}"]
    chunks = []
    values = [f"{float(freq):.9g}" for freq in frequencies_hz]
    for index in range(0, len(values), 6):
        prefix = f"FREQ,{set_id}" if index == 0 else f"FREQ,{set_id}"
        chunks.append(",".join([prefix, *values[index : index + 6]]))
    return chunks


def build_sol111_bulk_data(request: Sol111DeckRequest) -> List[str]:
    """Return bulk-data statements for a minimal SOL 111 setup."""

    lines = [
        "PARAM,POST,-1",
        f"EIGRL,{request.method_id},,,",
    ]
    lines.extend(_freq1_lines(request.frequency_set_id, request.frequencies_hz))
    lines.extend(request.bulk_data_lines)
    return lines


def build_sol111_deck(request: Sol111DeckRequest) -> str:
    """Build a complete SOL 111 deck."""

    return render_deck(
        solution_sequence=111,
        case_control_lines=build_sol111_case_control(request),
        bulk_data_lines=build_sol111_bulk_data(request),
    )


def _load_mapping(path: str | Path) -> Mapping:
    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    if config_path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise RuntimeError("PyYAML is required to read SOL111 YAML configs") from exc
        loaded = yaml.safe_load(text)
    else:
        loaded = json.loads(text)
    if not isinstance(loaded, Mapping):
        raise ValueError("SOL111 config must be a mapping")
    return loaded


def sol111_request_from_mapping(config: Mapping) -> Sol111DeckRequest:
    """Build a SOL111 request from JSON/YAML-compatible config."""

    return Sol111DeckRequest(
        title=str(config.get("title", "AVA SOL111 Run")),
        spc_id=int(config.get("spc_id", 1)),
        method_id=int(config.get("method_id", 100)),
        frequency_set_id=int(config.get("frequency_set_id", 10)),
        load_set_id=int(config.get("load_set_id", 20)),
        damping_table_id=int(config["damping_table_id"]) if config.get("damping_table_id") is not None else None,
        frequencies_hz=tuple(float(freq) for freq in config.get("frequencies_hz", ())),
        output_requests=tuple(str(line) for line in config.get("output_requests", ("DISPLACEMENT(PUNCH)=ALL",))),
        bulk_data_lines=tuple(str(line) for line in config.get("bulk_data_lines", ())),
        case_control_overrides=tuple(str(line) for line in config.get("case_control_overrides", ())),
    )


def build_sol111_deck_from_config(config: Mapping | str | Path) -> str:
    """Build a SOL111 deck from a mapping or a JSON/YAML config path."""

    mapping = _load_mapping(config) if isinstance(config, (str, Path)) else config
    return build_sol111_deck(sol111_request_from_mapping(mapping))


def write_deck(path: str | Path, text: str) -> Path:
    """Write a deck to disk and return the normalized path."""

    deck_path = Path(path)
    deck_path.write_text(text, encoding="utf-8")
    return deck_path

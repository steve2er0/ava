"""Lightweight OP2 access helpers for the AVA runtime.

The binary OP2 format is extensive and solver-specific enough that a complete
implementation would dominate this starter runtime layer. AVA only needs a
small, dependable subset at this stage:

- validate that a result file looks like a Fortran unformatted stream
- capture coarse binary metadata for run logging
- load deterministic tabular exports derived from OP2 result channels

This keeps the runtime practical without introducing heavy third-party parsing
dependencies before the workflow contracts are stable.
"""

from __future__ import annotations

import csv
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence


@dataclass(frozen=True)
class Op2StreamInfo:
    """Coarse metadata about an OP2-like binary stream."""

    path: Path
    file_size_bytes: int
    endian: str
    first_record_bytes: int
    looks_like_fortran_stream: bool


@dataclass(frozen=True)
class ComplexResponsePoint:
    """A single complex-valued response sample from a tabular export."""

    response_id: str
    abscissa: float
    real: float
    imag: float

    @property
    def magnitude(self) -> float:
        """Return the sample magnitude."""

        return (self.real**2 + self.imag**2) ** 0.5


@dataclass(frozen=True)
class ModalMode:
    """A modal result row extracted from OP2 metadata or an OP2-derived table."""

    mode: int
    frequency_hz: float
    eigenvalue: float | None = None
    generalized_mass: float | None = None
    generalized_stiffness: float | None = None


@dataclass(frozen=True)
class Op2ModalSummary:
    """Modal summary exposed by the approved OP2 tool."""

    path: Path
    modes: tuple[ModalMode, ...]
    stream_info: Op2StreamInfo | None = None
    source: str = "unknown"


def inspect_op2_stream(path: str | Path) -> Op2StreamInfo:
    """Inspect a binary stream and verify the first Fortran record marker.

    Many OP2 files are written as Fortran unformatted records. This function
    does not decode the full payload; it only checks that the first record is
    structurally consistent and records the detected endian convention.
    """

    stream_path = Path(path)
    file_size = stream_path.stat().st_size
    if file_size < 12:
        raise ValueError(f"OP2 stream is too small to inspect: {stream_path}")

    with stream_path.open("rb") as handle:
        marker_bytes = handle.read(4)
        for endian in ("<", ">"):
            first_record = struct.unpack(f"{endian}i", marker_bytes)[0]
            if first_record <= 0 or first_record > file_size - 8:
                continue
            handle.seek(4 + first_record)
            trailing = struct.unpack(f"{endian}i", handle.read(4))[0]
            if trailing == first_record:
                return Op2StreamInfo(
                    path=stream_path,
                    file_size_bytes=file_size,
                    endian="little" if endian == "<" else "big",
                    first_record_bytes=first_record,
                    looks_like_fortran_stream=True,
                )
        raise ValueError(f"Unable to validate OP2 stream markers: {stream_path}")


def _optional_float(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(str(value))


def _modal_mode_from_mapping(row: Mapping[str, object], index: int) -> ModalMode:
    mode_value = row.get("mode") or row.get("mode_id") or row.get("mode_number") or index
    frequency_value = (
        row.get("frequency_hz")
        or row.get("freq_hz")
        or row.get("frequency")
        or row.get("freq")
    )
    if frequency_value is None:
        raise ValueError("Modal row is missing a frequency_hz/frequency column")
    return ModalMode(
        mode=int(float(str(mode_value))),
        frequency_hz=float(str(frequency_value)),
        eigenvalue=_optional_float(row.get("eigenvalue")),
        generalized_mass=_optional_float(row.get("generalized_mass")),
        generalized_stiffness=_optional_float(row.get("generalized_stiffness")),
    )


def load_modal_table(path: str | Path) -> list[ModalMode]:
    """Load modal rows from a solver-neutral CSV or JSON export.

    This keeps the approved tool usable without forcing pyNastran into AVA's
    default dependency set. Real OP2 decoding can be layered in when that
    optional dependency is available.
    """

    table_path = Path(path)
    if table_path.suffix.lower() == ".json":
        payload = json.loads(table_path.read_text(encoding="utf-8"))
        rows = payload["modes"] if isinstance(payload, dict) and "modes" in payload else payload
        if not isinstance(rows, list):
            raise ValueError("Modal JSON must be a list or an object with a 'modes' list")
        return [_modal_mode_from_mapping(row, index + 1) for index, row in enumerate(rows)]

    modes: list[ModalMode] = []
    with table_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Modal CSV is missing a header row")
        for index, row in enumerate(reader, start=1):
            modes.append(_modal_mode_from_mapping(row, index))
    return modes


def summarize_op2_modal(path: str | Path) -> Op2ModalSummary:
    """Summarize OP2 modal content or a modal table export.

    CSV/JSON inputs return mode rows. Binary OP2 inputs are validated as
    Fortran streams and return coarse stream metadata unless an optional OP2
    decoder is added by the deployment.
    """

    op2_path = Path(path)
    suffix = op2_path.suffix.lower()
    if suffix in {".csv", ".json"}:
        modes = tuple(load_modal_table(op2_path))
        return Op2ModalSummary(path=op2_path, modes=modes, source=suffix.lstrip("."))

    stream_info = inspect_op2_stream(op2_path)
    return Op2ModalSummary(
        path=op2_path,
        modes=(),
        stream_info=stream_info,
        source="op2_stream_metadata",
    )


def modal_summary_dict(summary: Op2ModalSummary) -> dict:
    """Return a JSON-serializable modal summary."""

    frequencies = [mode.frequency_hz for mode in summary.modes]
    payload = {
        "path": str(summary.path),
        "source": summary.source,
        "mode_count": len(summary.modes),
        "frequency_min_hz": min(frequencies) if frequencies else None,
        "frequency_max_hz": max(frequencies) if frequencies else None,
        "modes": [
            {
                "mode": mode.mode,
                "frequency_hz": mode.frequency_hz,
                "eigenvalue": mode.eigenvalue,
                "generalized_mass": mode.generalized_mass,
                "generalized_stiffness": mode.generalized_stiffness,
            }
            for mode in summary.modes
        ],
    }
    if summary.stream_info is not None:
        payload["stream_info"] = {
            "file_size_bytes": summary.stream_info.file_size_bytes,
            "endian": summary.stream_info.endian,
            "first_record_bytes": summary.stream_info.first_record_bytes,
            "looks_like_fortran_stream": summary.stream_info.looks_like_fortran_stream,
        }
    return payload


def modes_to_modal_terms(
    modes: Sequence[ModalMode],
    *,
    damping_ratio: float = 0.02,
    modal_constant: float = 1.0,
) -> list[dict]:
    """Convert modal rows into the generic FRF modal-term schema."""

    return [
        {
            "natural_frequency_hz": mode.frequency_hz,
            "damping_ratio": damping_ratio,
            "modal_constant": modal_constant,
        }
        for mode in modes
    ]


def load_complex_table(
    path: str | Path,
    *,
    response_id_field: str = "response_id",
    abscissa_field: str = "frequency_hz",
    real_field: str = "real",
    imag_field: str = "imag",
) -> List[ComplexResponsePoint]:
    """Load a solver-neutral complex result table from CSV.

    The table is intended to be generated from an OP2 result extraction step
    upstream. Required columns are the abscissa, real component, and imaginary
    component. A response identifier column is optional; when absent, the
    series is assigned to `default`.
    """

    table_path = Path(path)
    samples: List[ComplexResponsePoint] = []
    with table_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required_fields = {abscissa_field, real_field, imag_field}
        missing = required_fields - set(reader.fieldnames or [])
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise ValueError(f"Missing required complex table columns: {missing_text}")
        has_response_id = response_id_field in (reader.fieldnames or [])
        for row in reader:
            response_id = row[response_id_field].strip() if has_response_id else "default"
            samples.append(
                ComplexResponsePoint(
                    response_id=response_id or "default",
                    abscissa=float(row[abscissa_field]),
                    real=float(row[real_field]),
                    imag=float(row[imag_field]),
                )
            )
    return samples


def group_by_response_id(
    samples: Iterable[ComplexResponsePoint],
) -> Dict[str, List[ComplexResponsePoint]]:
    """Group a complex table into named response channels."""

    grouped: Dict[str, List[ComplexResponsePoint]] = {}
    for sample in samples:
        grouped.setdefault(sample.response_id, []).append(sample)
    for series in grouped.values():
        series.sort(key=lambda item: item.abscissa)
    return grouped

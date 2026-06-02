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
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List


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

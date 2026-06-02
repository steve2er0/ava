"""BDF parsing utilities for the AVA runtime.

The AVA runtime does not need a full finite-element preprocessor to start
executing knowledge workflows. This module focuses on a conservative subset of
NASTRAN Bulk Data File parsing that is useful for workflow framing:

- count key cards
- read GRID coordinates
- compute model bounds
- expose a compact summary for downstream analysis and reporting

The implementation accepts both comma-separated and fixed-field cards and
ignores advanced continuation formats that are not required by the starter
runtime layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Tuple


@dataclass(frozen=True)
class GridPoint:
    """A structural grid point with coordinates expressed in the basic frame."""

    node_id: int
    x: float
    y: float
    z: float
    cp: int = 0


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned bounds for a set of structural grid points."""

    xmin: float
    xmax: float
    ymin: float
    ymax: float
    zmin: float
    zmax: float

    @property
    def span(self) -> Tuple[float, float, float]:
        """Return the extent of the model along each basic coordinate axis."""

        return (
            self.xmax - self.xmin,
            self.ymax - self.ymin,
            self.zmax - self.zmin,
        )


@dataclass(frozen=True)
class BdfModelSummary:
    """Compact metadata needed by AVA workflows."""

    path: Path
    grid_count: int
    element_counts: Dict[str, int]
    mass_element_count: int
    bounding_box: BoundingBox | None


def _parse_float(value: str) -> float:
    """Parse a NASTRAN numeric field, including D-format exponents."""

    return float(value.replace("D", "E").replace("d", "e"))


def _split_fields(line: str) -> List[str]:
    """Split a BDF card into stripped fields.

    The function supports both comma-separated free field input and the classic
    fixed-width 8-character field style used in many legacy decks.
    """

    payload = line.split("$", 1)[0].rstrip("\n")
    if not payload.strip():
        return []
    if "," in payload:
        return [field.strip() for field in payload.split(",")]
    return [payload[index : index + 8].strip() for index in range(0, 72, 8)]


def iter_bulk_cards(path: str | Path) -> Iterator[Tuple[str, List[str]]]:
    """Yield non-comment bulk data cards from a BDF file.

    Continuation lines are intentionally skipped in this starter parser because
    the runtime summary only relies on single-line cards such as GRID, shell
    elements, and concentrated masses.
    """

    with Path(path).open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            stripped = raw_line.lstrip()
            if not stripped or stripped.startswith("$"):
                continue
            if stripped.startswith(("CEND", "BEGIN BULK", "ENDDATA")):
                continue
            if stripped.startswith(("+", "*")):
                continue
            fields = _split_fields(raw_line)
            if not fields or not fields[0]:
                continue
            yield fields[0].upper(), fields


def parse_grid_points(path: str | Path) -> Dict[int, GridPoint]:
    """Return GRID coordinates indexed by node ID."""

    grids: Dict[int, GridPoint] = {}
    for card_name, fields in iter_bulk_cards(path):
        if card_name != "GRID" or len(fields) < 6:
            continue
        node_id = int(fields[1])
        cp = int(fields[2]) if len(fields) > 2 and fields[2] else 0
        x = _parse_float(fields[3]) if len(fields) > 3 and fields[3] else 0.0
        y = _parse_float(fields[4]) if len(fields) > 4 and fields[4] else 0.0
        z = _parse_float(fields[5]) if len(fields) > 5 and fields[5] else 0.0
        grids[node_id] = GridPoint(node_id=node_id, x=x, y=y, z=z, cp=cp)
    return grids


def compute_bounding_box(points: Iterable[GridPoint]) -> BoundingBox | None:
    """Compute an axis-aligned bounding box from an iterable of grid points."""

    point_list = list(points)
    if not point_list:
        return None
    xs = [point.x for point in point_list]
    ys = [point.y for point in point_list]
    zs = [point.z for point in point_list]
    return BoundingBox(
        xmin=min(xs),
        xmax=max(xs),
        ymin=min(ys),
        ymax=max(ys),
        zmin=min(zs),
        zmax=max(zs),
    )


def summarize_bdf(path: str | Path) -> BdfModelSummary:
    """Create a compact structural summary for workflow framing.

    The summary is intentionally minimal but useful for pipeline logging and
    review: model size, approximate type mix, and physical extent.
    """

    element_counts: Dict[str, int] = {}
    mass_element_count = 0
    for card_name, _fields in iter_bulk_cards(path):
        if card_name.startswith("C") and card_name != "CORD2R":
            element_counts[card_name] = element_counts.get(card_name, 0) + 1
        if card_name in {"CONM1", "CONM2", "CMASS1", "CMASS2", "CMASS3", "CMASS4"}:
            mass_element_count += 1
    grids = parse_grid_points(path)
    return BdfModelSummary(
        path=Path(path),
        grid_count=len(grids),
        element_counts=dict(sorted(element_counts.items())),
        mass_element_count=mass_element_count,
        bounding_box=compute_bounding_box(grids.values()),
    )

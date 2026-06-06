"""Fatigue damage spectrum screening utilities.

This is a deterministic lightweight FDS implementation for AVA workflows. It
uses the existing pseudo-acceleration SRS response as the oscillator response
measure and converts it into a relative damage index. The output is useful for
screening, tool-chain tests, and equivalent-PSD bookkeeping; detailed fatigue
certification should use a validated specialist implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ava_runtime.analysis.srs import compute_srs


@dataclass(frozen=True)
class FdsPoint:
    """One fatigue damage spectrum sample."""

    frequency_hz: float
    damage_index: float
    equivalent_psd: float


@dataclass(frozen=True)
class FdsResult:
    """Fatigue damage spectrum result."""

    damping_ratio: float
    fatigue_exponent: float
    points: tuple[FdsPoint, ...]


def compute_fds(
    time_s: Sequence[float],
    acceleration_g: Sequence[float],
    natural_frequencies_hz: Iterable[float],
    *,
    damping_ratio: float = 0.05,
    fatigue_exponent: float = 6.0,
) -> FdsResult:
    """Compute a relative fatigue damage spectrum from a time history."""

    if fatigue_exponent <= 0.0:
        raise ValueError("Fatigue exponent must be positive")
    srs = compute_srs(
        time_s,
        acceleration_g,
        natural_frequencies_hz,
        damping_ratio=damping_ratio,
    )
    duration = max(time_s) - min(time_s)
    points = []
    for point in srs.points:
        cycles = max(point.natural_frequency_hz * duration, 1.0)
        damage = cycles * (abs(point.pseudo_acceleration_g) ** fatigue_exponent)
        equivalent_psd = damage / max(point.natural_frequency_hz ** max(fatigue_exponent - 1.0, 1.0), 1.0e-12)
        points.append(
            FdsPoint(
                frequency_hz=point.natural_frequency_hz,
                damage_index=damage,
                equivalent_psd=equivalent_psd,
            )
        )
    return FdsResult(
        damping_ratio=damping_ratio,
        fatigue_exponent=fatigue_exponent,
        points=tuple(points),
    )


def fds_result_dict(result: FdsResult) -> dict:
    """Return a JSON-serializable FDS result."""

    peak = max(result.points, key=lambda point: point.damage_index) if result.points else None
    return {
        "damping_ratio": result.damping_ratio,
        "fatigue_exponent": result.fatigue_exponent,
        "point_count": len(result.points),
        "peak_damage_frequency_hz": peak.frequency_hz if peak else None,
        "peak_damage_index": peak.damage_index if peak else None,
        "points": [
            {
                "frequency_hz": point.frequency_hz,
                "damage_index": point.damage_index,
                "equivalent_psd": point.equivalent_psd,
            }
            for point in result.points
        ],
    }

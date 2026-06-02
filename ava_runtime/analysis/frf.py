"""Frequency-response utilities for the AVA runtime.

The starter implementation uses classical modal superposition to compute a
complex receptance-like response under unit harmonic forcing. This is useful
for screening studies, convergence checks, and lightweight post-processing when
the workflow does not need a full external solver run.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from typing import Iterable, Sequence, Tuple


@dataclass(frozen=True)
class ModalTerm:
    """A single modal contribution used in superposed FRF calculations."""

    natural_frequency_hz: float
    damping_ratio: float
    modal_constant: float


@dataclass(frozen=True)
class FrequencyResponsePoint:
    """A complex response value at one frequency sample."""

    frequency_hz: float
    complex_response: complex

    @property
    def magnitude(self) -> float:
        """Return the response magnitude."""

        return abs(self.complex_response)

    @property
    def phase_degrees(self) -> float:
        """Return the response phase in degrees."""

        return math.degrees(cmath.phase(self.complex_response))


@dataclass(frozen=True)
class FrequencyResponseResult:
    """Container for a sampled frequency response function."""

    response_type: str
    points: Tuple[FrequencyResponsePoint, ...]


def compute_modal_frf(
    modes: Iterable[ModalTerm],
    frequencies_hz: Sequence[float],
    *,
    response_type: str = "displacement",
) -> FrequencyResponseResult:
    """Compute a modal FRF for the requested response quantity.

    Supported response types are `displacement`, `velocity`, and
    `acceleration`. The modal constants are assumed to already reflect the
    generalized forcing and recovery terms for the response quantity location.
    """

    supported = {"displacement", "velocity", "acceleration"}
    if response_type not in supported:
        supported_text = ", ".join(sorted(supported))
        raise ValueError(f"Unsupported FRF response type {response_type!r}; expected one of {supported_text}")

    modal_terms = tuple(modes)
    response_points = []
    for frequency_hz in frequencies_hz:
        omega = 2.0 * math.pi * frequency_hz
        complex_sum = 0j
        for mode in modal_terms:
            omega_n = 2.0 * math.pi * mode.natural_frequency_hz
            denominator = (omega_n**2 - omega**2) + 2j * mode.damping_ratio * omega_n * omega
            base_response = mode.modal_constant / denominator
            if response_type == "displacement":
                complex_sum += base_response
            elif response_type == "velocity":
                complex_sum += 1j * omega * base_response
            else:
                complex_sum += -(omega**2) * base_response
        response_points.append(
            FrequencyResponsePoint(
                frequency_hz=frequency_hz,
                complex_response=complex_sum,
            )
        )
    return FrequencyResponseResult(response_type=response_type, points=tuple(response_points))


def estimate_convergence_delta_percent(
    baseline: FrequencyResponseResult,
    candidate: FrequencyResponseResult,
) -> float:
    """Return the worst-case magnitude delta between two FRF results.

    The two results must be sampled at the same frequencies and for the same
    response quantity. The returned value is a percent difference relative to
    the baseline magnitude, using a small floor to avoid division by zero.
    """

    if baseline.response_type != candidate.response_type:
        raise ValueError("FRF results must use the same response type for comparison")
    if len(baseline.points) != len(candidate.points):
        raise ValueError("FRF results must have the same sample count for comparison")

    deltas = []
    for left, right in zip(baseline.points, candidate.points):
        if not math.isclose(left.frequency_hz, right.frequency_hz, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("FRF frequency grids do not match")
        reference = max(left.magnitude, 1.0e-12)
        deltas.append(abs(right.magnitude - left.magnitude) / reference * 100.0)
    return max(deltas, default=0.0)

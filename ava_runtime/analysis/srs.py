"""Shock Response Spectrum calculations for the AVA runtime.

The implementation computes a pseudo-acceleration SRS from a base-acceleration
time history using Newmark-beta integration of a unit-mass SDOF oscillator.
This is suitable for workflow screening and for validating that the runtime can
generate shock metrics without a mandatory external solver dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence, Tuple

STANDARD_GRAVITY_M_PER_S2 = 9.80665


@dataclass(frozen=True)
class ShockSpectrumPoint:
    """One frequency sample from a pseudo-acceleration SRS."""

    natural_frequency_hz: float
    pseudo_acceleration_g: float
    relative_displacement_mm: float


@dataclass(frozen=True)
class ShockSpectrumResult:
    """A discrete shock response spectrum."""

    damping_ratio: float
    points: Tuple[ShockSpectrumPoint, ...]


def _validate_time_history(time_s: Sequence[float], base_acceleration_g: Sequence[float]) -> float:
    """Validate a uniform time history and return its time step."""

    if len(time_s) != len(base_acceleration_g):
        raise ValueError("Time and acceleration series must have the same length")
    if len(time_s) < 2:
        raise ValueError("At least two time samples are required for SRS calculation")

    steps = [time_s[index + 1] - time_s[index] for index in range(len(time_s) - 1)]
    dt = steps[0]
    if dt <= 0.0:
        raise ValueError("Time history must be strictly increasing")
    for step in steps[1:]:
        if not math.isclose(step, dt, rel_tol=1e-6, abs_tol=1e-12):
            raise ValueError("SRS calculation requires a uniform time step")
    return dt


def compute_srs(
    time_s: Sequence[float],
    base_acceleration_g: Sequence[float],
    natural_frequencies_hz: Iterable[float],
    *,
    damping_ratio: float = 0.05,
) -> ShockSpectrumResult:
    """Compute a pseudo-acceleration SRS from a base-acceleration time history."""

    dt = _validate_time_history(time_s, base_acceleration_g)
    if damping_ratio < 0.0:
        raise ValueError("Damping ratio must be non-negative")

    beta = 0.25
    gamma = 0.5
    forcing = [-sample * STANDARD_GRAVITY_M_PER_S2 for sample in base_acceleration_g]
    spectrum_points = []

    for natural_frequency_hz in natural_frequencies_hz:
        if natural_frequency_hz <= 0.0:
            raise ValueError("Natural frequencies must be positive")

        omega_n = 2.0 * math.pi * natural_frequency_hz
        stiffness = omega_n**2
        damping = 2.0 * damping_ratio * omega_n
        a0 = 1.0 / (beta * dt**2)
        a1 = gamma / (beta * dt)
        a2 = 1.0 / (beta * dt)
        a3 = 1.0 / (2.0 * beta) - 1.0
        a4 = gamma / beta - 1.0
        a5 = dt * (gamma / (2.0 * beta) - 1.0)
        effective_stiffness = stiffness + a0 + a1 * damping

        displacement = 0.0
        velocity = 0.0
        acceleration = forcing[0] - damping * velocity - stiffness * displacement
        max_abs_displacement = 0.0

        for force in forcing[1:]:
            effective_force = (
                force
                + a0 * displacement
                + a2 * velocity
                + a3 * acceleration
                + damping * (a1 * displacement + a4 * velocity + a5 * acceleration)
            )
            next_displacement = effective_force / effective_stiffness
            next_acceleration = a0 * (next_displacement - displacement) - a2 * velocity - a3 * acceleration
            next_velocity = velocity + dt * ((1.0 - gamma) * acceleration + gamma * next_acceleration)

            displacement = next_displacement
            velocity = next_velocity
            acceleration = next_acceleration
            max_abs_displacement = max(max_abs_displacement, abs(displacement))

        pseudo_acceleration_g = (omega_n**2 * max_abs_displacement) / STANDARD_GRAVITY_M_PER_S2
        spectrum_points.append(
            ShockSpectrumPoint(
                natural_frequency_hz=natural_frequency_hz,
                pseudo_acceleration_g=pseudo_acceleration_g,
                relative_displacement_mm=max_abs_displacement * 1000.0,
            )
        )

    return ShockSpectrumResult(damping_ratio=damping_ratio, points=tuple(spectrum_points))

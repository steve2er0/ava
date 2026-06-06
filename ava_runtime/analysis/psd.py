"""Power spectral density utilities for AVA approved tools.

The implementation uses a small stdlib DFT so the default AVA install can run
PSD tests without NumPy/SciPy. It is intended for moderate engineering
summaries and regression tests; high-volume processing can swap in a faster
adapter later without changing the tool contract.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class PsdPoint:
    """One one-sided PSD sample."""

    frequency_hz: float
    psd: float


@dataclass(frozen=True)
class PsdResult:
    """PSD result plus integrated RMS."""

    points: tuple[PsdPoint, ...]
    rms: float
    method: str


def _window_values(name: str, size: int) -> list[float]:
    if size <= 0:
        raise ValueError("Window size must be positive")
    normalized = name.lower()
    if normalized in {"boxcar", "rect", "rectangular", "none"}:
        return [1.0] * size
    if normalized in {"hann", "hanning"}:
        if size == 1:
            return [1.0]
        return [0.5 - 0.5 * math.cos(2.0 * math.pi * index / (size - 1)) for index in range(size)]
    raise ValueError(f"Unsupported PSD window {name!r}")


def _segments(samples: Sequence[float], segment_size: int, overlap: float) -> list[list[float]]:
    if not 0.0 <= overlap < 1.0:
        raise ValueError("Overlap must be in [0, 1)")
    if segment_size <= 1:
        raise ValueError("Segment size must be greater than one")
    if len(samples) < segment_size:
        raise ValueError("Not enough samples for the requested segment size")
    step = max(1, int(round(segment_size * (1.0 - overlap))))
    return [
        [float(value) for value in samples[start : start + segment_size]]
        for start in range(0, len(samples) - segment_size + 1, step)
    ]


def _dft(values: Sequence[float]) -> list[complex]:
    n = len(values)
    bins: list[complex] = []
    for k in range(n // 2 + 1):
        total = 0j
        for index, value in enumerate(values):
            total += value * cmath.exp(-2j * math.pi * k * index / n)
        bins.append(total)
    return bins


def rms_from_psd(points: Sequence[PsdPoint]) -> float:
    """Integrate a one-sided PSD with the trapezoidal rule and return RMS."""

    if len(points) < 2:
        return 0.0
    area = 0.0
    for left, right in zip(points, points[1:]):
        df = right.frequency_hz - left.frequency_hz
        area += 0.5 * (left.psd + right.psd) * df
    return math.sqrt(max(area, 0.0))


def calculate_psd_welch(
    samples: Sequence[float],
    sample_rate_hz: float,
    *,
    segment_size: int | None = None,
    overlap: float = 0.5,
    window: str = "hann",
    demean: bool = True,
) -> PsdResult:
    """Compute a one-sided Welch PSD."""

    if sample_rate_hz <= 0.0:
        raise ValueError("Sample rate must be positive")
    if segment_size is None:
        segment_size = min(256, len(samples))
    segments = _segments(samples, segment_size, overlap)
    weights = _window_values(window, segment_size)
    window_power = sum(value * value for value in weights)
    if window_power <= 0.0:
        raise ValueError("Window power must be positive")

    accum = [0.0] * (segment_size // 2 + 1)
    for segment in segments:
        if demean:
            mean = sum(segment) / len(segment)
            segment = [value - mean for value in segment]
        windowed = [value * weight for value, weight in zip(segment, weights)]
        spectrum = _dft(windowed)
        for index, coeff in enumerate(spectrum):
            scale = 1.0 / (sample_rate_hz * window_power)
            if index not in {0, segment_size // 2}:
                scale *= 2.0
            accum[index] += (abs(coeff) ** 2) * scale

    points = tuple(
        PsdPoint(
            frequency_hz=index * sample_rate_hz / segment_size,
            psd=value / len(segments),
        )
        for index, value in enumerate(accum)
    )
    return PsdResult(points=points, rms=rms_from_psd(points), method="welch")


def calculate_psd_maximax(
    channels: Sequence[Sequence[float]] | Sequence[float],
    sample_rate_hz: float,
    *,
    segment_size: int | None = None,
    overlap: float = 0.5,
    window: str = "hann",
) -> PsdResult:
    """Compute a maximax PSD envelope across channels and segments."""

    if not channels:
        raise ValueError("At least one channel is required")
    first = channels[0]  # type: ignore[index]
    if isinstance(first, (int, float)):
        channel_list = [channels]  # type: ignore[list-item]
    else:
        channel_list = list(channels)  # type: ignore[arg-type]

    results = [
        calculate_psd_welch(
            channel,
            sample_rate_hz,
            segment_size=segment_size,
            overlap=overlap,
            window=window,
        )
        for channel in channel_list
    ]
    point_count = len(results[0].points)
    max_points = []
    for index in range(point_count):
        frequency = results[0].points[index].frequency_hz
        max_psd = max(result.points[index].psd for result in results)
        max_points.append(PsdPoint(frequency_hz=frequency, psd=max_psd))
    points = tuple(max_points)
    return PsdResult(points=points, rms=rms_from_psd(points), method="maximax")


def psd_result_dict(result: PsdResult) -> dict:
    """Return a JSON-serializable PSD result."""

    peak = max(result.points, key=lambda point: point.psd) if result.points else None
    return {
        "method": result.method,
        "point_count": len(result.points),
        "rms": result.rms,
        "peak_frequency_hz": peak.frequency_hz if peak else None,
        "peak_psd": peak.psd if peak else None,
        "points": [
            {"frequency_hz": point.frequency_hz, "psd": point.psd}
            for point in result.points
        ],
    }

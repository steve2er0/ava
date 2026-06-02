"""Dependency-light FRF plotting utilities for the AVA runtime.

The runtime should be able to generate review-ready plots in restricted
environments where a full plotting stack may not be installed. This module
renders FRF magnitude data to a simple SVG file using only the standard
library.
"""

from __future__ import annotations

import math
from html import escape
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from ava_runtime.analysis.frf import FrequencyResponseResult


def _scale_points(points: Sequence[Tuple[float, float]], width: int, height: int) -> List[Tuple[float, float]]:
    """Scale x-y data into SVG canvas coordinates."""

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    xspan = xmax - xmin if xmax > xmin else 1.0
    yspan = ymax - ymin if ymax > ymin else 1.0

    scaled = []
    for x_value, y_value in points:
        x_canvas = 70.0 + (x_value - xmin) / xspan * (width - 110.0)
        y_canvas = height - 50.0 - (y_value - ymin) / yspan * (height - 90.0)
        scaled.append((x_canvas, y_canvas))
    return scaled


def write_frf_svg(
    result: FrequencyResponseResult,
    output_path: str | Path,
    *,
    title: str = "Frequency Response Function",
) -> Path:
    """Render an FRF magnitude plot to an SVG file.

    The x-axis uses a logarithmic frequency scale. The y-axis is rendered in dB
    relative to the raw magnitude value.
    """

    if not result.points:
        raise ValueError("FRF plot requires at least one response point")

    width = 960
    height = 540
    magnitudes_db = []
    for point in result.points:
        if point.frequency_hz <= 0.0:
            raise ValueError("FRF plot requires strictly positive frequencies")
        magnitude = max(point.magnitude, 1.0e-18)
        magnitudes_db.append((math.log10(point.frequency_hz), 20.0 * math.log10(magnitude)))
    scaled = _scale_points(magnitudes_db, width, height)
    polyline = " ".join(f"{x_coord:.2f},{y_coord:.2f}" for x_coord, y_coord in scaled)

    frequencies = [point.frequency_hz for point in result.points]
    x_min = min(frequencies)
    x_max = max(frequencies)
    db_values = [value for _x, value in magnitudes_db]
    y_min = min(db_values)
    y_max = max(db_values)

    svg_text = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#fbfbfc" />
  <text x="70" y="35" font-family="Helvetica, Arial, sans-serif" font-size="22" fill="#1f2933">{escape(title)}</text>
  <text x="70" y="{height - 15}" font-family="Helvetica, Arial, sans-serif" font-size="13" fill="#52606d">Frequency [Hz] (log scale)</text>
  <text x="20" y="70" transform="rotate(-90, 20, 70)" font-family="Helvetica, Arial, sans-serif" font-size="13" fill="#52606d">Magnitude [dB]</text>
  <line x1="70" y1="{height - 50}" x2="{width - 40}" y2="{height - 50}" stroke="#334e68" stroke-width="1.5" />
  <line x1="70" y1="60" x2="70" y2="{height - 50}" stroke="#334e68" stroke-width="1.5" />
  <polyline fill="none" stroke="#0b7285" stroke-width="2.5" points="{polyline}" />
  <text x="70" y="{height - 28}" font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#334e68">{x_min:.2f}</text>
  <text x="{width - 90}" y="{height - 28}" font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#334e68">{x_max:.2f}</text>
  <text x="28" y="{height - 50}" font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#334e68">{y_min:.1f}</text>
  <text x="28" y="66" font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#334e68">{y_max:.1f}</text>
</svg>
"""

    target = Path(output_path)
    target.write_text(svg_text, encoding="utf-8")
    return target

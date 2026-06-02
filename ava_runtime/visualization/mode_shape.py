"""Mode-shape rendering helpers for the AVA runtime.

The starter renderer produces a simple SVG projection showing undeformed and
deformed node locations. It is intended for lightweight engineering review when
full 3D post-processing tools are not available in the execution environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class NodeModeVector:
    """A node position plus modal displacement components."""

    node_id: int
    x: float
    y: float
    z: float
    dx: float
    dy: float
    dz: float


def scale_mode_shape(vectors: Sequence[NodeModeVector], deformation_fraction: float = 0.15) -> Tuple[NodeModeVector, ...]:
    """Scale modal displacements to a readable fraction of the model span."""

    if not vectors:
        raise ValueError("At least one mode vector is required")

    xs = [vector.x for vector in vectors]
    ys = [vector.y for vector in vectors]
    zs = [vector.z for vector in vectors]
    span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1.0)
    max_modal_displacement = max(
        (vector.dx**2 + vector.dy**2 + vector.dz**2) ** 0.5 for vector in vectors
    )
    if max_modal_displacement == 0.0:
        return tuple(vectors)

    scale_factor = deformation_fraction * span / max_modal_displacement
    return tuple(
        NodeModeVector(
            node_id=vector.node_id,
            x=vector.x,
            y=vector.y,
            z=vector.z,
            dx=vector.dx * scale_factor,
            dy=vector.dy * scale_factor,
            dz=vector.dz * scale_factor,
        )
        for vector in vectors
    )


def write_mode_shape_svg(
    vectors: Sequence[NodeModeVector],
    output_path: str | Path,
    *,
    view: str = "xy",
    title: str = "Mode Shape",
) -> Path:
    """Render undeformed and deformed node positions to SVG."""

    if view not in {"xy", "xz", "yz"}:
        raise ValueError("Supported views are 'xy', 'xz', and 'yz'")

    scaled_vectors = scale_mode_shape(vectors)
    axis_map = {
        "xy": ("x", "y", "dx", "dy"),
        "xz": ("x", "z", "dx", "dz"),
        "yz": ("y", "z", "dy", "dz"),
    }
    axis_a, axis_b, disp_a, disp_b = axis_map[view]

    def select(vector: NodeModeVector, name: str) -> float:
        return getattr(vector, name)

    undeformed = [(select(vector, axis_a), select(vector, axis_b)) for vector in scaled_vectors]
    deformed = [
        (select(vector, axis_a) + select(vector, disp_a), select(vector, axis_b) + select(vector, disp_b))
        for vector in scaled_vectors
    ]

    xs = [point[0] for point in undeformed + deformed]
    ys = [point[1] for point in undeformed + deformed]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    xspan = xmax - xmin if xmax > xmin else 1.0
    yspan = ymax - ymin if ymax > ymin else 1.0

    def project(point: Tuple[float, float]) -> Tuple[float, float]:
        x_canvas = 70.0 + (point[0] - xmin) / xspan * 780.0
        y_canvas = 470.0 - (point[1] - ymin) / yspan * 380.0
        return x_canvas, y_canvas

    svg_elements: List[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="920" height="540" viewBox="0 0 920 540">',
        '  <rect width="100%" height="100%" fill="#fbfbfc" />',
        f'  <text x="70" y="35" font-family="Helvetica, Arial, sans-serif" font-size="22" fill="#1f2933">{escape(title)}</text>',
        f'  <text x="70" y="60" font-family="Helvetica, Arial, sans-serif" font-size="13" fill="#52606d">View: {escape(view.upper())}</text>',
    ]

    for vector, undeformed_point, deformed_point in zip(scaled_vectors, undeformed, deformed):
        ux, uy = project(undeformed_point)
        dx, dy = project(deformed_point)
        svg_elements.append(f'  <line x1="{ux:.2f}" y1="{uy:.2f}" x2="{dx:.2f}" y2="{dy:.2f}" stroke="#9aa5b1" stroke-width="1.0" />')
        svg_elements.append(f'  <circle cx="{ux:.2f}" cy="{uy:.2f}" r="2.2" fill="#7b8794" />')
        svg_elements.append(f'  <circle cx="{dx:.2f}" cy="{dy:.2f}" r="2.8" fill="#0b7285" />')
        svg_elements.append(
            f'  <text x="{dx + 4.0:.2f}" y="{dy - 4.0:.2f}" font-family="Helvetica, Arial, sans-serif" font-size="10" fill="#334e68">{vector.node_id}</text>'
        )

    svg_elements.append("</svg>\n")
    target = Path(output_path)
    target.write_text("\n".join(svg_elements), encoding="utf-8")
    return target

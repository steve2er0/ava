"""Lightweight BDF parsing and diagnostics for AVA engineering tools.

The runtime intentionally avoids depending on a full finite-element
preprocessor. This module supports the common single-line bulk-data cards that
AVA needs for model inventory, basic connectivity checks, and conservative
mass rollups. Advanced continuation-heavy decks should still be handled by a
dedicated preprocessor or pyNastran-backed workflow.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Mapping, Sequence, Tuple


SHELL_ELEMENT_NODE_FIELDS: Mapping[str, tuple[int, ...]] = {
    "CTRIA3": (3, 4, 5),
    "CQUAD4": (3, 4, 5, 6),
}
LINE_ELEMENT_NODE_FIELDS: Mapping[str, tuple[int, ...]] = {
    "CBAR": (3, 4),
    "CBEAM": (3, 4),
    "CROD": (3, 4),
    "CONROD": (2, 3),
}
SOLID_ELEMENT_NODE_START: Mapping[str, int] = {
    "CTETRA": 3,
    "CPENTA": 3,
    "CHEXA": 3,
    "CPYRAM": 3,
}
MASS_ELEMENT_CARDS = {"CONM1", "CONM2", "CMASS1", "CMASS2", "CMASS3", "CMASS4"}


@dataclass(frozen=True)
class GridPoint:
    """A structural grid point with coordinates expressed in its declared frame."""

    node_id: int
    x: float
    y: float
    z: float
    cp: int = 0

    @property
    def coordinates(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass(frozen=True)
class Element:
    """A finite-element card reduced to the fields needed by AVA checks."""

    element_id: int
    card_name: str
    property_id: int | None
    node_ids: tuple[int, ...]


@dataclass(frozen=True)
class PropertyCard:
    """A property card and the material IDs it references."""

    property_id: int
    card_name: str
    material_ids: tuple[int, ...] = field(default_factory=tuple)
    thickness: float | None = None
    area: float | None = None


@dataclass(frozen=True)
class MaterialCard:
    """A material card with optional density."""

    material_id: int
    card_name: str
    density: float | None = None


@dataclass(frozen=True)
class MassElement:
    """A concentrated or scalar mass element."""

    element_id: int
    card_name: str
    node_id: int | None
    mass: float | None


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
        return (
            self.xmax - self.xmin,
            self.ymax - self.ymin,
            self.zmax - self.zmin,
        )


@dataclass(frozen=True)
class BdfModel:
    """Parsed BDF subset used by AVA tools."""

    path: Path
    grids: Mapping[int, GridPoint]
    elements: Mapping[int, Element]
    properties: Mapping[int, PropertyCard]
    materials: Mapping[int, MaterialCard]
    masses: Mapping[int, MassElement]
    coordinate_systems: Mapping[int, str]
    card_counts: Mapping[str, int]


@dataclass(frozen=True)
class BdfModelSummary:
    """Compact metadata needed by existing AVA workflows."""

    path: Path
    grid_count: int
    element_counts: Dict[str, int]
    mass_element_count: int
    bounding_box: BoundingBox | None


def _parse_float(value: str) -> float:
    """Parse a NASTRAN numeric field, including D-format exponents."""

    text = value.strip()
    if not text:
        return 0.0
    return float(text.replace("D", "E").replace("d", "e"))


def _parse_optional_float(value: str | None) -> float | None:
    if value is None or not str(value).strip():
        return None
    try:
        return _parse_float(str(value))
    except ValueError:
        return None


def _parse_optional_int(value: str | None) -> int | None:
    if value is None or not str(value).strip():
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def _split_fields(line: str) -> List[str]:
    """Split a BDF card into stripped fields.

    Supports comma-separated free field and classic fixed-width 8-character
    fields. Continuation lines are handled by callers that need them; this
    parser's supported cards are expected to be complete on their first line.
    """

    payload = line.split("$", 1)[0].rstrip("\n")
    if not payload.strip():
        return []
    if "," in payload:
        return [field.strip() for field in payload.split(",")]
    return [payload[index : index + 8].strip() for index in range(0, 72, 8)]


def iter_bulk_cards(path: str | Path) -> Iterator[Tuple[str, List[str]]]:
    """Yield non-comment bulk data cards from a BDF file."""

    with Path(path).open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            stripped = raw_line.lstrip()
            if not stripped or stripped.startswith("$"):
                continue
            upper = stripped.upper()
            if upper.startswith(("CEND", "BEGIN BULK", "ENDDATA")):
                continue
            if stripped.startswith(("+", "*")):
                continue
            fields = _split_fields(raw_line)
            if not fields or not fields[0]:
                continue
            yield fields[0].upper().rstrip("*"), fields


def parse_grid_points(path: str | Path) -> Dict[int, GridPoint]:
    """Return GRID coordinates indexed by node ID."""

    return dict(parse_bdf_model(path).grids)


def _node_fields_for_element(card_name: str, fields: Sequence[str]) -> tuple[int, ...]:
    indexes = SHELL_ELEMENT_NODE_FIELDS.get(card_name) or LINE_ELEMENT_NODE_FIELDS.get(card_name)
    if indexes:
        nodes = [_parse_optional_int(fields[index]) for index in indexes if index < len(fields)]
        return tuple(node for node in nodes if node is not None)
    if card_name in SOLID_ELEMENT_NODE_START:
        start = SOLID_ELEMENT_NODE_START[card_name]
        nodes = [_parse_optional_int(value) for value in fields[start:]]
        return tuple(node for node in nodes if node is not None)
    return ()


def _property_id_for_element(card_name: str, fields: Sequence[str]) -> int | None:
    if card_name in LINE_ELEMENT_NODE_FIELDS and card_name == "CONROD":
        return None
    if card_name.startswith("C") and len(fields) > 2:
        return _parse_optional_int(fields[2])
    return None


def _parse_property(card_name: str, fields: Sequence[str]) -> PropertyCard | None:
    if not card_name.startswith("P") or len(fields) < 2:
        return None
    property_id = _parse_optional_int(fields[1])
    if property_id is None:
        return None

    material_ids: list[int] = []
    thickness = None
    area = None
    if card_name == "PSHELL":
        for index in (2, 4, 6, 8):
            if index < len(fields):
                material_id = _parse_optional_int(fields[index])
                if material_id is not None:
                    material_ids.append(material_id)
        if len(fields) > 3:
            thickness = _parse_optional_float(fields[3])
    elif card_name in {"PROD", "PBAR", "PBEAM"}:
        if len(fields) > 2:
            material_id = _parse_optional_int(fields[2])
            if material_id is not None:
                material_ids.append(material_id)
        if len(fields) > 3:
            area = _parse_optional_float(fields[3])
    elif card_name in {"PSOLID", "PLSOLID"}:
        if len(fields) > 2:
            material_id = _parse_optional_int(fields[2])
            if material_id is not None:
                material_ids.append(material_id)

    return PropertyCard(
        property_id=property_id,
        card_name=card_name,
        material_ids=tuple(dict.fromkeys(material_ids)),
        thickness=thickness,
        area=area,
    )


def _parse_material(card_name: str, fields: Sequence[str]) -> MaterialCard | None:
    if not card_name.startswith("MAT") or len(fields) < 2:
        return None
    material_id = _parse_optional_int(fields[1])
    if material_id is None:
        return None
    density = _parse_optional_float(fields[5]) if card_name == "MAT1" and len(fields) > 5 else None
    return MaterialCard(material_id=material_id, card_name=card_name, density=density)


def _parse_mass(card_name: str, fields: Sequence[str]) -> MassElement | None:
    if card_name not in MASS_ELEMENT_CARDS or len(fields) < 2:
        return None
    element_id = _parse_optional_int(fields[1])
    if element_id is None:
        return None
    node_id = _parse_optional_int(fields[2]) if len(fields) > 2 else None
    mass = None
    if card_name == "CONM2" and len(fields) > 4:
        mass = _parse_optional_float(fields[4])
    elif card_name in {"CMASS2", "CMASS4"} and len(fields) > 2:
        mass = _parse_optional_float(fields[2])
    return MassElement(element_id=element_id, card_name=card_name, node_id=node_id, mass=mass)


def parse_bdf_model(path: str | Path) -> BdfModel:
    """Parse a BDF into the supported AVA runtime subset."""

    bdf_path = Path(path)
    grids: dict[int, GridPoint] = {}
    elements: dict[int, Element] = {}
    properties: dict[int, PropertyCard] = {}
    materials: dict[int, MaterialCard] = {}
    masses: dict[int, MassElement] = {}
    coordinate_systems: dict[int, str] = {}
    card_counts: Counter[str] = Counter()

    for card_name, fields in iter_bulk_cards(bdf_path):
        card_counts[card_name] += 1
        if card_name == "GRID" and len(fields) >= 6:
            node_id = _parse_optional_int(fields[1])
            if node_id is None:
                continue
            cp = _parse_optional_int(fields[2]) or 0
            grids[node_id] = GridPoint(
                node_id=node_id,
                cp=cp,
                x=_parse_optional_float(fields[3]) or 0.0,
                y=_parse_optional_float(fields[4]) or 0.0,
                z=_parse_optional_float(fields[5]) or 0.0,
            )
            continue

        if card_name.startswith("CORD") and len(fields) > 1:
            coordinate_id = _parse_optional_int(fields[1])
            if coordinate_id is not None:
                coordinate_systems[coordinate_id] = card_name
            continue

        material = _parse_material(card_name, fields)
        if material is not None:
            materials[material.material_id] = material
            continue

        prop = _parse_property(card_name, fields)
        if prop is not None:
            properties[prop.property_id] = prop
            continue

        mass = _parse_mass(card_name, fields)
        if mass is not None:
            masses[mass.element_id] = mass
            continue

        if card_name.startswith("C") and len(fields) > 2:
            element_id = _parse_optional_int(fields[1])
            if element_id is None:
                continue
            nodes = _node_fields_for_element(card_name, fields)
            elements[element_id] = Element(
                element_id=element_id,
                card_name=card_name,
                property_id=_property_id_for_element(card_name, fields),
                node_ids=nodes,
            )

    return BdfModel(
        path=bdf_path,
        grids=grids,
        elements=elements,
        properties=properties,
        materials=materials,
        masses=masses,
        coordinate_systems=coordinate_systems,
        card_counts=dict(sorted(card_counts.items())),
    )


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
    """Create a compact structural summary for workflow framing."""

    model = parse_bdf_model(path)
    element_counts = Counter(element.card_name for element in model.elements.values())
    return BdfModelSummary(
        path=Path(path),
        grid_count=len(model.grids),
        element_counts=dict(sorted(element_counts.items())),
        mass_element_count=len(model.masses),
        bounding_box=compute_bounding_box(model.grids.values()),
    )


def geometry_summary(path: str | Path) -> dict:
    """Return JSON-serializable BDF geometry and inventory metadata."""

    model = parse_bdf_model(path)
    bbox = compute_bounding_box(model.grids.values())
    element_counts = Counter(element.card_name for element in model.elements.values())
    return {
        "path": str(model.path),
        "nodes": len(model.grids),
        "elements": len(model.elements),
        "element_counts": dict(sorted(element_counts.items())),
        "properties": len(model.properties),
        "materials": len(model.materials),
        "mass_elements": len(model.masses),
        "coordinate_systems": dict(sorted(model.coordinate_systems.items())),
        "bounding_box": None
        if bbox is None
        else {
            "xmin": bbox.xmin,
            "xmax": bbox.xmax,
            "ymin": bbox.ymin,
            "ymax": bbox.ymax,
            "zmin": bbox.zmin,
            "zmax": bbox.zmax,
            "span": list(bbox.span),
        },
        "card_counts": dict(model.card_counts),
        "structural_components": structural_components(model),
    }


def find_duplicate_nodes(model: BdfModel, *, tolerance: float = 1.0e-9) -> list[dict]:
    """Find groups of GRID entries sharing the same rounded coordinates."""

    buckets: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    scale = 1.0 / tolerance if tolerance > 0.0 else 1.0e9
    for node in model.grids.values():
        key = (
            round(node.x * scale),
            round(node.y * scale),
            round(node.z * scale),
        )
        buckets[key].append(node.node_id)
    duplicates = []
    for node_ids in buckets.values():
        if len(node_ids) > 1:
            first = model.grids[node_ids[0]]
            duplicates.append(
                {
                    "node_ids": sorted(node_ids),
                    "coordinates": [first.x, first.y, first.z],
                }
            )
    return sorted(duplicates, key=lambda group: group["node_ids"][0])


def find_free_edges(model: BdfModel) -> list[dict]:
    """Return shell element edges that are referenced by only one element."""

    edge_to_elements: dict[tuple[int, int], list[int]] = defaultdict(list)
    for element in model.elements.values():
        if element.card_name not in SHELL_ELEMENT_NODE_FIELDS:
            continue
        nodes = [node for node in element.node_ids if node is not None]
        if len(nodes) < 3:
            continue
        edges = list(zip(nodes, nodes[1:] + nodes[:1]))
        for n1, n2 in edges:
            edge_to_elements[tuple(sorted((n1, n2)))].append(element.element_id)
    free_edges = []
    for edge, element_ids in edge_to_elements.items():
        if len(element_ids) == 1:
            free_edges.append({"edge": list(edge), "element_id": element_ids[0]})
    return sorted(free_edges, key=lambda item: (item["edge"], item["element_id"]))


def structural_components(model: BdfModel) -> list[dict]:
    """Return connected structural element components by shared nodes."""

    node_to_elements: dict[int, set[int]] = defaultdict(set)
    for element in model.elements.values():
        for node_id in element.node_ids:
            node_to_elements[node_id].add(element.element_id)

    unseen = set(model.elements)
    components = []
    while unseen:
        start = unseen.pop()
        queue = deque([start])
        element_ids = {start}
        node_ids: set[int] = set()
        while queue:
            element_id = queue.popleft()
            element = model.elements[element_id]
            for node_id in element.node_ids:
                node_ids.add(node_id)
                for neighbor_id in node_to_elements[node_id]:
                    if neighbor_id in unseen:
                        unseen.remove(neighbor_id)
                        element_ids.add(neighbor_id)
                        queue.append(neighbor_id)
        components.append(
            {
                "element_count": len(element_ids),
                "node_count": len(node_ids),
                "element_ids": sorted(element_ids),
            }
        )
    return sorted(components, key=lambda item: (-item["element_count"], item["element_ids"][0]))


def model_diagnostics(path: str | Path, *, duplicate_tolerance: float = 1.0e-9) -> dict:
    """Run the approved read-only BDF model checks."""

    model = parse_bdf_model(path)
    referenced_nodes = {node_id for element in model.elements.values() for node_id in element.node_ids}
    referenced_properties = {
        element.property_id
        for element in model.elements.values()
        if element.property_id is not None
    }
    referenced_materials = {
        material_id
        for property_card in model.properties.values()
        for material_id in property_card.material_ids
    }
    missing_nodes = sorted(referenced_nodes - set(model.grids))
    floating_nodes = sorted(set(model.grids) - referenced_nodes)
    unused_properties = sorted(set(model.properties) - referenced_properties)
    unused_materials = sorted(set(model.materials) - referenced_materials)
    duplicate_nodes = find_duplicate_nodes(model, tolerance=duplicate_tolerance)
    free_edges = find_free_edges(model)
    components = structural_components(model)

    return {
        "path": str(model.path),
        "status": "ok",
        "summary": {
            "nodes": len(model.grids),
            "elements": len(model.elements),
            "duplicate_node_groups": len(duplicate_nodes),
            "free_edges": len(free_edges),
            "floating_nodes": len(floating_nodes),
            "missing_nodes": len(missing_nodes),
            "unused_properties": len(unused_properties),
            "unused_materials": len(unused_materials),
            "structural_components": len(components),
        },
        "duplicate_nodes": duplicate_nodes,
        "free_edges": free_edges,
        "floating_nodes": floating_nodes,
        "missing_nodes": missing_nodes,
        "unused_properties": unused_properties,
        "unused_materials": unused_materials,
        "structural_components": components,
    }


def _triangle_area(a: GridPoint, b: GridPoint, c: GridPoint) -> float:
    ab = (b.x - a.x, b.y - a.y, b.z - a.z)
    ac = (c.x - a.x, c.y - a.y, c.z - a.z)
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return 0.5 * (cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2) ** 0.5


def _distance(a: GridPoint, b: GridPoint) -> float:
    return ((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + (b.z - a.z) ** 2) ** 0.5


def _element_area(model: BdfModel, element: Element) -> float | None:
    try:
        nodes = [model.grids[node_id] for node_id in element.node_ids]
    except KeyError:
        return None
    if element.card_name == "CTRIA3" and len(nodes) >= 3:
        return _triangle_area(nodes[0], nodes[1], nodes[2])
    if element.card_name == "CQUAD4" and len(nodes) >= 4:
        return _triangle_area(nodes[0], nodes[1], nodes[2]) + _triangle_area(nodes[0], nodes[2], nodes[3])
    return None


def _element_length(model: BdfModel, element: Element) -> float | None:
    if len(element.node_ids) < 2:
        return None
    try:
        return _distance(model.grids[element.node_ids[0]], model.grids[element.node_ids[1]])
    except KeyError:
        return None


def mass_summary(path: str | Path) -> dict:
    """Compute conservative mass rollups from supported BDF cards."""

    model = parse_bdf_model(path)
    total_mass = 0.0
    estimated_mass = 0.0
    mass_by_property: dict[str, float] = defaultdict(float)
    mass_by_material: dict[str, float] = defaultdict(float)
    mass_by_type: dict[str, float] = defaultdict(float)
    unsupported_elements = 0

    for mass in model.masses.values():
        if mass.mass is None:
            unsupported_elements += 1
            continue
        total_mass += mass.mass
        mass_by_type[mass.card_name] += mass.mass

    for element in model.elements.values():
        prop = model.properties.get(element.property_id or -1)
        if prop is None:
            unsupported_elements += 1
            continue
        material_id = prop.material_ids[0] if prop.material_ids else None
        density = model.materials.get(material_id or -1).density if material_id is not None and material_id in model.materials else None
        element_mass = None
        if element.card_name in SHELL_ELEMENT_NODE_FIELDS and prop.thickness is not None and density is not None:
            area = _element_area(model, element)
            if area is not None:
                element_mass = area * prop.thickness * density
        elif element.card_name in LINE_ELEMENT_NODE_FIELDS and prop.area is not None and density is not None:
            length = _element_length(model, element)
            if length is not None:
                element_mass = length * prop.area * density
        if element_mass is None:
            unsupported_elements += 1
            continue
        estimated_mass += element_mass
        mass_by_property[str(prop.property_id)] += element_mass
        if material_id is not None:
            mass_by_material[str(material_id)] += element_mass
        mass_by_type[element.card_name] += element_mass

    total_mass += estimated_mass
    return {
        "path": str(model.path),
        "summary": {
            "total_mass": total_mass,
            "estimated_structural_mass": estimated_mass,
            "concentrated_mass": sum(mass.mass or 0.0 for mass in model.masses.values()),
            "unsupported_elements": unsupported_elements,
        },
        "mass_by_property": dict(sorted(mass_by_property.items())),
        "mass_by_material": dict(sorted(mass_by_material.items())),
        "mass_by_type": dict(sorted(mass_by_type.items())),
    }

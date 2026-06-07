"""Local HTML FEM viewer builder for BDF geometry and OP2 modal results.

The data flow mirrors the useful parts of ``fem-explorer`` without carrying
its Electron shell: parse local engineering files, write static JSON artifacts,
and serve a browser-based Three.js viewer on 127.0.0.1.
"""

from __future__ import annotations

import atexit
import json
import shutil
import threading
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence

from ava_runtime.parsers.bdf_parser import (
    LINE_ELEMENT_NODE_FIELDS,
    SHELL_ELEMENT_NODE_FIELDS,
    SOLID_ELEMENT_NODE_START,
    BdfModel,
    compute_bounding_box,
    find_duplicate_nodes,
    find_free_edges,
    parse_bdf_model,
)


STATIC_ROOT = Path(__file__).with_name("fem_viewer_static")
VIEWER_SCHEMA = "ava_fem_viewer_v1"
GEOMETRY_SCHEMA = "ava_fem_geometry_v1"
MODES_SCHEMA = "ava_fem_modes_v1"
LOCAL_HOST = "127.0.0.1"


@dataclass
class _ServerHandle:
    workspace: Path
    requested_port: int | None
    httpd: ThreadingHTTPServer
    thread: threading.Thread

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    @property
    def url(self) -> str:
        return f"http://{LOCAL_HOST}:{self.port}/index.html"


_SERVERS: list[_ServerHandle] = []
_SERVERS_LOCK = threading.Lock()


class _QuietRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def build_bdf_3d_viewer(
    bdf: str | Path,
    output_dir: str | Path,
    *,
    title: str | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    """Build and serve an HTML 3D viewer for a BDF."""

    workspace = Path(output_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    geometry = build_geometry_payload(Path(bdf))
    paths = _write_workspace(
        workspace=workspace,
        title=title or Path(bdf).name,
        geometry=geometry,
        modes_manifest=None,
    )
    server = start_viewer_server(workspace, port=port)
    return _viewer_result(paths, geometry, server, modes_manifest=None)


def build_op2_mode_shape_viewer(
    bdf: str | Path,
    op2: str | Path,
    output_dir: str | Path,
    *,
    title: str | None = None,
    port: int | None = None,
    mode_limit: int | None = None,
) -> dict[str, Any]:
    """Build and serve an HTML viewer for BDF geometry plus modal results."""

    workspace = Path(output_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    geometry = build_geometry_payload(Path(bdf))
    modes_manifest = build_mode_shape_manifest(
        Path(op2),
        workspace / "data" / "modes",
        mode_limit=mode_limit,
    )
    paths = _write_workspace(
        workspace=workspace,
        title=title or f"{Path(bdf).name} modal results",
        geometry=geometry,
        modes_manifest=modes_manifest,
    )
    server = start_viewer_server(workspace, port=port)
    return _viewer_result(paths, geometry, server, modes_manifest=modes_manifest)


def build_geometry_payload(path: Path) -> dict[str, Any]:
    """Build viewer geometry JSON, preferring pyNastran when available."""

    try:
        return _build_geometry_payload_with_pynastran(path)
    except ModuleNotFoundError:
        return _build_geometry_payload_lightweight(path, warnings=["pyNastran is not installed; used AVA lightweight BDF parser"])


def build_mode_shape_manifest(
    result_path: Path,
    modes_dir: Path,
    *,
    mode_limit: int | None = None,
) -> dict[str, Any]:
    """Create a viewer modal manifest from OP2 or an OP2-derived JSON export."""

    modes_dir.mkdir(parents=True, exist_ok=True)
    if not result_path.exists():
        raise FileNotFoundError(result_path)
    if result_path.suffix.lower() == ".json":
        return _build_mode_manifest_from_json(result_path, modes_dir, mode_limit=mode_limit)
    return _build_mode_manifest_from_op2(result_path, modes_dir, mode_limit=mode_limit)


def start_viewer_server(workspace: str | Path, *, port: int | None = None) -> dict[str, Any]:
    """Serve an existing viewer workspace on loopback and return URL metadata."""

    resolved = Path(workspace).resolve()
    with _SERVERS_LOCK:
        for handle in _SERVERS:
            if handle.workspace == resolved and handle.thread.is_alive():
                if port is None or handle.requested_port == port or handle.port == port:
                    return _server_dict(handle)

        handler = partial(_QuietRequestHandler, directory=str(resolved))
        httpd = ThreadingHTTPServer((LOCAL_HOST, int(port or 0)), handler)
        thread = threading.Thread(
            target=httpd.serve_forever,
            name=f"ava-fem-viewer-{httpd.server_address[1]}",
            daemon=True,
        )
        thread.start()
        handle = _ServerHandle(
            workspace=resolved,
            requested_port=port,
            httpd=httpd,
            thread=thread,
        )
        _SERVERS.append(handle)
        return _server_dict(handle)


def shutdown_viewer_servers() -> None:
    """Stop all process-local FEM viewer servers."""

    with _SERVERS_LOCK:
        handles = list(_SERVERS)
        _SERVERS.clear()
    for handle in handles:
        handle.httpd.shutdown()
        handle.httpd.server_close()


def _write_workspace(
    *,
    workspace: Path,
    title: str,
    geometry: Mapping[str, Any],
    modes_manifest: Mapping[str, Any] | None,
) -> dict[str, Path]:
    data_dir = workspace / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    _copy_static_assets(workspace)

    geometry_path = _write_json(data_dir / "geometry.json", geometry)
    config = {
        "schema": VIEWER_SCHEMA,
        "title": title,
        "geometry_url": "data/geometry.json",
        "modes_url": "data/modes/manifest.json" if modes_manifest else None,
    }
    config_path = _write_json(workspace / "viewer_config.json", config)
    return {
        "workspace": workspace,
        "index_html": workspace / "index.html",
        "viewer_config": config_path,
        "geometry_json": geometry_path,
    }


def _viewer_result(
    paths: Mapping[str, Path],
    geometry: Mapping[str, Any],
    server: Mapping[str, Any],
    *,
    modes_manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    stats = dict(geometry["stats"])
    summary: dict[str, Any] = {
        "viewer_url": server["url"],
        "workspace_dir": str(paths["workspace"]),
        "index_html": str(paths["index_html"]),
        "geometry_json": str(paths["geometry_json"]),
        "viewer_config": str(paths["viewer_config"]),
        "server": dict(server),
        "geometry_parser": geometry["source"]["parser"],
        "node_count": stats["node_count"],
        "element_count": stats["element_count"],
        "bounding_box": geometry["bounding_box"],
    }
    artifacts = [
        str(paths["index_html"]),
        str(paths["viewer_config"]),
        str(paths["geometry_json"]),
    ]
    if modes_manifest is not None:
        summary.update(
            {
                "op2_parser": modes_manifest["source"]["parser"],
                "mode_count": modes_manifest["mode_count"],
                "frequency_min_hz": modes_manifest.get("frequency_min_hz"),
                "frequency_max_hz": modes_manifest.get("frequency_max_hz"),
                "op2_manifest_json": str(paths["workspace"] / "data" / "modes" / "manifest.json"),
                "op2_cache_dir": str(paths["workspace"] / "data" / "modes"),
            }
        )
        artifacts.append(summary["op2_manifest_json"])
    return {
        "summary": summary,
        "artifacts": tuple(artifacts),
    }


def _copy_static_assets(workspace: Path) -> None:
    if not STATIC_ROOT.exists():
        raise RuntimeError(f"FEM viewer static assets are missing: {STATIC_ROOT}")
    for child in STATIC_ROOT.iterdir():
        if child.name == "__pycache__":
            continue
        target = workspace / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    return path


def _server_dict(handle: _ServerHandle) -> dict[str, Any]:
    return {
        "host": LOCAL_HOST,
        "port": handle.port,
        "url": handle.url,
    }


def _build_geometry_payload_lightweight(path: Path, *, warnings: Sequence[str] = ()) -> dict[str, Any]:
    model = parse_bdf_model(path)
    return _payload_from_bdf_model(path, model, parser="ava_lightweight_bdf", warnings=list(warnings))


def _payload_from_bdf_model(path: Path, model: BdfModel, *, parser: str, warnings: list[str]) -> dict[str, Any]:
    bbox = compute_bounding_box(model.grids.values())
    if bbox is None:
        bbox_payload = {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0], "span": [0.0, 0.0, 0.0]}
    else:
        bbox_payload = {
            "min": [bbox.xmin, bbox.ymin, bbox.zmin],
            "max": [bbox.xmax, bbox.ymax, bbox.zmax],
            "span": list(bbox.span),
        }

    referenced_nodes = {node_id for element in model.elements.values() for node_id in element.node_ids}
    missing_nodes = sorted(referenced_nodes - set(model.grids))
    floating_nodes = sorted(set(model.grids) - referenced_nodes)
    property_material_ids = {
        prop.property_id: list(prop.material_ids)
        for prop in model.properties.values()
    }

    elements = []
    renderable_shell_count = 0
    line_element_count = 0
    solid_element_count = 0
    for element in sorted(model.elements.values(), key=lambda item: item.element_id):
        node_ids = list(element.node_ids)
        renderable = len(node_ids) >= 2 and all(node_id in model.grids for node_id in node_ids)
        if element.card_name in SHELL_ELEMENT_NODE_FIELDS and renderable:
            renderable_shell_count += 1
        if element.card_name in LINE_ELEMENT_NODE_FIELDS and renderable:
            line_element_count += 1
        if element.card_name in SOLID_ELEMENT_NODE_START and renderable:
            solid_element_count += 1
        material_ids = property_material_ids.get(element.property_id or -1, [])
        elements.append(
            {
                "id": element.element_id,
                "type": element.card_name,
                "property_id": element.property_id,
                "material_id": material_ids[0] if material_ids else None,
                "node_ids": node_ids,
                "renderable": renderable,
            }
        )

    return {
        "schema": GEOMETRY_SCHEMA,
        "source": {
            "path": str(path),
            "filename": path.name,
            "parser": parser,
            "warnings": warnings,
        },
        "bounding_box": bbox_payload,
        "stats": {
            "node_count": len(model.grids),
            "element_count": len(model.elements),
            "property_count": len(model.properties),
            "material_count": len(model.materials),
            "mass_element_count": len(model.masses),
            "renderable_shell_count": renderable_shell_count,
            "line_element_count": line_element_count,
            "solid_element_count": solid_element_count,
            "floating_node_count": len(floating_nodes),
            "missing_node_count": len(missing_nodes),
            "duplicate_node_group_count": len(find_duplicate_nodes(model)),
            "free_edge_count": len(find_free_edges(model)),
        },
        "nodes": [
            {"id": node.node_id, "xyz": [node.x, node.y, node.z]}
            for node in sorted(model.grids.values(), key=lambda item: item.node_id)
        ],
        "elements": elements,
        "properties": [
            {
                "id": prop.property_id,
                "type": prop.card_name,
                "material_ids": list(prop.material_ids),
                "thickness": prop.thickness,
                "area": prop.area,
            }
            for prop in sorted(model.properties.values(), key=lambda item: item.property_id)
        ],
        "materials": [
            {
                "id": material.material_id,
                "type": material.card_name,
                "density": material.density,
            }
            for material in sorted(model.materials.values(), key=lambda item: item.material_id)
        ],
        "mass_elements": [
            {
                "id": mass.element_id,
                "type": mass.card_name,
                "node_id": mass.node_id,
                "mass": mass.mass,
            }
            for mass in sorted(model.masses.values(), key=lambda item: item.element_id)
        ],
        "diagnostics": {
            "floating_node_ids": floating_nodes,
            "missing_node_ids": missing_nodes,
            "duplicate_node_groups": find_duplicate_nodes(model),
            "free_edges": find_free_edges(model),
        },
    }


def _build_geometry_payload_with_pynastran(path: Path) -> dict[str, Any]:
    try:
        from pyNastran.bdf.bdf import BDF
        from pyNastran.bdf.errors import MissingDeckSections
    except ModuleNotFoundError:
        raise

    model = BDF(debug=False)
    try:
        model.read_bdf(str(path), xref=True)
    except MissingDeckSections:
        model = BDF(debug=False)
        model.read_bdf(str(path), xref=True, punch=True)
    except Exception:
        fallback = _build_geometry_payload_lightweight(
            path,
            warnings=["pyNastran parse failed; used AVA lightweight BDF parser"],
        )
        fallback["source"]["parser"] = "ava_lightweight_bdf_after_pynastran_error"
        return fallback

    node_positions: dict[int, list[float]] = {}
    for node_id, node in sorted(model.nodes.items()):
        node_positions[int(node_id)] = _float_list(node.get_position(), length=3)
    bbox_payload = _bounding_box_from_positions(node_positions.values())

    properties = []
    property_material_ids: dict[int, list[int]] = {}
    for property_id, prop in sorted(model.properties.items()):
        material_ids = _material_ids_from_property(prop)
        property_material_ids[int(property_id)] = material_ids
        properties.append(
            {
                "id": int(property_id),
                "type": str(prop.type),
                "material_ids": material_ids,
                "thickness": _optional_float_from_call(prop, "Thickness", attrs=("t", "T")),
                "area": _optional_float_from_call(prop, "Area", attrs=("A",)),
            }
        )

    elements = []
    renderable_shell_count = 0
    line_element_count = 0
    solid_element_count = 0
    for element_id, element in sorted(model.elements.items()):
        node_ids = [int(value) for value in getattr(element, "node_ids", []) if value is not None]
        property_id = _property_id_from_element(element)
        renderable = len(node_ids) >= 2 and all(node_id in node_positions for node_id in node_ids)
        element_type = str(getattr(element, "type", ""))
        if element_type in SHELL_ELEMENT_NODE_FIELDS and renderable:
            renderable_shell_count += 1
        if element_type in LINE_ELEMENT_NODE_FIELDS and renderable:
            line_element_count += 1
        if element_type in SOLID_ELEMENT_NODE_START and renderable:
            solid_element_count += 1
        material_ids = property_material_ids.get(property_id or -1, [])
        elements.append(
            {
                "id": int(element_id),
                "type": element_type,
                "property_id": property_id,
                "material_id": material_ids[0] if material_ids else None,
                "node_ids": node_ids,
                "renderable": renderable,
            }
        )

    referenced_nodes = {node_id for element in elements for node_id in element["node_ids"]}
    floating_nodes = sorted(set(node_positions) - referenced_nodes)
    missing_nodes = sorted(referenced_nodes - set(node_positions))
    diagnostics = _lightweight_diagnostics(path)

    return {
        "schema": GEOMETRY_SCHEMA,
        "source": {
            "path": str(path),
            "filename": path.name,
            "parser": "pyNastran",
            "warnings": [],
        },
        "bounding_box": bbox_payload,
        "stats": {
            "node_count": len(node_positions),
            "element_count": len(elements),
            "property_count": len(properties),
            "material_count": len(model.materials),
            "mass_element_count": len(model.masses),
            "renderable_shell_count": renderable_shell_count,
            "line_element_count": line_element_count,
            "solid_element_count": solid_element_count,
            "floating_node_count": len(floating_nodes),
            "missing_node_count": len(missing_nodes),
            "duplicate_node_group_count": len(diagnostics["duplicate_node_groups"]),
            "free_edge_count": len(diagnostics["free_edges"]),
        },
        "nodes": [
            {"id": node_id, "xyz": node_positions[node_id]}
            for node_id in sorted(node_positions)
        ],
        "elements": elements,
        "properties": properties,
        "materials": [
            {"id": int(material_id), "type": str(material.type), "density": _material_density(material)}
            for material_id, material in sorted(model.materials.items())
        ],
        "mass_elements": [
            {
                "id": int(element_id),
                "type": str(mass.type),
                "node_id": _mass_node_id(mass),
                "mass": _mass_value(mass),
            }
            for element_id, mass in sorted(model.masses.items())
        ],
        "diagnostics": {
            "floating_node_ids": floating_nodes,
            "missing_node_ids": missing_nodes,
            "duplicate_node_groups": diagnostics["duplicate_node_groups"],
            "free_edges": diagnostics["free_edges"],
        },
    }


def _build_mode_manifest_from_json(result_path: Path, modes_dir: Path, *, mode_limit: int | None) -> dict[str, Any]:
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    raw_modes = payload.get("modes", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_modes, list):
        raise ValueError("Mode-shape JSON must be a list or an object with a 'modes' list")
    mode_shapes = payload.get("mode_shapes", {}) if isinstance(payload, dict) else {}
    manifest_modes = []
    for index, raw_mode in enumerate(raw_modes, start=1):
        if mode_limit is not None and len(manifest_modes) >= mode_limit:
            break
        if not isinstance(raw_mode, Mapping):
            raise ValueError("Each mode entry must be a JSON object")
        mode_id = str(raw_mode.get("mode_id") or f"s1_m{raw_mode.get('mode_number') or index}")
        shape = mode_shapes.get(mode_id, {}) if isinstance(mode_shapes, Mapping) else {}
        node_ids = raw_mode.get("node_ids") or shape.get("node_ids")
        translations = raw_mode.get("translations") or raw_mode.get("displacements") or shape.get("translations")
        rotations = raw_mode.get("rotations") or shape.get("rotations")
        mode_payload = _mode_payload(
            mode_id=mode_id,
            case_key=str(raw_mode.get("case_key") or "1"),
            mode_number=int(raw_mode.get("mode_number") or index),
            frequency_hz=_optional_float(raw_mode.get("frequency_hz")),
            eigenvalue=_optional_float(raw_mode.get("eigenvalue")),
            node_ids=node_ids,
            translations=translations,
            rotations=rotations,
        )
        _write_json(modes_dir / f"{mode_id}.json", mode_payload)
        manifest_modes.append(_mode_manifest_item(mode_payload, f"{mode_id}.json"))
    return _write_mode_manifest(
        modes_dir=modes_dir,
        source_path=result_path,
        parser="op2_json_export",
        modes=manifest_modes,
    )


def _lightweight_diagnostics(path: Path) -> dict[str, list[dict[str, Any]]]:
    try:
        model = parse_bdf_model(path)
    except Exception:
        return {"duplicate_node_groups": [], "free_edges": []}
    return {
        "duplicate_node_groups": find_duplicate_nodes(model),
        "free_edges": find_free_edges(model),
    }


def _build_mode_manifest_from_op2(result_path: Path, modes_dir: Path, *, mode_limit: int | None) -> dict[str, Any]:
    try:
        import numpy as np
        from pyNastran.op2.op2 import read_op2
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "OP2 mode-shape visualization requires pyNastran. "
            "Reinstall AVA so its core engineering dependencies are present."
        ) from exc

    model = read_op2(
        str(result_path),
        include_results=["eigenvalues", "eigenvectors"],
        build_dataframe=False,
        debug=False,
    )
    if not getattr(model, "eigenvectors", None):
        raise ValueError("No modal eigenvectors were found in the OP2 file")

    manifest_modes = []
    for case_key, eigenvector in sorted(model.eigenvectors.items(), key=lambda item: str(item[0])):
        node_ids = eigenvector.node_gridtype[:, 0].astype(int).tolist()
        translations = np.asarray(eigenvector.data[:, :, :3], dtype=float)
        rotations = np.asarray(eigenvector.data[:, :, 3:6], dtype=float)
        mode_numbers = np.asarray(getattr(eigenvector, "modes", []), dtype=int)
        eigenvalues = np.asarray(getattr(eigenvector, "eigns", []), dtype=float)
        frequencies = np.asarray(getattr(eigenvector, "mode_cycles", []), dtype=float)
        case_key_string = _stringify_case_key(case_key)

        for index, mode_number in enumerate(mode_numbers):
            if mode_limit is not None and len(manifest_modes) >= mode_limit:
                break
            mode_id = f"s{case_key_string}_m{int(mode_number)}"
            mode_payload = _mode_payload(
                mode_id=mode_id,
                case_key=case_key_string,
                mode_number=int(mode_number),
                frequency_hz=float(frequencies[index]) if index < len(frequencies) else None,
                eigenvalue=float(eigenvalues[index]) if index < len(eigenvalues) else None,
                node_ids=node_ids,
                translations=translations[index].tolist(),
                rotations=rotations[index].tolist(),
            )
            _write_json(modes_dir / f"{mode_id}.json", mode_payload)
            manifest_modes.append(_mode_manifest_item(mode_payload, f"{mode_id}.json"))
        if mode_limit is not None and len(manifest_modes) >= mode_limit:
            break

    return _write_mode_manifest(
        modes_dir=modes_dir,
        source_path=result_path,
        parser="pyNastran",
        modes=manifest_modes,
    )


def _mode_payload(
    *,
    mode_id: str,
    case_key: str,
    mode_number: int,
    frequency_hz: float | None,
    eigenvalue: float | None,
    node_ids: object,
    translations: object,
    rotations: object,
) -> dict[str, Any]:
    if not isinstance(node_ids, list) or not node_ids:
        raise ValueError(f"Mode {mode_id} is missing node_ids")
    if not isinstance(translations, list) or len(translations) != len(node_ids):
        raise ValueError(f"Mode {mode_id} translations must match node_ids length")
    normalized_rotations = rotations
    if not isinstance(normalized_rotations, list) or len(normalized_rotations) != len(node_ids):
        normalized_rotations = [[0.0, 0.0, 0.0] for _ in node_ids]
    return {
        "schema": "ava_fem_mode_shape_v1",
        "mode_id": mode_id,
        "case_key": case_key,
        "mode_number": mode_number,
        "frequency_hz": frequency_hz,
        "eigenvalue": eigenvalue,
        "node_ids": [int(value) for value in node_ids],
        "translations": [_vector3(row) for row in translations],
        "rotations": [_vector3(row) for row in normalized_rotations],
    }


def _mode_manifest_item(mode_payload: Mapping[str, Any], relative_path: str) -> dict[str, Any]:
    return {
        "mode_id": mode_payload["mode_id"],
        "case_key": mode_payload["case_key"],
        "mode_number": mode_payload["mode_number"],
        "frequency_hz": mode_payload["frequency_hz"],
        "eigenvalue": mode_payload["eigenvalue"],
        "node_count": len(mode_payload["node_ids"]),
        "shape_url": relative_path,
    }


def _write_mode_manifest(
    *,
    modes_dir: Path,
    source_path: Path,
    parser: str,
    modes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    frequencies = [float(mode["frequency_hz"]) for mode in modes if mode.get("frequency_hz") is not None]
    manifest = {
        "schema": MODES_SCHEMA,
        "source": {
            "path": str(source_path),
            "filename": source_path.name,
            "parser": parser,
        },
        "mode_count": len(modes),
        "frequency_min_hz": min(frequencies) if frequencies else None,
        "frequency_max_hz": max(frequencies) if frequencies else None,
        "modes": list(modes),
    }
    _write_json(modes_dir / "manifest.json", manifest)
    return manifest


def _bounding_box_from_positions(positions: Sequence[Sequence[float]]) -> dict[str, list[float]]:
    points = [list(point) for point in positions]
    if not points:
        return {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0], "span": [0.0, 0.0, 0.0]}
    mins = [min(point[index] for point in points) for index in range(3)]
    maxs = [max(point[index] for point in points) for index in range(3)]
    return {
        "min": mins,
        "max": maxs,
        "span": [maxs[index] - mins[index] for index in range(3)],
    }


def _float_list(values: object, *, length: int) -> list[float]:
    normalized = [float(value) for value in values]  # type: ignore[operator]
    if len(normalized) != length:
        raise ValueError(f"Expected {length} values")
    return normalized


def _vector3(values: object) -> list[float]:
    return _float_list(values, length=3)


def _material_ids_from_property(prop: object) -> list[int]:
    values: list[int] = []
    for method_name in ("Mid", "Mids"):
        method = getattr(prop, method_name, None)
        if not callable(method):
            continue
        try:
            resolved = method()
        except Exception:
            continue
        if resolved is None:
            continue
        if isinstance(resolved, (list, tuple)):
            values.extend(int(value) for value in resolved if value is not None)
        else:
            values.append(int(resolved))
    return list(dict.fromkeys(values))


def _property_id_from_element(element: object) -> int | None:
    method = getattr(element, "Pid", None)
    if not callable(method):
        return None
    try:
        value = method()
    except Exception:
        return None
    return int(value) if value is not None else None


def _optional_float_from_call(obj: object, method_name: str, *, attrs: Sequence[str] = ()) -> float | None:
    method = getattr(obj, method_name, None)
    if callable(method):
        try:
            value = method()
            if value is not None:
                return float(value)
        except Exception:
            pass
    for attr in attrs:
        value = getattr(obj, attr, None)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _material_density(material: object) -> float | None:
    return _optional_float_from_call(material, "Rho", attrs=("rho",))


def _mass_node_id(mass: object) -> int | None:
    node_ids = getattr(mass, "node_ids", None)
    if node_ids:
        return int(node_ids[0])
    node_id = getattr(mass, "nid", None)
    return int(node_id) if node_id is not None else None


def _mass_value(mass: object) -> float | None:
    for attr in ("mass", "Mass"):
        value = getattr(mass, attr, None)
        if callable(value):
            try:
                resolved = value()
            except Exception:
                continue
        else:
            resolved = value
        if resolved is not None:
            try:
                return float(resolved)
            except (TypeError, ValueError):
                continue
    return None


def _optional_float(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(str(value))


def _stringify_case_key(case_key: object) -> str:
    if isinstance(case_key, tuple):
        return "_".join(str(part) for part in case_key if part is not None)
    return str(case_key)


atexit.register(shutdown_viewer_servers)

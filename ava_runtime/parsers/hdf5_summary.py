"""HDF5 channel summary helpers with optional h5py support."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


HDF5_SIGNATURE = b"\x89HDF\r\n\x1a\n"


@dataclass(frozen=True)
class Hdf5Channel:
    """Summary of one HDF5 dataset."""

    path: str
    shape: tuple[int, ...]
    dtype: str
    units: str | None = None
    sample_rate_hz: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    rms: float | None = None


def is_hdf5_file(path: str | Path) -> bool:
    """Return True when the file has the HDF5 magic signature."""

    with Path(path).open("rb") as handle:
        return handle.read(len(HDF5_SIGNATURE)) == HDF5_SIGNATURE


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _numeric_stats(values: Iterable[Any], *, limit: int = 200_000) -> tuple[float | None, float | None, float | None]:
    count = 0
    total_square = 0.0
    minimum = None
    maximum = None
    for value in values:
        number = _as_float(value)
        if number is None:
            continue
        minimum = number if minimum is None else min(minimum, number)
        maximum = number if maximum is None else max(maximum, number)
        total_square += number * number
        count += 1
        if count >= limit:
            break
    if count == 0:
        return None, None, None
    return minimum, maximum, (total_square / count) ** 0.5


def _flatten_dataset(dataset: Any) -> Iterable[Any]:
    data = dataset[()]
    if hasattr(data, "flat"):
        yield from data.flat
        return
    if isinstance(data, (list, tuple)):
        stack = list(data)
        while stack:
            item = stack.pop(0)
            if isinstance(item, (list, tuple)):
                stack[:0] = list(item)
            else:
                yield item
        return
    yield data


def summarize_hdf5_channels(path: str | Path) -> dict:
    """Summarize HDF5 datasets when h5py is available.

    Without h5py, the tool still returns file-level metadata and a clear
    limited-status reason instead of failing in AVA's default install.
    """

    hdf5_path = Path(path)
    signature_ok = is_hdf5_file(hdf5_path)
    base = {
        "path": str(hdf5_path),
        "file_size_bytes": hdf5_path.stat().st_size,
        "hdf5_signature": signature_ok,
        "status": "ok" if signature_ok else "not_hdf5",
        "channels": [],
        "channel_count": 0,
    }
    if not signature_ok:
        return base

    try:
        h5py = importlib.import_module("h5py")
    except ModuleNotFoundError:
        base["status"] = "limited"
        base["reason"] = "h5py is not installed; channel-level HDF5 inspection is unavailable"
        return base

    channels: list[Hdf5Channel] = []

    def visit(name: str, obj: Any) -> None:
        if not hasattr(obj, "shape") or not hasattr(obj, "dtype"):
            return
        attrs = getattr(obj, "attrs", {})
        units = attrs.get("units") or attrs.get("unit")
        sample_rate = attrs.get("sample_rate_hz") or attrs.get("sample_rate") or attrs.get("fs")
        minimum, maximum, rms = _numeric_stats(_flatten_dataset(obj))
        channels.append(
            Hdf5Channel(
                path=f"/{name}",
                shape=tuple(int(item) for item in getattr(obj, "shape", ()) or ()),
                dtype=str(getattr(obj, "dtype", "unknown")),
                units=str(units) if units is not None else None,
                sample_rate_hz=_as_float(sample_rate),
                minimum=minimum,
                maximum=maximum,
                rms=rms,
            )
        )

    with h5py.File(hdf5_path, "r") as handle:
        handle.visititems(visit)

    return {
        **base,
        "status": "ok",
        "channels": [
            {
                "path": channel.path,
                "shape": list(channel.shape),
                "dtype": channel.dtype,
                "units": channel.units,
                "sample_rate_hz": channel.sample_rate_hz,
                "min": channel.minimum,
                "max": channel.maximum,
                "rms": channel.rms,
            }
            for channel in sorted(channels, key=lambda item: item.path)
        ],
        "channel_count": len(channels),
    }

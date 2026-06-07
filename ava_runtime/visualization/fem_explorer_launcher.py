"""Launch FEM Explorer desktop windows for AVA viewer requests."""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_FEM_EXPLORER_ROOT = Path("/Users/stephenwells/Documents/DevOps/fem-explorer")


def launch_fem_explorer_viewer(
    bdf: str | Path,
    output_dir: str | Path,
    *,
    op2: str | Path | None = None,
    initial_mode: str | int | None = None,
    auto_animate: bool = True,
    fem_explorer_root: str | Path | None = None,
) -> dict[str, Any]:
    """Launch FEM Explorer/Electron in a new window with referenced local files."""

    root = _resolve_fem_explorer_root(fem_explorer_root)
    bdf_path = Path(bdf).expanduser().resolve()
    if not bdf_path.exists():
        raise FileNotFoundError(bdf_path)

    op2_path: Path | None = None
    if op2 is not None:
        op2_path = Path(op2).expanduser().resolve()
        if not op2_path.exists():
            raise FileNotFoundError(op2_path)
        if op2_path.suffix.lower() != ".op2":
            raise ValueError(
                "FEM Explorer launch requires an .op2 modal result. "
                "Use viewer_backend='static' for modal JSON exports."
            )

    workspace = Path(output_dir).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    backend_port, frontend_port = _free_loopback_ports(2)
    token = secrets.token_urlsafe(24)

    manifest = {
        "bdf_path": str(bdf_path),
        "op2_path": str(op2_path) if op2_path else None,
        "initial_mode": initial_mode,
        "auto_animate": bool(auto_animate),
    }
    manifest_path = workspace / "fem_explorer_launch.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    stdout_path = workspace / "fem_explorer_stdout.log"
    stderr_path = workspace / "fem_explorer_stderr.log"
    env = os.environ.copy()
    env.update(
        {
            "FEM_EXPLORER_BACKEND_PORT": str(backend_port),
            "FEM_EXPLORER_FRONTEND_PORT": str(frontend_port),
            "FEM_EXPLORER_REFERENCE_TOKEN": token,
            "FEM_EXPLORER_LAUNCH_MANIFEST": str(manifest_path),
        }
    )

    command = _electron_command(manifest_path)
    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
        process = subprocess.Popen(
            command,
            cwd=str(root),
            env=env,
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    return {
        "summary": {
            "viewer_backend": "fem_explorer",
            "window": "launched",
            "process_id": process.pid,
            "fem_explorer_root": str(root),
            "frontend_url": f"http://127.0.0.1:{frontend_port}",
            "backend_url": f"http://127.0.0.1:{backend_port}",
            "launch_manifest": str(manifest_path),
            "bdf_path": str(bdf_path),
            "op2_path": str(op2_path) if op2_path else None,
            "initial_mode": initial_mode,
            "auto_animate": bool(auto_animate and op2_path),
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        },
        "artifacts": (
            str(manifest_path),
            str(stdout_path),
            str(stderr_path),
        ),
    }


def _resolve_fem_explorer_root(explicit: str | Path | None) -> Path:
    candidates = []
    if explicit is not None and str(explicit).strip():
        candidates.append(Path(explicit).expanduser())
    env_root = os.environ.get("FEM_EXPLORER_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser())
    candidates.append(DEFAULT_FEM_EXPLORER_ROOT)

    for candidate in candidates:
        root = candidate.resolve()
        if (root / "package.json").exists() and (root / "electron" / "main.js").exists():
            return root
    raise FileNotFoundError(
        "Could not find fem-explorer. Set FEM_EXPLORER_ROOT or pass fem_explorer_root."
    )


def _free_loopback_ports(count: int) -> tuple[int, ...]:
    sockets = []
    try:
        for _ in range(count):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", 0))
            sockets.append(sock)
        return tuple(int(sock.getsockname()[1]) for sock in sockets)
    finally:
        for sock in sockets:
            sock.close()


def _electron_command(manifest_path: Path) -> list[str]:
    npm = "npm.cmd" if sys.platform.startswith("win") else "npm"
    return [
        npm,
        "run",
        "start:electron",
        "--",
        f"--launch-manifest={manifest_path}",
    ]

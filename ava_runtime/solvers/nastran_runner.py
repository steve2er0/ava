"""Non-interactive NASTRAN execution helpers for the AVA runtime.

This module keeps solver invocation narrow and inspectable. It does not hide
the command line; instead it assembles a deterministic command, executes it in
batch mode, and records the key run metadata that downstream workflows need for
traceability.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping


@dataclass(frozen=True)
class NastranRunRequest:
    """Configuration for a single solver execution."""

    deck_path: Path
    working_directory: Path
    executable: str = "nastran"
    keywords: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class NastranRunResult:
    """Captured metadata from a completed solver run."""

    command: tuple[str, ...]
    return_code: int
    duration_seconds: float
    stdout: str
    stderr: str
    output_files: Dict[str, Path]

    @property
    def succeeded(self) -> bool:
        """Return `True` when the solver exited successfully."""

        return self.return_code == 0


class NastranRunner:
    """Launch NASTRAN in batch mode and collect its outputs."""

    def build_command(self, request: NastranRunRequest) -> tuple[str, ...]:
        """Assemble a deterministic command line for the requested run."""

        command = [
            request.executable,
            str(request.deck_path),
        ]
        for key, value in sorted(request.keywords.items()):
            command.append(f"{key}={value}")
        return tuple(command)

    def run(self, request: NastranRunRequest, timeout_seconds: float | None = None) -> NastranRunResult:
        """Execute the solver and return the captured run metadata."""

        command = self.build_command(request)
        start = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=request.working_directory,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
        duration = time.perf_counter() - start
        return NastranRunResult(
            command=command,
            return_code=completed.returncode,
            duration_seconds=duration,
            stdout=completed.stdout,
            stderr=completed.stderr,
            output_files=discover_output_files(request.deck_path),
        )


def discover_output_files(deck_path: str | Path) -> Dict[str, Path]:
    """Locate common NASTRAN outputs produced next to a deck."""

    deck = Path(deck_path)
    stem = deck.with_suffix("")
    known_extensions = {
        "f06": ".f06",
        "log": ".log",
        "op2": ".op2",
        "pch": ".pch",
        "xdb": ".xdb",
    }
    discovered: Dict[str, Path] = {}
    for key, suffix in known_extensions.items():
        candidate = Path(f"{stem}{suffix}")
        if candidate.exists():
            discovered[key] = candidate
    return discovered

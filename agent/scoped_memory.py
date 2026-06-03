"""Filesystem-backed scoped memory for AVA.

V1 deliberately stays transparent and reviewable: small Markdown summaries are
loaded into the prompt, while approved team knowledge remains human-governed.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from hermes_constants import get_hermes_home
from utils import atomic_replace


CORE_SUMMARY_FILES = (
    "AGENTS.md",
    "standards/README.md",
    "templates/README.md",
    "validation/README.md",
    "workflows/README.md",
)

PROJECT_SUMMARY_FILES = (
    "project_context.md",
    "assumptions.md",
    "validation_history.md",
    "known_issues.md",
    "file_map.md",
)

USER_SUMMARY_FILES = (
    "preferences.md",
    "expertise.md",
    "workflow_preferences.md",
)

TEAM_SUMMARY_FILES = (
    "README.md",
    "approved/README.md",
    "approved/index.md",
    "experts.md",
    "expertise_map.md",
)

PROJECT_WRITE_TARGETS = {
    "project_context": "project_context.md",
    "assumptions": "assumptions.md",
    "validation_history": "validation_history.md",
    "known_issues": "known_issues.md",
    "file_map": "file_map.md",
}

USER_WRITE_TARGETS = {
    "preferences": "preferences.md",
    "expertise": "expertise.md",
    "workflow_preferences": "workflow_preferences.md",
}

_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _expand_path(value: str | os.PathLike[str] | None, default: Path) -> Path:
    raw = str(value or "").strip()
    if not raw:
        return default
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def _normalize_id(value: str, *, fallback: str = "default") -> str:
    normalized = _SAFE_ID_RE.sub("_", str(value or "").strip()).strip("._-")
    return normalized or fallback


def normalize_scope_id(value: str, *, fallback: str = "default") -> str:
    """Public wrapper for config/CLI callers."""
    return _normalize_id(value, fallback=fallback)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(value: str) -> str:
    slug = _SAFE_ID_RE.sub("-", str(value or "").lower()).strip("-._")
    return slug[:80] or "candidate"


def _yaml_string(value: str) -> str:
    return json.dumps(str(value or "").replace("\r", " ").replace("\n", " "))


def _scan_prompt_content(content: str, filename: str) -> str:
    """Return safe prompt content, or a blocked placeholder."""
    try:
        from tools.threat_patterns import scan_for_threats

        findings = scan_for_threats(content, scope="context")
    except Exception:
        findings = []
    if findings:
        return (
            f"[BLOCKED: {filename} contained potential prompt injection "
            f"({', '.join(findings)}). Content not loaded.]"
        )
    return content


def _scan_write_content(content: str) -> Optional[str]:
    try:
        from tools.memory_tool import _scan_memory_content

        return _scan_memory_content(content)
    except Exception:
        return None


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=".scoped_mem_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        atomic_replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


@dataclass
class ScopedMemoryConfig:
    enabled: bool = True
    root: Path = field(default_factory=lambda: get_hermes_home() / "scoped_memory")
    core_path: Path = field(default_factory=lambda: _repo_root() / "ava_core")
    team_path: Path = field(default_factory=lambda: get_hermes_home() / "scoped_memory" / "team_memory")
    projects_path: Path = field(default_factory=lambda: get_hermes_home() / "scoped_memory" / "projects")
    users_path: Path = field(default_factory=lambda: get_hermes_home() / "scoped_memory" / "users")
    project_id: str = ""
    user_id: str = "default"
    load_mode: str = "summaries"
    summary_char_limit: int = 3000
    total_char_limit: int = 12000

    @classmethod
    def from_mapping(
        cls,
        raw: Dict[str, Any] | None,
        *,
        runtime_user_id: str = "",
        runtime_user_name: str = "",
    ) -> "ScopedMemoryConfig":
        data = raw if isinstance(raw, dict) else {}
        home = get_hermes_home()
        root = _expand_path(data.get("root"), home / "scoped_memory")
        user_source = (
            str(data.get("user_id") or "").strip()
            or runtime_user_id
            or runtime_user_name
            or os.getenv("USER", "")
            or os.getenv("USERNAME", "")
            or "default"
        )
        return cls(
            enabled=bool(data.get("enabled", True)),
            root=root,
            core_path=_expand_path(data.get("core_path"), _repo_root() / "ava_core"),
            team_path=_expand_path(data.get("team_path"), root / "team_memory"),
            projects_path=_expand_path(data.get("projects_path"), root / "projects"),
            users_path=_expand_path(data.get("users_path"), root / "users"),
            project_id=_normalize_id(str(data.get("project_id") or ""), fallback=""),
            user_id=_normalize_id(user_source),
            load_mode=str(data.get("load_mode") or "summaries").strip().lower() or "summaries",
            summary_char_limit=max(500, int(data.get("summary_char_limit", 3000) or 3000)),
            total_char_limit=max(2000, int(data.get("total_char_limit", 12000) or 12000)),
        )


class ScopedMemoryStore:
    """Load and mutate AVA Core/Team/Project/User scoped memory."""

    def __init__(self, config: ScopedMemoryConfig):
        self.config = config
        self._snapshot = ""
        self._loaded_files: List[str] = []

    @classmethod
    def from_config(
        cls,
        raw: Dict[str, Any] | None,
        *,
        user_id: str = "",
        user_name: str = "",
    ) -> "ScopedMemoryStore":
        return cls(ScopedMemoryConfig.from_mapping(
            raw,
            runtime_user_id=user_id,
            runtime_user_name=user_name,
        ))

    @property
    def project_path(self) -> Optional[Path]:
        if not self.config.project_id:
            return None
        return self.config.projects_path / self.config.project_id

    @property
    def user_path(self) -> Path:
        return self.config.users_path / self.config.user_id

    @property
    def loaded_files(self) -> List[str]:
        return list(self._loaded_files)

    def initialize_layout(self, *, project_id: str = "", user_id: str = "") -> Dict[str, Any]:
        """Create the scoped memory directory skeleton without overwriting files."""
        project = _normalize_id(project_id or self.config.project_id, fallback="")
        user = _normalize_id(user_id or self.config.user_id)

        dirs = [
            self.config.root,
            self.config.team_path,
            self.config.team_path / "approved",
            self.config.team_path / "candidates",
            self.config.projects_path,
            self.config.users_path,
            self.config.users_path / user,
        ]
        if project:
            dirs.append(self.config.projects_path / project)
        for path in dirs:
            path.mkdir(parents=True, exist_ok=True)

        self._write_if_missing(
            self.config.team_path / "README.md",
            "# Team Memory\n\nApproved team knowledge is human-reviewed. "
            "AVA writes reusable discoveries to `candidates/` first.\n",
        )
        self._write_if_missing(
            self.config.team_path / "approved" / "README.md",
            "# Approved Team Knowledge\n\nHuman-approved reusable engineering knowledge belongs here.\n",
        )
        self._write_if_missing(
            self.config.team_path / "experts.md",
            "# Expertise Map\n\nRecord who owns or deeply understands important systems here.\n",
        )
        for name in USER_SUMMARY_FILES:
            self._write_if_missing(self.config.users_path / user / name, f"# {name[:-3].replace('_', ' ').title()}\n")
        if project:
            for name in PROJECT_SUMMARY_FILES:
                self._write_if_missing(self.config.projects_path / project / name, f"# {name[:-3].replace('_', ' ').title()}\n")

        return {
            "success": True,
            "root": str(self.config.root),
            "team_path": str(self.config.team_path),
            "projects_path": str(self.config.projects_path),
            "users_path": str(self.config.users_path),
            "project_id": project,
            "user_id": user,
        }

    @staticmethod
    def _write_if_missing(path: Path, content: str) -> None:
        if not path.exists():
            _atomic_write(path, content)

    def load_from_disk(self) -> None:
        self._loaded_files = []
        self._snapshot = ""
        if not self.config.enabled:
            return

        sections = []

        def remaining_budget() -> int:
            return self.config.total_char_limit - len("\n\n".join(sections))

        core_section = self._render_scope(
            "AVA Core",
            self.config.core_path,
            CORE_SUMMARY_FILES,
            remaining_budget=remaining_budget(),
        )
        if core_section.strip():
            sections.append(core_section)
        if self.project_path is not None:
            project_section = self._render_scope(
                f"Project Memory: {self.config.project_id}",
                self.project_path,
                PROJECT_SUMMARY_FILES,
                remaining_budget=remaining_budget(),
            )
            if project_section.strip():
                sections.append(project_section)
        team_section = self._render_team_scope(remaining_budget=remaining_budget())
        if team_section.strip():
            sections.append(team_section)
        user_section = self._render_scope(
            f"User Memory: {self.config.user_id}",
            self.user_path,
            USER_SUMMARY_FILES,
            remaining_budget=remaining_budget(),
        )
        if user_section.strip():
            sections.append(user_section)

        body = "\n\n".join(sections)
        if not body.strip():
            return
        self._snapshot = (
            "SCOPED MEMORY\n"
            "Priority: Compliance Rules > AVA Core > Project Memory > "
            "Team Memory > User Memory > Session Context. Lower-priority "
            "memory must not override higher-priority requirements.\n\n"
            f"{body}"
        )

    def format_for_system_prompt(self) -> Optional[str]:
        return self._snapshot or None

    def status(self) -> Dict[str, Any]:
        project_path = self.project_path
        return {
            "enabled": self.config.enabled,
            "root": str(self.config.root),
            "core_path": str(self.config.core_path),
            "team_path": str(self.config.team_path),
            "projects_path": str(self.config.projects_path),
            "users_path": str(self.config.users_path),
            "project_id": self.config.project_id,
            "project_path": str(project_path) if project_path else "",
            "user_id": self.config.user_id,
            "user_path": str(self.user_path),
            "load_mode": self.config.load_mode,
            "loaded_files": self.loaded_files,
            "candidate_count": len(self.list_candidate_paths()),
        }

    def _render_team_scope(self, *, remaining_budget: Optional[int] = None) -> str:
        files = list(TEAM_SUMMARY_FILES)
        approved = self.config.team_path / "approved"
        if approved.is_dir():
            for child in sorted(approved.iterdir()):
                if child.is_dir():
                    files.append(f"approved/{child.name}/README.md")
        return self._render_scope(
            "Team Memory",
            self.config.team_path,
            files,
            remaining_budget=remaining_budget,
        )

    def _render_scope(
        self,
        label: str,
        base: Optional[Path],
        rel_files: Iterable[str],
        *,
        remaining_budget: Optional[int] = None,
    ) -> str:
        if base is None:
            return ""
        parts = []
        prefix = f"### {label}\n"
        budget = remaining_budget if remaining_budget is not None else self.config.total_char_limit
        if budget <= len(prefix):
            return ""
        for rel in rel_files:
            path = base / rel
            if not path.is_file():
                continue
            text = self._read_prompt_file(path, base)
            if not text:
                continue
            if len(text) > self.config.summary_char_limit:
                text = self._truncate_text(text, self.config.summary_char_limit)
            sep = "\n\n" if parts else ""
            header = f"## {rel}\n"
            used = len(prefix) + self._snapshot_size(parts) + len(sep) + len(header)
            text_budget = budget - used
            if text_budget <= 0:
                break
            if len(text) > text_budget:
                text = self._truncate_text(text, text_budget)
            parts.append(f"## {rel}\n{text}")
        if not parts:
            return ""
        return prefix + "\n\n".join(parts)

    @staticmethod
    def _snapshot_size(parts: Iterable[str]) -> int:
        return sum(len(part) for part in parts)

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        if limit <= 0:
            return ""
        if len(text) <= limit:
            return text
        marker = "\n[TRUNCATED]"
        if limit <= len(marker):
            return text[:limit]
        return text[: limit - len(marker)].rstrip() + marker

    def _read_prompt_file(self, path: Path, base: Path) -> str:
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            return ""
        if not raw:
            return ""
        rel = str(path.relative_to(base)) if path.is_relative_to(base) else path.name
        self._loaded_files.append(str(path))
        return _scan_prompt_content(raw, rel)

    def read_scope(self, scope: str, *, path: str = "") -> Dict[str, Any]:
        base = self._base_for_scope(scope)
        if base is None:
            return {"success": False, "error": f"Scope '{scope}' is not active."}
        if path:
            target = self._safe_child(base, path)
            if target is None or not target.is_file():
                return {"success": False, "error": "Requested scoped memory file was not found."}
            try:
                content = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                return {"success": False, "error": f"Failed to read scoped memory file: {exc}"}
            return {
                "success": True,
                "scope": scope,
                "path": str(target),
                "content": _scan_prompt_content(content, str(target)),
            }
        prior_loaded = list(self._loaded_files)
        self._loaded_files = []
        content = self._render_single_scope(scope)
        loaded_files = list(self._loaded_files)
        self._loaded_files = prior_loaded
        return {
            "success": True,
            "scope": scope,
            "content": content,
            "loaded_files": loaded_files,
        }

    def _render_single_scope(self, scope: str) -> str:
        normalized = str(scope or "").strip().lower()
        if normalized in {"core", "ava_core"}:
            return self._render_scope("AVA Core", self.config.core_path, CORE_SUMMARY_FILES)
        if normalized in {"team", "team_memory"}:
            return self._render_team_scope()
        if normalized in {"project", "project_memory"}:
            if self.project_path is None:
                return ""
            return self._render_scope(
                f"Project Memory: {self.config.project_id}",
                self.project_path,
                PROJECT_SUMMARY_FILES,
            )
        if normalized in {"user", "personal", "user_memory"}:
            return self._render_scope(
                f"User Memory: {self.config.user_id}",
                self.user_path,
                USER_SUMMARY_FILES,
            )
        return ""

    def _base_for_scope(self, scope: str) -> Optional[Path]:
        normalized = str(scope or "").strip().lower()
        if normalized in {"core", "ava_core"}:
            return self.config.core_path
        if normalized in {"team", "team_memory"}:
            return self.config.team_path
        if normalized in {"project", "project_memory"}:
            return self.project_path
        if normalized in {"user", "personal", "user_memory"}:
            return self.user_path
        return None

    @staticmethod
    def _safe_child(base: Path, rel_path: str) -> Optional[Path]:
        if not rel_path or Path(rel_path).is_absolute():
            return None
        try:
            target = (base / rel_path).resolve()
            target.relative_to(base.resolve())
            return target
        except (OSError, ValueError):
            return None

    def save_personal(self, content: str, *, category: str = "preferences") -> Dict[str, Any]:
        category_key = str(category or "preferences").strip().lower()
        filename = USER_WRITE_TARGETS.get(category_key)
        if not filename:
            return {"success": False, "error": f"Unknown user memory category '{category}'."}
        return self._append_markdown_entry(
            self.user_path / filename,
            content,
            heading="AVA Note",
            metadata={"scope": "user", "category": category_key},
        )

    def save_project(self, content: str, *, category: str = "project_context") -> Dict[str, Any]:
        if self.project_path is None:
            return {
                "success": False,
                "error": "No active project_id is configured for Project Memory.",
            }
        category_key = str(category or "project_context").strip().lower()
        filename = PROJECT_WRITE_TARGETS.get(category_key)
        if not filename:
            return {"success": False, "error": f"Unknown project memory category '{category}'."}
        return self._append_markdown_entry(
            self.project_path / filename,
            content,
            heading="AVA Note",
            metadata={
                "scope": "project",
                "project_id": self.config.project_id,
                "category": category_key,
            },
        )

    def propose_team_candidate(
        self,
        content: str,
        *,
        title: str = "",
        scope: str = "",
        source: str = "",
        applicability_limits: str = "",
    ) -> Dict[str, Any]:
        content = str(content or "").strip()
        if not content:
            return {"success": False, "error": "Content cannot be empty."}
        scan_error = _scan_write_content(content)
        if scan_error:
            return {"success": False, "error": scan_error}
        title = str(title or "").strip() or "Untitled candidate knowledge"
        timestamp = _utc_timestamp()
        slug = _slugify(title)
        candidates = self.config.team_path / "candidates"
        candidates.mkdir(parents=True, exist_ok=True)
        path = candidates / f"{timestamp.replace(':', '').replace('-', '')}-{slug}.md"
        counter = 2
        while path.exists():
            path = candidates / f"{timestamp.replace(':', '').replace('-', '')}-{slug}-{counter}.md"
            counter += 1
        body = (
            "---\n"
            f"title: {_yaml_string(title)}\n"
            f"scope: {_yaml_string(scope or 'team')}\n"
            f"proposed_by: {_yaml_string(self.config.user_id)}\n"
            f"created_at: {_yaml_string(timestamp)}\n"
            "review_status: candidate\n"
            f"source: {_yaml_string(source or 'ava_memory_tool')}\n"
            "---\n\n"
            f"# {title}\n\n"
            "## Proposed Content\n\n"
            f"{content}\n\n"
            "## Applicability Limits\n\n"
            f"{applicability_limits or 'Not specified.'}\n"
        )
        _atomic_write(path, body)
        return {
            "success": True,
            "message": "Team candidate knowledge saved for review.",
            "path": str(path),
            "review_status": "candidate",
        }

    def list_candidate_paths(self) -> List[Path]:
        candidates = self.config.team_path / "candidates"
        if not candidates.is_dir():
            return []
        return sorted(p for p in candidates.glob("*.md") if p.is_file())

    def list_candidates(self) -> Dict[str, Any]:
        items = []
        for path in self.list_candidate_paths():
            items.append({
                "path": str(path),
                "name": path.name,
                "size": path.stat().st_size,
            })
        return {"success": True, "candidates": items, "count": len(items)}

    def _append_markdown_entry(
        self,
        path: Path,
        content: str,
        *,
        heading: str,
        metadata: Dict[str, str],
    ) -> Dict[str, Any]:
        content = str(content or "").strip()
        if not content:
            return {"success": False, "error": "Content cannot be empty."}
        scan_error = _scan_write_content(content)
        if scan_error:
            return {"success": False, "error": scan_error}
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = ""
        if path.exists():
            try:
                existing = path.read_text(encoding="utf-8").rstrip()
            except (OSError, UnicodeDecodeError):
                existing = ""
        if not existing:
            existing = f"# {path.stem.replace('_', ' ').title()}"
        meta = " ".join(f"{key}={value}" for key, value in metadata.items() if value)
        entry = f"\n\n## {heading} - {_utc_timestamp()}\n\n{content}\n"
        if meta:
            entry += f"\n_Metadata: {meta}_\n"
        _atomic_write(path, existing + entry)
        return {"success": True, "path": str(path), "message": "Scoped memory saved."}

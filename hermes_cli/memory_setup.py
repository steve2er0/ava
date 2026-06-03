"""hermes memory setup|status — configure memory provider plugins.

Auto-detects installed memory providers via the plugin system.
Interactive curses-based UI for provider selection, then walks through
the provider's config schema. Writes config to config.yaml + .env.
"""

from __future__ import annotations

import os
import sys
import shlex
from pathlib import Path

from hermes_constants import get_hermes_home
from hermes_cli.secret_prompt import masked_secret_prompt


# ---------------------------------------------------------------------------
# Curses-based interactive picker (same pattern as hermes tools)
# ---------------------------------------------------------------------------

def _curses_select(title: str, items: list[tuple[str, str]], default: int = 0) -> int:
    """Interactive single-select with arrow keys.

    items: list of (label, description) tuples.
    Returns selected index, or default on escape/quit.
    """
    from hermes_cli.curses_ui import curses_radiolist
    # Format (label, desc) tuples into display strings
    display_items = [
        f"{label}  {desc}" if desc else label
        for label, desc in items
    ]
    return curses_radiolist(title, display_items, selected=default, cancel_returns=default)


def _prompt(label: str, default: str | None = None, secret: bool = False) -> str:
    """Prompt for a value with optional default and secret masking."""
    suffix = f" [{default}]" if default else ""
    if secret:
        val = masked_secret_prompt(f"  {label}{suffix}: ")
    else:
        sys.stdout.write(f"  {label}{suffix}: ")
        sys.stdout.flush()
        val = sys.stdin.readline().strip()
    return val or (default or "")


# ---------------------------------------------------------------------------
# Provider discovery
# ---------------------------------------------------------------------------

def _install_dependencies(provider_name: str) -> None:
    """Install pip dependencies declared in plugin.yaml."""
    import subprocess
    from plugins.memory import find_provider_dir

    plugin_dir = find_provider_dir(provider_name)
    if not plugin_dir:
        return
    yaml_path = plugin_dir / "plugin.yaml"
    if not yaml_path.exists():
        return

    try:
        import yaml
        with open(yaml_path, encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}
    except Exception:
        return

    pip_deps = meta.get("pip_dependencies", [])
    if not pip_deps:
        return

    # pip name → import name mapping for packages where they differ
    _IMPORT_NAMES = {
        "honcho-ai": "honcho",
        "mem0ai": "mem0",
        "hindsight-client": "hindsight_client",
        "hindsight-all": "hindsight",
    }

    # Check which packages are missing
    missing = []
    for dep in pip_deps:
        import_name = _IMPORT_NAMES.get(dep, dep.replace("-", "_").split("[")[0])
        try:
            __import__(import_name)
        except ImportError:
            missing.append(dep)

    if not missing:
        return

    print(f"\n  Installing dependencies: {', '.join(missing)}")

    import shutil
    uv_path = shutil.which("uv")
    if not uv_path:
        print(f"  ⚠ uv not found — cannot install dependencies")
        print("  Install uv:")
        print("    curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh")
        print("    sh /tmp/uv-install.sh")
        print(f"  Then re-run: hermes memory setup")
        return

    try:
        subprocess.run(
            [uv_path, "pip", "install", "--python", sys.executable, "--quiet"] + missing,
            check=True, timeout=120,
            capture_output=True,
        )
        print(f"  ✓ Installed {', '.join(missing)}")
    except subprocess.CalledProcessError as e:
        print(f"  ⚠ Failed to install {', '.join(missing)}")
        stderr = (e.stderr or b"").decode()[:200]
        if stderr:
            print(f"    {stderr}")
        print(f"  Run manually: uv pip install --python {sys.executable} {' '.join(missing)}")
    except Exception as e:
        print(f"  ⚠ Install failed: {e}")
        print(f"  Run manually: uv pip install --python {sys.executable} {' '.join(missing)}")

    # Also show external dependencies (non-pip) if any
    ext_deps = meta.get("external_dependencies", [])
    for dep in ext_deps:
        dep_name = dep.get("name", "")
        check_cmd = dep.get("check", "")
        install_cmd = dep.get("install", "")
        if check_cmd:
            try:
                subprocess.run(
                    shlex.split(check_cmd), check=True, capture_output=True, timeout=5
                )
            except Exception:
                if install_cmd:
                    print(f"\n  ⚠ '{dep_name}' not found. Install with:")
                    print(f"    {install_cmd}")


def _get_available_providers() -> list:
    """Discover memory providers from plugins/memory/.

    Returns list of (name, description, provider_instance) tuples.
    """
    try:
        from plugins.memory import discover_memory_providers, load_memory_provider
        raw = discover_memory_providers()
    except Exception:
        raw = []

    results = []
    for name, desc, available in raw:
        try:
            provider = load_memory_provider(name)
            if not provider:
                continue
        except Exception:
            continue

        schema = provider.get_config_schema() if hasattr(provider, "get_config_schema") else []
        has_secrets = any(f.get("secret") for f in schema)
        has_non_secrets = any(not f.get("secret") for f in schema)
        if has_secrets and has_non_secrets:
            setup_hint = "API key / local"
        elif has_secrets:
            setup_hint = "requires API key"
        elif not schema:
            setup_hint = "no setup needed"
        else:
            setup_hint = "local"

        results.append((name, setup_hint, provider))
    return results


# ---------------------------------------------------------------------------
# Setup wizard
# ---------------------------------------------------------------------------

def cmd_setup_provider(provider_name: str) -> None:
    """Run memory setup for a specific provider, skipping the picker."""
    from hermes_cli.config import load_config, save_config

    providers = _get_available_providers()
    match = None
    for name, desc, provider in providers:
        if name == provider_name:
            match = (name, desc, provider)
            break

    if not match:
        print(f"\n  Memory provider '{provider_name}' not found.")
        print("  Run 'hermes memory setup' to see available providers.\n")
        return

    name, _, provider = match

    _install_dependencies(name)

    config = load_config()
    if not isinstance(config.get("memory"), dict):
        config["memory"] = {}

    if hasattr(provider, "post_setup"):
        hermes_home = str(get_hermes_home())
        provider.post_setup(hermes_home, config)
        return

    # Fallback: generic schema-based setup (same as cmd_setup)
    config["memory"]["provider"] = name
    save_config(config)
    print(f"\n  Memory provider: {name}")
    print(f"  Activation saved to config.yaml\n")


def cmd_setup(args) -> None:
    """Interactive memory provider setup wizard."""
    from hermes_cli.config import load_config, save_config

    providers = _get_available_providers()

    if not providers:
        print("\n  No memory provider plugins detected.")
        print("  Install a plugin to ~/.hermes/plugins/ and try again.\n")
        return

    # Build picker items
    items = []
    for name, desc, _ in providers:
        items.append((name, f"— {desc}"))
    items.append(("Built-in only", "— MEMORY.md / USER.md (default)"))

    builtin_idx = len(items) - 1
    selected = _curses_select("Memory provider setup", items, default=builtin_idx)

    config = load_config()
    if not isinstance(config.get("memory"), dict):
        config["memory"] = {}

    # Built-in only
    if selected >= len(providers) or selected < 0:
        config["memory"]["provider"] = ""
        save_config(config)
        print("\n  ✓ Memory provider: built-in only")
        print("  Saved to config.yaml\n")
        return

    name, _, provider = providers[selected]

    # Install pip dependencies if declared in plugin.yaml
    _install_dependencies(name)

    # If the provider has a post_setup hook, delegate entirely to it.
    # The hook handles its own config, connection test, and activation.
    if hasattr(provider, "post_setup"):
        hermes_home = str(get_hermes_home())
        provider.post_setup(hermes_home, config)
        return

    schema = provider.get_config_schema() if hasattr(provider, "get_config_schema") else []

    provider_config = config["memory"].get(name, {})
    if not isinstance(provider_config, dict):
        provider_config = {}

    env_path = get_hermes_home() / ".env"
    env_writes = {}

    if schema:
        print(f"\n  Configuring {name}:\n")

        for field in schema:
            key = field["key"]
            desc = field.get("description", key)
            default = field.get("default")
            # Dynamic default: look up default from another field's value
            default_from = field.get("default_from")
            if default_from and isinstance(default_from, dict):
                ref_field = default_from.get("field", "")
                ref_map = default_from.get("map", {})
                ref_value = provider_config.get(ref_field, "")
                if ref_value and ref_value in ref_map:
                    default = ref_map[ref_value]
            is_secret = field.get("secret", False)
            choices = field.get("choices")
            env_var = field.get("env_var")
            url = field.get("url")

            # Skip fields whose "when" condition doesn't match
            when = field.get("when")
            if when and isinstance(when, dict):
                if not all(provider_config.get(k) == v for k, v in when.items()):
                    continue

            if choices and not is_secret:
                # Use curses picker for choice fields
                choice_items = [(c, "") for c in choices]
                current = provider_config.get(key, default)
                current_idx = 0
                if current and current in choices:
                    current_idx = choices.index(current)
                sel = _curses_select(f"  {desc}", choice_items, default=current_idx)
                provider_config[key] = choices[sel]
            elif is_secret:
                # Prompt for secret
                existing = os.environ.get(env_var, "") if env_var else ""
                if existing:
                    masked = f"...{existing[-4:]}" if len(existing) > 4 else "set"
                    val = _prompt(f"{desc} (current: {masked}, blank to keep)", secret=True)
                else:
                    hint = f"  Get yours at {url}" if url else ""
                    if hint:
                        print(hint)
                    val = _prompt(desc, secret=True)
                if val and env_var:
                    env_writes[env_var] = val
            else:
                # Regular text prompt
                current = provider_config.get(key)
                effective_default = current or default
                val = _prompt(desc, default=str(effective_default) if effective_default else None)
                if val:
                    provider_config[key] = val
                    # Also write to .env if this field has an env_var
                    if env_var and env_var not in env_writes:
                        env_writes[env_var] = val

    # Write activation key to config.yaml
    config["memory"]["provider"] = name
    save_config(config)

    # Write non-secret config to provider's native location
    hermes_home = str(get_hermes_home())
    if provider_config and hasattr(provider, "save_config"):
        try:
            provider.save_config(provider_config, hermes_home)
        except Exception as e:
            print(f"  Failed to write provider config: {e}")

    # Write secrets to .env
    if env_writes:
        _write_env_vars(env_path, env_writes)

    print(f"\n  Memory provider: {name}")
    print(f"  Activation saved to config.yaml")
    if provider_config:
        print(f"  Provider config saved")
    if env_writes:
        print(f"  API keys saved to .env")
    print(f"\n  Start a new session to activate.\n")


def _write_env_vars(env_path: Path, env_writes: dict) -> None:
    """Append or update env vars in .env file."""
    env_path.parent.mkdir(parents=True, exist_ok=True)

    existing_lines = []
    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()

    updated_keys = set()
    new_lines = []
    for line in existing_lines:
        key_match = line.split("=", 1)[0].strip() if "=" in line else ""
        if key_match in env_writes:
            new_lines.append(f"{key_match}={env_writes[key_match]}")
            updated_keys.add(key_match)
        else:
            new_lines.append(line)

    for key, val in env_writes.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    # Restrict permissions — .env holds API keys and tokens.
    try:
        import stat
        env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass  # Windows or read-only FS


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def _scoped_store_from_config(config: dict):
    from agent.scoped_memory import ScopedMemoryStore

    mem_config = config.get("memory", {})
    scopes_config = mem_config.get("scopes", {}) if isinstance(mem_config, dict) else {}
    return ScopedMemoryStore.from_config(scopes_config)


def _ensure_scopes_config(config: dict) -> dict:
    if not isinstance(config.get("memory"), dict):
        config["memory"] = {}
    scopes = config["memory"].get("scopes")
    if not isinstance(scopes, dict):
        scopes = {}
        config["memory"]["scopes"] = scopes
    scopes.setdefault("enabled", True)
    scopes.setdefault("load_mode", "summaries")
    return scopes


def cmd_init_scopes(args) -> None:
    """Create the scoped-memory directory skeleton."""
    from hermes_cli.config import load_config, save_config
    from agent.scoped_memory import normalize_scope_id

    config = load_config()
    scopes = _ensure_scopes_config(config)
    project_id = normalize_scope_id(
        str(getattr(args, "project", "") or "").strip(),
        fallback="",
    )
    user_id = normalize_scope_id(
        str(getattr(args, "user", "") or "").strip(),
        fallback="",
    )
    if project_id:
        scopes["project_id"] = project_id
    if user_id:
        scopes["user_id"] = user_id
    save_config(config)

    store = _scoped_store_from_config(config)
    result = store.initialize_layout(project_id=project_id, user_id=user_id)

    print("\nScoped memory initialized")
    print("─" * 40)
    print(f"  Root:      {result['root']}")
    print(f"  Team:      {result['team_path']}")
    print(f"  Projects:  {result['projects_path']}")
    print(f"  Users:     {result['users_path']}")
    if result.get("project_id"):
        print(f"  Project:   {result['project_id']}")
    print(f"  User:      {result['user_id']}")
    print("\n  Team writes from AVA go to team_memory/candidates/ for review.\n")


def cmd_project(args) -> None:
    """Set or show the explicit active Project Memory id."""
    from hermes_cli.config import load_config, save_config
    from agent.scoped_memory import normalize_scope_id

    config = load_config()
    scopes = _ensure_scopes_config(config)
    action = getattr(args, "project_action", None)
    if action == "set":
        project_id = normalize_scope_id(
            str(getattr(args, "project_id", "") or "").strip(),
            fallback="",
        )
        if not project_id:
            print("\n  Project id cannot be empty.\n")
            return
        scopes["project_id"] = project_id
        save_config(config)
        print(f"\n  ✓ Active Project Memory: {project_id}")
        print("  Start a new session for the prompt snapshot to include it.\n")
        return
    current = scopes.get("project_id") or "(none)"
    print(f"\n  Active Project Memory: {current}\n")


def cmd_status(args) -> None:
    """Show current memory provider config."""
    from hermes_cli.config import load_config

    config = load_config()
    mem_config = config.get("memory", {})
    provider_name = mem_config.get("provider", "")

    print(f"\nMemory status\n" + "─" * 40)
    print(f"  Built-in:  always active")
    print(f"  Provider:  {provider_name or '(none — built-in only)'}")

    try:
        store = _scoped_store_from_config(config)
        store.load_from_disk()
        scoped = store.status()
        print(f"\nScoped memory")
        print(f"  Enabled:   {'yes' if scoped['enabled'] else 'no'}")
        print(f"  Project:   {scoped['project_id'] or '(none)'}")
        print(f"  User:      {scoped['user_id']}")
        print(f"  Root:      {scoped['root']}")
        print(f"  Core:      {scoped['core_path']}")
        print(f"  Team:      {scoped['team_path']}")
        print(f"  Candidates:{scoped['candidate_count']}")
        if scoped["loaded_files"]:
            print("  Loaded:")
            for path in scoped["loaded_files"]:
                print(f"    • {path}")
        elif scoped["enabled"]:
            print("  Loaded:    (no scoped summary files found)")
    except Exception as exc:
        print(f"\nScoped memory: status unavailable ({exc})")

    if provider_name:
        provider_config = mem_config.get(provider_name, {})
        if provider_config:
            print(f"\n  {provider_name} config:")
            for key, val in provider_config.items():
                print(f"    {key}: {val}")

        providers = _get_available_providers()
        found = any(name == provider_name for name, _, _ in providers)
        if found:
            print(f"\n  Plugin:    installed ✓")
            for pname, _, p in providers:
                if pname == provider_name:
                    if p.is_available():
                        print(f"  Status:    available ✓")
                    else:
                        print(f"  Status:    not available ✗")
                        schema = p.get_config_schema() if hasattr(p, "get_config_schema") else []
                        # Check all fields that have env_var (both secret and non-secret)
                        required_fields = [f for f in schema if f.get("env_var")]
                        if required_fields:
                            print(f"  Missing:")
                            for f in required_fields:
                                env_var = f.get("env_var", "")
                                url = f.get("url", "")
                                is_set = bool(os.environ.get(env_var))
                                mark = "✓" if is_set else "✗"
                                line = f"    {mark} {env_var}"
                                if url and not is_set:
                                    line += f"  → {url}"
                                print(line)
                    break
        else:
            print(f"\n  Plugin:    NOT installed ✗")
            print(f"  Install the '{provider_name}' memory plugin to ~/.hermes/plugins/")

    providers = _get_available_providers()
    if providers:
        print(f"\n  Installed plugins:")
        for pname, desc, _ in providers:
            active = " ← active" if pname == provider_name else ""
            print(f"    • {pname}  ({desc}){active}")

    print()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def memory_command(args) -> None:
    """Route memory subcommands."""
    sub = getattr(args, "memory_command", None)
    if sub == "setup":
        provider = getattr(args, "provider", None)
        if provider:
            cmd_setup_provider(provider)
        else:
            cmd_setup(args)
    elif sub == "status":
        cmd_status(args)
    elif sub == "init-scopes":
        cmd_init_scopes(args)
    elif sub == "project":
        cmd_project(args)
    else:
        cmd_status(args)

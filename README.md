# AVA

AVA is a fork of Hermes shaped into a vibroacoustic agent that learns with you.
It keeps the upstream agent runtime, tool system, gateway, scheduler, memory,
and setup machinery, then adds AVA-specific vibration, acoustics, shock, modal,
Nastran, OP2, and engineering-analysis tools.

## Quick Install

### Linux, macOS, WSL2, Termux

```bash
curl -fsSL https://raw.githubusercontent.com/steve2er0/ava/main/scripts/install.sh | bash
```

### Windows PowerShell

```powershell
iex (irm https://raw.githubusercontent.com/steve2er0/ava/main/scripts/install.ps1)
```

Fresh installs use:

- Command: `ava`
- Data directory: `~/.ava` on Unix-like systems
- Windows data directory: `%LOCALAPPDATA%\ava`
- Source checkout: `~/.ava/ava-agent` or `%LOCALAPPDATA%\ava\ava-agent`

The legacy `hermes` command is still installed as an alias for compatibility.

## Getting Started

```bash
ava              # Start a conversation
ava setup        # Configure providers, tools, gateway, and API keys
ava model        # Choose your LLM provider and model
ava tools        # Configure enabled tools
ava status       # Check configuration
ava gateway      # Start the messaging gateway
ava update       # Update to the latest fork version
ava doctor       # Diagnose setup issues
```

## AVA Engineering Tools

This fork includes bundled AVA tools under `plugins/ava`:

- `ava_compute_modal_frf`
- `ava_compute_srs`
- `ava_summarize_bdf`
- `ava_inspect_op2`
- `ava_build_modal_deck`
- `ava_run_shock_delta`

The supporting Python packages are `ava_runtime` and `ava_knowledge`.

## Developer Setup

```bash
git clone https://github.com/steve2er0/ava.git
cd ava
./setup-ava.sh
./ava
```

Manual setup:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv venv --python 3.11
source venv/bin/activate
uv pip install -e ".[all,dev]"
scripts/run_tests.sh
```

## Compatibility Notes

The internal Python namespace is still `hermes_cli` in this pass. That keeps the
fork compatible with the upstream runtime while the user-facing install,
command, package name, repository URL, and data directory move to AVA.

`HERMES_HOME` is still honored as a legacy environment-variable alias. Prefer
`AVA_HOME` for new installs and scripts.

## License

MIT. See [LICENSE](LICENSE).

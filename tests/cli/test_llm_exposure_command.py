"""Tests for the /llm-exposure CLI command."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _import_cli():
    import hermes_cli.config as config_mod

    if not hasattr(config_mod, "save_env_value_secure"):
        config_mod.save_env_value_secure = lambda key, value: {
            "success": True,
            "stored_as": key,
            "validated": False,
        }

    import cli as cli_mod

    return cli_mod


class TestHandleLlmExposureCommand(unittest.TestCase):
    def _make_cli(self, llm_exposure="full", agent=None):
        return SimpleNamespace(
            llm_exposure=llm_exposure,
            agent=agent,
        )

    def test_no_args_shows_status(self):
        cli_mod = _import_cli()
        stub = self._make_cli("minimal")
        with (
            patch.object(cli_mod, "_cprint") as mock_cprint,
            patch.object(cli_mod, "save_config_value") as mock_save,
        ):
            cli_mod.HermesCLI._handle_llm_exposure_command(stub, "/llm-exposure")

        mock_save.assert_not_called()
        printed = " ".join(str(c) for c in mock_cprint.call_args_list)
        self.assertIn("minimal", printed)
        self.assertIn("protected-output", printed)

    def test_minimal_argument_updates_session_agent_and_config(self):
        cli_mod = _import_cli()
        agent = MagicMock()
        agent.llm_exposure = "full"
        stub = self._make_cli("full", agent=agent)
        with (
            patch.object(cli_mod, "_cprint"),
            patch.object(cli_mod, "save_config_value", return_value=True) as mock_save,
        ):
            cli_mod.HermesCLI._handle_llm_exposure_command(stub, "/llm-exposure minimal")

        self.assertEqual(stub.llm_exposure, "minimal")
        self.assertEqual(agent.llm_exposure, "minimal")
        mock_save.assert_called_once_with("security.llm_exposure", "minimal")

    def test_full_argument_updates_session_agent_and_config(self):
        cli_mod = _import_cli()
        agent = MagicMock()
        agent.llm_exposure = "minimal"
        stub = self._make_cli("minimal", agent=agent)
        with (
            patch.object(cli_mod, "_cprint"),
            patch.object(cli_mod, "save_config_value", return_value=True) as mock_save,
        ):
            cli_mod.HermesCLI._handle_llm_exposure_command(stub, "/llm-exposure full")

        self.assertEqual(stub.llm_exposure, "full")
        self.assertEqual(agent.llm_exposure, "full")
        mock_save.assert_called_once_with("security.llm_exposure", "full")

    def test_invalid_argument_prints_usage(self):
        cli_mod = _import_cli()
        stub = self._make_cli("full")
        with (
            patch.object(cli_mod, "_cprint") as mock_cprint,
            patch.object(cli_mod, "save_config_value") as mock_save,
        ):
            cli_mod.HermesCLI._handle_llm_exposure_command(stub, "/llm-exposure private")

        mock_save.assert_not_called()
        printed = " ".join(str(c) for c in mock_cprint.call_args_list)
        self.assertIn("Usage: /llm-exposure", printed)


class TestLlmExposureCommandRegistry(unittest.TestCase):
    def test_command_and_alias_resolve(self):
        from hermes_cli.commands import COMMANDS, resolve_command

        assert "/llm-exposure" in COMMANDS
        assert "/llm_exposure" in COMMANDS
        assert resolve_command("llm-exposure").name == "llm-exposure"
        assert resolve_command("llm_exposure").name == "llm-exposure"

    def test_subcommands_documented(self):
        from hermes_cli.commands import COMMAND_REGISTRY, SUBCOMMANDS

        cmd = next(c for c in COMMAND_REGISTRY if c.name == "llm-exposure")
        assert cmd.category == "Configuration"
        assert cmd.cli_only is True
        assert cmd.args_hint == "[full|minimal|status]"
        assert SUBCOMMANDS["/llm-exposure"] == ["full", "minimal", "status"]

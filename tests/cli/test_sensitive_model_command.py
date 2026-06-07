"""Tests for the /sensitive-model CLI command."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch


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


class TestHandleSensitiveModelCommand(unittest.TestCase):
    def _make_cli(self):
        return SimpleNamespace(
            provider="openai-codex",
            model="gpt-5.5",
        )

    def test_no_args_shows_primary_and_sensitive_status(self):
        cli_mod = _import_cli()
        stub = self._make_cli()
        cfg = {
            "model": {"provider": "openai-codex", "default": "gpt-5.5"},
            "auxiliary": {"sensitive_data": {"provider": "auto", "model": ""}},
        }
        with (
            patch("hermes_cli.config.load_config", return_value=cfg),
            patch.object(cli_mod, "_cprint") as mock_cprint,
            patch.object(cli_mod, "save_config_value") as mock_save,
        ):
            cli_mod.HermesCLI._handle_sensitive_model_command(stub, "/sensitive-model")

        mock_save.assert_not_called()
        printed = " ".join(str(c) for c in mock_cprint.call_args_list)
        self.assertIn("Primary model", printed)
        self.assertIn("gpt-5.5", printed)
        self.assertIn("Sensitive model", printed)
        self.assertIn("not configured", printed)

    def test_openai_alias_sets_sensitive_model(self):
        cli_mod = _import_cli()
        stub = self._make_cli()
        with (
            patch.object(cli_mod, "_cprint"),
            patch.object(cli_mod, "save_config_value", return_value=True) as mock_save,
        ):
            cli_mod.HermesCLI._handle_sensitive_model_command(
                stub, "/sensitive-model openai gpt-4o-mini"
            )

        self.assertEqual(
            mock_save.call_args_list[0].args,
            ("auxiliary.sensitive_data.provider", "openai-api"),
        )
        self.assertEqual(
            mock_save.call_args_list[1].args,
            ("auxiliary.sensitive_data.model", "gpt-4o-mini"),
        )
        self.assertEqual(
            mock_save.call_args_list[2].args,
            ("auxiliary.sensitive_data.base_url", ""),
        )
        self.assertEqual(
            mock_save.call_args_list[3].args,
            ("auxiliary.sensitive_data.api_key", ""),
        )
        self.assertEqual(
            mock_save.call_args_list[4].args,
            ("auxiliary.sensitive_data.api_mode", ""),
        )

    def test_custom_endpoint_sets_sensitive_model(self):
        cli_mod = _import_cli()
        stub = self._make_cli()
        with (
            patch.object(cli_mod, "_cprint"),
            patch.object(cli_mod, "save_config_value", return_value=True) as mock_save,
        ):
            cli_mod.HermesCLI._handle_sensitive_model_command(
                stub,
                "/sensitive-model custom approved-sensitive http://localhost:11434/v1",
            )

        self.assertEqual(
            mock_save.call_args_list[0].args,
            ("auxiliary.sensitive_data.provider", "custom"),
        )
        self.assertEqual(
            mock_save.call_args_list[1].args,
            ("auxiliary.sensitive_data.model", "approved-sensitive"),
        )
        self.assertEqual(
            mock_save.call_args_list[2].args,
            ("auxiliary.sensitive_data.base_url", "http://localhost:11434/v1"),
        )
        self.assertEqual(
            mock_save.call_args_list[3].args,
            ("auxiliary.sensitive_data.api_key", ""),
        )
        self.assertEqual(
            mock_save.call_args_list[4].args,
            ("auxiliary.sensitive_data.api_mode", ""),
        )

    def test_reset_leaves_sensitive_reads_fail_closed(self):
        cli_mod = _import_cli()
        stub = self._make_cli()
        with (
            patch.object(cli_mod, "_cprint") as mock_cprint,
            patch.object(cli_mod, "save_config_value", return_value=True) as mock_save,
        ):
            cli_mod.HermesCLI._handle_sensitive_model_command(
                stub, "/sensitive-model reset"
            )

        self.assertEqual(
            mock_save.call_args_list[0].args,
            ("auxiliary.sensitive_data.provider", "auto"),
        )
        printed = " ".join(str(c) for c in mock_cprint.call_args_list)
        self.assertIn("fail closed", printed)

    def test_rejects_auto_or_main_as_sensitive_model(self):
        cli_mod = _import_cli()
        stub = self._make_cli()
        with (
            patch.object(cli_mod, "_cprint") as mock_cprint,
            patch.object(cli_mod, "save_config_value") as mock_save,
        ):
            cli_mod.HermesCLI._handle_sensitive_model_command(
                stub, "/sensitive-model main"
            )

        mock_save.assert_not_called()
        printed = " ".join(str(c) for c in mock_cprint.call_args_list)
        self.assertIn("cannot use", printed)


class TestSensitiveModelCommandRegistry(unittest.TestCase):
    def test_command_and_alias_resolve(self):
        from hermes_cli.commands import COMMANDS, resolve_command

        assert "/sensitive-model" in COMMANDS
        assert "/sensitive_model" in COMMANDS
        assert resolve_command("sensitive-model").name == "sensitive-model"
        assert resolve_command("sensitive_model").name == "sensitive-model"

    def test_subcommands_documented(self):
        from hermes_cli.commands import COMMAND_REGISTRY, SUBCOMMANDS

        cmd = next(c for c in COMMAND_REGISTRY if c.name == "sensitive-model")
        assert cmd.category == "Configuration"
        assert cmd.cli_only is True
        assert "custom" in SUBCOMMANDS["/sensitive-model"]

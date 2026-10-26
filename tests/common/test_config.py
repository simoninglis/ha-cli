"""Tests for configuration utilities."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer

from ha_cli.common.config import get_client_config


class TestGetClientConfig:
    """Tests for get_client_config function."""

    def test_args_take_highest_precedence(self, tmp_path: Path) -> None:
        """Test that command line arguments take highest precedence."""
        # Set up environment variables that should be overridden
        with patch.dict(os.environ, {
            "HA_URL": "http://env.local:8123",
            "HA_TOKEN": "env_token",
            "ARGS_TOKEN": "args_token",
        }):
            url, token = get_client_config(
                url="http://args.local:8123",
                token="ARGS_TOKEN",  # --token names an env var, never the token
                interactive=False
            )

        assert url == "http://args.local:8123"
        assert token == "args_token"

    def test_env_vars_take_precedence_over_config(self, tmp_path: Path) -> None:
        """Test that environment variables take precedence over config file."""
        # Create config file
        config_dir = tmp_path / ".config" / "home-assistant-cli"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({
            "url": "http://config.local:8123",
            "token": "config_token"
        }))

        with patch.dict(os.environ, {
            "HA_URL": "http://env.local:8123",
            "HA_TOKEN": "env_token"
        }, clear=False):
            with patch("ha_cli.common.utils.get_config_path", return_value=config_file):
                url, token = get_client_config(interactive=False)

        assert url == "http://env.local:8123"
        assert token == "env_token"

    def test_home_assistant_url_env_var(self) -> None:
        """Test HOME_ASSISTANT_URL environment variable is supported."""
        with patch.dict(os.environ, {
            "HOME_ASSISTANT_URL": "http://ha.local:8123",
            "HOME_ASSISTANT_TOKEN": "ha_token"
        }, clear=True):
            with patch("ha_cli.common.envfile.read_env_file", return_value={}):
                url, token = get_client_config(interactive=False)

        assert url == "http://ha.local:8123"
        assert token == "ha_token"

    def test_ha_url_takes_precedence_over_home_assistant_url(self) -> None:
        """Test HA_URL takes precedence over HOME_ASSISTANT_URL."""
        with patch.dict(os.environ, {
            "HA_URL": "http://ha-short.local:8123",
            "HA_TOKEN": "ha_token",
            "HOME_ASSISTANT_URL": "http://ha-long.local:8123",
            "HOME_ASSISTANT_TOKEN": "ha_long_token"
        }, clear=True):
            with patch("ha_cli.common.envfile.read_env_file", return_value={}):
                url, token = get_client_config(interactive=False)

        assert url == "http://ha-short.local:8123"
        assert token == "ha_token"

    def test_config_file_supplies_url_never_token(self, tmp_path: Path, caplog) -> None:
        """The config file may supply the URL; a token in it is ignored with a warning (#236)."""
        config_dir = tmp_path / ".config" / "home-assistant-cli"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({
            "url": "http://config.local:8123",
            "token": "config_token"
        }))

        with patch.dict(os.environ, {"HA_TOKEN": "env_token"}, clear=True):
            with patch("ha_cli.common.envfile.read_env_file", return_value={}):
                with patch("ha_cli.common.config.get_config_path", return_value=config_file):
                    url, token = get_client_config(interactive=False)

        assert url == "http://config.local:8123"
        assert token == "env_token"
        assert "Ignoring the token" in caplog.text
        assert "config_token" not in caplog.text

    def test_config_file_token_alone_is_not_enough(self, tmp_path: Path) -> None:
        """A token only in the config file is refused, not silently used (#236)."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "url": "http://config.local:8123",
            "token": "config_token"
        }))

        with patch.dict(os.environ, {}, clear=True):
            with patch("ha_cli.common.envfile.read_env_file", return_value={}):
                with patch("ha_cli.common.config.get_config_path", return_value=config_file):
                    with pytest.raises(ValueError, match="HA_TOKEN") as exc_info:
                        get_client_config(interactive=False)

        assert "config_token" not in str(exc_info.value)

    def test_missing_credentials_raises_error(self, tmp_path: Path) -> None:
        """Test that missing credentials raises ValueError."""
        # Use non-existent config file
        config_file = tmp_path / "non_existent" / "config.json"

        with patch.dict(os.environ, {}, clear=True):
            with patch("ha_cli.common.envfile.read_env_file", return_value={}):
                with patch("ha_cli.common.config.get_config_path", return_value=config_file):
                    with pytest.raises(ValueError) as exc_info:
                        get_client_config(interactive=False)

        assert "URL" in str(exc_info.value)
        assert "token" in str(exc_info.value)

    def test_missing_url_only_error_message(self, tmp_path: Path) -> None:
        """Test error message when only URL is missing."""
        with patch.dict(os.environ, {"HA_TOKEN": "token"}, clear=True):
            with patch("ha_cli.common.envfile.read_env_file", return_value={}):
                with patch("ha_cli.common.config.get_config_path", return_value=tmp_path / "x"):
                    with pytest.raises(ValueError) as exc_info:
                        get_client_config(interactive=False)

        assert "URL" in str(exc_info.value)
        # Token should not be mentioned as missing
        error_msg = str(exc_info.value)
        assert "URL" in error_msg

    def test_missing_token_only_error_message(self, tmp_path: Path) -> None:
        """Test error message when only token is missing."""
        with patch.dict(os.environ, {"HA_URL": "http://ha.local:8123"}, clear=True):
            with patch("ha_cli.common.envfile.read_env_file", return_value={}):
                with patch("ha_cli.common.config.get_config_path", return_value=tmp_path / "x"):
                    with pytest.raises(ValueError) as exc_info:
                        get_client_config(interactive=False)

        assert "token" in str(exc_info.value)

    def test_dotenv_is_loaded(self) -> None:
        """Test that .env file is loaded via load_dotenv."""
        with patch("ha_cli.common.envfile.read_env_file", return_value={}) as mock_load:
            with patch.dict(os.environ, {
                "HA_URL": "http://ha.local:8123",
                "HA_TOKEN": "token"
            }):
                get_client_config(interactive=False)

        mock_load.assert_called_once()

    def test_partial_args_supplemented_by_env(self) -> None:
        """Test that partial args are supplemented by environment variables."""
        with patch.dict(os.environ, {
            "HA_URL": "http://env.local:8123",
            "HA_TOKEN": "env_token",
            "ARGS_TOKEN": "args_token",
        }, clear=True):
            with patch("ha_cli.common.envfile.read_env_file", return_value={}):
                # Only provide token via args (as the name of an env var)
                url, token = get_client_config(
                    token="ARGS_TOKEN",
                    interactive=False
                )

        assert url == "http://env.local:8123"  # From env
        assert token == "args_token"  # From args

    def test_partial_env_supplemented_by_config(self, tmp_path: Path) -> None:
        """A token in the env plus a URL from the config file works."""
        config_dir = tmp_path / ".config" / "home-assistant-cli"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"url": "http://config.local:8123"}))

        with patch.dict(os.environ, {"HA_TOKEN": "env_token"}, clear=True):
            with patch("ha_cli.common.envfile.read_env_file", return_value={}):
                with patch("ha_cli.common.config.get_config_path", return_value=config_file):
                    url, token = get_client_config(interactive=False)

        assert url == "http://config.local:8123"  # From config
        assert token == "env_token"  # From env


class TestInteractivePrompt:
    """#236: never hang without a terminal; never save the token."""

    def _run(self, tmp_path: Path, env: dict[str, str], tty: bool, prompts: list[str] | None = None):
        config_file = tmp_path / "cfg" / "config.json"
        prompt = MagicMock(side_effect=prompts or [])
        with patch.dict(os.environ, env, clear=True), \
             patch("ha_cli.common.envfile.read_env_file", return_value={}), \
             patch("ha_cli.common.config.get_config_path", return_value=config_file), \
             patch("ha_cli.common.config._stdin_is_tty", return_value=tty), \
             patch("typer.prompt", prompt):
            result = get_client_config()
        return result, prompt, config_file

    def test_no_tty_fails_fast_without_prompting(self, tmp_path: Path) -> None:
        """No terminal (agent, cron, pipe): a usage error naming HA_URL, not a blocking prompt."""
        with pytest.raises(ValueError, match="HA_URL") as exc_info:
            self._run(tmp_path, {"HA_TOKEN": "t"}, tty=False)
        assert "HA_TOKEN" not in str(exc_info.value)  # the token was found

    def test_no_tty_names_both_when_both_missing(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="HA_URL.*HA_TOKEN"):
            self._run(tmp_path, {}, tty=False)

    def test_real_stdin_not_a_tty_does_not_prompt(self, tmp_path: Path) -> None:
        """Without patching the tty check: pytest's captured stdin is not a terminal."""
        config_file = tmp_path / "config.json"
        with patch.dict(os.environ, {}, clear=True), \
             patch("ha_cli.common.envfile.read_env_file", return_value={}), \
             patch("ha_cli.common.config.get_config_path", return_value=config_file), \
             patch("typer.prompt", side_effect=AssertionError("prompted")):
            with pytest.raises(ValueError, match="Missing"):
                get_client_config()

    def test_tty_prompts_and_never_saves_token(self, tmp_path: Path) -> None:
        (url, token), prompt, config_file = self._run(
            tmp_path, {}, tty=True, prompts=["http://ha.test:8123", "secret-token"]
        )
        assert (url, token) == ("http://ha.test:8123", "secret-token")
        assert prompt.call_count == 2
        saved = json.loads(config_file.read_text())
        assert saved == {"url": "http://ha.test:8123"}
        assert "secret-token" not in config_file.read_text()

    def test_tty_existing_config_file_left_alone(self, tmp_path: Path) -> None:
        config_file = tmp_path / "cfg" / "config.json"
        config_file.parent.mkdir(parents=True)
        config_file.write_text(json.dumps({"url": "http://kept:8123", "token": "old"}))
        before = config_file.read_text()
        (url, token), prompt, _ = self._run(tmp_path, {}, tty=True, prompts=["typed-token"])
        assert (url, token) == ("http://kept:8123", "typed-token")
        assert prompt.call_count == 1  # only the token was asked for
        assert config_file.read_text() == before

    def test_tty_prompt_aborted_is_a_clean_error(self, tmp_path: Path) -> None:
        import typer

        with pytest.raises(ValueError, match="Cancelled"):
            self._run(tmp_path, {}, tty=True, prompts=[typer.Abort()])

    def test_interactive_false_never_prompts_even_with_tty(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        with patch.dict(os.environ, {}, clear=True), \
             patch("ha_cli.common.envfile.read_env_file", return_value={}), \
             patch("ha_cli.common.config.get_config_path", return_value=config_file), \
             patch("ha_cli.common.config._stdin_is_tty", return_value=True), \
             patch("typer.prompt", side_effect=AssertionError("prompted")):
            with pytest.raises(ValueError):
                get_client_config(interactive=False)


class TestTokenUsedAsFound:
    """Round-3 review: a token value is never dereferenced as another variable's name."""

    def test_env_token_that_looks_like_a_var_name_is_not_dereferenced(self) -> None:
        from ha_cli.common import envfile

        envfile._FROM_ENV_FILE.clear()
        with patch.dict(os.environ, {"HA_URL": "http://x:8123", "HA_TOKEN": "FILE_TOKEN"}, clear=True), \
             patch("ha_cli.common.envfile.read_env_file", return_value={"FILE_TOKEN": "file-secret"}):
            assert get_client_config(interactive=False) == ("http://x:8123", "FILE_TOKEN")
        envfile._FROM_ENV_FILE.clear()

    def test_flag_resolves_exactly_once(self) -> None:
        with patch.dict(os.environ, {"HA_URL": "http://x:8123", "A_TOK": "B_TOK", "B_TOK": "deeper"}, clear=True), \
             patch("ha_cli.common.envfile.read_env_file", return_value={}):
            assert get_client_config(token="A_TOK", interactive=False)[1] == "B_TOK"


class TestResolveCliToken:
    """--token takes an env var NAME; a literal token on the command line is refused."""

    LITERAL = "eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJ4In0.c2lnbmF0dXJl"

    def test_env_var_name_resolves(self) -> None:
        from ha_cli.common.utils import resolve_cli_token

        with patch.dict(os.environ, {"HA_TOKEN": "actual_token"}):
            assert resolve_cli_token("HA_TOKEN") == "actual_token"

    def test_literal_token_refused_without_echoing_it(self) -> None:
        from ha_cli.common.utils import resolve_cli_token

        with pytest.raises(ValueError, match="NAME of an environment variable") as exc:
            resolve_cli_token(self.LITERAL)
        assert "NAME of an environment variable" in str(exc.value)
        assert self.LITERAL not in str(exc.value)

    @pytest.mark.parametrize("value", ["this_is_a_literal_token", "Ha_Token", "HA-TOKEN", "", " HA_TOKEN"])
    def test_non_env_var_names_refused(self, value: str) -> None:
        from ha_cli.common.utils import resolve_cli_token

        with pytest.raises(ValueError, match="NAME of an environment variable"):
            resolve_cli_token(value)

    def test_unset_env_var_refused(self) -> None:
        from ha_cli.common.utils import resolve_cli_token

        with patch.dict(os.environ, {}, clear=True), pytest.raises(ValueError, match="not set"):
            resolve_cli_token("HA_TOKEN")

    def test_get_client_config_refuses_literal_cli_token(self) -> None:
        import typer

        from ha_cli.common.config import get_client_config

        with pytest.raises(typer.BadParameter, match="NAME of an environment variable") as exc:
            get_client_config("http://ha.local:8123", self.LITERAL, interactive=False)
        assert self.LITERAL not in str(exc.value)

    def test_get_client_config_cli_env_var_name(self) -> None:
        from ha_cli.common.config import get_client_config

        with patch.dict(os.environ, {"OTHER_HA_TOKEN": "t2"}, clear=True):
            assert get_client_config("http://ha.local:8123", "OTHER_HA_TOKEN", interactive=False) == (
                "http://ha.local:8123",
                "t2",
            )

    def test_env_token_still_used_without_flag(self) -> None:
        """No --token: HA_TOKEN's value comes from the environment, not argv."""
        from ha_cli.common.config import get_client_config

        with patch.dict(os.environ, {"HA_URL": "http://ha.local:8123", "HA_TOKEN": self.LITERAL}, clear=True):
            assert get_client_config(None, None, interactive=False) == ("http://ha.local:8123", self.LITERAL)


class TestGetConfigPath:
    """Tests for get_config_path function."""

    def test_canonical_path_preferred(self, tmp_path: Path) -> None:
        """Test that canonical path is used when it exists."""
        from ha_cli.common.utils import get_config_path

        canonical = tmp_path / ".config" / "home-assistant-cli"
        canonical.mkdir(parents=True)
        (canonical / "config.json").touch()

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = get_config_path()

        assert "home-assistant-cli" in str(result)

    def test_legacy_path_fallback(self, tmp_path: Path) -> None:
        """Test that legacy path is used when canonical doesn't exist."""
        from ha_cli.common.utils import get_config_path

        legacy = tmp_path / ".config" / "ha-automation"
        legacy.mkdir(parents=True)
        (legacy / "config.json").touch()

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = get_config_path()

        assert "ha-automation" in str(result)

    def test_canonical_returned_when_neither_exists(self, tmp_path: Path) -> None:
        """Test that canonical path is returned when neither exists."""
        from ha_cli.common.utils import get_config_path

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = get_config_path()

        assert "home-assistant-cli" in str(result)


class TestEnvFileNeverSuppliesTokens:
    """A .env file is a file: tokens come from the environment only."""

    @pytest.fixture(autouse=True)
    def fresh_provenance(self):
        from ha_cli.common import envfile

        envfile._FROM_ENV_FILE.clear()
        yield
        envfile._FROM_ENV_FILE.clear()

    @staticmethod
    def env_file(values: dict[str, str]):
        return patch("ha_cli.common.envfile.read_env_file", return_value=dict(values))

    def test_dotenv_token_is_dropped_with_warning(self, tmp_path: Path, caplog) -> None:
        with patch.dict(os.environ, {}, clear=True), \
             self.env_file({"HA_URL": "http://dot.env:8123", "HA_TOKEN": "file-token"}), \
             patch("ha_cli.common.config.get_config_path", return_value=tmp_path / "none.json"):
            with pytest.raises(ValueError, match="HA_TOKEN") as exc:
                get_client_config(interactive=False)
            assert "HA_TOKEN" not in os.environ
        assert "file-token" not in str(exc.value)
        assert "Ignoring HA_TOKEN in a .env file" in caplog.text
        assert "file-token" not in caplog.text

    def test_dotenv_url_still_used_and_env_token_wins(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"HA_TOKEN": "env-token"}, clear=True), \
             self.env_file({"HA_URL": "http://dot.env:8123", "HA_TOKEN": "file-token"}):
            assert get_client_config(interactive=False) == ("http://dot.env:8123", "env-token")

    def test_dotenv_cannot_supply_the_token_var_named_by_flag(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"HA_URL": "http://x:8123"}, clear=True), \
             self.env_file({"MY_HA_TOKEN": "file-token"}):
            with pytest.raises(typer.BadParameter, match="set by a .env file") as exc:
                get_client_config(token="MY_HA_TOKEN", interactive=False)
        assert "file-token" not in str(exc.value)

    def test_flag_var_from_real_environment_still_works(self) -> None:
        with patch.dict(os.environ, {"HA_URL": "http://x:8123", "MY_HA_TOKEN": "real"}, clear=True), \
             self.env_file({"MY_HA_TOKEN": "file-token"}):
            assert get_client_config(token="MY_HA_TOKEN", interactive=False)[1] == "real"

    def test_home_assistant_token_also_dropped(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"HA_URL": "http://x:8123"}, clear=True), \
             self.env_file({"HOME_ASSISTANT_TOKEN": "file-token"}), \
             patch("ha_cli.common.config.get_config_path", return_value=tmp_path / "none.json"):
            with pytest.raises(ValueError):
                get_client_config(interactive=False)


class TestEnvFileFreshProcess:
    """Through the real entry point in a new interpreter: no import-time .env load may
    let a file's token in (round-2 review reproduced exactly that)."""

    def _run(self, tmp_path: Path, env_file: str, args: list[str], extra_env=None):
        import subprocess
        import sys

        (tmp_path / ".env").write_text(env_file)
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home), **(extra_env or {})}
        return subprocess.run(
            [sys.executable, "-m", "ha_cli", *args],
            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
        )

    def test_env_file_token_never_used(self, tmp_path: Path) -> None:
        # Port 9 (discard) on loopback: if the token were accepted, the command would
        # try to connect and fail differently; it must stop at "missing token" first.
        result = self._run(
            tmp_path, "HA_URL=http://127.0.0.1:9\nHA_TOKEN=file-token-abc\n", ["repairs", "list"]
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "Missing Home Assistant token" in result.stdout
        assert "Ignoring HA_TOKEN in a .env file" in result.stderr
        assert "file-token-abc" not in result.stdout + result.stderr

    def test_env_file_var_named_by_token_flag_refused(self, tmp_path: Path) -> None:
        result = self._run(
            tmp_path, "HA_URL=http://127.0.0.1:9\nMY_TOK=file-token-abc\n",
            ["repairs", "list", "--token", "MY_TOK"],
        )
        assert result.returncode != 0
        assert "set by a .env file" in result.stdout + result.stderr
        assert "file-token-abc" not in result.stdout + result.stderr

    def test_env_file_url_is_used(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, "HA_URL=http://127.0.0.1:9\n", ["repairs", "list"])
        assert "Missing Home Assistant token" in result.stdout  # the URL came from .env
        assert "URL" not in result.stdout.split("Missing Home Assistant", 1)[1].split(".")[0]


class TestMissingCredentialsCli:
    """End to end through a real command: one line, exit 1, no prompt, no traceback."""

    def _invoke(self, args):
        from typer.testing import CliRunner

        from ha_cli.domains.repairs.cli import app

        with patch.dict(os.environ, {}, clear=True), \
             patch("ha_cli.common.envfile.read_env_file", return_value={}), \
             patch("ha_cli.common.config.get_config_path", return_value=Path("/nonexistent/config.json")), \
             patch("typer.prompt", side_effect=AssertionError("prompted")):
            return CliRunner().invoke(app, args)

    def test_plain(self) -> None:
        result = self._invoke(["list"])
        assert result.exit_code == 1
        assert "Missing Home Assistant URL and token" in result.output
        assert "Traceback" not in result.output

    def test_porcelain(self) -> None:
        result = self._invoke(["list", "--porcelain"])
        assert result.exit_code == 1
        error = json.loads(result.output)["error"]
        assert error["type"] == "MissingCredentialsError"

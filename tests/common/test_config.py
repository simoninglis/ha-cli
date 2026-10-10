"""Tests for configuration utilities."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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
            with patch("ha_cli.common.config.load_dotenv"):
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
            with patch("ha_cli.common.config.load_dotenv"):
                url, token = get_client_config(interactive=False)

        assert url == "http://ha-short.local:8123"
        assert token == "ha_token"

    def test_config_file_fallback(self, tmp_path: Path) -> None:
        """Test config file is used when env vars are not set."""
        config_dir = tmp_path / ".config" / "home-assistant-cli"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({
            "url": "http://config.local:8123",
            "token": "config_token"
        }))

        # Clear environment and mock config path
        with patch.dict(os.environ, {}, clear=True):
            with patch("ha_cli.common.config.load_dotenv"):
                with patch("ha_cli.common.config.get_config_path", return_value=config_file):
                    url, token = get_client_config(interactive=False)

        assert url == "http://config.local:8123"
        assert token == "config_token"

    def test_missing_credentials_raises_error(self, tmp_path: Path) -> None:
        """Test that missing credentials raises ValueError."""
        # Use non-existent config file
        config_file = tmp_path / "non_existent" / "config.json"

        with patch.dict(os.environ, {}, clear=True):
            with patch("ha_cli.common.config.load_dotenv"):
                with patch("ha_cli.common.config.get_config_path", return_value=config_file):
                    with pytest.raises(ValueError) as exc_info:
                        get_client_config(interactive=False)

        assert "URL" in str(exc_info.value)
        assert "token" in str(exc_info.value)

    def test_missing_url_only_error_message(self, tmp_path: Path) -> None:
        """Test error message when only URL is missing."""
        with patch.dict(os.environ, {"HA_TOKEN": "token"}, clear=True):
            with patch("ha_cli.common.config.load_dotenv"):
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
            with patch("ha_cli.common.config.load_dotenv"):
                with patch("ha_cli.common.config.get_config_path", return_value=tmp_path / "x"):
                    with pytest.raises(ValueError) as exc_info:
                        get_client_config(interactive=False)

        assert "token" in str(exc_info.value)

    def test_dotenv_is_loaded(self) -> None:
        """Test that .env file is loaded via load_dotenv."""
        with patch("ha_cli.common.config.load_dotenv") as mock_load:
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
            with patch("ha_cli.common.config.load_dotenv"):
                # Only provide token via args (as the name of an env var)
                url, token = get_client_config(
                    token="ARGS_TOKEN",
                    interactive=False
                )

        assert url == "http://env.local:8123"  # From env
        assert token == "args_token"  # From args

    def test_partial_env_supplemented_by_config(self, tmp_path: Path) -> None:
        """Test that partial env vars are supplemented by config file."""
        config_dir = tmp_path / ".config" / "home-assistant-cli"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({
            "url": "http://config.local:8123",
            "token": "config_token"
        }))

        # Only URL in env
        with patch.dict(os.environ, {"HA_URL": "http://env.local:8123"}, clear=True):
            with patch("ha_cli.common.config.load_dotenv"):
                with patch("ha_cli.common.config.get_config_path", return_value=config_file):
                    url, token = get_client_config(interactive=False)

        assert url == "http://env.local:8123"  # From env
        assert token == "config_token"  # From config


class TestGetTokenFromEnv:
    """Tests for get_token_from_env function."""

    def test_env_var_reference_resolved(self) -> None:
        """Test that env var names are resolved."""
        from ha_cli.common.utils import get_token_from_env

        with patch.dict(os.environ, {"MY_SECRET_TOKEN": "actual_token"}):
            result = get_token_from_env("MY_SECRET_TOKEN")

        assert result == "actual_token"

    def test_literal_token_returned(self) -> None:
        """Test that literal tokens are returned as-is."""
        from ha_cli.common.utils import get_token_from_env

        result = get_token_from_env("this_is_a_literal_token")
        assert result == "this_is_a_literal_token"

    def test_mixed_case_not_env_var(self) -> None:
        """Test that mixed case strings are not treated as env vars."""
        from ha_cli.common.utils import get_token_from_env

        result = get_token_from_env("This_Is_Not_EnvVar")
        assert result == "This_Is_Not_EnvVar"

    def test_env_var_not_found_returns_original(self) -> None:
        """Test that unset env var returns original value."""
        from ha_cli.common.utils import get_token_from_env

        with patch.dict(os.environ, {}, clear=True):
            result = get_token_from_env("NONEXISTENT_VAR")

        # Without underscore, not treated as env var
        assert result == "NONEXISTENT_VAR"


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

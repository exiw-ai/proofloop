"""Tests for MCPConfigurator infrastructure service."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.domain.value_objects.mcp_types import (
    MCPInstallSource,
    MCPServerConfig,
    MCPServerTemplate,
    MCPServerType,
)
from src.infrastructure.mcp.configurator import MCPConfigurator


@pytest.fixture
def temp_config_dirs() -> tuple[Path, Path]:
    """Create temporary config directories."""
    with (
        tempfile.TemporaryDirectory() as user_dir,
        tempfile.TemporaryDirectory() as project_dir,
    ):
        yield Path(user_dir), Path(project_dir)


@pytest.fixture
def configurator(temp_config_dirs: tuple[Path, Path]) -> MCPConfigurator:
    """Create MCPConfigurator with temp directories."""
    user_dir, project_dir = temp_config_dirs
    return MCPConfigurator(
        user_config_dir=user_dir,
        project_config_dir=project_dir,
    )


@pytest.fixture
def sample_template() -> MCPServerTemplate:
    """Create a sample template."""
    return MCPServerTemplate(
        name="github",
        description="GitHub API",
        type=MCPServerType.STDIO,
        install_source=MCPInstallSource.NPM,
        command="npx",
        default_args=["@anthropic/mcp-server-github"],
        required_credentials=["GITHUB_TOKEN"],
        credential_descriptions={"GITHUB_TOKEN": "GitHub personal access token"},
    )


@pytest.fixture
def sample_config() -> MCPServerConfig:
    """Create a sample config."""
    return MCPServerConfig(
        name="github",
        type=MCPServerType.STDIO,
        command="npx",
        args=["@anthropic/mcp-server-github"],
        env={"GITHUB_TOKEN": "ghp_test"},
    )


class TestMCPConfiguratorSaveLoad:
    """Tests for save/load operations."""

    def test_save_and_load_user_config(
        self,
        configurator: MCPConfigurator,
        sample_config: MCPServerConfig,
    ) -> None:
        """Test saving and loading user-level config."""
        configurator.save_config(sample_config, scope="user")

        loaded = configurator.load_config("github")

        assert loaded is not None
        assert loaded.name == sample_config.name
        assert loaded.type == sample_config.type
        assert loaded.command == sample_config.command

    def test_save_and_load_project_config(
        self,
        configurator: MCPConfigurator,
        sample_config: MCPServerConfig,
    ) -> None:
        """Test saving and loading project-level config."""
        configurator.save_config(sample_config, scope="project")

        loaded = configurator.load_config("github")

        assert loaded is not None
        assert loaded.name == sample_config.name

    def test_project_config_takes_precedence(
        self,
        configurator: MCPConfigurator,
    ) -> None:
        """Test that project config takes precedence over user config."""
        user_config = MCPServerConfig(
            name="test",
            type=MCPServerType.STDIO,
            command="user-cmd",
        )
        project_config = MCPServerConfig(
            name="test",
            type=MCPServerType.STDIO,
            command="project-cmd",
        )

        configurator.save_config(user_config, scope="user")
        configurator.save_config(project_config, scope="project")

        loaded = configurator.load_config("test")

        assert loaded is not None
        assert loaded.command == "project-cmd"

    def test_load_nonexistent_returns_none(self, configurator: MCPConfigurator) -> None:
        """Test loading non-existent config returns None."""
        loaded = configurator.load_config("nonexistent")
        assert loaded is None

    def test_load_corrupted_file_returns_none(
        self,
        configurator: MCPConfigurator,
    ) -> None:
        """Test loading corrupted JSON returns None."""
        config_path = configurator._get_user_config_path("broken")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{ invalid json }")

        loaded = configurator.load_config("broken")
        assert loaded is None


class TestMCPConfiguratorDelete:
    """Tests for delete operations."""

    def test_delete_existing_config(
        self,
        configurator: MCPConfigurator,
        sample_config: MCPServerConfig,
    ) -> None:
        """Test deleting existing config."""
        configurator.save_config(sample_config, scope="user")

        result = configurator.delete_config("github", scope="user")

        assert result is True
        assert configurator.load_config("github") is None

    def test_delete_nonexistent_returns_false(self, configurator: MCPConfigurator) -> None:
        """Test deleting non-existent config returns False."""
        result = configurator.delete_config("nonexistent")
        assert result is False


class TestMCPConfiguratorListServers:
    """Tests for listing configured servers."""

    def test_list_empty(self, configurator: MCPConfigurator) -> None:
        """Test listing when no servers configured."""
        servers = configurator.list_configured_servers()
        assert servers == []

    def test_list_multiple_servers(self, configurator: MCPConfigurator) -> None:
        """Test listing multiple configured servers."""
        for name in ["server1", "server2", "server3"]:
            config = MCPServerConfig(
                name=name,
                type=MCPServerType.STDIO,
                command="test",
            )
            configurator.save_config(config, scope="user")

        servers = configurator.list_configured_servers()

        assert sorted(servers) == ["server1", "server2", "server3"]

    def test_list_deduplicates_user_and_project(self, configurator: MCPConfigurator) -> None:
        """Test that same server in user and project is listed once."""
        config = MCPServerConfig(
            name="shared",
            type=MCPServerType.STDIO,
            command="test",
        )
        configurator.save_config(config, scope="user")
        configurator.save_config(config, scope="project")

        servers = configurator.list_configured_servers()

        assert servers == ["shared"]


class TestMCPConfiguratorCredentials:
    """Tests for credential handling."""

    def test_get_missing_credentials_all_missing(
        self,
        configurator: MCPConfigurator,
        sample_template: MCPServerTemplate,
    ) -> None:
        """Test getting missing credentials when none configured."""
        missing = configurator.get_missing_credentials(sample_template)
        assert missing == ["GITHUB_TOKEN"]

    def test_get_missing_credentials_from_env(
        self,
        configurator: MCPConfigurator,
        sample_template: MCPServerTemplate,
    ) -> None:
        """Test that credentials in env are not missing."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}):
            missing = configurator.get_missing_credentials(sample_template)

        assert missing == []

    def test_get_missing_credentials_from_config(
        self,
        configurator: MCPConfigurator,
        sample_template: MCPServerTemplate,
        sample_config: MCPServerConfig,
    ) -> None:
        """Test that credentials in saved config are not missing."""
        configurator.save_config(sample_config, scope="user")

        missing = configurator.get_missing_credentials(sample_template)

        assert missing == []


class TestMCPConfiguratorConfigureFromTemplate:
    """Tests for configure_from_template."""

    def test_configure_from_template_basic(
        self,
        configurator: MCPConfigurator,
        sample_template: MCPServerTemplate,
    ) -> None:
        """Test creating config from template."""
        config = configurator.configure_from_template(
            sample_template,
            credentials={"GITHUB_TOKEN": "ghp_xxx"},
        )

        assert config.name == "github"
        assert config.env["GITHUB_TOKEN"] == "ghp_xxx"

        # Verify it was saved
        loaded = configurator.load_config("github")
        assert loaded is not None

    def test_configure_with_extra_args(
        self,
        configurator: MCPConfigurator,
        sample_template: MCPServerTemplate,
    ) -> None:
        """Test configuring with extra arguments."""
        config = configurator.configure_from_template(
            sample_template,
            credentials={"GITHUB_TOKEN": "ghp_xxx"},
            extra_args=["--verbose"],
        )

        assert "--verbose" in config.args


class TestMCPConfiguratorGetOrConfigure:
    """Tests for get_or_configure."""

    def test_returns_existing_config(
        self,
        configurator: MCPConfigurator,
        sample_template: MCPServerTemplate,
        sample_config: MCPServerConfig,
    ) -> None:
        """Test returning existing config without prompting."""
        configurator.save_config(sample_config, scope="user")

        # Mock env to have the credential
        with patch.dict(os.environ, {"GITHUB_TOKEN": "from_env"}):
            result = configurator.get_or_configure(
                sample_template,
                credentials_provider=lambda _: {"GITHUB_TOKEN": "new"},
            )

        assert result is not None
        # Should use existing config, not provider
        assert result.env.get("GITHUB_TOKEN") == "ghp_test"

    def test_uses_provider_for_missing_credentials(
        self,
        configurator: MCPConfigurator,
        sample_template: MCPServerTemplate,
    ) -> None:
        """Test using provider for missing credentials."""
        provider_called = []

        def provider(missing: list[str]) -> dict[str, str]:
            provider_called.append(missing)
            return {"GITHUB_TOKEN": "from_provider"}

        result = configurator.get_or_configure(sample_template, provider)

        assert result is not None
        assert result.env["GITHUB_TOKEN"] == "from_provider"
        assert provider_called == [["GITHUB_TOKEN"]]

    def test_returns_none_when_provider_not_given(
        self,
        configurator: MCPConfigurator,
        sample_template: MCPServerTemplate,
    ) -> None:
        """Test returning None when credentials needed but no provider."""
        result = configurator.get_or_configure(sample_template, None)
        assert result is None

    def test_returns_none_when_provider_returns_empty(
        self,
        configurator: MCPConfigurator,
        sample_template: MCPServerTemplate,
    ) -> None:
        """Test returning None when provider returns empty dict."""
        result = configurator.get_or_configure(
            sample_template,
            credentials_provider=lambda _: {},
        )
        assert result is None

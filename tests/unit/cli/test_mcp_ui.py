"""Tests for MCP UI module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from src.application.use_cases.select_mcp_servers import MCPSuggestion
from src.domain.value_objects.mcp_types import (
    MCPInstallSource,
    MCPServerConfig,
    MCPServerRegistry,
    MCPServerStatus,
    MCPServerTemplate,
    MCPServerType,
)


@pytest.fixture
def sample_template() -> MCPServerTemplate:
    return MCPServerTemplate(
        name="test-server",
        description="Test server description",
        type=MCPServerType.STDIO,
        install_source=MCPInstallSource.NPM,
        install_package="@test/server",
        category="testing",
        required_credentials=["TEST_TOKEN"],
        credential_descriptions={"TEST_TOKEN": "Your test token"},
    )


@pytest.fixture
def sample_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="test-server",
        type=MCPServerType.STDIO,
        command="npx",
        args=["@test/server"],
        env={"TEST_TOKEN": "abc123"},
    )


@pytest.fixture
def sample_suggestions() -> list[MCPSuggestion]:
    return [
        MCPSuggestion(
            server_name="playwright",
            reason="Browser testing needed",
            confidence=0.9,
        ),
        MCPSuggestion(
            server_name="github",
            reason="GitHub integration",
            confidence=0.7,
        ),
    ]


@pytest.fixture
def sample_registry() -> MCPServerRegistry:
    registry = MCPServerRegistry()
    registry.register(
        MCPServerTemplate(
            name="playwright",
            description="Browser automation",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            category="browser",
        )
    )
    registry.register(
        MCPServerTemplate(
            name="github",
            description="GitHub API",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            category="api",
            required_credentials=["GITHUB_TOKEN"],
        )
    )
    return registry


class TestShowMcpServersTable:
    """Tests for show_mcp_servers_table function."""

    def test_shows_table_with_templates(self, sample_template: MCPServerTemplate) -> None:
        """Test showing table with templates."""
        from src.cli.mcp.ui import show_mcp_servers_table

        mock_console = MagicMock(spec=Console)

        show_mcp_servers_table(mock_console, [sample_template], "Test Title")

        mock_console.print.assert_called_once()
        # Verify a table was passed
        call_args = mock_console.print.call_args
        assert call_args is not None


class TestShowMcpSuggestions:
    """Tests for show_mcp_suggestions function."""

    def test_empty_suggestions(self) -> None:
        """Test showing empty suggestions."""
        from src.cli.mcp.ui import show_mcp_suggestions

        mock_console = MagicMock(spec=Console)

        show_mcp_suggestions(mock_console, [])

        mock_console.print.assert_called_once()
        call_args = str(mock_console.print.call_args)
        assert "No MCP servers suggested" in call_args

    def test_shows_suggestions(self, sample_suggestions: list[MCPSuggestion]) -> None:
        """Test showing suggestions."""
        from src.cli.mcp.ui import show_mcp_suggestions

        mock_console = MagicMock(spec=Console)

        show_mcp_suggestions(mock_console, sample_suggestions)

        assert mock_console.print.call_count >= 1


class TestInteractiveMcpSelection:
    """Tests for interactive_mcp_selection function."""

    def test_accept_all_suggestions(
        self, sample_suggestions: list[MCPSuggestion], sample_registry: MCPServerRegistry
    ) -> None:
        """Test accepting all suggested servers."""
        from src.cli.mcp.ui import interactive_mcp_selection

        with (
            patch("src.cli.mcp.ui.show_mcp_suggestions"),
            patch("src.cli.mcp.ui.Prompt") as mock_prompt,
        ):
            mock_prompt.ask.return_value = "y"

            result = interactive_mcp_selection(sample_suggestions, sample_registry)

            assert result == ["playwright", "github"]

    def test_skip_mcp(
        self, sample_suggestions: list[MCPSuggestion], sample_registry: MCPServerRegistry
    ) -> None:
        """Test skipping MCP."""
        from src.cli.mcp.ui import interactive_mcp_selection

        with (
            patch("src.cli.mcp.ui.show_mcp_suggestions"),
            patch("src.cli.mcp.ui.Prompt") as mock_prompt,
        ):
            mock_prompt.ask.return_value = "s"

            result = interactive_mcp_selection(sample_suggestions, sample_registry)

            assert result == []

    def test_select_specific_servers(
        self, sample_suggestions: list[MCPSuggestion], sample_registry: MCPServerRegistry
    ) -> None:
        """Test selecting specific servers."""
        from src.cli.mcp.ui import interactive_mcp_selection

        with (
            patch("src.cli.mcp.ui.show_mcp_suggestions"),
            patch("src.cli.mcp.ui.Prompt") as mock_prompt,
        ):
            # First call: choice is 'n' for selecting specific
            # Second call: selecting server "1"
            mock_prompt.ask.side_effect = ["n", "1"]

            result = interactive_mcp_selection(sample_suggestions, sample_registry)

            assert result == ["playwright"]

    def test_empty_suggestions_no_registry(self) -> None:
        """Test with empty suggestions and no registry."""
        from src.cli.mcp.ui import interactive_mcp_selection

        with (
            patch("src.cli.mcp.ui.show_mcp_suggestions"),
            patch("src.cli.mcp.ui.Prompt") as mock_prompt,
        ):
            mock_prompt.ask.return_value = "s"

            result = interactive_mcp_selection([], None)

            assert result == []


class TestSelectFromSuggestions:
    """Tests for _select_from_suggestions function."""

    def test_select_by_number(
        self, sample_suggestions: list[MCPSuggestion], sample_registry: MCPServerRegistry
    ) -> None:
        """Test selecting by number."""
        from src.cli.mcp.ui import _select_from_suggestions

        mock_console = MagicMock(spec=Console)

        with patch("src.cli.mcp.ui.Prompt") as mock_prompt:
            mock_prompt.ask.return_value = "1"

            result = _select_from_suggestions(mock_console, sample_suggestions, sample_registry)

            assert result == ["playwright"]

    def test_select_multiple(
        self, sample_suggestions: list[MCPSuggestion], sample_registry: MCPServerRegistry
    ) -> None:
        """Test selecting multiple servers."""
        from src.cli.mcp.ui import _select_from_suggestions

        mock_console = MagicMock(spec=Console)

        with patch("src.cli.mcp.ui.Prompt") as mock_prompt:
            mock_prompt.ask.return_value = "1, 2"

            result = _select_from_suggestions(mock_console, sample_suggestions, sample_registry)

            assert "playwright" in result
            assert "github" in result

    def test_empty_suggestions_with_registry(self, sample_registry: MCPServerRegistry) -> None:
        """Test empty suggestions with registry."""
        from src.cli.mcp.ui import _select_from_suggestions

        mock_console = MagicMock(spec=Console)

        with patch("src.cli.mcp.ui.Prompt") as mock_prompt:
            mock_prompt.ask.return_value = ""

            result = _select_from_suggestions(mock_console, [], sample_registry)

            # With empty suggestions and registry, should fall through to browse
            assert isinstance(result, list)


class TestBrowseAndSelect:
    """Tests for _browse_and_select function."""

    def test_browse_and_select_servers(self, sample_registry: MCPServerRegistry) -> None:
        """Test browsing and selecting servers."""
        from src.cli.mcp.ui import _browse_and_select

        mock_console = MagicMock(spec=Console)

        with patch("src.cli.mcp.ui.Prompt") as mock_prompt:
            mock_prompt.ask.return_value = "playwright, github"

            result = _browse_and_select(mock_console, sample_registry)

            assert "playwright" in result
            assert "github" in result

    def test_browse_with_invalid_names(self, sample_registry: MCPServerRegistry) -> None:
        """Test browsing with invalid server names."""
        from src.cli.mcp.ui import _browse_and_select

        mock_console = MagicMock(spec=Console)

        with patch("src.cli.mcp.ui.Prompt") as mock_prompt:
            mock_prompt.ask.return_value = "invalid, playwright"

            result = _browse_and_select(mock_console, sample_registry)

            # Should only include valid server
            assert result == ["playwright"]


class TestInteractiveMcpConfiguration:
    """Tests for interactive_mcp_configuration function."""

    @pytest.mark.asyncio
    async def test_configure_installed_server(self, sample_template: MCPServerTemplate) -> None:
        """Test configuring an already installed server."""
        from src.cli.mcp.ui import interactive_mcp_configuration
        from src.infrastructure.mcp.configurator import MCPConfigurator
        from src.infrastructure.mcp.installer import MCPInstaller

        mock_console = MagicMock(spec=Console)
        mock_configurator = MagicMock(spec=MCPConfigurator)
        mock_installer = AsyncMock(spec=MCPInstaller)

        mock_installer.check_status.return_value = MCPServerStatus.INSTALLED
        mock_configurator.get_missing_credentials.return_value = ["TEST_TOKEN"]
        mock_configurator.configure_from_template.return_value = MCPServerConfig(
            name="test-server",
            type=MCPServerType.STDIO,
            command="npx",
        )

        with patch("src.cli.mcp.ui.Prompt") as mock_prompt:
            mock_prompt.ask.return_value = "abc123"

            result = await interactive_mcp_configuration(
                sample_template, mock_configurator, mock_installer, mock_console
            )

            assert result is not None
            mock_configurator.configure_from_template.assert_called_once()

    @pytest.mark.asyncio
    async def test_configure_not_installed_skip(self, sample_template: MCPServerTemplate) -> None:
        """Test skipping configuration when server not installed."""
        from src.cli.mcp.ui import interactive_mcp_configuration
        from src.infrastructure.mcp.configurator import MCPConfigurator
        from src.infrastructure.mcp.installer import MCPInstaller

        mock_console = MagicMock(spec=Console)
        mock_configurator = MagicMock(spec=MCPConfigurator)
        mock_installer = AsyncMock(spec=MCPInstaller)

        mock_installer.check_status.return_value = MCPServerStatus.NOT_INSTALLED

        with patch("src.cli.mcp.ui.Confirm") as mock_confirm:
            mock_confirm.ask.return_value = False

            result = await interactive_mcp_configuration(
                sample_template, mock_configurator, mock_installer, mock_console
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_configure_missing_credentials_skip(
        self, sample_template: MCPServerTemplate
    ) -> None:
        """Test skipping when user doesn't provide credentials."""
        from src.cli.mcp.ui import interactive_mcp_configuration
        from src.infrastructure.mcp.configurator import MCPConfigurator
        from src.infrastructure.mcp.installer import MCPInstaller

        mock_console = MagicMock(spec=Console)
        mock_configurator = MagicMock(spec=MCPConfigurator)
        mock_installer = AsyncMock(spec=MCPInstaller)

        mock_installer.check_status.return_value = MCPServerStatus.INSTALLED
        mock_configurator.get_missing_credentials.return_value = ["TEST_TOKEN"]

        with patch("src.cli.mcp.ui.Prompt") as mock_prompt:
            mock_prompt.ask.return_value = ""  # Empty credential

            result = await interactive_mcp_configuration(
                sample_template, mock_configurator, mock_installer, mock_console
            )

            assert result is None


class TestCollectMcpCredentials:
    """Tests for collect_mcp_credentials function."""

    def test_collect_credentials(self, sample_template: MCPServerTemplate) -> None:
        """Test collecting credentials."""
        from src.cli.mcp.ui import collect_mcp_credentials

        mock_console = MagicMock(spec=Console)

        with patch("src.cli.mcp.ui.Prompt") as mock_prompt:
            mock_prompt.ask.return_value = "secret_value"

            result = collect_mcp_credentials(["TEST_TOKEN"], sample_template, mock_console)

            assert result == {"TEST_TOKEN": "secret_value"}

    def test_collect_multiple_credentials(self) -> None:
        """Test collecting multiple credentials."""
        from src.cli.mcp.ui import collect_mcp_credentials

        mock_console = MagicMock(spec=Console)

        with patch("src.cli.mcp.ui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["value1", "value2"]

            result = collect_mcp_credentials(["CRED1", "CRED2"], None, mock_console)

            assert result == {"CRED1": "value1", "CRED2": "value2"}

    def test_collect_credentials_without_template(self) -> None:
        """Test collecting credentials without template."""
        from src.cli.mcp.ui import collect_mcp_credentials

        mock_console = MagicMock(spec=Console)

        with patch("src.cli.mcp.ui.Prompt") as mock_prompt:
            mock_prompt.ask.return_value = "test"

            result = collect_mcp_credentials(["API_KEY"], None, mock_console)

            assert result == {"API_KEY": "test"}

"""Tests for CLI main module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.cli.main import setup_logging


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_default(self, tmp_path: Path) -> None:
        """Test default logging setup configures file handler."""
        from loguru import logger

        with patch("src.cli.main.get_log_dir", return_value=tmp_path):
            log_file = setup_logging(verbose=False)
            # Verify logger has handlers configured (1 file handler)
            assert len(logger._core.handlers) >= 1
            # Log file should be in tmp_path with timestamp format
            assert log_file.parent == tmp_path
            assert log_file.suffix == ".log"

    def test_setup_logging_verbose(self, tmp_path: Path) -> None:
        """Test verbose logging adds stderr handler."""
        from loguru import logger

        with patch("src.cli.main.get_log_dir", return_value=tmp_path):
            log_file = setup_logging(verbose=True)
            # Verbose mode adds both file and stderr handlers
            assert len(logger._core.handlers) >= 2
            assert log_file.parent == tmp_path

    def test_setup_logging_with_task_id(self, tmp_path: Path) -> None:
        """Test log file includes task_id when provided."""
        with patch("src.cli.main.get_log_dir", return_value=tmp_path):
            log_file = setup_logging(verbose=False, task_id="abc123")
            # Log file should include task_id
            assert "abc123" in log_file.name
            assert log_file.suffix == ".log"


class TestMcpListFunction:
    """Tests for mcp_list function."""

    def test_mcp_list_no_servers(self) -> None:
        """Test mcp list when no servers available."""
        from src.cli.main import mcp_list

        with (
            patch("src.cli.main.get_default_registry") as mock_get_registry,
            patch("src.cli.main.Console") as mock_console_class,
        ):
            mock_registry = MagicMock()
            mock_registry.list_all.return_value = []
            mock_get_registry.return_value = mock_registry

            mock_console = MagicMock()
            mock_console_class.return_value = mock_console

            mcp_list(category=None)

            # Should print "No MCP servers found"
            mock_console.print.assert_called()
            call_args = str(mock_console.print.call_args)
            assert "No MCP servers found" in call_args

    def test_mcp_list_with_category(self) -> None:
        """Test mcp list with category filter."""
        from src.cli.main import mcp_list
        from src.domain.value_objects.mcp_types import (
            MCPInstallSource,
            MCPServerTemplate,
            MCPServerType,
        )

        mock_template = MCPServerTemplate(
            name="test-server",
            description="Test server",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            category="browser",
        )

        with (
            patch("src.cli.main.get_default_registry") as mock_get_registry,
            patch("src.cli.main.Console") as mock_console_class,
            patch("src.cli.mcp.ui.show_mcp_servers_table") as mock_show,
        ):
            mock_registry = MagicMock()
            mock_registry.list_by_category.return_value = [mock_template]
            mock_get_registry.return_value = mock_registry

            mock_console = MagicMock()
            mock_console_class.return_value = mock_console

            mcp_list(category="browser")

            mock_registry.list_by_category.assert_called_once_with("browser")
            mock_show.assert_called_once()


class TestMcpConfigureFunction:
    """Tests for mcp_configure function."""

    def test_mcp_configure_unknown_server(self) -> None:
        """Test configuring unknown server."""
        import typer

        from src.cli.main import mcp_configure

        with (
            patch("src.cli.main.get_default_registry") as mock_get_registry,
            patch("src.cli.main.Console") as mock_console_class,
            pytest.raises(typer.Exit),
        ):
            mock_registry = MagicMock()
            mock_registry.get.return_value = None
            mock_get_registry.return_value = mock_registry

            mock_console = MagicMock()
            mock_console_class.return_value = mock_console

            mcp_configure(server_name="unknown-server")

    def test_mcp_configure_success(self) -> None:
        """Test successful MCP configuration."""
        from src.cli.main import mcp_configure
        from src.domain.value_objects.mcp_types import (
            MCPInstallSource,
            MCPServerConfig,
            MCPServerTemplate,
            MCPServerType,
        )

        mock_template = MCPServerTemplate(
            name="test-server",
            description="Test server",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
        )
        mock_config = MCPServerConfig(
            name="test-server",
            type=MCPServerType.STDIO,
            command="test",
        )

        with (
            patch("src.cli.main.get_default_registry") as mock_get_registry,
            patch("src.cli.main.Console") as mock_console_class,
            patch("src.infrastructure.mcp.configurator.MCPConfigurator"),
            patch("src.infrastructure.mcp.installer.MCPInstaller"),
            patch("src.cli.main.asyncio.run") as mock_run,
        ):
            mock_registry = MagicMock()
            mock_registry.get.return_value = mock_template
            mock_get_registry.return_value = mock_registry

            mock_console = MagicMock()
            mock_console_class.return_value = mock_console

            mock_run.return_value = mock_config

            mcp_configure(server_name="test-server")

            # Should print success message
            call_args = [str(c) for c in mock_console.print.call_args_list]
            assert any("configured successfully" in arg for arg in call_args)


class TestMcpInstalledFunction:
    """Tests for mcp_installed function."""

    def test_mcp_installed_empty(self) -> None:
        """Test mcp installed when no servers configured."""
        from src.cli.main import mcp_installed

        with (
            patch("src.infrastructure.mcp.configurator.MCPConfigurator") as mock_configurator_class,
            patch("src.cli.main.Console") as mock_console_class,
        ):
            mock_configurator = MagicMock()
            mock_configurator.list_configured_servers.return_value = []
            mock_configurator_class.return_value = mock_configurator

            mock_console = MagicMock()
            mock_console_class.return_value = mock_console

            mcp_installed()

            call_args = str(mock_console.print.call_args_list)
            assert "No MCP servers configured" in call_args

    def test_mcp_installed_with_servers(self) -> None:
        """Test mcp installed with configured servers."""
        from src.cli.main import mcp_installed

        with (
            patch("src.infrastructure.mcp.configurator.MCPConfigurator") as mock_configurator_class,
            patch("src.cli.main.Console") as mock_console_class,
        ):
            mock_configurator = MagicMock()
            mock_configurator.list_configured_servers.return_value = ["server1", "server2"]
            mock_configurator_class.return_value = mock_configurator

            mock_console = MagicMock()
            mock_console_class.return_value = mock_console

            mcp_installed()

            call_args = str(mock_console.print.call_args_list)
            assert "Configured MCP Servers" in call_args
            assert "server1" in call_args
            assert "server2" in call_args

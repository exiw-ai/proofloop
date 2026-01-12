"""Tests for MCPInstaller infrastructure service."""

from unittest.mock import AsyncMock, patch

import pytest

from src.domain.value_objects.mcp_types import (
    MCPInstallSource,
    MCPServerStatus,
    MCPServerTemplate,
    MCPServerType,
)
from src.infrastructure.mcp.installer import MCPInstaller


@pytest.fixture
def installer() -> MCPInstaller:
    """Create MCPInstaller instance."""
    return MCPInstaller()


@pytest.fixture
def npm_template() -> MCPServerTemplate:
    """Create npm-based template."""
    return MCPServerTemplate(
        name="test-npm",
        description="Test NPM server",
        type=MCPServerType.STDIO,
        install_source=MCPInstallSource.NPM,
        install_package="@test/mcp-server",
        command="npx",
        default_args=["@test/mcp-server"],
    )


@pytest.fixture
def pip_template() -> MCPServerTemplate:
    """Create pip-based template."""
    return MCPServerTemplate(
        name="test-pip",
        description="Test pip server",
        type=MCPServerType.STDIO,
        install_source=MCPInstallSource.PIP,
        install_package="mcp-server-test",
        command="mcp-test",
    )


@pytest.fixture
def no_install_template() -> MCPServerTemplate:
    """Create template that doesn't need installation."""
    return MCPServerTemplate(
        name="builtin",
        description="Built-in server",
        type=MCPServerType.STDIO,
        install_source=MCPInstallSource.NONE,
        command="some-builtin-cmd",
    )


class TestMCPInstallerCheckStatus:
    """Tests for MCPInstaller.check_status."""

    async def test_no_install_source_returns_installed(
        self, installer: MCPInstaller, no_install_template: MCPServerTemplate
    ) -> None:
        """Test that NONE install source returns INSTALLED."""
        status = await installer.check_status(no_install_template)
        assert status == MCPServerStatus.INSTALLED

    async def test_npm_package_installed(
        self, installer: MCPInstaller, npm_template: MCPServerTemplate
    ) -> None:
        """Test detecting installed npm package."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            status = await installer.check_status(npm_template)

        assert status == MCPServerStatus.INSTALLED

    async def test_npm_package_not_installed(
        self, installer: MCPInstaller, npm_template: MCPServerTemplate
    ) -> None:
        """Test detecting uninstalled npm package."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"not found"))

        # Mock shutil.which to return None so command check doesn't short-circuit
        with (
            patch("shutil.which", return_value=None),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            status = await installer.check_status(npm_template)

        assert status == MCPServerStatus.NOT_INSTALLED

    async def test_pip_package_installed(
        self, installer: MCPInstaller, pip_template: MCPServerTemplate
    ) -> None:
        """Test detecting installed pip package."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"Name: mcp-server-test", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            status = await installer.check_status(pip_template)

        assert status == MCPServerStatus.INSTALLED

    async def test_pip_package_not_installed(
        self, installer: MCPInstaller, pip_template: MCPServerTemplate
    ) -> None:
        """Test detecting uninstalled pip package."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"not found"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            status = await installer.check_status(pip_template)

        assert status == MCPServerStatus.NOT_INSTALLED

    async def test_command_exists_in_path(self, installer: MCPInstaller) -> None:
        """Test that command in PATH is detected as installed."""
        template = MCPServerTemplate(
            name="with-path-cmd",
            description="Has command in PATH",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="some-package",
            command="python",  # Usually exists in PATH
        )

        with patch("shutil.which", return_value="/usr/bin/python"):
            status = await installer.check_status(template)

        assert status == MCPServerStatus.INSTALLED


class TestMCPInstallerInstall:
    """Tests for MCPInstaller.install."""

    async def test_no_install_source_returns_true(
        self, installer: MCPInstaller, no_install_template: MCPServerTemplate
    ) -> None:
        """Test that NONE install source returns True without installing."""
        result = await installer.install(no_install_template)
        assert result is True

    async def test_npm_install_success(
        self, installer: MCPInstaller, npm_template: MCPServerTemplate
    ) -> None:
        """Test successful npm installation."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"installed", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await installer.install(npm_template)

        assert result is True
        # Verify npm install -g was called
        call_args = mock_exec.call_args[0]
        assert call_args[0] == "npm"
        assert call_args[1] == "install"
        assert call_args[2] == "-g"
        assert call_args[3] == "@test/mcp-server"

    async def test_npm_install_failure(
        self, installer: MCPInstaller, npm_template: MCPServerTemplate
    ) -> None:
        """Test failed npm installation."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await installer.install(npm_template)

        assert result is False

    async def test_pip_install_success(
        self, installer: MCPInstaller, pip_template: MCPServerTemplate
    ) -> None:
        """Test successful pip installation."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"installed", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await installer.install(pip_template)

        assert result is True
        call_args = mock_exec.call_args[0]
        assert call_args[0] == "pip"
        assert call_args[1] == "install"

    async def test_no_package_returns_false(self, installer: MCPInstaller) -> None:
        """Test that template without package returns False."""
        template = MCPServerTemplate(
            name="no-package",
            description="No package defined",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            # No install_package
        )

        result = await installer.install(template)
        assert result is False


class TestMCPInstallerEnsureInstalled:
    """Tests for MCPInstaller.ensure_installed."""

    async def test_already_installed_returns_true(
        self, installer: MCPInstaller, no_install_template: MCPServerTemplate
    ) -> None:
        """Test that already installed returns True without prompting."""
        callback = AsyncMock()

        result = await installer.ensure_installed(no_install_template, callback)

        assert result is True
        callback.assert_not_called()

    async def test_user_approves_installation(
        self, installer: MCPInstaller, npm_template: MCPServerTemplate
    ) -> None:
        """Test installation when user approves."""
        callback = AsyncMock(return_value=True)

        mock_proc = AsyncMock()
        mock_proc.returncode = 1  # Not installed initially
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        install_proc = AsyncMock()
        install_proc.returncode = 0
        install_proc.communicate = AsyncMock(return_value=(b"installed", b""))

        # Mock shutil.which to return None so command check doesn't short-circuit
        with (
            patch("shutil.which", return_value=None),
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=[mock_proc, install_proc],
            ),
        ):
            result = await installer.ensure_installed(npm_template, callback)

        assert result is True
        callback.assert_called_once()

    async def test_user_declines_installation(
        self, installer: MCPInstaller, npm_template: MCPServerTemplate
    ) -> None:
        """Test that declining installation returns False."""
        callback = AsyncMock(return_value=False)

        mock_proc = AsyncMock()
        mock_proc.returncode = 1  # Not installed
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        # Mock shutil.which to return None so command check doesn't short-circuit
        with (
            patch("shutil.which", return_value=None),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            result = await installer.ensure_installed(npm_template, callback)

        assert result is False

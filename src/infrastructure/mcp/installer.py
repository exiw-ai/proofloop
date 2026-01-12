"""MCP server installation service."""

import asyncio
import shutil
from collections.abc import Awaitable, Callable

from loguru import logger

from src.domain.value_objects.mcp_types import (
    MCPInstallSource,
    MCPServerStatus,
    MCPServerTemplate,
)


class MCPInstaller:
    """Service for checking and installing MCP servers."""

    async def check_status(self, template: MCPServerTemplate) -> MCPServerStatus:
        """Check if an MCP server is installed.

        Returns:
            MCPServerStatus indicating current installation state.
        """
        if template.install_source == MCPInstallSource.NONE:
            return MCPServerStatus.INSTALLED

        if template.command:
            # Check if command exists in PATH
            cmd_parts = template.command.split()
            if cmd_parts:
                base_cmd = cmd_parts[0]
                if shutil.which(base_cmd):
                    return MCPServerStatus.INSTALLED

        if template.install_source == MCPInstallSource.NPM:
            return await self._check_npm_package(template)
        elif template.install_source == MCPInstallSource.PIP:
            return await self._check_pip_package(template)

        return MCPServerStatus.NOT_INSTALLED

    async def _check_npm_package(self, template: MCPServerTemplate) -> MCPServerStatus:
        """Check if npm package is installed globally."""
        if not template.install_package:
            return MCPServerStatus.NOT_INSTALLED

        proc = await asyncio.create_subprocess_exec(
            "npm",
            "list",
            "-g",
            template.install_package,
            "--depth=0",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return MCPServerStatus.INSTALLED if proc.returncode == 0 else MCPServerStatus.NOT_INSTALLED

    async def _check_pip_package(self, template: MCPServerTemplate) -> MCPServerStatus:
        """Check if pip package is installed."""
        if not template.install_package:
            return MCPServerStatus.NOT_INSTALLED

        proc = await asyncio.create_subprocess_exec(
            "pip",
            "show",
            template.install_package,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return MCPServerStatus.INSTALLED if proc.returncode == 0 else MCPServerStatus.NOT_INSTALLED

    async def install(self, template: MCPServerTemplate) -> bool:
        """Install an MCP server.

        Returns:
            True if installation succeeded, False otherwise.
        """
        if template.install_source == MCPInstallSource.NONE:
            logger.info(f"MCP server '{template.name}' does not require installation")
            return True

        if not template.install_package:
            logger.error(f"MCP server '{template.name}' has no install package defined")
            return False

        logger.info(f"Installing MCP server '{template.name}' via {template.install_source.value}")

        if template.install_source == MCPInstallSource.NPM:
            return await self._install_npm(template)
        elif template.install_source == MCPInstallSource.PIP:
            return await self._install_pip(template)
        elif template.install_source == MCPInstallSource.BINARY:
            return await self._install_binary(template)

        logger.error(f"Unknown install source: {template.install_source}")
        return False

    async def _install_npm(self, template: MCPServerTemplate) -> bool:
        """Install npm package globally."""
        proc = await asyncio.create_subprocess_exec(
            "npm",
            "install",
            "-g",
            template.install_package or "",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            logger.info(f"Successfully installed npm package: {template.install_package}")
            return True
        else:
            logger.error(
                f"Failed to install npm package {template.install_package}: {stderr.decode(errors='replace')}"
            )
            return False

    async def _install_pip(self, template: MCPServerTemplate) -> bool:
        """Install pip package."""
        proc = await asyncio.create_subprocess_exec(
            "pip",
            "install",
            template.install_package or "",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            logger.info(f"Successfully installed pip package: {template.install_package}")
            return True
        else:
            logger.error(
                f"Failed to install pip package {template.install_package}: {stderr.decode(errors='replace')}"
            )
            return False

    async def _install_binary(self, template: MCPServerTemplate) -> bool:
        """Install binary from URL."""
        logger.warning(f"Binary installation not yet implemented for {template.name}")
        return False

    async def ensure_installed(
        self,
        template: MCPServerTemplate,
        prompt_callback: "Callable[[str], Awaitable[bool]] | None" = None,
    ) -> bool:
        """Ensure MCP server is installed, prompting user if needed.

        Args:
            template: Server template to install.
            prompt_callback: Optional async callback to ask user for installation approval.
                            Takes message string, returns True to proceed.

        Returns:
            True if server is installed (or was just installed), False otherwise.
        """
        status = await self.check_status(template)

        if status == MCPServerStatus.INSTALLED:
            return True

        # Ask user for approval if callback provided
        if prompt_callback:
            msg = (
                f"MCP server '{template.name}' is not installed.\n"
                f"Install via {template.install_source.value}: {template.install_package}?"
            )
            approved = await prompt_callback(msg)
            if not approved:
                logger.info(f"User declined installation of '{template.name}'")
                return False

        return await self.install(template)

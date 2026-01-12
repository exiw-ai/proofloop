"""MCP server configuration service."""

import json
import os
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from src.domain.value_objects.mcp_types import (
    MCPServerConfig,
    MCPServerTemplate,
)


class MCPConfigurator:
    """Service for configuring MCP servers with credentials and settings.

    Stores configurations in user config (~/.proofloop/mcp/) or project
    config (.proofloop/mcp/).
    """

    def __init__(
        self,
        user_config_dir: Path | None = None,
        project_config_dir: Path | None = None,
    ) -> None:
        """Initialize configurator with config directories.

        Args:
            user_config_dir: User-level config dir (default: ~/.proofloop/mcp/)
            project_config_dir: Project-level config dir (default: .proofloop/mcp/)
        """
        self.user_config_dir = user_config_dir or Path.home() / ".proofloop" / "mcp"
        self.project_config_dir = project_config_dir

    def _get_user_config_path(self, server_name: str) -> Path:
        """Get path for user-level server config."""
        return self.user_config_dir / f"{server_name}.json"

    def _get_project_config_path(self, server_name: str) -> Path | None:
        """Get path for project-level server config."""
        if self.project_config_dir:
            return self.project_config_dir / f"{server_name}.json"
        return None

    def load_config(self, server_name: str) -> MCPServerConfig | None:
        """Load server config from disk.

        Checks project config first, then user config.
        """
        # Check project config first
        if self.project_config_dir:
            project_path = self._get_project_config_path(server_name)
            if project_path and project_path.exists():
                return self._load_from_file(project_path)

        # Check user config
        user_path = self._get_user_config_path(server_name)
        if user_path.exists():
            return self._load_from_file(user_path)

        return None

    def _load_from_file(self, path: Path) -> MCPServerConfig | None:
        """Load config from JSON file."""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return MCPServerConfig(**data)
        except Exception as e:
            logger.warning(f"Failed to load config from {path}: {e}")
            return None

    def save_config(
        self,
        config: MCPServerConfig,
        scope: str = "user",
    ) -> Path:
        """Save server config to disk.

        Args:
            config: Server configuration to save.
            scope: "user" for user-level, "project" for project-level.

        Returns:
            Path where config was saved.
        """
        if scope == "project" and self.project_config_dir:
            path = self.project_config_dir / f"{config.name}.json"
        else:
            path = self._get_user_config_path(config.name)

        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(config.model_dump(), f, indent=2)

        logger.info(f"Saved MCP config for '{config.name}' to {path}")
        return path

    def delete_config(self, server_name: str, scope: str = "user") -> bool:
        """Delete server config from disk.

        Args:
            server_name: Name of server to delete config for.
            scope: "user" for user-level, "project" for project-level.

        Returns:
            True if config was deleted, False if not found.
        """
        if scope == "project" and self.project_config_dir:
            path = self.project_config_dir / f"{server_name}.json"
        else:
            path = self._get_user_config_path(server_name)

        if path.exists():
            path.unlink()
            logger.info(f"Deleted MCP config for '{server_name}' from {path}")
            return True
        return False

    def list_configured_servers(self) -> list[str]:
        """List all configured server names."""
        servers: set[str] = set()

        # Check user config
        if self.user_config_dir.exists():
            for f in self.user_config_dir.glob("*.json"):
                servers.add(f.stem)

        # Check project config
        if self.project_config_dir and self.project_config_dir.exists():
            for f in self.project_config_dir.glob("*.json"):
                servers.add(f.stem)

        return sorted(servers)

    def get_missing_credentials(
        self,
        template: MCPServerTemplate,
    ) -> list[str]:
        """Get list of required credentials not yet configured.

        Checks environment variables and existing config.
        """
        missing: list[str] = []

        # Load existing config if any
        config = self.load_config(template.name)
        existing_env = config.env if config else {}

        for cred in template.required_credentials:
            # Check environment
            if os.environ.get(cred):
                continue
            # Check existing config
            if existing_env.get(cred):
                continue
            missing.append(cred)

        return missing

    def configure_from_template(
        self,
        template: MCPServerTemplate,
        credentials: dict[str, str],
        extra_args: list[str] | None = None,
        scope: str = "user",
    ) -> MCPServerConfig:
        """Create and save config from template with credentials.

        Args:
            template: Server template to configure.
            credentials: Dict of credential name -> value.
            extra_args: Additional command args.
            scope: "user" or "project" for where to save.

        Returns:
            Created MCPServerConfig.
        """
        config = template.to_config(credentials=credentials, extra_args=extra_args)
        self.save_config(config, scope=scope)
        return config

    def get_or_configure(
        self,
        template: MCPServerTemplate,
        credentials_provider: "Callable[[list[str]], dict[str, str]] | None" = None,
    ) -> MCPServerConfig | None:
        """Get existing config or create new one with provided credentials.

        Args:
            template: Server template.
            credentials_provider: Optional callback that takes list of missing
                                 credential names and returns credential values.
                                 If None and credentials are needed, returns None.

        Returns:
            MCPServerConfig if configured, None if credentials needed but not provided.
        """
        # Check for existing config
        existing = self.load_config(template.name)
        if existing:
            # Verify all credentials are still available
            missing = self.get_missing_credentials(template)
            if not missing:
                return existing

        # Need to configure
        missing = self.get_missing_credentials(template)

        if missing and not credentials_provider:
            logger.warning(f"MCP server '{template.name}' needs credentials: {missing}")
            return None

        credentials: dict[str, str] = {}
        if missing and credentials_provider:
            credentials = credentials_provider(missing)
            if not credentials:
                return None

        return self.configure_from_template(template, credentials)

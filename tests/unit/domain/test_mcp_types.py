"""Tests for MCP domain types."""

import pytest
from pydantic import ValidationError

from src.domain.value_objects.mcp_types import (
    MCPInstallSource,
    MCPServerConfig,
    MCPServerRegistry,
    MCPServerTemplate,
    MCPServerType,
)


class TestMCPServerConfig:
    """Tests for MCPServerConfig value object."""

    def test_stdio_config_to_sdk(self) -> None:
        """Test converting stdio config to SDK format."""
        config = MCPServerConfig(
            name="test-server",
            type=MCPServerType.STDIO,
            command="node",
            args=["server.js", "--port", "3000"],
            env={"API_KEY": "secret"},
        )

        sdk_config = config.to_sdk_config()

        assert sdk_config["command"] == "node"
        assert sdk_config["args"] == ["server.js", "--port", "3000"]
        assert sdk_config["env"] == {"API_KEY": "secret"}

    def test_stdio_config_minimal(self) -> None:
        """Test minimal stdio config without optional fields."""
        config = MCPServerConfig(
            name="minimal",
            type=MCPServerType.STDIO,
            command="my-server",
        )

        sdk_config = config.to_sdk_config()

        assert sdk_config == {"command": "my-server"}

    def test_stdio_config_without_command_raises(self) -> None:
        """Test that stdio config without command raises ValueError."""
        config = MCPServerConfig(
            name="no-command",
            type=MCPServerType.STDIO,
        )

        with pytest.raises(ValueError, match="requires command"):
            config.to_sdk_config()

    def test_sse_config_to_sdk(self) -> None:
        """Test converting SSE config to SDK format."""
        config = MCPServerConfig(
            name="sse-server",
            type=MCPServerType.SSE,
            url="https://api.example.com/sse",
            headers={"Authorization": "Bearer token"},
        )

        sdk_config = config.to_sdk_config()

        assert sdk_config["type"] == "sse"
        assert sdk_config["url"] == "https://api.example.com/sse"
        assert sdk_config["headers"] == {"Authorization": "Bearer token"}

    def test_sse_config_without_url_raises(self) -> None:
        """Test that SSE config without URL raises ValueError."""
        config = MCPServerConfig(
            name="no-url",
            type=MCPServerType.SSE,
        )

        with pytest.raises(ValueError, match="requires url"):
            config.to_sdk_config()

    def test_http_config_to_sdk(self) -> None:
        """Test converting HTTP config to SDK format."""
        config = MCPServerConfig(
            name="http-server",
            type=MCPServerType.HTTP,
            url="https://api.example.com/mcp",
        )

        sdk_config = config.to_sdk_config()

        assert sdk_config["type"] == "http"
        assert sdk_config["url"] == "https://api.example.com/mcp"

    def test_http_config_without_url_raises(self) -> None:
        """Test that HTTP config without URL raises ValueError."""
        config = MCPServerConfig(
            name="no-url",
            type=MCPServerType.HTTP,
        )

        with pytest.raises(ValueError, match="requires url"):
            config.to_sdk_config()

    def test_config_is_frozen(self) -> None:
        """Test that MCPServerConfig is immutable."""
        config = MCPServerConfig(
            name="frozen-test",
            type=MCPServerType.STDIO,
            command="test",
        )

        with pytest.raises(ValidationError):
            config.name = "new-name"  # type: ignore


class TestMCPServerTemplate:
    """Tests for MCPServerTemplate."""

    def test_to_config_basic(self) -> None:
        """Test creating config from template without credentials."""
        template = MCPServerTemplate(
            name="playwright",
            description="Browser automation",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-playwright",
            command="npx",
            default_args=["@anthropic/mcp-server-playwright"],
        )

        config = template.to_config()

        assert config.name == "playwright"
        assert config.type == MCPServerType.STDIO
        assert config.command == "npx"
        assert config.args == ["@anthropic/mcp-server-playwright"]

    def test_to_config_with_credentials(self) -> None:
        """Test creating config with credentials."""
        template = MCPServerTemplate(
            name="github",
            description="GitHub API",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            command="npx",
            default_args=["@anthropic/mcp-server-github"],
            required_credentials=["GITHUB_TOKEN"],
        )

        config = template.to_config(credentials={"GITHUB_TOKEN": "ghp_xxx"})

        assert config.env == {"GITHUB_TOKEN": "ghp_xxx"}

    def test_to_config_with_extra_args(self) -> None:
        """Test creating config with extra arguments."""
        template = MCPServerTemplate(
            name="test",
            description="Test server",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            command="npx",
            default_args=["server"],
        )

        config = template.to_config(extra_args=["--verbose", "--port", "8080"])

        assert config.args == ["server", "--verbose", "--port", "8080"]

    def test_to_config_url_template_substitution(self) -> None:
        """Test URL template variable substitution."""
        template = MCPServerTemplate(
            name="custom-api",
            description="Custom API",
            type=MCPServerType.SSE,
            install_source=MCPInstallSource.NONE,
            url_template="https://${API_HOST}/sse?key=${API_KEY}",
            required_credentials=["API_HOST", "API_KEY"],
        )

        config = template.to_config(credentials={"API_HOST": "example.com", "API_KEY": "secret123"})

        assert config.url == "https://example.com/sse?key=secret123"

    def test_template_is_frozen(self) -> None:
        """Test that MCPServerTemplate is immutable."""
        template = MCPServerTemplate(
            name="test",
            description="Test",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NONE,
        )

        with pytest.raises(ValidationError):
            template.name = "new-name"  # type: ignore


class TestMCPServerRegistry:
    """Tests for MCPServerRegistry."""

    def test_register_and_get(self) -> None:
        """Test registering and retrieving templates."""
        registry = MCPServerRegistry()
        template = MCPServerTemplate(
            name="test-server",
            description="Test",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NONE,
        )

        registry.register(template)
        result = registry.get("test-server")

        assert result == template

    def test_get_nonexistent_returns_none(self) -> None:
        """Test getting non-existent template returns None."""
        registry = MCPServerRegistry()

        assert registry.get("nonexistent") is None

    def test_list_all(self) -> None:
        """Test listing all templates."""
        registry = MCPServerRegistry()
        registry.register(
            MCPServerTemplate(
                name="server1",
                description="First",
                type=MCPServerType.STDIO,
                install_source=MCPInstallSource.NONE,
            )
        )
        registry.register(
            MCPServerTemplate(
                name="server2",
                description="Second",
                type=MCPServerType.STDIO,
                install_source=MCPInstallSource.NONE,
            )
        )

        templates = registry.list_all()

        assert len(templates) == 2
        names = {t.name for t in templates}
        assert names == {"server1", "server2"}

    def test_list_by_category(self) -> None:
        """Test listing templates by category."""
        registry = MCPServerRegistry()
        registry.register(
            MCPServerTemplate(
                name="browser1",
                description="Browser 1",
                type=MCPServerType.STDIO,
                install_source=MCPInstallSource.NPM,
                category="browser",
            )
        )
        registry.register(
            MCPServerTemplate(
                name="db1",
                description="Database 1",
                type=MCPServerType.STDIO,
                install_source=MCPInstallSource.NPM,
                category="database",
            )
        )
        registry.register(
            MCPServerTemplate(
                name="browser2",
                description="Browser 2",
                type=MCPServerType.STDIO,
                install_source=MCPInstallSource.NPM,
                category="browser",
            )
        )

        browser_templates = registry.list_by_category("browser")

        assert len(browser_templates) == 2
        assert all(t.category == "browser" for t in browser_templates)

    def test_get_categories(self) -> None:
        """Test getting all unique categories."""
        registry = MCPServerRegistry()
        registry.register(
            MCPServerTemplate(
                name="s1",
                description="",
                type=MCPServerType.STDIO,
                install_source=MCPInstallSource.NONE,
                category="cat-b",
            )
        )
        registry.register(
            MCPServerTemplate(
                name="s2",
                description="",
                type=MCPServerType.STDIO,
                install_source=MCPInstallSource.NONE,
                category="cat-a",
            )
        )
        registry.register(
            MCPServerTemplate(
                name="s3",
                description="",
                type=MCPServerType.STDIO,
                install_source=MCPInstallSource.NONE,
                category="cat-b",
            )
        )

        categories = registry.get_categories()

        assert categories == ["cat-a", "cat-b"]  # Sorted

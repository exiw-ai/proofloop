"""Tests for predefined MCP server registry."""

from src.domain.value_objects.mcp_types import MCPInstallSource, MCPServerType
from src.infrastructure.mcp.registry import get_default_registry, get_server_template


class TestDefaultRegistry:
    """Tests for the default MCP server registry."""

    def test_registry_not_empty(self) -> None:
        """Test that default registry has servers."""
        registry = get_default_registry()
        templates = registry.list_all()
        assert len(templates) > 0

    def test_playwright_template_exists(self) -> None:
        """Test that playwright template is registered."""
        registry = get_default_registry()
        template = registry.get("playwright")

        assert template is not None
        assert template.name == "playwright"
        assert template.type == MCPServerType.STDIO
        assert template.install_source == MCPInstallSource.NPM

    def test_github_template_has_credentials(self) -> None:
        """Test that github template requires credentials."""
        registry = get_default_registry()
        template = registry.get("github")

        assert template is not None
        assert "GITHUB_TOKEN" in template.required_credentials
        assert "GITHUB_TOKEN" in template.credential_descriptions

    def test_postgres_template_exists(self) -> None:
        """Test that postgres template is registered."""
        registry = get_default_registry()
        template = registry.get("postgres")

        assert template is not None
        assert "POSTGRES_CONNECTION_STRING" in template.required_credentials

    def test_all_templates_have_required_fields(self) -> None:
        """Test that all templates have required fields."""
        registry = get_default_registry()
        for template in registry.list_all():
            assert template.name
            assert template.description
            assert template.type in MCPServerType
            assert template.install_source in MCPInstallSource
            assert template.category

    def test_categories_are_defined(self) -> None:
        """Test that categories are properly set."""
        registry = get_default_registry()
        categories = registry.get_categories()

        # Should have multiple categories
        assert len(categories) >= 3
        # Common expected categories
        assert "browser" in categories
        assert "database" in categories

    def test_browser_category_has_playwright(self) -> None:
        """Test that browser category includes playwright."""
        registry = get_default_registry()
        browser_servers = registry.list_by_category("browser")

        names = [t.name for t in browser_servers]
        assert "playwright" in names

    def test_no_duplicate_names(self) -> None:
        """Test that all server names are unique."""
        registry = get_default_registry()
        templates = registry.list_all()
        names = [t.name for t in templates]

        assert len(names) == len(set(names)), "Duplicate server names found"

    def test_stdio_servers_have_command(self) -> None:
        """Test that all stdio servers have command defined."""
        registry = get_default_registry()
        for template in registry.list_all():
            if template.type == MCPServerType.STDIO:
                assert template.command is not None, f"{template.name} missing command"

    def test_npm_servers_have_package(self) -> None:
        """Test that npm-installed servers have package name."""
        registry = get_default_registry()
        for template in registry.list_all():
            if template.install_source == MCPInstallSource.NPM:
                assert template.install_package, f"{template.name} missing install_package"


class TestGetServerTemplate:
    """Tests for get_server_template convenience function."""

    def test_get_existing_template(self) -> None:
        """Test getting existing template."""
        template = get_server_template("playwright")
        assert template is not None
        assert template.name == "playwright"

    def test_get_nonexistent_returns_none(self) -> None:
        """Test getting non-existent template returns None."""
        template = get_server_template("nonexistent-server")
        assert template is None


class TestTemplateToConfig:
    """Tests for template.to_config conversion."""

    def test_playwright_to_config(self) -> None:
        """Test converting playwright template to config."""
        template = get_server_template("playwright")
        assert template is not None

        config = template.to_config()

        assert config.name == "playwright"
        assert config.type == MCPServerType.STDIO
        assert config.command == "npx"
        assert "@anthropic/mcp-server-playwright" in config.args

    def test_github_to_config_with_token(self) -> None:
        """Test converting github template with credentials."""
        template = get_server_template("github")
        assert template is not None

        config = template.to_config(credentials={"GITHUB_TOKEN": "ghp_xxx"})

        assert config.env["GITHUB_TOKEN"] == "ghp_xxx"

    def test_config_to_sdk_format(self) -> None:
        """Test full pipeline: template -> config -> SDK format."""
        template = get_server_template("playwright")
        assert template is not None

        config = template.to_config()
        sdk_config = config.to_sdk_config()

        assert sdk_config["command"] == "npx"
        assert "@anthropic/mcp-server-playwright" in sdk_config["args"]

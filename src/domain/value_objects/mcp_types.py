"""MCP (Model Context Protocol) server configuration types."""

from enum import Enum

from pydantic import BaseModel, Field


class MCPServerType(str, Enum):
    """Type of MCP server transport."""

    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


class MCPInstallSource(str, Enum):
    """Installation source for MCP server."""

    NPM = "npm"
    PIP = "pip"
    BINARY = "binary"
    NONE = "none"


class MCPServerConfig(BaseModel, frozen=True):
    """Configuration for an MCP server.

    Supports all Claude Code SDK transport types: stdio, sse, http.
    """

    name: str = Field(description="Unique identifier for the server")
    type: MCPServerType = Field(description="Transport type")
    description: str = Field(default="", description="Human-readable description")

    # Stdio-specific fields
    command: str | None = Field(default=None, description="Command to execute (stdio)")
    args: list[str] = Field(default_factory=list, description="Command arguments (stdio)")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables")

    # URL-based fields (sse, http)
    url: str | None = Field(default=None, description="Server URL (sse/http)")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP headers")

    # Installation metadata
    install_source: MCPInstallSource = Field(
        default=MCPInstallSource.NONE, description="How to install the server"
    )
    install_package: str | None = Field(
        default=None, description="Package name (npm/pip) or binary URL"
    )

    # Credentials needed
    required_credentials: list[str] = Field(
        default_factory=list, description="Environment variable names required for this server"
    )

    def to_sdk_config(self) -> dict[str, object]:
        """Convert to Claude Code SDK MCP server config format."""
        if self.type == MCPServerType.STDIO:
            if not self.command:
                raise ValueError(f"Stdio server '{self.name}' requires command")
            config: dict[str, object] = {"command": self.command}
            if self.args:
                config["args"] = self.args
            if self.env:
                config["env"] = self.env
            return config
        elif self.type == MCPServerType.SSE:
            if not self.url:
                raise ValueError(f"SSE server '{self.name}' requires url")
            config = {"type": "sse", "url": self.url}
            if self.headers:
                config["headers"] = self.headers
            return config
        elif self.type == MCPServerType.HTTP:
            if not self.url:
                raise ValueError(f"HTTP server '{self.name}' requires url")
            config = {"type": "http", "url": self.url}
            if self.headers:
                config["headers"] = self.headers
            return config
        else:
            raise ValueError(f"Unknown server type: {self.type}")


class MCPServerStatus(str, Enum):
    """Status of an MCP server."""

    NOT_INSTALLED = "not_installed"
    INSTALLED = "installed"
    CONFIGURED = "configured"
    NOT_CONFIGURED = "not_configured"


class MCPServerTemplate(BaseModel, frozen=True):
    """Template for a predefined MCP server.

    Contains all information needed to install and configure a server.
    """

    name: str
    description: str
    type: MCPServerType
    install_source: MCPInstallSource
    install_package: str | None = None
    command: str | None = None
    default_args: list[str] = Field(default_factory=list)
    required_credentials: list[str] = Field(default_factory=list)
    credential_descriptions: dict[str, str] = Field(default_factory=dict)
    url_template: str | None = Field(
        default=None, description="URL template for sse/http (may use env vars)"
    )
    category: str = Field(default="general", description="Category for grouping")

    def to_config(
        self,
        credentials: dict[str, str] | None = None,
        extra_args: list[str] | None = None,
    ) -> MCPServerConfig:
        """Create MCPServerConfig from template with provided credentials."""
        env: dict[str, str] = {}
        headers: dict[str, str] = {}

        if credentials:
            for key, value in credentials.items():
                if key in self.required_credentials:
                    env[key] = value

        url = self.url_template
        if url and credentials:
            for key, value in credentials.items():
                url = url.replace(f"${{{key}}}", value)

        args = list(self.default_args)
        if extra_args:
            args.extend(extra_args)

        return MCPServerConfig(
            name=self.name,
            type=self.type,
            description=self.description,
            command=self.command,
            args=args,
            env=env,
            url=url,
            headers=headers,
            install_source=self.install_source,
            install_package=self.install_package,
            required_credentials=list(self.required_credentials),
        )


class MCPServerRegistry(BaseModel):
    """Registry of predefined MCP server templates."""

    templates: dict[str, MCPServerTemplate] = Field(default_factory=dict)

    def register(self, template: MCPServerTemplate) -> None:
        """Register a server template."""
        self.templates[template.name] = template

    def get(self, name: str) -> MCPServerTemplate | None:
        """Get a template by name."""
        return self.templates.get(name)

    def list_all(self) -> list[MCPServerTemplate]:
        """List all registered templates."""
        return list(self.templates.values())

    def list_by_category(self, category: str) -> list[MCPServerTemplate]:
        """List templates in a specific category."""
        return [t for t in self.templates.values() if t.category == category]

    def get_categories(self) -> list[str]:
        """Get all unique categories."""
        return sorted({t.category for t in self.templates.values()})

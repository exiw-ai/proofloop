"""Predefined MCP server registry with popular servers."""

from src.domain.value_objects.mcp_types import (
    MCPInstallSource,
    MCPServerRegistry,
    MCPServerTemplate,
    MCPServerType,
)


def get_default_registry() -> MCPServerRegistry:
    """Get the default registry with predefined MCP servers."""
    registry = MCPServerRegistry()

    # Browser automation (Playwright)
    registry.register(
        MCPServerTemplate(
            name="playwright",
            description="Browser automation for web testing and scraping",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-playwright",
            command="npx",
            default_args=["@anthropic/mcp-server-playwright"],
            required_credentials=[],
            category="browser",
        )
    )

    # Puppeteer browser automation
    registry.register(
        MCPServerTemplate(
            name="puppeteer",
            description="Browser automation with Puppeteer for web scraping",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-puppeteer",
            command="npx",
            default_args=["@anthropic/mcp-server-puppeteer"],
            required_credentials=[],
            category="browser",
        )
    )

    # Filesystem access
    registry.register(
        MCPServerTemplate(
            name="filesystem",
            description="Read and write files with extended access",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-filesystem",
            command="npx",
            default_args=["@anthropic/mcp-server-filesystem"],
            required_credentials=[],
            category="files",
        )
    )

    # GitHub integration
    registry.register(
        MCPServerTemplate(
            name="github",
            description="GitHub API integration for issues, PRs, repos",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-github",
            command="npx",
            default_args=["@anthropic/mcp-server-github"],
            required_credentials=["GITHUB_TOKEN"],
            credential_descriptions={
                "GITHUB_TOKEN": "GitHub personal access token with repo access",
            },
            category="vcs",
        )
    )

    # GitLab integration
    registry.register(
        MCPServerTemplate(
            name="gitlab",
            description="GitLab API integration for issues, MRs, repos",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-gitlab",
            command="npx",
            default_args=["@anthropic/mcp-server-gitlab"],
            required_credentials=["GITLAB_TOKEN", "GITLAB_URL"],
            credential_descriptions={
                "GITLAB_TOKEN": "GitLab personal access token",
                "GITLAB_URL": "GitLab instance URL (e.g., https://gitlab.com)",
            },
            category="vcs",
        )
    )

    # Jira integration
    registry.register(
        MCPServerTemplate(
            name="jira",
            description="Jira integration for issues and projects",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-jira",
            command="npx",
            default_args=["@anthropic/mcp-server-jira"],
            required_credentials=["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"],
            credential_descriptions={
                "JIRA_URL": "Jira instance URL (e.g., https://your-org.atlassian.net)",
                "JIRA_EMAIL": "Your Jira account email",
                "JIRA_API_TOKEN": "Jira API token (create at id.atlassian.com)",
            },
            category="project-management",
        )
    )

    # Linear integration
    registry.register(
        MCPServerTemplate(
            name="linear",
            description="Linear integration for issues and projects",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-linear",
            command="npx",
            default_args=["@anthropic/mcp-server-linear"],
            required_credentials=["LINEAR_API_KEY"],
            credential_descriptions={
                "LINEAR_API_KEY": "Linear API key (create in Settings > API)",
            },
            category="project-management",
        )
    )

    # PostgreSQL database
    registry.register(
        MCPServerTemplate(
            name="postgres",
            description="PostgreSQL database access",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-postgres",
            command="npx",
            default_args=["@anthropic/mcp-server-postgres"],
            required_credentials=["POSTGRES_CONNECTION_STRING"],
            credential_descriptions={
                "POSTGRES_CONNECTION_STRING": "PostgreSQL connection string (postgresql://user:pass@host:5432/db)",
            },
            category="database",
        )
    )

    # SQLite database
    registry.register(
        MCPServerTemplate(
            name="sqlite",
            description="SQLite database access",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-sqlite",
            command="npx",
            default_args=["@anthropic/mcp-server-sqlite"],
            required_credentials=[],
            category="database",
        )
    )

    # Slack integration
    registry.register(
        MCPServerTemplate(
            name="slack",
            description="Slack workspace integration",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-slack",
            command="npx",
            default_args=["@anthropic/mcp-server-slack"],
            required_credentials=["SLACK_BOT_TOKEN"],
            credential_descriptions={
                "SLACK_BOT_TOKEN": "Slack bot OAuth token (xoxb-...)",
            },
            category="communication",
        )
    )

    # Memory/knowledge base
    registry.register(
        MCPServerTemplate(
            name="memory",
            description="Persistent memory and knowledge storage",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-memory",
            command="npx",
            default_args=["@anthropic/mcp-server-memory"],
            required_credentials=[],
            category="storage",
        )
    )

    # Brave Search
    registry.register(
        MCPServerTemplate(
            name="brave-search",
            description="Web search using Brave Search API",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-brave-search",
            command="npx",
            default_args=["@anthropic/mcp-server-brave-search"],
            required_credentials=["BRAVE_API_KEY"],
            credential_descriptions={
                "BRAVE_API_KEY": "Brave Search API key",
            },
            category="search",
        )
    )

    # Fetch/HTTP
    registry.register(
        MCPServerTemplate(
            name="fetch",
            description="HTTP requests and web content fetching",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-fetch",
            command="npx",
            default_args=["@anthropic/mcp-server-fetch"],
            required_credentials=[],
            category="network",
        )
    )

    # Sentry integration
    registry.register(
        MCPServerTemplate(
            name="sentry",
            description="Sentry error tracking integration",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-sentry",
            command="npx",
            default_args=["@anthropic/mcp-server-sentry"],
            required_credentials=["SENTRY_AUTH_TOKEN", "SENTRY_ORG"],
            credential_descriptions={
                "SENTRY_AUTH_TOKEN": "Sentry authentication token",
                "SENTRY_ORG": "Sentry organization slug",
            },
            category="monitoring",
        )
    )

    # AWS integration
    registry.register(
        MCPServerTemplate(
            name="aws",
            description="AWS services integration (S3, Lambda, etc.)",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-aws",
            command="npx",
            default_args=["@anthropic/mcp-server-aws"],
            required_credentials=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"],
            credential_descriptions={
                "AWS_ACCESS_KEY_ID": "AWS access key ID",
                "AWS_SECRET_ACCESS_KEY": "AWS secret access key",
                "AWS_REGION": "AWS region (e.g., us-east-1)",
            },
            category="cloud",
        )
    )

    # Google Drive
    registry.register(
        MCPServerTemplate(
            name="google-drive",
            description="Google Drive file access",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-google-drive",
            command="npx",
            default_args=["@anthropic/mcp-server-google-drive"],
            required_credentials=["GOOGLE_CREDENTIALS_PATH"],
            credential_descriptions={
                "GOOGLE_CREDENTIALS_PATH": "Path to Google OAuth credentials JSON file",
            },
            category="storage",
        )
    )

    # Notion integration
    registry.register(
        MCPServerTemplate(
            name="notion",
            description="Notion workspace integration",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-notion",
            command="npx",
            default_args=["@anthropic/mcp-server-notion"],
            required_credentials=["NOTION_API_KEY"],
            credential_descriptions={
                "NOTION_API_KEY": "Notion integration secret (internal integration token)",
            },
            category="productivity",
        )
    )

    # Todoist integration
    registry.register(
        MCPServerTemplate(
            name="todoist",
            description="Todoist task management integration",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            install_package="@anthropic/mcp-server-todoist",
            command="npx",
            default_args=["@anthropic/mcp-server-todoist"],
            required_credentials=["TODOIST_API_TOKEN"],
            credential_descriptions={
                "TODOIST_API_TOKEN": "Todoist API token (from Settings > Integrations)",
            },
            category="productivity",
        )
    )

    return registry


# Convenience function to get template by name
def get_server_template(name: str) -> MCPServerTemplate | None:
    """Get a predefined server template by name."""
    registry = get_default_registry()
    return registry.get(name)

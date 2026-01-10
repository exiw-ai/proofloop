# MCP Servers

Connect Proofloop to external services using Model Context Protocol (MCP).

## What is MCP?

MCP (Model Context Protocol) is a standard for connecting AI agents to external tools and services. Proofloop supports MCP servers for:

- **GitHub** - Issues, PRs, code search
- **Slack** - Send notifications, read channels
- **Jira** - Create/update tickets
- **Databases** - Query data directly
- **And more...**

## Enabling MCP

MCP servers are disabled by default. Enable them with:

```bash
proofloop run "Create GitHub issue for each TODO" --path . --allow-mcp
```

## Available Servers

List all available MCP servers:

```bash
proofloop mcp list
```

Filter by category:

```bash
proofloop mcp list --category code
proofloop mcp list --category productivity
```

## Configuring a Server

### Interactive Setup

```bash
proofloop mcp configure github
```

This prompts for required credentials:

```
GitHub MCP Server Configuration
-------------------------------
Personal Access Token: ********
Default Organization (optional): myorg

Server 'github' configured successfully.
```

### View Configured Servers

```bash
proofloop mcp installed
```

## Server Reference

### GitHub

Access GitHub repositories, issues, and pull requests.

**Configuration:**
- Personal Access Token (required)
- Default Organization (optional)

**Capabilities:**
- Create/read/update issues
- Create/read pull requests
- Search code and repositories
- Read file contents

**Example task:**
```bash
proofloop run "Create a GitHub issue for the authentication bug" --path . --allow-mcp
```

### Slack

Send messages and read channels.

**Configuration:**
- Bot Token (required)
- Default Channel (optional)

**Capabilities:**
- Send messages to channels
- Read channel history
- Post thread replies

**Example task:**
```bash
proofloop run "Post deployment summary to #releases" --path . --allow-mcp
```

### Jira

Manage Jira issues and projects.

**Configuration:**
- Jira URL (required)
- API Token (required)
- Email (required)

**Capabilities:**
- Create/update issues
- Search with JQL
- Add comments
- Transition issue status

**Example task:**
```bash
proofloop run "Update PROJ-123 with implementation details" --path . --allow-mcp
```

### PostgreSQL

Query PostgreSQL databases.

**Configuration:**
- Connection string (required)

**Capabilities:**
- Execute SELECT queries
- Describe schema
- List tables

**Example task:**
```bash
proofloop run "Analyze user table schema and suggest indexes" --path . --allow-mcp
```

## Security

### Credential Storage

MCP credentials are stored in:
- macOS: Keychain
- Linux: Secret Service (libsecret)

Never stored in plain text.

### Permissions

MCP servers have limited permissions:
- Read-only where possible
- No destructive operations without confirmation
- Audit log of all MCP calls

### Best Practices

1. Use tokens with minimal required permissions
2. Rotate credentials regularly
3. Review MCP calls in verbose mode (`-v`)
4. Disable MCP when not needed

## Troubleshooting

### Server not connecting

```bash
# Check configuration
proofloop mcp installed

# Reconfigure
proofloop mcp configure github
```

### Permission denied

Verify your token has required scopes:
- GitHub: `repo`, `read:org`
- Slack: `chat:write`, `channels:read`
- Jira: Project access

### Verbose logging

```bash
proofloop run "task" --path . --allow-mcp --verbose
```

Check `output.log` for MCP request/response details.

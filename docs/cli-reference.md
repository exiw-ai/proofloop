# CLI Reference

Complete reference for all Proofloop commands.

## proofloop run

Execute a development task.

```
proofloop run [OPTIONS] DESCRIPTION
```

### Arguments

| Argument | Description |
|----------|-------------|
| `DESCRIPTION` | Task description (required) |

### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--path PATH` | `-p` | Project path (required) | - |
| `--auto-approve` | `-y` | Skip approval prompts | `false` |
| `--timeout MINUTES` | `-t` | Task timeout | `60` |
| `--verbose` | `-v` | Debug output | `false` |
| `--allow-mcp` | - | Enable MCP servers | `false` |
| `--research` | - | Research mode *(beta)* | `false` |

### Examples

```bash
# Basic task
proofloop run "Add login endpoint" --path ./api

# Fully autonomous
proofloop run "Fix all type errors" -p . -y

# With timeout
proofloop run "Large refactor" -p . -t 120

# Research mode
proofloop run "Analyze caching strategies" -p ./docs --research
```

---

## proofloop task

Task management commands.

### proofloop task status

Show current task status.

```
proofloop task status [OPTIONS]
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--path PATH` | `-p` | Project path | Current directory |

**Output:**
- Task state (running/stopped/done/blocked)
- Current iteration
- Conditions and their verification status
- Time elapsed

### proofloop task list

List all tasks in the project.

```
proofloop task list [OPTIONS]
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--path PATH` | `-p` | Project path | Current directory |

### proofloop task resume

Resume a stopped task.

```
proofloop task resume [OPTIONS]
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--path PATH` | `-p` | Project path | Current directory |
| `--auto-approve` | `-y` | Skip approval prompts | `false` |

---

## proofloop mcp

MCP server management.

### proofloop mcp list

List available MCP servers.

```
proofloop mcp list [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--category CATEGORY` | `-c` | Filter by category |

**Categories:**
- `code` - Code analysis tools
- `data` - Database integrations
- `productivity` - Productivity tools
- `communication` - Slack, email, etc.

### proofloop mcp configure

Configure an MCP server.

```
proofloop mcp configure SERVER_NAME
```

Interactive setup prompts for required credentials and settings.

**Example:**

```bash
$ proofloop mcp configure github

GitHub MCP Server Configuration
-------------------------------
Personal Access Token: ********
Default Organization (optional): myorg

Server 'github' configured successfully.
```

### proofloop mcp installed

List configured MCP servers.

```
proofloop mcp installed
```

---

## proofloop derive-code

Generate code from a specification.

```
proofloop derive-code [OPTIONS] SPEC_FILE
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--output PATH` | `-o` | Output directory | Current directory |
| `--verbose` | `-v` | Debug output | `false` |

---

## Global Options

These options work with any command:

| Option | Short | Description |
|--------|-------|-------------|
| `--help` | - | Show help message |
| `--version` | - | Show version |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error or task blocked |
| `2` | Invalid arguments |

---

## Shell Completion

Enable tab completion:

```bash
# Bash
proofloop --install-completion bash

# Zsh
proofloop --install-completion zsh

# Fish
proofloop --install-completion fish
```

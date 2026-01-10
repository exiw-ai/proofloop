# Usage Guide

Detailed examples and workflows for using Proofloop effectively.

## Basic Usage

### Running a Task

```bash
proofloop run "Your task description" --path ./your-project
```

The `--path` option specifies which directory Proofloop should work in. This is required.

### Task Description Tips

Write clear, specific descriptions:

| Good | Bad |
|------|-----|
| "Add /users endpoint with GET and POST methods" | "Add API endpoint" |
| "Fix null pointer in parseConfig when config.yaml missing" | "Fix bug" |
| "Add pytest tests for auth module with 80% coverage" | "Add tests" |

## Auto-Approve Mode

Skip manual approval prompts for fully autonomous operation:

```bash
proofloop run "Refactor database layer" --path ./project --auto-approve
```

Or use the short form:

```bash
proofloop run "Refactor database layer" -p ./project -y
```

## Research Mode *(Beta)*

Generate reports and gather information without writing code:

```bash
proofloop run "Compare SQLAlchemy vs Tortoise ORM for our use case" --path ./docs --research
```

Research mode:
- Searches documentation and code
- Analyzes tradeoffs
- Generates a detailed report
- Does not modify source files

## Multi-Repository Workflow

Work across multiple repositories in a single task:

```bash
# Structure:
# ~/projects/my-feature/
# ├── backend/     (git repo)
# └── frontend/    (git repo)

proofloop run "Add /users endpoint to backend, UserList component to frontend" \
  --path ~/projects/my-feature
```

Proofloop detects multiple git repositories and coordinates changes across them.

## Timeout Control

Set a custom timeout (default: 60 minutes):

```bash
proofloop run "Complex migration task" --path . --timeout 120
```

## Verbose Output

Enable debug logging:

```bash
proofloop run "Debug this issue" --path . --verbose
```

Or use the short form:

```bash
proofloop run "Debug this issue" -p . -v
```

## MCP Integrations

Enable MCP servers for external integrations:

```bash
proofloop run "Create issue for each TODO comment" --path . --allow-mcp
```

See [MCP Servers](mcp-servers.md) for configuration.

## Task Management

### Check Status

```bash
proofloop task status
```

Shows:
- Current task state (running/stopped/done)
- Iteration count
- Conditions and their status

### List Tasks

```bash
proofloop task list
```

Lists all tasks in the current project.

### Resume a Task

If a task was stopped (timeout or manual stop):

```bash
proofloop task resume
```

Continues from where it left off.

## Example Workflows

### Feature Development

```bash
# 1. Create the feature
proofloop run "Add user authentication with JWT tokens" -p ./backend -y

# 2. Add tests
proofloop run "Add integration tests for authentication flow" -p ./backend -y

# 3. Update documentation
proofloop run "Document authentication API in OpenAPI spec" -p ./backend -y
```

### Bug Fix

```bash
# 1. Investigate and fix
proofloop run "Fix race condition in WebSocket message handler" -p . -y

# 2. Add regression test
proofloop run "Add test case for WebSocket race condition" -p . -y
```

### Code Review Prep

```bash
# Run all checks before PR
proofloop run "Fix all linter warnings and type errors" -p . -y
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PROOFLOOP_STATE_DIR` | Task state storage | `.proofloop/` in project |

## Completion States

| State | Meaning | Action |
|-------|---------|--------|
| **DONE** | All conditions passed with evidence | Task complete |
| **STOPPED** | Budget exhausted (time/iterations) | Use `task resume` |
| **BLOCKED** | Needs user input | Check output for questions |

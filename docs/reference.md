# CLI Reference

Complete reference for all Proofloop commands.

## proofloop run

Execute a development task.

```
proofloop run <DESCRIPTION> --path <PATH> [OPTIONS]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `DESCRIPTION` | Task description (required) |

### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--path PATH` | `-p` | Workspace path (required) | - |
| `--auto-approve` | `-y` | Skip approval prompts | `false` |
| `--baseline` | - | Run baseline checks first | `false` |
| `--timeout HOURS` | `-t` | Task timeout in hours | `4` |
| `--verbose` | `-v` | Debug output | `false` |
| `--state-dir PATH` | - | State directory | `~/.local/share/proofloop` |
| `--task-id TEXT` | - | Custom task ID | auto-generated |
| `--provider TEXT` | - | Agent: claude, codex, opencode | `claude` |

### Examples

```bash
# Basic task
proofloop run "Add login endpoint" --path ./api

# Fully autonomous
proofloop run "Fix all type errors" -p . -y

# With timeout
proofloop run "Large refactor" -p . -t 8

# Different provider
proofloop run "Add tests" -p . --provider codex
```

---

## proofloop task

Task management commands.

### proofloop task list

List all tasks.

```
proofloop task list [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--state-dir PATH` | State directory | `~/.local/share/proofloop` |

### proofloop task status

Show task status.

```
proofloop task status <TASK_ID> [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `TASK_ID` | Full UUID or short prefix (4+ chars) |

| Option | Description | Default |
|--------|-------------|---------|
| `--state-dir PATH` | State directory | `~/.local/share/proofloop` |

Output includes:
- Task state (running/stopped/done/blocked)
- Current iteration
- Conditions and verification status

### proofloop task resume

Resume a stopped task.

```
proofloop task resume <TASK_ID> [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `TASK_ID` | Full UUID or short prefix (4+ chars) |

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--state-dir PATH` | - | State directory | `~/.local/share/proofloop` |
| `--auto-approve` | `-y` | Skip approvals | `false` |
| `--provider` | - | Agent: claude, codex, opencode | `claude` |

---

## proofloop logs

Show logs directory location.

```
proofloop logs
```

Default location: `~/.local/share/proofloop/logs/`

---

## proofloop doctor

Check environment and dependencies.

```
proofloop doctor
```

Verifies:
- Python version
- Provider availability
- State directory access
- Required dependencies

---

## Global Options

Available for all commands:

| Option | Short | Description |
|--------|-------|-------------|
| `--help` | - | Show help |
| `--verbose` | `-v` | Enable verbose output |
| `--version` | `-V` | Show version |

---

## Providers

### OpenCode (default)

Flexible backends. Requires:
- OpenCode CLI installed
- Provider configured

```bash
opencode  # Interactive setup
proofloop run "task" -p . --provider opencode
```

### Codex

Uses ChatGPT. Requires:
- Codex CLI installed
- ChatGPT Plus or Pro subscription

```bash
codex  # OAuth login
proofloop run "task" -p . --provider codex
```

### Claude Code

Requires:
- Claude Code CLI installed
- Anthropic account authenticated

```bash
claude login
proofloop run "task" -p . --provider claude
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success (task DONE) |
| `1` | Error or task BLOCKED |
| `2` | Invalid arguments |

---

## Completion States

| State | Description | Next Action |
|-------|-------------|-------------|
| **DONE** | All blocking conditions passed | Task complete |
| **STOPPED** | Budget exhausted | `proofloop task resume` |
| **BLOCKED** | Needs user input | Provide requested info |

---

## Troubleshooting

### Task stuck in BLOCKED

Check what input is needed:
```bash
proofloop task status <task_id>
```

### Provider not found

Verify installation:
```bash
claude --version  # or codex, opencode
```

### Timeout too short

Increase with `-t`:
```bash
proofloop run "large task" -p . -t 10  # 10 hours
```

### State directory issues

Default location: `~/.local/share/proofloop`

Check permissions:
```bash
ls -la ~/.local/share/proofloop/
```

Reset if corrupted:
```bash
rm -rf ~/.local/share/proofloop/
```

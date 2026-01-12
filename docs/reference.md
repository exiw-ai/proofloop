# CLI Reference

Complete reference for all Proofloop commands.

## proofloop run

Execute a development task.

```
proofloop run <DESCRIPTION> --path <PATH> --provider <provider> [OPTIONS]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `DESCRIPTION` | Task description (required) |

### Required Options

| Option | Short | Description |
|--------|-------|-------------|
| `--path PATH` | `-p` | Workspace path |
| `--provider <provider>` | - | Agent: `claude`, `codex`, `opencode` |

### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--auto-approve` | `-y` | Skip approval prompts | `false` |
| `--baseline` | - | Run baseline checks first | `false` |
| `--timeout HOURS` | `-t` | Task timeout in hours | `4` |
| `--verbose` | `-v` | Debug output | `false` |
| `--state-dir PATH` | - | State directory | `~/.local/share/proofloop` |
| `--task-id TEXT` | - | Custom task ID | auto-generated |

### Examples

```bash
# Basic task
proofloop run "Add login endpoint" --path ./api --provider <provider>

# Fully autonomous
proofloop run "Fix all type errors" -p . -y --provider claude

# With timeout
proofloop run "Large refactor" -p . -t 8 --provider codex

# With OpenCode
proofloop run "Add tests" -p . --provider opencode
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
proofloop task resume <TASK_ID> --provider <provider> [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `TASK_ID` | Full UUID or short prefix (4+ chars) |

| Required Option | Description |
|-----------------|-------------|
| `--provider <provider>` | Agent: `claude`, `codex`, `opencode` |

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--state-dir PATH` | - | State directory | `~/.local/share/proofloop` |
| `--auto-approve` | `-y` | Skip approvals | `false` |

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

### OpenCode

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

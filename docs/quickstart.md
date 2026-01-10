# Quick Start

Get up and running with Proofloop in under 5 minutes.

## Prerequisites

- Python 3.11+
- [Claude Code](https://claude.ai/download) installed and authenticated

## Installation

```bash
curl -fsSL https://raw.githubusercontent.com/egorborisow/proofloop/main/install.sh | bash
```

## Your First Task

1. **Navigate to your project:**

```bash
cd ~/my-project
```

2. **Run a simple task:**

```bash
proofloop run "Add a health check endpoint to the API" --path .
```

3. **Watch it work:**

Proofloop will:
- Analyze your codebase
- Create an implementation plan
- Define success conditions (tests, lints, builds)
- Implement changes iteratively until all checks pass

## What Happens

```
$ proofloop run "Add unit tests for auth module" --path ./backend

[Intake] Analyzing project structure...
[Plan] Creating implementation plan...
[Conditions] Defining success criteria:
  - pytest tests/test_auth.py passes
  - ruff check passes
  - mypy passes

[Execute] Iteration 1/50
  Writing tests/test_auth.py...
  Running checks...
  ✗ 3 tests failing

[Execute] Iteration 2/50
  Fixing test failures...
  Running checks...
  ✓ All tests passing
  ✓ Linter clean
  ✓ Type checker clean

[Done] All conditions met with evidence.
```

## Common Use Cases

### Add a Feature

```bash
proofloop run "Create REST endpoint for user profiles with CRUD operations" --path .
```

### Fix a Bug

```bash
proofloop run "Fix the authentication timeout issue in login flow" --path .
```

### Add Tests

```bash
proofloop run "Add comprehensive unit tests for the payment module" --path .
```

### Refactor Code

```bash
proofloop run "Refactor database layer to use repository pattern" --path .
```

## Tips

- **Be specific**: "Add pagination to /users endpoint with limit/offset" works better than "improve the API"
- **Use auto-approve**: Add `-y` for fully autonomous operation
- **Check status**: Use `proofloop task status` to see current progress
- **Resume if stopped**: Use `proofloop task resume` to continue a stopped task

## Next Steps

- [Usage Guide](usage.md) - Detailed examples and workflows
- [CLI Reference](cli-reference.md) - All commands and options
- [How It Works](how-it-works.md) - Understanding the pipeline

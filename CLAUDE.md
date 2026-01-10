# CLAUDE.md

Instructions for AI coding agents working on this repository.

## Quick Reference

```bash
make test       # Run tests
make lint       # Run linter
make typecheck  # Run type checker
make check      # Run all checks
```

## Project Overview

Proofloop is an autonomous coding agent built with Python 3.11+. It uses Claude Code SDK to execute development tasks iteratively until completion criteria are met.

**Key technologies:** Python, Typer (CLI), Pydantic, asyncio, Claude Code SDK

## Code Style

- Python 3.11+ with type hints required
- Async/await for I/O operations
- Use `loguru` for logging
- Follow existing patterns in the codebase

### Comments Policy
- Avoid comments that restate the code
- Docstrings only for public interfaces and non-obvious logic
- Goal: self-documenting code

## Architecture

The project follows layered architecture:

```
src/
├── cli/            # Command-line interface
├── domain/         # Business logic, entities, value objects
├── application/    # Use cases, orchestration
└── infrastructure/ # External adapters (Claude SDK, Git, MCP)
```

**Rules:**
- Domain layer has no external dependencies
- Infrastructure implements interfaces defined in domain
- Keep business logic in domain, not in adapters

## Guidelines

### Do
- Follow existing project structure and patterns
- Keep changes minimal and focused
- Add tests for functional changes
- Run `make check` before committing

### Don't
- Commit secrets or API keys
- Break existing tests
- Add unnecessary defensive code for impossible cases
- Invent custom implementations when a library exists

## Dependencies

Core libraries used in the project:
- Validation: `pydantic`
- Retry logic: `tenacity`
- Logging: `loguru`
- HTTP: `httpx`

## When Done

A change is complete when:
- All checks pass (`make check`)
- New behavior is covered by tests
- Working tree is clean

## System Contract

Key guarantees that must be preserved when modifying the core pipeline:

- **Done** = all blocking conditions have `check_status=PASS` with evidence
- **No edits** allowed until verification inventory is complete
- **Evidence required** - every check result must have command output
- **Budgets** - max 50 iterations, 10h wall time, 3 stagnation limit
- **Supervisor verifies** - manual conditions re-checked each iteration

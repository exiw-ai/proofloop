# Contributing to Proofloop

Thank you for your interest in contributing to Proofloop!

## How to Contribute

### Reporting Bugs

1. Check if the issue already exists in [GitHub Issues](https://github.com/egorborisow/proofloop/issues)
2. If not, create a new issue using the bug report template
3. Include reproduction steps, expected vs actual behavior, and environment details

### Suggesting Features

1. Open a feature request issue using the template
2. Describe the problem you're solving and your proposed solution
3. Be open to discussion about alternative approaches

### Pull Requests

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes
4. Ensure all checks pass:
   ```bash
   make lint      # Linter
   make typecheck # Type checking
   make test      # Tests
   ```
5. Submit a pull request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/proofloop.git
cd proofloop

# Install dependencies
uv sync --all-extras

# Install pre-commit hooks
pre-commit install

# Run checks
make check
```

## Code Style

- Python 3.11+
- Type hints required
- Use `loguru` for logging
- Follow existing patterns in the codebase
- See [CLAUDE.md](CLAUDE.md) for detailed guidelines

## Project Architecture

The project follows Domain-Driven Design (DDD):

- `src/domain/` - Business logic, entities, value objects
- `src/application/` - Use cases, orchestration
- `src/infrastructure/` - External adapters (Claude SDK, Git, MCP)
- `src/cli/` - Command-line interface

## Testing

- Add tests for new functionality
- Maintain test coverage (90% target)
- Use pytest with async support

```bash
make test      # Run tests
make test-cov  # Run with coverage report
```

## Questions?

Open a [discussion](https://github.com/egorborisow/proofloop/discussions) for questions or ideas.

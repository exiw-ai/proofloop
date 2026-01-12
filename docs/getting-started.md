# Getting Started

Get up and running with Proofloop in under 5 minutes.

## Requirements

- **Python 3.12+**
- **macOS** (10.15+) or **Linux** (Ubuntu 20.04+, Debian 11+, Fedora 36+)
- **Git**

## Installation

### Recommended: uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install proofloop
```

### Alternative: pip

```bash
pip3 install proofloop
```

### From Source

```bash
git clone https://github.com/egorx1/proofloop.git
cd proofloop
pip3 install -e .
```

If `proofloop` command is not found after install:

```bash
# Add to ~/.bashrc or ~/.zshrc
export PATH="$HOME/.local/bin:$PATH"
source ~/.bashrc  # or ~/.zshrc
```

## Provider Setup

Proofloop supports three AI providers. Choose one and set it up.

### OpenCode

```bash
# 1. Install OpenCode
npm i -g opencode-ai@latest

# 2. Configure provider (interactive)
opencode
```

Supports multiple backends: Anthropic, OpenAI, local models.

### Codex (ChatGPT Plus/Pro)

```bash
# 1. Install Codex CLI
npm i -g @openai/codex

# 2. OAuth login - opens browser
codex
```

Requires active ChatGPT Plus or Pro subscription.

### Claude Code

```bash
# 1. Install CLI
# Download from: https://claude.com/download
# Or: npm i -g @anthropic-ai/claude-code

# 2. Login
claude login
```

## Verify Installation

```bash
proofloop doctor
```

Checks Python version, available providers (claude, codex, opencode), and state directory.

## Your First Task

```bash
proofloop run "Add REST API endpoint for user registration with validation" \
  --path ./my-project
```

What happens:

1. **Intake** — Proofloop analyzes your project structure
2. **Plan** — Creates implementation plan with success conditions
3. **Approval** — You review plan, adjust conditions if needed, approve
4. **Execute** — Agent works until all conditions pass
5. **Done** — Results with evidence

Example session:

```
$ proofloop run "Add REST API for user registration with email validation" --path ./backend

[Intake] Analyzing project structure...
[Inventory] Found: pytest, ruff, mypy
[Plan] Creating implementation plan...

Plan:
  1. Create User model with email, password fields
  2. Add registration endpoint POST /api/users
  3. Implement email validation
  4. Add unit tests

Conditions:
  - pytest tests/ passes
  - ruff check passes
  - mypy --strict passes
  - "POST /api/users returns 201 for valid data"
  - "POST /api/users returns 400 for invalid email"

[Approve?] (y)es / (n)o / (f)eedback / (c)onditions: y

[Execute] Iteration 1/50
  Creating models/user.py...
  Creating routes/users.py...
  Running checks...
  ✗ mypy: 2 type errors

[Execute] Iteration 2/50
  Fixing type annotations...
  ✓ All checks passing

[Done] All conditions met with evidence.
```

## Troubleshooting

### Command not found

```bash
# Check PATH
echo $PATH | grep -q ".local/bin" && echo "OK" || echo "Add ~/.local/bin to PATH"

# Update shell
uv tool update-shell
source ~/.bashrc
```

### Python version too old

```bash
# macOS
brew install python@3.12

# Ubuntu/Debian
sudo apt install python3.12 python3.12-venv

# Fedora
sudo dnf install python3.12
```

### Permission denied

Don't use `sudo`. Ensure ~/.local/bin is writable:

```bash
mkdir -p ~/.local/bin
chmod 755 ~/.local/bin
```

## Next Steps

- [User Guide](guide.md) — Workflows and features
- [Reference](reference.md) — CLI commands and options

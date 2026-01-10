# Installation Guide

## Requirements

- **Python 3.11+** (3.12 also supported)
- **macOS** (10.15+, Apple Silicon compatible) or **Linux** (Ubuntu 20.04+, Debian 11+, Fedora 36+)
- **Git** for source installation
- **[Claude Code](https://claude.ai/download)** installed and authenticated

## Quick Install

The fastest way to install on macOS or Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/egorborisow/proofloop/main/install.sh | bash
```

This script will:
1. Check Python version (3.11+ required)
2. Install [uv](https://github.com/astral-sh/uv) if not present
3. Clone the repository to `~/.proofloop`
4. Install `proofloop` command globally

## Alternative Methods

### From Source

```bash
git clone https://github.com/egorborisow/proofloop.git
cd proofloop
make install
```

### Using pipx

If you have [pipx](https://pypa.github.io/pipx/):

```bash
pipx install git+https://github.com/egorborisow/proofloop.git
```

### Using uv

If you have [uv](https://github.com/astral-sh/uv):

```bash
uv tool install git+https://github.com/egorborisow/proofloop.git
```

## Verify Installation

```bash
proofloop --help
```

If the command is not found, add `~/.local/bin` to your PATH:

```bash
# Add to ~/.bashrc or ~/.zshrc
export PATH="$HOME/.local/bin:$PATH"

# Then reload
source ~/.bashrc  # or ~/.zshrc
```

## Configuration

### Claude Code

Proofloop uses Claude Code SDK. Make sure Claude Code is installed and authenticated:

```bash
# Install Claude Code (if not already)
# Visit: https://claude.ai/download

# Authenticate
claude login
```

### State Directory

By default, proofloop stores task state in `.proofloop/` within your project. Override with:

```bash
export PROOFLOOP_STATE_DIR="/custom/path"
```

## Updating

```bash
cd ~/.proofloop  # or wherever you cloned
make update
```

Or re-run the install script:

```bash
curl -fsSL https://raw.githubusercontent.com/egorborisow/proofloop/main/install.sh | bash
```

## Uninstalling

```bash
cd ~/.proofloop
make uninstall

# Optionally remove the repo
rm -rf ~/.proofloop
```

## Troubleshooting

### Python version too old

```bash
# macOS (Homebrew)
brew install python@3.11

# Ubuntu/Debian
sudo apt update
sudo apt install python3.11 python3.11-venv

# Fedora
sudo dnf install python3.11
```

### Command not found after install

```bash
# Check if ~/.local/bin is in PATH
echo $PATH | grep -q ".local/bin" && echo "OK" || echo "Add ~/.local/bin to PATH"

# Update shell
uv tool update-shell
source ~/.bashrc  # or ~/.zshrc
```

### Permission denied

Don't use `sudo` with the install script. If you have permission issues:

```bash
# Ensure ~/.local/bin exists and is writable
mkdir -p ~/.local/bin
chmod 755 ~/.local/bin
```

## Development Setup

For contributing or modifying proofloop:

```bash
git clone https://github.com/egorborisow/proofloop.git
cd proofloop
make dev        # Install dev dependencies
make check      # Run all checks
make help       # Show all available commands
```

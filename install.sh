#!/usr/bin/env bash
set -e

# Proofloop installer
# Usage: curl -fsSL https://raw.githubusercontent.com/egorborisow/proofloop/main/install.sh | bash

REPO_URL="https://github.com/egorborisow/proofloop.git"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info() { echo -e "${BLUE}==>${NC} $1"; }
success() { echo -e "${GREEN}==>${NC} $1"; }
warn() { echo -e "${YELLOW}==>${NC} $1"; }
error() { echo -e "${RED}==>${NC} $1"; exit 1; }

# Check OS
check_os() {
    case "$(uname -s)" in
        Linux*)  OS=linux;;
        Darwin*) OS=macos;;
        *)       error "Unsupported OS: $(uname -s). Use Linux or macOS.";;
    esac
    info "Detected OS: $OS"
}

# Check Python version
check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
            success "Python $PYTHON_VERSION found"
            return 0
        fi
    fi
    error "Python 3.11+ required. Found: ${PYTHON_VERSION:-none}

Install Python 3.11+:
  macOS:   brew install python@3.11
  Ubuntu:  sudo apt install python3.11
  Fedora:  sudo dnf install python3.11"
}

# Install uv if not present
install_uv() {
    if command -v uv &> /dev/null; then
        success "uv already installed"
    else
        info "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
        success "uv installed"
    fi
}

# Clone and install
install_proofloop() {
    INSTALL_DIR="${PROOFLOOP_INSTALL_DIR:-$HOME/.proofloop}"

    if [ -d "$INSTALL_DIR" ]; then
        info "Updating existing installation..."
        cd "$INSTALL_DIR"
        git pull --quiet
    else
        info "Cloning proofloop..."
        git clone --quiet "$REPO_URL" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi

    info "Installing proofloop..."
    uv tool install . --editable --force --quiet
    success "proofloop installed"
}

# Verify installation
verify() {
    if command -v proofloop &> /dev/null; then
        success "Installation complete!"
        echo ""
        proofloop --help | head -20
        echo ""
        echo -e "${GREEN}Run your first task:${NC}"
        echo '  proofloop run "your task description" --path ./your-project'
    else
        warn "proofloop not found in PATH"
        echo ""
        echo "Add to your shell config (~/.bashrc, ~/.zshrc):"
        echo '  export PATH="$HOME/.local/bin:$PATH"'
        echo ""
        echo "Then restart your terminal or run:"
        echo '  source ~/.bashrc  # or ~/.zshrc'
    fi
}

main() {
    echo ""
    echo "  ____                   __ _                   "
    echo " |  _ \ _ __ ___   ___  / _| | ___   ___  _ __  "
    echo " | |_) | '__/ _ \ / _ \| |_| |/ _ \ / _ \| '_ \ "
    echo " |  __/| | | (_) | (_) |  _| | (_) | (_) | |_) |"
    echo " |_|   |_|  \___/ \___/|_| |_|\___/ \___/| .__/ "
    echo "                                        |_|    "
    echo ""
    echo " Autonomous coding agent powered by Claude"
    echo ""

    check_os
    check_python
    install_uv
    install_proofloop
    verify
}

main "$@"

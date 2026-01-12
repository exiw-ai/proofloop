#!/bin/bash
set -e

echo "Installing Proofloop..."

# Install uv if not present
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Install proofloop from GitHub
echo "Installing proofloop..."
uv tool install git+https://github.com/exiw-ai/proofloop.git

echo ""
echo "Done! Run 'proofloop --help' to get started."

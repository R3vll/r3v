#!/usr/bin/env bash
set -e

echo "Installing R3v..."
mkdir -p ~/.r3v/history

INSTALL_DIR="/usr/local/bin"
if [ ! -w "$INSTALL_DIR" ]; then
    INSTALL_DIR="$HOME/.local/bin"
    mkdir -p "$INSTALL_DIR"
fi

cp r3v.py "$INSTALL_DIR/r3v"
chmod +x "$INSTALL_DIR/r3v"

echo "✓ R3v installed successfully to $INSTALL_DIR/r3v!"
echo "Run 'r3v' to start."

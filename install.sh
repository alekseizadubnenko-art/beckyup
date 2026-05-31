#!/bin/bash
set -e

APP="beckyup"
SRC_DIR="$(cd "$(dirname "$0")/backup_tool" && pwd)"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Detect OS
OS="$(uname -s)"
case "$OS" in
  Darwin)   PLATFORM="macos" ;;
  Linux)    PLATFORM="linux" ;;
  *)        echo "Unsupported OS: $OS. For Windows use install.ps1."; exit 1 ;;
esac

echo "=== $APP Installer ($PLATFORM) ==="
echo "Source: $SRC_DIR"

# Step 1: Install deps
echo ""
echo "[1/3] Installing dependencies..."
cd "$SRC_DIR"
if command -v uv &>/dev/null; then
    uv sync 2>/dev/null || uv pip install -r requirements.txt -q
else
    pip3 install -r requirements.txt -q
fi
echo "  ✓ Dependencies installed"

# Step 2: Add shell alias
if [ "$PLATFORM" = "macos" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ "$PLATFORM" = "linux" ]; then
    # Detect default shell
    USER_SHELL="$(basename "$SHELL" 2>/dev/null || echo "bash")"
    case "$USER_SHELL" in
        zsh) SHELL_RC="$HOME/.zshrc" ;;
        bash) SHELL_RC="$HOME/.bashrc" ;;
        fish) SHELL_RC="$HOME/.config/fish/config.fish" ;;
        *) SHELL_RC="$HOME/.bashrc" ;;
    esac
fi

# Determine python command
PY_CMD="python3"
if command -v uv &>/dev/null; then
    ALIAS_CMD="uv run python"
else
    ALIAS_CMD="$PY_CMD"
fi

ALIAS_LINE="beckyup() { cd \"$SRC_DIR\" && $ALIAS_CMD main.py \"\$@\"; }"

if grep -q "beckyup()" "$SHELL_RC" 2>/dev/null; then
    echo "[2/3] Alias already in $SHELL_RC — skipping"
else
    echo "" >> "$SHELL_RC"
    echo "# $APP — emergency backup tool" >> "$SHELL_RC"
    echo "$ALIAS_LINE" >> "$SHELL_RC"
    echo "  ✓ Alias added to $SHELL_RC"
    echo "    Restart terminal or run: source $SHELL_RC"
fi

# Step 3: First run hint
AUTOSTART_PATH=""
if [ "$PLATFORM" = "macos" ]; then
    AUTOSTART_PATH="~/Library/LaunchAgents/com.beckyup.monitor.plist"
elif [ "$PLATFORM" = "linux" ]; then
    AUTOSTART_PATH="~/.config/systemd/user/beckyup.service"
fi

echo ""
echo "[3/3] First run:"
echo ""
echo "  beckyup"
echo ""
echo "  This starts the setup wizard. Follow the prompts:"
echo "    1. Pick folders to back up"
echo "    2. Select file types"
echo "    3. Plug in your backup USB drive"
echo "    4. Choose security mode"
echo "    5. Enable autostart"
echo ""
echo "  After setup, beckyup runs in the background."
echo "  Plug in your known USB → backup starts automatically."
echo ""
echo "━━━ Installation structure ━━━"
echo "  App:     $SRC_DIR"
echo "  Config:  ~/.config/backup_tool/config.json"
echo "  Logs:    ~/.config/backup_tool/logs/"
echo "  Alias:   $SHELL_RC (function beckyup)"
echo "  Autostart (if enabled): $AUTOSTART_PATH"
echo ""

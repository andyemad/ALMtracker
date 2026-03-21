#!/usr/bin/env bash
set -e

echo ""
echo "  ALM Inventory Tracker — Setup"
echo "  =============================="
echo ""

# ── Check Python ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Install Python 3.9+ first."
  exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python $PYTHON_VERSION found"

# ── Check / Install Node via nvm ──────────────────────────────────────────────
if ! command -v node &>/dev/null; then
  echo "  Node.js not found — installing via nvm..."
  # Install nvm if not present
  if [ ! -d "$HOME/.nvm" ]; then
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
  fi
  export NVM_DIR="$HOME/.nvm"
  # shellcheck disable=SC1091
  [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
  nvm install --lts
  nvm use --lts
fi
echo "  Node $(node -v) found"

# ── Backend ───────────────────────────────────────────────────────────────────
echo ""
echo "  [1/3] Installing Python dependencies..."
cd "$(dirname "$0")/backend"

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "  [2/3] Installing Playwright Chromium browser..."
playwright install chromium

# ── Frontend ──────────────────────────────────────────────────────────────────
echo ""
echo "  [3/3] Installing Node dependencies..."
cd "../frontend"

# Use npm if bun not available
if command -v bun &>/dev/null; then
  bun install
else
  npm install
fi

# ── .env template ─────────────────────────────────────────────────────────────
cd ..
if [ ! -f backend/.env ]; then
  cat > backend/.env << 'ENVEOF'
# ALM Tracker — Environment Config
# Rename this to .env and fill in values

# SMTP (optional) — for email notifications on watchlist matches
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
ENVEOF
  echo ""
  echo "  Created backend/.env — configure SMTP if you want email alerts"
fi

echo ""
echo "  =============================="
echo "  Setup complete!"
echo ""
echo "  To start the app, run:"
echo "    ./start.sh"
echo ""

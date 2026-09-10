#!/usr/bin/env bash
# =====================================================================
# File Analysis - macOS / Linux one-time setup
# Usage:  bash setup.sh
# =====================================================================
set -e
cd "$(dirname "$0")"

echo ""
echo "============================================================"
echo " File Analysis - First-time setup"
echo "============================================================"
echo ""

# ---- 1. Find Python -------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] python3 was not found."
    echo "Install Python 3.11+ with your package manager first."
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "  macOS:         brew install python@3.11"
    exit 1
fi
echo "[OK] Using $(python3 --version)"

# ---- 2. Create virtual environment ----------------------------------
if [ ! -x ".venv/bin/python" ]; then
    echo ""
    echo "Creating isolated Python environment (.venv)..."
    python3 -m venv .venv
    echo "[OK] Virtual environment created."
else
    echo "[OK] Virtual environment already exists."
fi

# ---- 3. Install dependencies ----------------------------------------
echo ""
echo "Installing required packages (this takes a few minutes)..."
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "[OK] All packages installed."

# ---- 4. Prepare .env configuration ----------------------------------
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "[OK] Created .env configuration file from the template."
    fi
else
    echo "[OK] .env already exists - leaving it untouched."
fi

echo ""
echo "============================================================"
echo " Setup complete!"
echo "============================================================"
echo ""
echo " NEXT STEPS:"
echo ""
echo " 1. Make sure PostgreSQL is installed and running"
echo "    (see INSTALL.md Step 2 if you have not done this yet)."
echo ""
echo " 2. Edit the .env file and set your DB_PASSWORD:"
echo "      nano .env"
echo ""
echo " 3. Start the application:"
echo "      bash start.sh"
echo ""
echo " 4. Open your browser at:  http://127.0.0.1:5000"
echo "    The first visit shows a Database Setup page - just enter"
echo "    your PostgreSQL 'postgres' password. The database and all"
echo "    tables are created automatically."
echo ""
echo " Full guide for absolute beginners: INSTALL.md"

#!/usr/bin/env bash
# =====================================================================
# File Analysis - macOS / Linux start script
# Usage:  bash start.sh
# =====================================================================
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo ""
    echo "[ERROR] The application is not set up yet."
    echo "Please run  bash setup.sh  first (one time only)."
    echo ""
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo ""
echo "============================================================"
echo " Starting File Analysis..."
echo " Open your browser at:  http://127.0.0.1:5000"
echo " Press CTRL+C to stop the server."
echo "============================================================"
echo ""

python run_web.py

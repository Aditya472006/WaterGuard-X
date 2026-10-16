#!/bin/bash
# OT Digital Twin — Streamlit UI Launcher
# Starts all necessary components for the web dashboard

set -e

echo "🚀 OT Digital Twin — Starting Web UI"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${BLUE}✓ Python version: ${python_version}${NC}"

# Check dependencies
echo -e "${BLUE}Checking dependencies...${NC}"

required_packages=("streamlit" "plotly" "pandas" "numpy" "scikit-learn" "tensorflow")

for package in "${required_packages[@]}"; do
    if python3 -c "import ${package//-/_}" 2>/dev/null; then
        echo -e "${GREEN}  ✓ ${package}${NC}"
    else
        echo -e "${YELLOW}  ✗ ${package} not found${NC}"
        echo -e "${YELLOW}    Install with: pip install -r requirements.txt${NC}"
    fi
done

echo ""
echo -e "${YELLOW}SETUP INSTRUCTIONS:${NC}"
echo ""
echo "Before launching the UI, start these components in separate terminals:"
echo ""
echo -e "${BLUE}Terminal 1 — PLC Slave (Modbus TCP Server):${NC}"
echo "  python -m ot_twin.cli start-plc"
echo ""
echo -e "${BLUE}Terminal 2 — SCADA Master (Polls PLC):${NC}"
echo "  python -m ot_twin.cli start-scada"
echo ""
echo -e "${BLUE}Terminal 3 — Streamlit UI (This launcher):${NC}"
echo "  ./launch_ui.sh  (or just: streamlit run streamlit_app.py)"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  • Edit .env for PLC host/port and LLM keys"
echo "  • Review .streamlit/config.toml for UI theme"
echo ""
echo "Press Enter to start Streamlit UI..."
read

# Launch Streamlit
echo ""
echo -e "${GREEN}🎬 Launching Streamlit...${NC}"
echo ""
streamlit run streamlit_app.py --client.toolbarMode=minimal


#!/bin/bash

# SuperSlicer FastMCP Server Launcher
# This script starts the FastMCP server that connects to SuperSlicer's ConfigServer

# Default configuration
CONFIG_SERVER_HOST="${CONFIG_SERVER_HOST:-localhost}"
CONFIG_SERVER_PORT="${CONFIG_SERVER_PORT:-21987}"
MCP_SERVER_HOST="${MCP_SERVER_HOST:-0.0.0.0}"
MCP_SERVER_PORT="${MCP_SERVER_PORT:-3000}"
CONNECTION_TIMEOUT="${CONNECTION_TIMEOUT:-5.0}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}SuperSlicer FastMCP Server Launcher${NC}"
echo "======================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    exit 1
fi

# Check if uv is installed (optional but recommended)
if command -v uv &> /dev/null; then
    echo -e "${GREEN}✓ Using uv for dependency management${NC}"
    USE_UV=1
else
    echo -e "${YELLOW}ℹ uv not found, using pip${NC}"
    USE_UV=0
fi

# Check if virtual environment exists
VENV_DIR="venv_mcp"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    if [ $USE_UV -eq 1 ]; then
        uv venv $VENV_DIR
    else
        python3 -m venv $VENV_DIR
    fi
fi

# Activate virtual environment
source $VENV_DIR/bin/activate

# Install/upgrade dependencies
echo -e "${YELLOW}Checking dependencies...${NC}"
if [ $USE_UV -eq 1 ]; then
    uv pip install -q --upgrade -r requirements-mcp.txt
else
    pip install -q --upgrade -r requirements-mcp.txt
fi

# Check if SuperSlicer is running (optional check)
echo ""
echo "Configuration:"
echo "  ConfigServer Host: $CONFIG_SERVER_HOST:$CONFIG_SERVER_PORT"
echo "  MCP Server:        $MCP_SERVER_HOST:$MCP_SERVER_PORT"
echo "  Timeout:           $CONNECTION_TIMEOUT seconds"
echo ""

# Test connection to SuperSlicer
echo -e "${YELLOW}Testing SuperSlicer connection...${NC}"
python3 -c "
import socket
import sys

try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex(('$CONFIG_SERVER_HOST', $CONFIG_SERVER_PORT))
    sock.close()
    if result == 0:
        print('✓ SuperSlicer ConfigServer is accessible')
        sys.exit(0)
    else:
        print('✗ Cannot connect to SuperSlicer ConfigServer')
        print('  Make sure SuperSlicer is running with --enable-config-server')
        sys.exit(1)
except Exception as e:
    print(f'✗ Connection test failed: {e}')
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo ""
    echo -e "${YELLOW}To enable ConfigServer in SuperSlicer:${NC}"
    echo "  1. Apply the integration patch: patch -p1 < integrate_configserver.patch"
    echo "  2. Rebuild SuperSlicer: cd build && make -j\$(nproc)"
    echo "  3. Start with flag: ./build/bin/superslicer --enable-config-server"
    echo "  4. Or add to ~/.config/SuperSlicer/SuperSlicer.ini:"
    echo "     enable_config_server = 1"
    echo "     config_server_port = 21987"
    echo ""
    read -p "Start MCP server anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Export environment variables
export CONFIG_SERVER_HOST
export CONFIG_SERVER_PORT
export CONNECTION_TIMEOUT

# Start the FastMCP server
echo ""
echo -e "${GREEN}Starting SuperSlicer FastMCP Server...${NC}"
echo "======================================="
echo ""
echo "The server will be available at:"
echo "  http://$MCP_SERVER_HOST:$MCP_SERVER_PORT"
echo ""
echo "To use with MCP clients:"
echo "  MCP_SERVER_URL=http://localhost:$MCP_SERVER_PORT"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Run with uvicorn
exec uvicorn superslicer_fastmcp_server:app \
    --host "$MCP_SERVER_HOST" \
    --port "$MCP_SERVER_PORT" \
    --reload \
    --log-level info
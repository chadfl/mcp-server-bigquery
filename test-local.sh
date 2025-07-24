#!/bin/bash

# Local testing script for MCP BigQuery Server with Supergateway
# This script helps test the Supergateway integration locally before Cloud Run deployment

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${YELLOW}INFO: $1${NC}"
}

print_success() {
    echo -e "${GREEN}SUCCESS: $1${NC}"
}

# Default configuration
PORT=${PORT:-8080}

print_info "Starting MCP BigQuery Server locally with Supergateway"
print_info "Port: $PORT"

# Check if Supergateway is installed
if ! command -v supergateway &> /dev/null; then
    print_info "Installing Supergateway..."
    npm install -g supergateway
fi

# Check for environment file
if [ -f ".env" ]; then
    print_info "Loading environment variables from .env file"
    export $(cat .env | grep -v '^#' | xargs)
elif [ -f "example.env" ]; then
    print_info "No .env file found. You can copy example.env to .env and customize it."
    print_info "Using example.env for now (you may need to set BIGQUERY_PROJECT and BIGQUERY_LOCATION)"
    export $(cat example.env | grep -v '^#' | xargs)
fi

# Build the MCP command
MCP_CMD="uv run mcp-server-bigquery"

if [ ! -z "$BIGQUERY_PROJECT" ]; then
    MCP_CMD="$MCP_CMD --project $BIGQUERY_PROJECT"
fi

if [ ! -z "$BIGQUERY_LOCATION" ]; then
    MCP_CMD="$MCP_CMD --location $BIGQUERY_LOCATION"
fi

if [ ! -z "$BIGQUERY_DATASETS" ]; then
    IFS=',' read -ra DATASETS <<< "$BIGQUERY_DATASETS"
    for dataset in "${DATASETS[@]}"; do
        dataset=$(echo "$dataset" | xargs)
        if [ ! -z "$dataset" ]; then
            MCP_CMD="$MCP_CMD --dataset $dataset"
        fi
    done
fi

if [ "$BIGQUERY_USE_OAUTH_FLOW" = "true" ]; then
    MCP_CMD="$MCP_CMD --oauth-flow"
fi

print_info "MCP Command: $MCP_CMD"
print_info "Starting Supergateway..."
print_info "SSE Endpoint: http://localhost:$PORT/sse"
print_info "Message Endpoint: http://localhost:$PORT/message"
echo ""
print_success "Once running, you can test with:"
echo "  curl -N http://localhost:$PORT/sse"
echo ""
print_success "To use with Claude Desktop, add this to your config:"
echo '{
  "mcpServers": {
    "bigquery-local": {
      "command": "npx",
      "args": [
        "-y",
        "supergateway",
        "--sse",
        "http://localhost:'$PORT'/sse"
      ]
    }
  }
}'
echo ""

# Start Supergateway with the MCP server
exec supergateway \
    --stdio "$MCP_CMD" \
    --port $PORT \
    --baseUrl "http://localhost:$PORT" \
    --ssePath "/sse" \
    --messagePath "/message" 
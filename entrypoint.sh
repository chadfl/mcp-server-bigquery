#!/bin/bash

# Entrypoint script for Cloud Run deployment
# This script runs Supergateway wrapping the MCP BigQuery server

set -e

# Default port for Cloud Run
PORT=${PORT:-8080}

# Build the MCP server command with environment variables
echo "DEBUG: Starting entrypoint script"
echo "DEBUG: Current working directory: $(pwd)"
echo "DEBUG: Environment variables:"
env | grep BIGQUERY || echo "No BIGQUERY env vars found"

# Check if entry point script exists, otherwise call main function directly  
if [ -f "/app/.venv/bin/mcp-server-bigquery" ]; then
    MCP_CMD="/app/.venv/bin/mcp-server-bigquery"
    echo "DEBUG: Using entry point script: $MCP_CMD"
else
    echo "DEBUG: Entry point script not found, trying to call main function with arguments"
    # Create a temporary script that calls main with proper argument parsing
    cat > /tmp/run_mcp.py << 'EOF'
import sys
import os
sys.path.insert(0, '/app/.venv/lib/python3.13/site-packages')

# Set up the arguments for mcp_server_bigquery
original_argv = sys.argv[:]
sys.argv = ['mcp-server-bigquery'] + original_argv[1:]

import mcp_server_bigquery
mcp_server_bigquery.main()
EOF
    MCP_CMD="/app/.venv/bin/python /tmp/run_mcp.py"
    echo "DEBUG: Using temporary script: $MCP_CMD"
fi
echo "DEBUG: Testing Python version and module import:"
/app/.venv/bin/python --version
/app/.venv/bin/python -c "import mcp_server_bigquery; print('✅ Module import successful!')" || echo "❌ ERROR: Cannot import module"

# Add project if specified
if [ ! -z "$BIGQUERY_PROJECT" ]; then
    MCP_CMD="$MCP_CMD --project $BIGQUERY_PROJECT"
fi

# Add location if specified
if [ ! -z "$BIGQUERY_LOCATION" ]; then
    MCP_CMD="$MCP_CMD --location $BIGQUERY_LOCATION"
fi

# Add key file if specified
if [ ! -z "$BIGQUERY_KEY_FILE" ]; then
    MCP_CMD="$MCP_CMD --key-file $BIGQUERY_KEY_FILE"
fi

# Add datasets if specified
if [ ! -z "$BIGQUERY_DATASETS" ]; then
    # Split comma-separated datasets and add each one
    IFS=',' read -ra DATASETS <<< "$BIGQUERY_DATASETS"
    for dataset in "${DATASETS[@]}"; do
        dataset=$(echo "$dataset" | xargs)  # trim whitespace
        if [ ! -z "$dataset" ]; then
            MCP_CMD="$MCP_CMD --dataset $dataset"
        fi
    done
fi

# Add OAuth flow if specified
if [ "$BIGQUERY_USE_OAUTH_FLOW" = "true" ]; then
    MCP_CMD="$MCP_CMD --oauth-flow"
fi

echo "Starting MCP BigQuery Server with Supergateway..."
echo "MCP Command: $MCP_CMD"
echo "Port: $PORT"
echo "SSE Endpoint: http://localhost:$PORT/sse"
echo "Message Endpoint: http://localhost:$PORT/message"

# Start Supergateway with the MCP server
exec supergateway \
    --stdio "$MCP_CMD" \
    --port $PORT \
    --baseUrl "http://0.0.0.0:$PORT" \
    --ssePath "/sse" \
    --messagePath "/message" 
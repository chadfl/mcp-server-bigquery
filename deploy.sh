#!/bin/bash

# Deployment script for MCP BigQuery Server on Google Cloud Run
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}
SERVICE_NAME="mcp-bigquery-server"
REGION=${GOOGLE_CLOUD_REGION:-"us-central1"}
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Functions
print_error() {
    echo -e "${RED}ERROR: $1${NC}" >&2
}

print_success() {
    echo -e "${GREEN}SUCCESS: $1${NC}"
}

print_info() {
    echo -e "${YELLOW}INFO: $1${NC}"
}

# Validate prerequisites
if [ -z "$PROJECT_ID" ]; then
    print_error "PROJECT_ID is not set. Please set GOOGLE_CLOUD_PROJECT environment variable or configure gcloud."
    exit 1
fi

print_info "Deploying MCP BigQuery Server to Google Cloud Run"
print_info "Project ID: $PROJECT_ID"
print_info "Service Name: $SERVICE_NAME"
print_info "Region: $REGION"
print_info "Image: $IMAGE_NAME"

# Prompt for required configuration
echo ""
print_info "Please provide the following configuration:"

# BigQuery Project
read -p "BigQuery Project ID (default: $PROJECT_ID): " BIGQUERY_PROJECT
BIGQUERY_PROJECT=${BIGQUERY_PROJECT:-$PROJECT_ID}

# BigQuery Location
read -p "BigQuery Location (default: US): " BIGQUERY_LOCATION
BIGQUERY_LOCATION=${BIGQUERY_LOCATION:-"US"}

# Optional datasets filter
read -p "Datasets to include (comma-separated, leave empty for all): " BIGQUERY_DATASETS

# Authentication method
echo ""
print_info "Authentication method:"
echo "1. Default Application Credentials (recommended for Cloud Run)"
echo "2. OAuth Flow (requires client secrets setup)"
read -p "Choose authentication method (1 or 2, default: 1): " AUTH_METHOD
AUTH_METHOD=${AUTH_METHOD:-1}

# Enable required APIs
print_info "Enabling required Google Cloud APIs..."
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    containerregistry.googleapis.com \
    bigquery.googleapis.com \
    --project=$PROJECT_ID

# Build the Docker image
print_info "Building Docker image..."
gcloud builds submit \
    --config=cloudbuild.yaml \
    --substitutions=_IMAGE_NAME=$IMAGE_NAME \
    --project=$PROJECT_ID \
    .

if [ $? -ne 0 ]; then
    print_error "Docker build failed"
    exit 1
fi

print_success "Docker image built successfully"

# Prepare environment variables
ENV_VARS="BIGQUERY_PROJECT=$BIGQUERY_PROJECT,BIGQUERY_LOCATION=$BIGQUERY_LOCATION"

if [ ! -z "$BIGQUERY_DATASETS" ]; then
    ENV_VARS="$ENV_VARS,BIGQUERY_DATASETS=$BIGQUERY_DATASETS"
fi

if [ "$AUTH_METHOD" = "2" ]; then
    ENV_VARS="$ENV_VARS,BIGQUERY_USE_OAUTH_FLOW=true"
    print_info "OAuth flow selected. Make sure to provide client secrets via Secret Manager or environment variables."
fi

# Deploy to Cloud Run
print_info "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --set-env-vars "$ENV_VARS" \
    --timeout 3600s \
    --concurrency 1000 \
    --min-instances 0 \
    --max-instances 100 \
    --cpu 1 \
    --memory 512Mi \
    --port 8080 \
    --project=$PROJECT_ID

if [ $? -ne 0 ]; then
    print_error "Cloud Run deployment failed"
    exit 1
fi

# Get the service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --platform managed \
    --region $REGION \
    --project=$PROJECT_ID \
    --format 'value(status.url)')

print_success "Deployment completed successfully!"
echo ""
print_info "Service Details:"
echo "  Service URL: $SERVICE_URL"
echo "  SSE Endpoint: $SERVICE_URL/sse"
echo "  Message Endpoint: $SERVICE_URL/message"
echo ""
print_info "To use with ChatGPT or Claude Desktop, use this configuration:"
echo '{
  "mcpServers": {
    "bigquery": {
      "command": "npx",
      "args": [
        "-y",
        "supergateway",
        "--sse",
        "'$SERVICE_URL'/sse"
      ]
    }
  }
}'
echo ""
print_info "To test the deployment:"
echo "curl -N $SERVICE_URL/sse" 
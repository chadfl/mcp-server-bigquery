# BigQuery MCP server

[![smithery badge](https://smithery.ai/badge/mcp-server-bigquery)](https://smithery.ai/server/mcp-server-bigquery)

A Model Context Protocol server that provides access to BigQuery. This server enables LLMs to inspect database schemas and execute queries.

## Components

### Tools

The server implements these tools:

- `execute-query`: Executes a SQL query using BigQuery dialect
- `list-tables`: Lists all tables in the BigQuery database
- `describe-table`: Describes the schema of a specific table
- `reauth-oauth`: Re-authenticate using OAuth flow with fresh credentials (only available when using `--oauth-flow`)

## Configuration

The server can be configured either with command line arguments or environment variables.

| Argument       | Environment Variable | Required | Description                                                                                                                                                                                                                                                                                                                                                    |
| -------------- | -------------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--project`    | `BIGQUERY_PROJECT`   | Yes      | The GCP project ID.                                                                                                                                                                                                                                                                                                                                            |
| `--location`   | `BIGQUERY_LOCATION`  | Yes      | The GCP location (e.g. `europe-west9`).                                                                                                                                                                                                                                                                                                                        |
| `--dataset`    | `BIGQUERY_DATASETS`  | No       | Only take specific BigQuery datasets into consideration. Several datasets can be specified by repeating the argument (e.g. `--dataset my_dataset_1 --dataset my_dataset_2`) or by joining them with a comma in the environment variable (e.g. `BIGQUERY_DATASETS=my_dataset_1,my_dataset_2`). If not provided, all datasets in the project will be considered. |
| `--key-file`   | `BIGQUERY_KEY_FILE`  | No       | Path to a service account key file for BigQuery. If not provided, the server will use the default credentials.                                                                                                                                                                                                                                                 |
| `--oauth-flow` | N/A                  | No       | Use OAuth flow for authentication instead of service account. When enabled, opens a browser for user authentication. Requires OAuth2 client credentials file.                                                                                                                                                                                                |

## Authentication

### OAuth Flow Authentication

To use OAuth flow authentication instead of service account credentials:

1. **Create OAuth2 Credentials in YOUR Google Cloud Console:**
   - Go to the [Google Cloud Console](https://console.cloud.google.com/) for **your project**
   - Navigate to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth 2.0 Client IDs"
   - Select "Desktop application" as the application type
   - Download the JSON credentials file

2. **Set up the credentials file:**
   - Save the downloaded file as `client_secrets.json` in your working directory
   - Or set the `GOOGLE_CLIENT_SECRETS_FILE` environment variable to point to your file
   - **Important**: This file contains YOUR credentials for YOUR project - never share it

3. **Optional: Configure token storage:**
   - Set `GOOGLE_TOKEN_FILE` environment variable to specify where to save the refresh token (default: `token.json`)

4. **Run with OAuth flow:**
   ```bash
   mcp-server-bigquery --project YOUR_PROJECT --location YOUR_LOCATION --oauth-flow
   ```

When using `--oauth-flow`, the server will:
- Open your default browser for Google OAuth authentication
- Save the refresh token for future use (no need to re-authenticate)
- Automatically refresh expired tokens

**Re-authentication**: Use the `reauth-oauth` tool when you need to:
- Switch to a different Google account
- Refresh permissions after role changes
- Fix authentication issues
- Force a fresh OAuth flow

**Note**: Each user creates their own OAuth credentials for their own Google Cloud project and BigQuery data. No credentials are shared between users.

### For Public Distribution

This MCP server is designed to be used by anyone with their own Google Cloud project:

1. **No credentials are included** in the server distribution
2. **Each user** creates their own OAuth credentials for their own project
3. **Each user** connects to their own BigQuery data
4. **OAuth tokens are stored locally** on each user's machine

This ensures:
- ✅ Complete data privacy and security
- ✅ Each user only accesses their own data
- ✅ No shared credentials or security risks
- ✅ Easy setup for any Google Cloud project

### Service Account Authentication

Use service account credentials by providing the `--key-file` argument or setting `GOOGLE_APPLICATION_CREDENTIALS` environment variable.

## Cloud Run Deployment

Deploy the MCP BigQuery server to Google Cloud Run for multi-user access via ChatGPT and Claude Desktop. This setup uses [Supergateway](https://github.com/supercorp-ai/supergateway) to convert the stdio MCP server to HTTP SSE.

### Quick Deploy

1. **Prerequisites:**
   ```bash
   # Install Google Cloud CLI
   # https://cloud.google.com/sdk/docs/install
   
   # Authenticate and set project
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

2. **Deploy with automated script:**
   ```bash
   ./deploy.sh
   ```
   The script will prompt you for configuration and handle the entire deployment process.

### Manual Deployment

1. **Build and deploy the Docker image:**
   ```bash
   # Set your project ID
   export PROJECT_ID=your-gcp-project-id
   export SERVICE_NAME=mcp-bigquery-server
   export REGION=us-central1
   
   # Build the image
   gcloud builds submit \
     --tag gcr.io/$PROJECT_ID/$SERVICE_NAME \
     --file Dockerfile.cloudrun
   
   # Deploy to Cloud Run
   gcloud run deploy $SERVICE_NAME \
     --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
     --platform managed \
     --region $REGION \
     --allow-unauthenticated \
     --set-env-vars "BIGQUERY_PROJECT=$PROJECT_ID,BIGQUERY_LOCATION=US" \
     --timeout 3600s \
     --concurrency 1000 \
     --port 8080
   ```

2. **Get the service URL:**
   ```bash
   gcloud run services describe $SERVICE_NAME \
     --platform managed \
     --region $REGION \
     --format 'value(status.url)'
   ```

### Usage with AI Clients

Once deployed, you can use the service with various AI clients:

#### ChatGPT/Claude Desktop Configuration

```json
{
  "mcpServers": {
    "bigquery": {
      "command": "npx",
      "args": [
        "-y",
        "supergateway",
        "--sse",
        "https://your-service-url.run.app/sse"
      ]
    }
  }
}
```

#### Testing the Deployment

```bash
# Test SSE endpoint
curl -N https://your-service-url.run.app/sse

# Test with Supergateway locally
npx -y supergateway --sse "https://your-service-url.run.app/sse"
```

### Environment Variables for Cloud Run

Configure the following environment variables in your Cloud Run service:

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `BIGQUERY_PROJECT` | Yes | GCP project ID | `my-project-123` |
| `BIGQUERY_LOCATION` | Yes | BigQuery location | `US` or `europe-west1` |
| `BIGQUERY_DATASETS` | No | Comma-separated list of datasets | `dataset1,dataset2` |
| `BIGQUERY_USE_OAUTH_FLOW` | No | Enable OAuth flow | `true` |
| `GOOGLE_CLIENT_SECRETS_FILE` | OAuth only | Client secrets for OAuth | `client_secrets.json` |

### Authentication for Cloud Run

**Recommended: Default Application Credentials**
- Use Cloud Run's default service account
- Grant BigQuery permissions to the service account
- No additional configuration needed

**Advanced: OAuth Flow**
- Set `BIGQUERY_USE_OAUTH_FLOW=true`
- Provide client secrets via Secret Manager or environment variables
- Each user authenticates individually

### Scaling and Performance

The Cloud Run configuration supports:
- **Auto-scaling**: 0-100 instances based on demand
- **Concurrency**: Up to 1000 concurrent connections per instance
- **Timeout**: 1 hour for long-running queries
- **Resources**: 1-2 CPU cores, 512Mi-2Gi memory

### Monitoring and Logs

```bash
# View logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME" \
  --project=$PROJECT_ID \
  --limit=50 \
  --format="table(timestamp,textPayload)"

# Monitor metrics
gcloud monitoring metrics list --filter="resource.type=cloud_run_revision"
```

## Quickstart

### Install

#### Installing via Smithery

To install BigQuery Server for Claude Desktop automatically via [Smithery](https://smithery.ai/server/mcp-server-bigquery):

```bash
npx -y @smithery/cli install mcp-server-bigquery --client claude
```

#### Claude Desktop

On MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`
On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

##### Development/Unpublished Servers Configuration</summary>

**Service Account Authentication:**
```json
"mcpServers": {
  "bigquery": {
    "command": "uv",
    "args": [
      "--directory",
      "{{PATH_TO_REPO}}",
      "run",
      "mcp-server-bigquery",
      "--project",
      "{{GCP_PROJECT_ID}}",
      "--location",
      "{{GCP_LOCATION}}"
    ]
  }
}
```

**OAuth Flow Authentication:**
```json
"mcpServers": {
  "bigquery": {
    "command": "uv",
    "args": [
      "--directory",
      "{{PATH_TO_REPO}}",
      "run",
      "mcp-server-bigquery",
      "--project",
      "{{GCP_PROJECT_ID}}",
      "--location",
      "{{GCP_LOCATION}}",
      "--oauth-flow"
    ]
  }
}
```

##### Published Servers Configuration

**Service Account Authentication:**
```json
"mcpServers": {
  "bigquery": {
    "command": "uvx",
    "args": [
      "mcp-server-bigquery",
      "--project",
      "{{GCP_PROJECT_ID}}",
      "--location",
      "{{GCP_LOCATION}}"
    ]
  }
}
```

**OAuth Flow Authentication:**
```json
"mcpServers": {
  "bigquery": {
    "command": "uvx",
    "args": [
      "mcp-server-bigquery",
      "--project",
      "{{GCP_PROJECT_ID}}",
      "--location",
      "{{GCP_LOCATION}}",
      "--oauth-flow"
    ]
  }
}
```

Replace `{{PATH_TO_REPO}}`, `{{GCP_PROJECT_ID}}`, and `{{GCP_LOCATION}}` with the appropriate values.

## Development

### Building and Publishing

To prepare the package for distribution:

1. Increase the version number in `pyproject.toml`

2. Sync dependencies and update lockfile:

```bash
uv sync
```

3. Build package distributions:

```bash
uv build
```

This will create source and wheel distributions in the `dist/` directory.

4. Publish to PyPI:

```bash
uv publish
```

Note: You'll need to set PyPI credentials via environment variables or command flags:

- Token: `--token` or `UV_PUBLISH_TOKEN`
- Or username/password: `--username`/`UV_PUBLISH_USERNAME` and `--password`/`UV_PUBLISH_PASSWORD`

### Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging
experience, we strongly recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).

You can launch the MCP Inspector via [`npm`](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) with this command:

```bash
npx @modelcontextprotocol/inspector uv --directory {{PATH_TO_REPO}} run mcp-server-bigquery
```

Upon launching, the Inspector will display a URL that you can access in your browser to begin debugging.

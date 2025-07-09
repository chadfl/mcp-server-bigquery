from google.cloud import bigquery
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os
import logging
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
from typing import Any, Optional

# Set up logging to both stdout and file
logger = logging.getLogger('mcp_bigquery_server')
handler_stdout = logging.StreamHandler()
handler_file = logging.FileHandler('/tmp/mcp_bigquery_server.log')

# Set format for both handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler_stdout.setFormatter(formatter)
handler_file.setFormatter(formatter)

# Add both handlers to logger
logger.addHandler(handler_stdout)
logger.addHandler(handler_file)

# Set overall logging level
logger.setLevel(logging.DEBUG)

logger.info("Starting MCP BigQuery Server")

class BigQueryDatabase:
    def __init__(self, project: str, location: str, key_file: Optional[str], datasets_filter: list[str], use_oauth_flow: bool = False):
        """Initialize a BigQuery database client"""
        logger.info(f"Initializing BigQuery client for project: {project}, location: {location}, use_oauth_flow: {use_oauth_flow}")
        if not project:
            raise ValueError("Project is required")
        if not location:
            raise ValueError("Location is required")
        
        # Store these for potential reauth
        self.project = project
        self.location = location
        self.key_file = key_file
        self.datasets_filter = datasets_filter
        self.use_oauth_flow = use_oauth_flow
        
        credentials = None
        
        if use_oauth_flow:
            logger.info("Using OAuth flow for authentication")
            credentials = self._get_oauth_credentials()
        elif key_file:
            logger.info("Using service account credentials from key file")
            try:
                credentials_path = key_file
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
            except Exception as e:
                logger.error(f"Error loading service account credentials: {e}")
                raise ValueError(f"Invalid key file: {e}")
        else:
            logger.info("Using default credentials (Application Default Credentials)")

        self.client = bigquery.Client(credentials=credentials, project=project, location=location)
        self.datasets_filter = datasets_filter

    def _get_oauth_credentials(self):
        """Get OAuth2 credentials using installed app flow"""
        # Define the scope for BigQuery access
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        
        # Check if we have client secrets (file path or JSON content)
        client_secrets_env = os.environ.get('GOOGLE_CLIENT_SECRETS_FILE', 'client_secrets.json')
        
        flow = None
        
        # Try to determine if it's a file path or JSON content
        if os.path.exists(client_secrets_env):
            # It's a file path
            logger.info(f"Using client secrets from file: {client_secrets_env}")
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secrets_env, 
                scopes=scopes
            )
        else:
            # Try to parse as JSON content
            try:
                import json
                client_secrets_data = json.loads(client_secrets_env)
                logger.info("Using client secrets from JSON content in environment variable")
                flow = InstalledAppFlow.from_client_config(
                    client_secrets_data,
                    scopes=scopes
                )
            except json.JSONDecodeError:
                # Not valid JSON, assume it's a file path that doesn't exist
                logger.error(f"Client secrets file not found and content is not valid JSON: {client_secrets_env}")
                raise ValueError(
                    f"OAuth flow requires client secrets. Please:\n"
                    f"1. Go to Google Cloud Console\n"
                    f"2. Create OAuth2 credentials (Desktop application type)\n"
                    f"3. Either:\n"
                    f"   a) Download the JSON file and save it as '{client_secrets_env}'\n"
                    f"   b) Set GOOGLE_CLIENT_SECRETS_FILE environment variable to the JSON file path\n"
                    f"   c) Set GOOGLE_CLIENT_SECRETS_FILE environment variable to the JSON content directly"
                )
        
        # Check if we have saved credentials
        token_file = os.environ.get('GOOGLE_TOKEN_FILE', 'token.json')
        credentials = None
        
        if os.path.exists(token_file):
            logger.info(f"Loading saved credentials from {token_file}")
            try:
                import json
                with open(token_file, 'r') as f:
                    token_data = json.load(f)
                credentials = flow.credentials
                credentials.token = token_data.get('token')
                credentials.refresh_token = token_data.get('refresh_token')
                credentials.token_uri = token_data.get('token_uri')
                credentials.client_id = token_data.get('client_id')
                credentials.client_secret = token_data.get('client_secret')
                credentials.scopes = token_data.get('scopes')
            except Exception as e:
                logger.warning(f"Error loading saved credentials: {e}")
                credentials = None
        
        # If credentials are not available or invalid, initiate OAuth flow
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                logger.info("Refreshing expired credentials")
                credentials.refresh(Request())
            else:
                logger.info("Starting OAuth flow - your browser will open for authentication")
                credentials = flow.run_local_server(port=0)
            
            # Save credentials for future use
            logger.info(f"Saving credentials to {token_file}")
            try:
                import json
                token_data = {
                    'token': credentials.token,
                    'refresh_token': credentials.refresh_token,
                    'token_uri': credentials.token_uri,
                    'client_id': credentials.client_id,
                    'client_secret': credentials.client_secret,
                    'scopes': credentials.scopes
                }
                with open(token_file, 'w') as f:
                    json.dump(token_data, f)
            except Exception as e:
                logger.warning(f"Error saving credentials: {e}")
        
        return credentials

    def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a SQL query and return results as a list of dictionaries"""
        logger.debug(f"Executing query: {query}")
        try:
            if params:
                job = self.client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params))
            else:
                job = self.client.query(query)
                
            results = job.result()
            rows = [dict(row.items()) for row in results]
            logger.debug(f"Query returned {len(rows)} rows")
            return rows
        except Exception as e:
            logger.error(f"Database error executing query: {e}")
            raise
    
    def list_tables(self) -> list[str]:
        """List all tables in the BigQuery database"""
        logger.debug("Listing all tables")

        if self.datasets_filter:
            datasets = [self.client.dataset(dataset) for dataset in self.datasets_filter]
        else:
            datasets = list(self.client.list_datasets())

        logger.debug(f"Found {len(datasets)} datasets")

        tables = []
        for dataset in datasets:
            dataset_tables = self.client.list_tables(dataset.dataset_id)
            tables.extend([
                f"{dataset.dataset_id}.{table.table_id}" for table in dataset_tables
            ])

        logger.debug(f"Found {len(tables)} tables")
        return tables

    def describe_table(self, table_name: str) -> list[dict[str, Any]]:
        """Describe a table in the BigQuery database"""
        logger.debug(f"Describing table: {table_name}")

        parts = table_name.split(".")
        if len(parts) != 2 and len(parts) != 3:
            raise ValueError(f"Invalid table name: {table_name}")

        dataset_id = ".".join(parts[:-1])
        table_id = parts[-1]

        query = f"""
            SELECT ddl
            FROM {dataset_id}.INFORMATION_SCHEMA.TABLES
            WHERE table_name = @table_name;
        """
        return self.execute_query(query, params=[
            bigquery.ScalarQueryParameter("table_name", "STRING", table_id),
        ])

    def reauth_oauth(self) -> str:
        """Re-authenticate using OAuth flow by deleting saved tokens and forcing new authentication"""
        if not self.use_oauth_flow:
            raise ValueError("OAuth re-authentication is only available when using --oauth-flow")
        
        logger.info("Starting OAuth re-authentication")
        
        # Delete saved token file to force new authentication
        token_file = os.environ.get('GOOGLE_TOKEN_FILE', 'token.json')
        if os.path.exists(token_file):
            try:
                os.remove(token_file)
                logger.info(f"Removed saved credentials from {token_file}")
            except Exception as e:
                logger.warning(f"Error removing token file: {e}")
        
        try:
            # Force new OAuth flow
            credentials = self._get_oauth_credentials()
            
            # Create new BigQuery client with fresh credentials
            self.client = bigquery.Client(credentials=credentials, project=self.project, location=self.location)
            
            # Test the connection
            list(self.client.list_datasets(max_results=1))
            
            logger.info("OAuth re-authentication successful")
            return "✅ OAuth re-authentication successful! You are now connected with fresh credentials."
            
        except Exception as e:
            logger.error(f"OAuth re-authentication failed: {e}")
            raise ValueError(f"OAuth re-authentication failed: {e}")

async def main(project: str, location: str, key_file: Optional[str], datasets_filter: list[str], use_oauth_flow: bool = False):
    logger.info(f"Starting BigQuery MCP Server with project: {project}, location: {location}, oauth_flow: {use_oauth_flow}")

    db = BigQueryDatabase(project, location, key_file, datasets_filter, use_oauth_flow)
    server = Server("bigquery-manager")

    # Register handlers
    logger.debug("Registering handlers")

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        """List available tools"""
        return [
            types.Tool(
                name="execute-query",
                description="Execute a SELECT query on the BigQuery database",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "SELECT SQL query to execute using BigQuery dialect"},
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="list-tables",
                description="List all tables in the BigQuery database",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            types.Tool(
                name="describe-table",
                description="Get the schema information for a specific table",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "table_name": {"type": "string", "description": "Name of the table to describe (e.g. my_dataset.my_table)"},
                    },
                    "required": ["table_name"],
                },
            ),
            types.Tool(
                name="reauth-oauth",
                description="Re-authenticate using OAuth flow with fresh credentials. This will open your browser for authentication and is useful for switching Google accounts or refreshing permissions. Only available when using --oauth-flow.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """Handle tool execution requests"""
        logger.debug(f"Handling tool execution request: {name}")

        try:
            if name == "list-tables":
                results = db.list_tables()
                return [types.TextContent(type="text", text=str(results))]

            elif name == "describe-table":
                if not arguments or "table_name" not in arguments:
                    raise ValueError("Missing table_name argument")
                results = db.describe_table(arguments["table_name"])
                return [types.TextContent(type="text", text=str(results))]

            elif name == "execute-query":
                results = db.execute_query(arguments["query"])
                return [types.TextContent(type="text", text=str(results))]

            elif name == "reauth-oauth":
                result = db.reauth_oauth()
                return [types.TextContent(type="text", text=result)]

            else:
                raise ValueError(f"Unknown tool: {name}")
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        logger.info("Server running with stdio transport")
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="bigquery",
                server_version="0.3.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

# Extending the Incident Resolution System

Guide for adding custom tools and agents (Slack, Terraform, GitHub PR, etc.)

## Architecture

The Incident Resolution System uses **Claude Agent SDK** which supports:
- **Built-in tools**: Bash, Read, Write, Edit, Grep, Glob
- **MCP tools**: Custom tools via Model Context Protocol
- **Dynamic agent registration**: Add new agent types at runtime

## Adding Custom MCP Tools

### Example 1: Slack Integration

Create a Slack MCP tool to send notifications and get approvals:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server
import httpx

@tool("slack_send", "Send message to Slack channel", {"channel": str, "message": str})
async def slack_send(args):
    """Send message to Slack"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {os.getenv('SLACK_TOKEN')}"},
            json={
                "channel": args["channel"],
                "text": args["message"]
            }
        )
        return {
            "content": [{
                "type": "text",
                "text": f"Message sent to #{args['channel']}"
            }]
        }

@tool("slack_get_thread", "Get Slack thread messages", {"channel": str, "thread_ts": str})
async def slack_get_thread(args):
    """Get messages from a Slack thread"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://slack.com/api/conversations.replies",
            headers={"Authorization": f"Bearer {os.getenv('SLACK_TOKEN')}"},
            params={
                "channel": args["channel"],
                "ts": args["thread_ts"]
            }
        )
        messages = response.json().get("messages", [])
        return {
            "content": [{
                "type": "text",
                "text": f"Found {len(messages)} messages in thread"
            }]
        }

# Create Slack MCP server
slack_server = create_sdk_mcp_server(
    name="slack",
    version="1.0.0",
    tools=[slack_send, slack_get_thread]
)
```

### Example 2: Terraform Integration

Create Terraform MCP tool for infrastructure changes:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server
import subprocess

@tool("terraform_plan", "Run terraform plan", {"directory": str})
async def terraform_plan(args):
    """Run terraform plan"""
    result = subprocess.run(
        ["terraform", "plan"],
        cwd=args["directory"],
        capture_output=True,
        text=True
    )
    return {
        "content": [{
            "type": "text",
            "text": f"Terraform plan output:\n{result.stdout}"
        }]
    }

@tool("terraform_apply", "Apply terraform changes", {"directory": str, "auto_approve": bool})
async def terraform_apply(args):
    """Apply terraform changes"""
    cmd = ["terraform", "apply"]
    if args.get("auto_approve"):
        cmd.append("-auto-approve")

    result = subprocess.run(
        cmd,
        cwd=args["directory"],
        capture_output=True,
        text=True
    )
    return {
        "content": [{
            "type": "text",
            "text": f"Terraform apply result:\n{result.stdout}"
        }]
    }

terraform_server = create_sdk_mcp_server(
    name="terraform",
    version="1.0.0",
    tools=[terraform_plan, terraform_apply]
)
```

### Example 3: GitHub PR Integration

Create GitHub MCP tool for PR analysis:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server
import httpx

@tool("github_get_pr", "Get GitHub PR details", {"repo": str, "pr_number": int})
async def github_get_pr(args):
    """Get PR details"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.github.com/repos/{args['repo']}/pulls/{args['pr_number']}",
            headers={"Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"}
        )
        pr = response.json()
        return {
            "content": [{
                "type": "text",
                "text": f"PR #{pr['number']}: {pr['title']}\nStatus: {pr['state']}\nFiles changed: {pr['changed_files']}"
            }]
        }

@tool("github_get_pr_files", "Get PR file changes", {"repo": str, "pr_number": int})
async def github_get_pr_files(args):
    """Get files changed in PR"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.github.com/repos/{args['repo']}/pulls/{args['pr_number']}/files",
            headers={"Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"}
        )
        files = response.json()
        return {
            "content": [{
                "type": "text",
                "text": f"Files changed: {', '.join([f['filename'] for f in files])}"
            }]
        }

github_server = create_sdk_mcp_server(
    name="github",
    version="1.0.0",
    tools=[github_get_pr, github_get_pr_files]
)
```

## Registering Custom Agents

### Step 1: Create Custom Agent with MCP Tools

```python
from src.incident_resolver.remediation_executor import RemediationExecutor

# Initialize executor
executor = RemediationExecutor(
    use_bedrock=True,
    aws_region="us-east-1"
)

# Register Slack notification agent
await executor.create_custom_tool_agent(
    action_type="slack_notify",
    custom_tools=["Bash", "Read", "mcp__slack__slack_send", "mcp__slack__slack_get_thread"],
    description="Send Slack notifications and get team approval",
    model="haiku",  # Fast and cheap for notifications
    permission_mode="default"
)

# Register Terraform remediation agent
await executor.create_custom_tool_agent(
    action_type="terraform_fix",
    custom_tools=["Read", "Write", "Bash", "mcp__terraform__terraform_plan", "mcp__terraform__terraform_apply"],
    description="Fix infrastructure issues with Terraform",
    model="sonnet",  # Complex infrastructure changes
    permission_mode="acceptEdits"
)

# Register GitHub PR analysis agent
await executor.create_custom_tool_agent(
    action_type="github_pr_analysis",
    custom_tools=["Read", "Grep", "Glob", "mcp__github__github_get_pr", "mcp__github__github_get_pr_files"],
    description="Analyze GitHub PRs for incident correlation",
    model="sonnet",
    permission_mode="default"  # Read-only
)
```

### Step 2: Update API to Use Custom Agent

```python
# In api.py - add MCP servers to options
from claude_agent_sdk import ClaudeAgentOptions

# When initializing remediation executor, pass MCP servers
options = ClaudeAgentOptions(
    mcp_servers={
        "slack": slack_server,
        "terraform": terraform_server,
        "github": github_server
    }
)
```

### Step 3: Use Custom Agent

```python
# Call the custom agent via API
curl -X POST http://localhost:8084/api/v1/incident/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "loc-01",
    "namespace": "production",
    "action_type": "slack_notify",
    "action_description": "Notify #incidents channel about the outage and get approval for emergency scaling"
  }'
```

## Complete Example: Adding Datadog Integration

### 1. Create Datadog MCP Tool

```python
# src/incident_resolver/tools/datadog_tool.py

from claude_agent_sdk import tool, create_sdk_mcp_server
import httpx
import os

@tool("datadog_get_metrics", "Get Datadog metrics", {
    "metric": str,
    "start": int,  # Unix timestamp
    "end": int,    # Unix timestamp
    "tags": str    # Optional: "env:prod,service:api"
})
async def datadog_get_metrics(args):
    """Get metrics from Datadog"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.datadoghq.com/api/v1/query",
            headers={
                "DD-API-KEY": os.getenv("DATADOG_API_KEY"),
                "DD-APPLICATION-KEY": os.getenv("DATADOG_APP_KEY")
            },
            params={
                "query": args["metric"],
                "from": args["start"],
                "to": args["end"]
            }
        )
        data = response.json()
        return {
            "content": [{
                "type": "text",
                "text": f"Metric data: {data}"
            }]
        }

@tool("datadog_get_logs", "Search Datadog logs", {
    "query": str,
    "from": int,
    "to": int,
    "limit": int
})
async def datadog_get_logs(args):
    """Search logs in Datadog"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.datadoghq.com/api/v1/logs-queries/list",
            headers={
                "DD-API-KEY": os.getenv("DATADOG_API_KEY"),
                "DD-APPLICATION-KEY": os.getenv("DATADOG_APP_KEY")
            },
            json={
                "query": args["query"],
                "time": {
                    "from": args["from"],
                    "to": args["to"]
                },
                "limit": args.get("limit", 100)
            }
        )
        logs = response.json()
        return {
            "content": [{
                "type": "text",
                "text": f"Found {len(logs.get('logs', []))} logs"
            }]
        }

# Create MCP server
datadog_server = create_sdk_mcp_server(
    name="datadog",
    version="1.0.0",
    tools=[datadog_get_metrics, datadog_get_logs]
)
```

### 2. Register Datadog Agent

```python
# src/incident_resolver/agents/datadog_agent.py

async def setup_datadog_agent(executor: RemediationExecutor):
    """Setup Datadog correlation agent"""
    await executor.create_custom_tool_agent(
        action_type="datadog_correlate",
        custom_tools=[
            "Bash",
            "Read",
            "Grep",
            "mcp__datadog__datadog_get_metrics",
            "mcp__datadog__datadog_get_logs"
        ],
        description="Correlate Kubernetes incidents with Datadog metrics and logs",
        model="sonnet",
        permission_mode="default"
    )
```

### 3. Use in Workflow

```python
# Example: Correlate incident with Datadog data
curl -X POST http://localhost:8084/api/v1/incident/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "loc-01",
    "namespace": "production",
    "action_type": "datadog_correlate",
    "action_description": "Check Datadog metrics and logs for errors between 10:00 and 10:15",
    "time_window_hours": 0.25
  }'
```

## Tool Naming Convention

When using MCP tools in `allowed_tools`, follow this pattern:

```
mcp__<server_name>__<tool_name>
```

Examples:
- `mcp__slack__slack_send`
- `mcp__terraform__terraform_plan`
- `mcp__github__github_get_pr`
- `mcp__datadog__datadog_get_metrics`

## Permission Modes

Choose the right permission mode for your agent:

| Mode | Use Case |
|------|----------|
| `default` | User approves each tool execution |
| `acceptEdits` | Auto-approve file edits (for config fixes) |
| `plan` | Planning mode - no actual execution |
| `bypassPermissions` | Auto-approve everything (use with caution) |

## Environment Variables

Add tool-specific credentials to `.env`:

```bash
# Slack
SLACK_TOKEN=xoxb-your-slack-token

# Terraform
TF_VAR_region=us-east-1

# GitHub
GITHUB_TOKEN=ghp_your-github-token

# Datadog
DATADOG_API_KEY=your-api-key
DATADOG_APP_KEY=your-app-key
```

## Testing Custom Tools

Test your custom tools before production:

```python
import asyncio
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

async def test_custom_tool():
    options = ClaudeAgentOptions(
        mcp_servers={"slack": slack_server},
        allowed_tools=["mcp__slack__slack_send"],
        permission_mode="default"
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query("Send a test message to #test-channel saying 'Hello from incident resolver'")

        async for message in client.receive_response():
            print(message)

asyncio.run(test_custom_tool())
```

## Future Tool Ideas

Ready-to-implement tool ideas:

1. **PagerDuty**: Create/update incidents, get on-call schedule
2. **Jira**: Create tickets, update status
3. **AWS**: EC2/ECS/Lambda operations
4. **Grafana**: Query dashboards, create annotations
5. **ArgoCD**: Rollback deployments, sync applications
6. **Vault**: Rotate secrets, get credentials
7. **Prometheus**: Query metrics, silence alerts

## Security Considerations

1. **API Keys**: Store in environment variables or secrets manager
2. **Permission Modes**: Use `default` for write operations
3. **Tool Validation**: Validate inputs in tool handlers
4. **Audit Logging**: Log all tool executions
5. **Rate Limiting**: Implement rate limits for external APIs
6. **Error Handling**: Gracefully handle API failures

## Contributing

To add a new tool:

1. Create tool file in `src/incident_resolver/tools/<tool_name>.py`
2. Implement MCP tools with `@tool` decorator
3. Create MCP server with `create_sdk_mcp_server()`
4. Register agent with `create_custom_tool_agent()`
5. Add credentials to `.env.example`
6. Document in this file
7. Test with sample incidents

# Incident Resolution System

AI-powered incident resolution with customer approval and rollback capabilities using Claude Agent SDK.

## Overview

The Incident Resolution System automates remediation actions for Kubernetes incidents while maintaining safety through:
- **Customer approval workflow** for risky actions
- **Rollback snapshots** for undo capability
- **Risk assessment** to classify action severity
- **Token budget management** to prevent runaway costs
- **Claude Agent SDK** for autonomous remediation execution

## Architecture

### Components

1. **ContextGatherer** - Collects incident context from:
   - Root cause analysis API
   - Causal chain API
   - Blast radius API
   - Topology API
   - Health monitoring API
   - Neo4j knowledge graph

2. **RiskAssessor** - Classifies actions by risk level:
   - **LOW**: Read-only operations (kubectl get, describe, logs)
   - **MEDIUM**: Pod restarts, config changes
   - **HIGH**: Scaling operations, multi-resource changes
   - **CRITICAL**: Deletions, cluster-wide operations

3. **ApprovalEngine** - Manages customer approval:
   - Auto-approves LOW risk actions
   - Requires manual approval for MEDIUM+ risk
   - 5-minute timeout (configurable)
   - Approval history tracking

4. **RemediationExecutor** - Executes actions using Claude Agent SDK:
   - **pod_restart**: Haiku model, Bash tool
   - **config_fix**: Sonnet model, Read/Edit/Bash tools
   - **resource_scale**: Haiku model, Bash tool
   - **investigation**: Sonnet model, Read/Bash/Grep/Glob tools

5. **RollbackManager** - Snapshot and undo:
   - Pre-action state capture
   - Rollback command generation
   - Automated rollback execution
   - Dry-run mode for testing

6. **TokenBudgetManager** - Prevents runaway costs:
   - Per-incident limit: 100k tokens (default)
   - Per-agent limit: 50k tokens (default)
   - Real-time tracking and warnings
   - Loop detection (max 10 iterations)

## API Endpoints

### POST `/api/v1/incident/resolve`

Start incident resolution workflow.

**Request:**
```json
{
  "client_id": "loc-01",
  "namespace": "buglab",
  "action_type": "pod_restart",
  "action_description": "Restart failed nginx pods",
  "event_id": "optional-event-id",
  "time_window_hours": 2.0,
  "auto_approve": false,
  "token_limit": 100000
}
```

**Response (awaiting approval):**
```json
{
  "resolution_id": "uuid",
  "status": "awaiting_approval",
  "approval_id": "uuid",
  "requires_approval": true,
  "risk_level": "MEDIUM",
  "risk_factors": ["Production namespace", "Multiple resources affected (5)"],
  "estimated_impact": "Moderate impact - temporary disruption to 5 resource(s)",
  "mitigation_steps": ["Create rollback snapshot", "Monitor health"],
  "affected_resources": [
    {"kind": "Pod", "name": "nginx-abc", "namespace": "buglab"}
  ]
}
```

### POST `/api/v1/incident/approve/{approval_id}`

Approve or reject a pending resolution.

**Request:**
```json
{
  "approved_by": "user@example.com",
  "decision": "approve",
  "reason": "Approved after review"
}
```

**Response:**
```json
{
  "resolution_id": "uuid",
  "approval_id": "uuid",
  "status": "approved",
  "message": "Resolution approved and executing"
}
```

### POST `/api/v1/incident/rollback`

Rollback a resolution using snapshot.

**Request:**
```json
{
  "snapshot_id": "uuid",
  "dry_run": false
}
```

**Response:**
```json
{
  "snapshot_id": "uuid",
  "dry_run": false,
  "success": true,
  "commands_executed": 3,
  "results": [
    {
      "command": "kubectl apply -f /tmp/rollback_nginx.yaml",
      "status": "success",
      "output": "deployment.apps/nginx configured"
    }
  ],
  "errors": []
}
```

### GET `/api/v1/incident/status/{resolution_id}`

Get status of an incident resolution.

**Response:**
```json
{
  "resolution_id": "uuid",
  "client_id": "loc-01",
  "namespace": "buglab",
  "action_type": "pod_restart",
  "status": "completed",
  "risk_level": "MEDIUM",
  "created_at": "2025-11-01T10:00:00Z",
  "token_usage": {
    "total_tokens": 5234,
    "cost_usd": 0.013,
    "percent_used": 5.2
  },
  "snapshot_id": "uuid",
  "execution_result": {
    "success": true,
    "output": "Pods restarted successfully",
    "commands_executed": ["kubectl delete pod nginx-abc -n buglab"]
  }
}
```

### POST `/api/v1/incident/interrupt/{resolution_id}`

Interrupt a running resolution (safety mechanism).

### GET `/api/v1/incident/pending-approvals`

Get all pending approvals (optionally filter by client_id).

### GET `/api/v1/incident/history`

Get resolution history (optionally filter by client_id).

## Workflow

### 1. Start Resolution
```bash
curl -X POST http://localhost:8084/api/v1/incident/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "loc-01",
    "namespace": "buglab",
    "action_type": "pod_restart",
    "action_description": "Restart failed nginx pods",
    "time_window_hours": 2.0
  }'
```

### 2. Approve Resolution
```bash
curl -X POST http://localhost:8084/api/v1/incident/approve/{approval_id} \
  -H "Content-Type: application/json" \
  -d '{
    "approved_by": "user@example.com",
    "decision": "approve"
  }'
```

### 3. Check Status
```bash
curl http://localhost:8084/api/v1/incident/status/{resolution_id}
```

### 4. Rollback (if needed)
```bash
curl -X POST http://localhost:8084/api/v1/incident/rollback \
  -H "Content-Type: application/json" \
  -d '{
    "snapshot_id": "{snapshot_id}",
    "dry_run": false
  }'
```

## Safety Mechanisms

### Pre-flight Checks
- ✅ Risk assessment and classification
- ✅ Approval required for MEDIUM+ risk
- ✅ Token budget validation
- ✅ Resource validation

### Real-time Monitoring
- ✅ Token usage tracking (per-incident, per-agent)
- ✅ Iteration counter (loop detection)
- ✅ Interrupt capability (manual safety stop)
- ✅ Progress updates

### Post-execution Verification
- ✅ Health checks after changes
- ✅ Rollback snapshot available
- ✅ Execution transcript logging
- ✅ Cost tracking

### Rollback Triggers
- ✅ Customer request (manual rollback)
- ✅ Execution failure (auto-rollback option)
- ✅ Timeout (configurable)
- ✅ Errors or exceptions

## Configuration

### Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-your-key-here
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# Optional
INCIDENT_RESOLVER_TOKEN_LIMIT=100000  # Default: 100k tokens
INCIDENT_RESOLVER_APPROVAL_TIMEOUT=300  # Default: 5 minutes
```

### Token Budget Configuration

```python
# In your code
token_budget_manager = TokenBudgetManager(
    incident_limit=100_000,  # 100k tokens per incident
    agent_limit=50_000       # 50k tokens per agent
)
```

### Risk Assessment Configuration

Modify `risk_assessor.py` to customize risk rules:

```python
ACTION_RISK_MAP = {
    "kubectl get": RiskLevel.LOW,
    "kubectl delete pod": RiskLevel.MEDIUM,
    "kubectl scale": RiskLevel.HIGH,
    "kubectl delete deployment": RiskLevel.CRITICAL
}
```

## Integration with Existing APIs

The incident resolver integrates with existing APIs:

- **Root Causes**: `GET /api/v1/rca/root-causes/{client_id}`
- **Causal Chain**: `GET /api/v1/rca/causal-chain/{event_id}`
- **Blast Radius**: `GET /api/v1/rca/blast-radius/{event_id}`
- **Topology**: `GET /api/v1/catalog/topology/{client_id}/{namespace}/{resource_name}`
- **Health Status**: `GET /api/v1/health/status/{client_id}`
- **Active Incidents**: `GET /api/v1/health/incidents/{client_id}`

## Claude Agent SDK

The remediation executor uses Claude Agent SDK with specialized agents:

### Agent Configurations

| Agent | Model | Tools | Use Case |
|-------|-------|-------|----------|
| pod_restart | Haiku | Bash | Fast pod restarts |
| config_fix | Sonnet | Read, Edit, Bash | Configuration fixes |
| resource_scale | Haiku | Bash | Scaling operations |
| investigation | Sonnet | Read, Bash, Grep, Glob | Read-only diagnostics |

### Model Selection Strategy

- **Haiku**: Simple operations (pod restart, scaling) - fast and cheap
- **Sonnet**: Complex operations (config fixes, investigations) - balanced performance
- **Opus**: Not used (too expensive for operational tasks)

## Testing

### Manual Testing

1. **Test with dry-run rollback**:
```bash
curl -X POST http://localhost:8084/api/v1/incident/rollback \
  -H "Content-Type: application/json" \
  -d '{"snapshot_id": "uuid", "dry_run": true}'
```

2. **Test LOW risk action** (auto-approved):
```json
{
  "action_type": "investigation",
  "action_description": "Investigate pod logs"
}
```

3. **Test MEDIUM risk action** (requires approval):
```json
{
  "action_type": "pod_restart",
  "action_description": "Restart failed pods"
}
```

### Integration Tests

Run integration tests:
```bash
pytest src/incident_resolver/tests/ -v
```

## Cost Estimation

### Token Usage by Action Type

| Action Type | Avg Tokens | Model | Cost per Action |
|-------------|------------|-------|-----------------|
| investigation | 8,000 | Sonnet | ~$0.024 |
| pod_restart | 4,000 | Haiku | ~$0.001 |
| config_fix | 12,000 | Sonnet | ~$0.036 |
| resource_scale | 4,000 | Haiku | ~$0.001 |

### Budget Recommendations

- **Testing**: 10k tokens per incident
- **Production**: 100k tokens per incident
- **Complex investigations**: 200k tokens per incident

## Troubleshooting

### Issue: "Services not initialized"

**Solution**: Ensure `initialize_services()` is called in FastAPI startup:
```python
@app.on_event("startup")
async def startup_event():
    incident_resolver_api.initialize_services(
        neo4j_service=neo4j_service,
        base_url="http://localhost:8084"
    )
```

### Issue: "ANTHROPIC_API_KEY not set"

**Solution**: Set environment variable:
```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### Issue: "Budget exceeded"

**Solution**: Increase token limit:
```json
{
  "token_limit": 200000
}
```

### Issue: "Approval timeout"

**Solution**: Approve within 5 minutes or increase timeout:
```python
approval_engine = ApprovalEngine(default_timeout_seconds=600)  # 10 minutes
```

## Future Enhancements

- [ ] Webhook notifications for approval requests
- [ ] Slack integration for approvals
- [ ] Auto-rollback on failure (configurable)
- [ ] Multi-step remediation workflows
- [ ] Learning from past resolutions (feedback loop)
- [ ] Integration with runbook generation
- [ ] Scheduled maintenance windows
- [ ] Approval delegation and escalation

## Security Considerations

1. **Authentication**: Add API authentication (JWT, OAuth)
2. **Authorization**: Role-based access control (RBAC)
3. **Audit logging**: Log all approval decisions and executions
4. **Secrets management**: Use secrets manager (Vault, AWS Secrets Manager)
5. **Network isolation**: Run in private network with VPN access
6. **Rate limiting**: Prevent abuse with rate limits
7. **Kubectl context**: Use dedicated service account with minimal permissions

## License

Internal use only - Part of AI SRE Platform.

# KGRoot RCA API Integration Guide

How to integrate with Slack and add new connectors.

## Table of Contents

- [Slack Integration](#slack-integration)
- [Adding New Connectors](#adding-new-connectors)
- [Webhook Integration](#webhook-integration)
- [CI/CD Integration](#cicd-integration)
- [Monitoring Integration](#monitoring-integration)

---

## Slack Integration

### Overview

Slack integration enables:
- Real-time incident alerts
- Health status reports
- Interactive commands (future)
- Runbook sharing

### Setup Steps

#### 1. Create Slack App

1. Go to https://api.slack.com/apps
2. Click **"Create New App"** → **"From scratch"**
3. **App Name:** KGRoot RCA Bot
4. **Workspace:** Select your workspace
5. Click **"Create App"**

#### 2. Configure Bot Permissions

1. Go to **"OAuth & Permissions"** in sidebar
2. Scroll to **"Bot Token Scopes"**
3. Add the following scopes:
   - `chat:write` - Send messages as bot
   - `chat:write.public` - Send to public channels without invite
   - `channels:read` - View public channels
   - `users:read` - Read user information
   - `files:write` - Upload files (for runbooks)

#### 3. Install App to Workspace

1. Scroll to top of **"OAuth & Permissions"**
2. Click **"Install to Workspace"**
3. Review permissions
4. Click **"Allow"**
5. Copy **"Bot User OAuth Token"** (starts with `xoxb-`)

#### 4. Configure Environment

Add to `.env`:

```bash
# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-token-here
SLACK_DEFAULT_CHANNEL=#alerts
SLACK_ENABLED=true

# Optional: Multiple channels
SLACK_ALERT_CHANNEL=#alerts
SLACK_HEALTH_CHANNEL=#health-reports
SLACK_RUNBOOK_CHANNEL=#runbooks
```

#### 5. Invite Bot to Channels

In Slack:
```
/invite @KGRoot RCA Bot
```

Do this for all channels you want the bot to post to.

### Usage Examples

#### Send RCA Alert

```python
# Automatic (background task)
@router.post("/rca/analyze")
async def analyze_rca(request: RCARequest, background_tasks: BackgroundTasks):
    result = perform_rca(...)

    # Send alert in background
    if request.send_slack_alert:
        background_tasks.add_task(
            slack_service.send_rca_alert,
            incident_data={
                "title": "RCA Alert",
                "root_cause": result["root_causes"][0]["reason"],
                ...
            }
        )

    return result
```

```bash
# Manual via API
curl -X POST "http://localhost:8000/rca/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Why did nginx pods fail?",
    "client_id": "ab-01",
    "send_slack_alert": true
  }'
```

#### Send Health Report

```bash
curl -X POST "http://localhost:8000/health/send-health-report/ab-01?channel=%23health-reports"
```

### Customizing Slack Messages

#### Edit Slack Service

[src/services/slack_service.py:55-85](src/services/slack_service.py#L55-L85)

```python
def _build_incident_blocks(self, incident_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build Slack blocks for incident alert"""

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🚨 {incident_data.get('title', 'RCA Incident Alert')}"
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Client:* {incident_data.get('client_id', 'N/A')}"},
                {"type": "mrkdwn", "text": f"*Severity:* {incident_data.get('severity', 'Unknown').upper()}"}
            ]
        }
    ]

    # Add custom fields
    if incident_data.get('custom_field'):
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Custom:* {incident_data['custom_field']}"
            }
        })

    return blocks
```

### Slack Message Templates

#### Incident Alert

```json
{
  "blocks": [
    {
      "type": "header",
      "text": {"type": "plain_text", "text": "🚨 RCA Incident Alert"}
    },
    {
      "type": "section",
      "fields": [
        {"type": "mrkdwn", "text": "*Client:* ab-01"},
        {"type": "mrkdwn", "text": "*Severity:* HIGH"}
      ]
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Root Cause:* OOMKilled on Pod/nginx-pod-1"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Affected Resources:*\n• Service/nginx-service\n• Pod/nginx-pod-2"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Remediation:*\n1. Increase memory limit\n2. Restart deployment"
      }
    },
    {
      "type": "actions",
      "elements": [
        {
          "type": "button",
          "text": {"type": "plain_text", "text": "View Details"},
          "url": "https://rca-dashboard.example.com/incidents/12345"
        }
      ]
    }
  ]
}
```

#### Health Report

```json
{
  "blocks": [
    {
      "type": "header",
      "text": {"type": "plain_text", "text": "📊 Health Status Report"}
    },
    {
      "type": "section",
      "fields": [
        {"type": "mrkdwn", "text": "*Client:* ab-01"},
        {"type": "mrkdwn", "text": "*Health:* 95.5%"}
      ]
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Resources:*\n✅ Healthy: 487\n❌ Unhealthy: 23\n📊 Total: 510"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Active Incidents:* 2\n*Top Issues:*\n• OOMKilled: 8 events\n• CrashLoopBackOff: 5 events"
      }
    }
  ]
}
```

### Automated Alerts

#### Schedule Health Reports

Use cron to send daily health reports:

```bash
# /etc/cron.d/kgroot-health-report
0 9 * * * curl -X POST "http://localhost:8000/health/send-health-report/ab-01"
```

#### Trigger on Incidents

Modify RCA endpoint to always send alerts for high severity:

```python
@router.post("/rca/analyze")
async def analyze_rca(request: RCARequest, background_tasks: BackgroundTasks):
    result = perform_rca(...)

    # Auto-alert on high severity
    severity = calculate_severity(result)
    if severity in ["high", "critical"]:
        background_tasks.add_task(
            slack_service.send_rca_alert,
            incident_data={...},
            channel="#critical-alerts"
        )

    return result
```

---

## Adding New Connectors

### Connector Architecture

```
┌─────────────────────────────────────────────┐
│         RCA API (FastAPI)                   │
│                                             │
│  ┌───────────────────────────────────────┐ │
│  │      Service Interface                │ │
│  │  (abstract base class)                │ │
│  └───────────────────────────────────────┘ │
│           │           │           │         │
│           ▼           ▼           ▼         │
│  ┌────────────┐ ┌────────────┐ ┌────────┐ │
│  │   Slack    │ │ PagerDuty  │ │  Jira  │ │
│  │  Service   │ │  Service   │ │Service │ │
│  └────────────┘ └────────────┘ └────────┘ │
└─────────────────────────────────────────────┘
```

### Example: PagerDuty Integration

#### Step 1: Create Service File

Create `src/services/pagerduty_service.py`:

```python
"""
PagerDuty integration for incident creation
"""
import requests
import logging
from typing import Dict, Any, Optional

from ..config import settings

logger = logging.getLogger(__name__)


class PagerDutyService:
    """Service for PagerDuty integration"""

    def __init__(self):
        self.api_key: Optional[str] = None
        self.service_id: Optional[str] = None
        self.base_url = "https://api.pagerduty.com"

    def initialize(self):
        """Initialize PagerDuty client"""
        self.api_key = settings.pagerduty_api_key
        self.service_id = settings.pagerduty_service_id

        if not self.api_key:
            logger.warning("PagerDuty API key not configured")
            return

        logger.info("PagerDuty service initialized successfully")

    def create_incident(
        self,
        title: str,
        description: str,
        severity: str = "high",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Create PagerDuty incident

        Returns:
            Incident ID if successful, None otherwise
        """
        if not self.api_key:
            logger.warning("PagerDuty not configured, skipping incident creation")
            return None

        headers = {
            "Authorization": f"Token token={self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.pagerduty+json;version=2"
        }

        # Map severity
        urgency_map = {
            "critical": "high",
            "high": "high",
            "medium": "low",
            "low": "low"
        }
        urgency = urgency_map.get(severity, "high")

        payload = {
            "incident": {
                "type": "incident",
                "title": title,
                "service": {
                    "id": self.service_id,
                    "type": "service_reference"
                },
                "urgency": urgency,
                "body": {
                    "type": "incident_body",
                    "details": description
                }
            }
        }

        # Add custom fields
        if metadata:
            payload["incident"]["custom_fields"] = metadata

        try:
            response = requests.post(
                f"{self.base_url}/incidents",
                headers=headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()

            incident_id = response.json()["incident"]["id"]
            logger.info(f"PagerDuty incident created: {incident_id}")
            return incident_id

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create PagerDuty incident: {e}")
            return None


# Global PagerDuty service instance
pagerduty_service = PagerDutyService()
```

#### Step 2: Update Configuration

Add to [src/config.py:35](src/config.py#L35):

```python
class Settings(BaseSettings):
    # ... existing settings ...

    # PagerDuty
    pagerduty_api_key: Optional[str] = None
    pagerduty_service_id: Optional[str] = None
    pagerduty_enabled: bool = Field(default=False)
```

Add to `.env`:

```bash
# PagerDuty Configuration
PAGERDUTY_API_KEY=your-api-key
PAGERDUTY_SERVICE_ID=your-service-id
PAGERDUTY_ENABLED=true
```

#### Step 3: Initialize in Main App

Update [src/main.py:25](src/main.py#L25):

```python
from .services.pagerduty_service import pagerduty_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    neo4j_service.connect()
    embedding_service.initialize()
    gpt5_service.initialize()
    slack_service.initialize()
    pagerduty_service.initialize()  # Add this

    # ... rest of startup ...

    yield

    # Shutdown
    neo4j_service.close()
```

#### Step 4: Use in RCA Endpoint

Update [src/api/rca.py:50](src/api/rca.py#L50):

```python
from ..services.pagerduty_service import pagerduty_service

@router.post("/rca/analyze", response_model=RCAResponse)
async def analyze_rca(request: RCARequest, background_tasks: BackgroundTasks):
    # ... perform RCA ...

    # Create PagerDuty incident for high severity
    if severity in ["high", "critical"]:
        background_tasks.add_task(
            pagerduty_service.create_incident,
            title=f"[{severity.upper()}] {root_causes[0]['reason']} in {request.client_id}",
            description=gpt5_analysis["summary"],
            severity=severity,
            metadata={
                "client_id": request.client_id,
                "root_cause": root_causes[0]["reason"],
                "affected_resources": len(affected_resources)
            }
        )

    return response
```

### Example: Jira Integration

#### Create Service

`src/services/jira_service.py`:

```python
"""
Jira integration for ticket creation
"""
from jira import JIRA
import logging
from typing import Dict, Any, Optional

from ..config import settings

logger = logging.getLogger(__name__)


class JiraService:
    """Service for Jira integration"""

    def __init__(self):
        self.client: Optional[JIRA] = None

    def initialize(self):
        """Initialize Jira client"""
        if not settings.jira_url or not settings.jira_token:
            logger.warning("Jira credentials not configured")
            return

        try:
            self.client = JIRA(
                server=settings.jira_url,
                token_auth=settings.jira_token
            )
            logger.info("Jira service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Jira: {e}")

    def create_ticket(
        self,
        title: str,
        description: str,
        priority: str = "High",
        labels: list = None
    ) -> Optional[str]:
        """
        Create Jira ticket

        Returns:
            Ticket key if successful, None otherwise
        """
        if not self.client:
            logger.warning("Jira not configured, skipping ticket creation")
            return None

        issue_dict = {
            "project": {"key": settings.jira_project_key},
            "summary": title,
            "description": description,
            "issuetype": {"name": "Bug"},
            "priority": {"name": priority}
        }

        if labels:
            issue_dict["labels"] = labels

        try:
            issue = self.client.create_issue(fields=issue_dict)
            logger.info(f"Jira ticket created: {issue.key}")
            return issue.key
        except Exception as e:
            logger.error(f"Failed to create Jira ticket: {e}")
            return None


# Global Jira service instance
jira_service = JiraService()
```

#### Add Dependencies

Update `requirements.txt`:

```txt
jira==3.5.0
```

### Example: Email Integration

#### Create Service

`src/services/email_service.py`:

```python
"""
Email notification service
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from typing import List, Optional

from ..config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for email notifications"""

    def __init__(self):
        self.smtp_server: Optional[str] = None
        self.smtp_port: Optional[int] = None
        self.sender: Optional[str] = None
        self.password: Optional[str] = None

    def initialize(self):
        """Initialize email service"""
        self.smtp_server = settings.smtp_server
        self.smtp_port = settings.smtp_port
        self.sender = settings.smtp_sender
        self.password = settings.smtp_password

        if not all([self.smtp_server, self.sender, self.password]):
            logger.warning("Email service not fully configured")
            return

        logger.info("Email service initialized successfully")

    def send_rca_alert(
        self,
        recipients: List[str],
        subject: str,
        body_html: str,
        body_text: str
    ) -> bool:
        """Send RCA alert email"""
        if not self.smtp_server:
            logger.warning("Email not configured, skipping alert")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(recipients)

        # Add text and HTML parts
        part1 = MIMEText(body_text, "plain")
        part2 = MIMEText(body_html, "html")
        msg.attach(part1)
        msg.attach(part2)

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender, self.password)
                server.send_message(msg)

            logger.info(f"Email sent to {len(recipients)} recipients")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


# Global email service instance
email_service = EmailService()
```

---

## Webhook Integration

### Incoming Webhooks (Future)

Receive events from external systems:

```python
# src/api/webhooks.py

from fastapi import APIRouter, Header, HTTPException
import hmac
import hashlib

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/github")
async def github_webhook(
    payload: dict,
    x_hub_signature_256: str = Header(None)
):
    """Receive GitHub webhook events"""

    # Verify signature
    secret = settings.github_webhook_secret.encode()
    signature = hmac.new(
        secret,
        msg=json.dumps(payload).encode(),
        digestmod=hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(f"sha256={signature}", x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Process event
    if payload["action"] == "opened" and "issue" in payload:
        # Trigger RCA for related failures
        issue_title = payload["issue"]["title"]
        # ... perform RCA ...

    return {"status": "received"}
```

### Outgoing Webhooks (Future)

Send events to external systems:

```python
# src/services/webhook_service.py

import requests
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class WebhookService:
    """Service for sending webhooks"""

    def send_incident_webhook(
        self,
        webhook_url: str,
        incident_data: Dict[str, Any]
    ) -> bool:
        """Send incident data to webhook URL"""
        try:
            response = requests.post(
                webhook_url,
                json={
                    "event": "rca.incident.created",
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": incident_data
                },
                timeout=5
            )
            response.raise_for_status()
            logger.info(f"Webhook sent to {webhook_url}")
            return True
        except Exception as e:
            logger.error(f"Webhook failed: {e}")
            return False
```

---

## CI/CD Integration

### GitHub Actions

Trigger RCA analysis on deployment failures:

```yaml
# .github/workflows/rca-on-failure.yml

name: RCA on Deployment Failure

on:
  deployment_status

jobs:
  rca-analysis:
    if: github.event.deployment_status.state == 'failure'
    runs-on: ubuntu-latest

    steps:
      - name: Trigger RCA Analysis
        run: |
          curl -X POST "https://rca-api.example.com/rca/analyze" \
            -H "Content-Type: application/json" \
            -d '{
              "query": "Why did deployment ${{ github.event.deployment.environment }} fail?",
              "client_id": "${{ secrets.CLIENT_ID }}",
              "time_range_hours": 1
            }'
```

### GitLab CI

```yaml
# .gitlab-ci.yml

rca_on_failure:
  stage: post-deploy
  when: on_failure
  script:
    - |
      curl -X POST "${RCA_API_URL}/rca/analyze" \
        -H "Content-Type: application/json" \
        -d "{
          \"query\": \"Why did pipeline ${CI_PIPELINE_ID} fail?\",
          \"client_id\": \"${CLIENT_ID}\"
        }"
```

---

## Monitoring Integration

### Prometheus Metrics (Future)

Expose metrics for monitoring:

```python
# src/api/metrics.py

from prometheus_client import Counter, Histogram, generate_latest
from fastapi import APIRouter

router = APIRouter()

# Metrics
rca_requests_total = Counter("rca_requests_total", "Total RCA requests")
rca_duration_seconds = Histogram("rca_duration_seconds", "RCA request duration")

@router.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type="text/plain"
    )
```

### Grafana Dashboard

Query RCA API for dashboard data:

```json
{
  "dashboard": {
    "title": "KGRoot RCA Metrics",
    "panels": [
      {
        "title": "Health Status",
        "targets": [
          {
            "expr": "http://rca-api:8000/health/status/ab-01"
          }
        ]
      }
    ]
  }
}
```

---

## Best Practices

### Error Handling

Always handle connector failures gracefully:

```python
try:
    slack_service.send_alert(...)
except Exception as e:
    logger.error(f"Slack alert failed: {e}")
    # Don't fail the request
```

### Async Operations

Use background tasks for external calls:

```python
background_tasks.add_task(
    external_service.notify,
    data=...
)
```

### Configuration

Make all connectors configurable:

```python
class Settings(BaseSettings):
    slack_enabled: bool = True
    pagerduty_enabled: bool = False
    jira_enabled: bool = False
```

### Testing

Mock external services in tests:

```python
@pytest.fixture
def mock_slack(monkeypatch):
    def mock_send(*args, **kwargs):
        return True
    monkeypatch.setattr(slack_service, "send_message", mock_send)
```

---

## Next Steps

- [API Reference](API.md) - Explore all endpoints
- [Setup Guide](SETUP.md) - Installation and configuration
- [Examples](EXAMPLES.md) - Real-world usage examples

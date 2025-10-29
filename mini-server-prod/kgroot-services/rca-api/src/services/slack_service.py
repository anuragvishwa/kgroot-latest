"""
Slack integration service
"""
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from typing import Optional, Dict, Any, List
import logging

from ..config import settings

logger = logging.getLogger(__name__)


class SlackService:
    """Service for Slack integrations"""

    def __init__(self):
        self.client: Optional[WebClient] = None
        self.enabled = False

    def initialize(self):
        """Initialize Slack client"""
        if not settings.slack_bot_token:
            logger.warning("Slack bot token not configured, Slack integration disabled")
            return

        try:
            self.client = WebClient(token=settings.slack_bot_token)
            # Test connection
            self.client.auth_test()
            self.enabled = True
            logger.info("Slack service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Slack service: {e}")
            self.enabled = False

    def send_rca_alert(
        self,
        incident_data: Dict[str, Any],
        channel: Optional[str] = None
    ) -> bool:
        """
        Send RCA incident alert to Slack
        """
        if not self.enabled:
            logger.warning("Slack not enabled, skipping alert")
            return False

        channel = channel or settings.slack_channel_alerts

        try:
            # Build Slack blocks for rich formatting
            blocks = self._build_incident_blocks(incident_data)

            response = self.client.chat_postMessage(
                channel=channel,
                blocks=blocks,
                text=incident_data.get('title', 'RCA Incident Alert')  # Fallback text
            )

            logger.info(f"Sent RCA alert to Slack channel {channel}")
            return response["ok"]

        except SlackApiError as e:
            logger.error(f"Failed to send Slack alert: {e.response['error']}")
            return False

    def send_simple_message(
        self,
        message: str,
        channel: Optional[str] = None
    ) -> bool:
        """
        Send simple text message
        """
        if not self.enabled:
            return False

        channel = channel or settings.slack_channel_alerts

        try:
            response = self.client.chat_postMessage(
                channel=channel,
                text=message
            )
            return response["ok"]
        except SlackApiError as e:
            logger.error(f"Failed to send Slack message: {e.response['error']}")
            return False

    def send_health_summary(
        self,
        health_data: Dict[str, Any],
        channel: Optional[str] = None
    ) -> bool:
        """
        Send health status summary
        """
        if not self.enabled:
            return False

        channel = channel or settings.slack_channel_alerts

        try:
            blocks = self._build_health_blocks(health_data)

            response = self.client.chat_postMessage(
                channel=channel,
                blocks=blocks,
                text="Health Status Update"
            )

            return response["ok"]
        except SlackApiError as e:
            logger.error(f"Failed to send health summary: {e.response['error']}")
            return False

    def _build_incident_blocks(self, incident_data: Dict[str, Any]) -> List[Dict]:
        """
        Build Slack blocks for incident alert
        """
        severity = incident_data.get('severity', 'medium')
        severity_emoji = {
            'critical': '🔴',
            'high': '🟠',
            'medium': '🟡',
            'low': '🟢'
        }.get(severity, '⚪')

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{severity_emoji} {incident_data.get('title', 'RCA Incident')}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Client:*\n{incident_data.get('client_id', 'Unknown')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{severity.upper()}"
                    }
                ]
            }
        ]

        # Description
        if incident_data.get('description'):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": incident_data['description']
                }
            })

        # Root cause
        if incident_data.get('root_cause'):
            blocks.append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Root Cause:*\n{incident_data['root_cause']}"
                    }
                ]
            })

        # Affected resources
        if incident_data.get('affected_resources'):
            resources_text = "\n".join([f"• {r}" for r in incident_data['affected_resources'][:5]])
            if len(incident_data['affected_resources']) > 5:
                resources_text += f"\n• ... and {len(incident_data['affected_resources']) - 5} more"

            blocks.append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Affected Resources:*\n{resources_text}"
                    }
                ]
            })

        # Runbook link
        if incident_data.get('runbook_url'):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<{incident_data['runbook_url']}|📖 View Runbook>"
                }
            })

        # Tags
        if incident_data.get('tags'):
            tags_text = " ".join([f"`{tag}`" for tag in incident_data['tags']])
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": tags_text
                    }
                ]
            })

        # Divider
        blocks.append({"type": "divider"})

        # Timestamp
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"🕐 {incident_data.get('timestamp', 'Unknown time')}"
                }
            ]
        })

        return blocks

    def _build_health_blocks(self, health_data: Dict[str, Any]) -> List[Dict]:
        """
        Build Slack blocks for health summary
        """
        health_pct = health_data.get('health_percentage', 0)
        health_emoji = '🟢' if health_pct >= 90 else '🟡' if health_pct >= 70 else '🔴'

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{health_emoji} System Health: {health_pct:.1f}%",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Healthy:*\n{health_data.get('healthy_resources', 0)}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Unhealthy:*\n{health_data.get('unhealthy_resources', 0)}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Total:*\n{health_data.get('total_resources', 0)}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Active Incidents:*\n{health_data.get('active_incidents', 0)}"
                    }
                ]
            }
        ]

        # Top issues
        if health_data.get('top_issues'):
            issues_text = "\n".join([
                f"• {issue['reason']}: {issue['count']} occurrences"
                for issue in health_data['top_issues'][:5]
            ])

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Top Issues:*\n{issues_text}"
                }
            })

        return blocks


# Global Slack service instance
slack_service = SlackService()

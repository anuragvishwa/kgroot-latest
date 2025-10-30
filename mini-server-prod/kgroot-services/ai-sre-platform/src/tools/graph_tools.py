"""Neo4j graph tools for causality analysis"""

from src.core.tool_registry import BaseTool, ToolMetadata, tool_registry
from src.core.neo4j_service import Neo4jService
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class Neo4jRootCauseTool(BaseTool):
    """Find root causes from Neo4j causality graph"""

    def __init__(self, neo4j_service: Neo4jService):
        self.neo4j = neo4j_service
        tool_registry.register(self)

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="neo4j_find_root_causes",
            description="Find likely root causes from the causality graph. Returns events that have no upstream causes but caused downstream events.",
            category="graph",
            requires_auth=False,
            rate_limit_per_min=100,
            cost_per_call=0.0
        )

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute root cause finding"""
        try:
            client_id = params['client_id']
            time_range_hours = params.get('time_range_hours', 24)
            limit = params.get('limit', 10)

            logger.info(f"Finding root causes for {client_id}, last {time_range_hours}h")

            root_causes = self.neo4j.find_root_causes(
                client_id=client_id,
                time_range_hours=time_range_hours,
                limit=limit
            )

            return {
                "success": True,
                "data": root_causes,
                "count": len(root_causes)
            }

        except Exception as e:
            logger.error(f"Failed to find root causes: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_id": {
                            "type": "string",
                            "description": "Client/tenant identifier"
                        },
                        "time_range_hours": {
                            "type": "integer",
                            "description": "Hours of history to analyze",
                            "default": 24
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of root causes to return",
                            "default": 10
                        }
                    },
                    "required": ["client_id"]
                }
            }
        }


class Neo4jCausalChainTool(BaseTool):
    """Get causal chain for a specific event"""

    def __init__(self, neo4j_service: Neo4jService):
        self.neo4j = neo4j_service
        tool_registry.register(self)

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="neo4j_get_causal_chain",
            description="Get the causal chain (sequence of events) leading to a specific event. Shows how a root cause propagated through the system.",
            category="graph",
            requires_auth=False,
            rate_limit_per_min=100,
            cost_per_call=0.0
        )

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute causal chain query"""
        try:
            event_id = params['event_id']
            client_id = params['client_id']
            max_hops = params.get('max_hops', 3)

            logger.info(f"Getting causal chain for event {event_id}")

            chain = self.neo4j.find_causal_chain(
                event_id=event_id,
                client_id=client_id,
                max_hops=max_hops
            )

            return {
                "success": True,
                "data": chain,
                "length": len(chain)
            }

        except Exception as e:
            logger.error(f"Failed to get causal chain: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {
                            "type": "string",
                            "description": "Event ID to trace back to root cause"
                        },
                        "client_id": {
                            "type": "string",
                            "description": "Client/tenant identifier"
                        },
                        "max_hops": {
                            "type": "integer",
                            "description": "Maximum number of hops in causal chain",
                            "default": 3
                        }
                    },
                    "required": ["event_id", "client_id"]
                }
            }
        }


class Neo4jBlastRadiusTool(BaseTool):
    """Get blast radius (affected events) from a root cause"""

    def __init__(self, neo4j_service: Neo4jService):
        self.neo4j = neo4j_service
        tool_registry.register(self)

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="neo4j_get_blast_radius",
            description="Get all events affected by a root cause (blast radius). Shows the downstream impact of a failure.",
            category="graph",
            requires_auth=False,
            rate_limit_per_min=100,
            cost_per_call=0.0
        )

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute blast radius query"""
        try:
            root_event_id = params['root_event_id']
            client_id = params['client_id']
            limit = params.get('limit', 50)

            logger.info(f"Getting blast radius for {root_event_id}")

            blast_radius = self.neo4j.get_blast_radius(
                root_event_id=root_event_id,
                client_id=client_id,
                limit=limit
            )

            return {
                "success": True,
                "data": blast_radius,
                "affected_count": len(blast_radius)
            }

        except Exception as e:
            logger.error(f"Failed to get blast radius: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "root_event_id": {
                            "type": "string",
                            "description": "Root cause event ID"
                        },
                        "client_id": {
                            "type": "string",
                            "description": "Client/tenant identifier"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of affected events to return",
                            "default": 50
                        }
                    },
                    "required": ["root_event_id", "client_id"]
                }
            }
        }


class Neo4jCrossServiceFailuresTool(BaseTool):
    """Detect failures that propagated across services via topology"""

    def __init__(self, neo4j_service: Neo4jService):
        self.neo4j = neo4j_service
        tool_registry.register(self)

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="neo4j_get_cross_service_failures",
            description="Get failures that propagated across different services using topology relationships. Identifies service-to-service failure cascades.",
            category="graph",
            requires_auth=False,
            rate_limit_per_min=100,
            cost_per_call=0.0
        )

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute cross-service failures query"""
        try:
            client_id = params['client_id']
            time_range_hours = params.get('time_range_hours', 24)
            limit = params.get('limit', 20)

            logger.info(f"Finding cross-service failures for {client_id}")

            failures = self.neo4j.get_cross_service_failures(
                client_id=client_id,
                time_range_hours=time_range_hours,
                limit=limit
            )

            return {
                "success": True,
                "data": failures,
                "count": len(failures)
            }

        except Exception as e:
            logger.error(f"Failed to get cross-service failures: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_id": {
                            "type": "string",
                            "description": "Client/tenant identifier"
                        },
                        "time_range_hours": {
                            "type": "integer",
                            "description": "Hours of history to analyze",
                            "default": 24
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of cross-service failures to return",
                            "default": 20
                        }
                    },
                    "required": ["client_id"]
                }
            }
        }
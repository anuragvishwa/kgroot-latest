"""Base agent class"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from src.core.tool_registry import BaseTool
from src.core.schemas import AgentResult
import logging
import time

logger = logging.getLogger(__name__)


class AgentCapability(BaseModel):
    """Agent capability definition"""
    name: str
    description: str
    tools: List[str]  # Tool names this agent can use
    expertise: str  # Domain expertise


class BaseAgent(ABC):
    """Base class for all agents"""

    def __init__(self, tools: List[BaseTool], llm_client: Optional[Any] = None):
        """
        Initialize agent

        Args:
            tools: List of tools this agent can use
            llm_client: Optional LLM client for reasoning
        """
        self.tools = {t.metadata.name: t for t in tools}
        self.llm = llm_client
        logger.info(f"Initialized {self.capability.name} with {len(tools)} tools: {list(self.tools.keys())}")

    @property
    @abstractmethod
    def capability(self) -> AgentCapability:
        """Return agent capability"""
        pass

    @abstractmethod
    async def investigate(self, query: str, scope: Dict[str, Any]) -> AgentResult:
        """
        Main investigation method

        Args:
            query: Investigation query
            scope: Incident scope (tenant_id, time_window, etc.)

        Returns:
            AgentResult with findings
        """
        pass

    async def _call_tool(
        self,
        tool_name: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Helper to call a tool with error handling

        Args:
            tool_name: Name of the tool to call
            params: Parameters to pass to the tool

        Returns:
            Tool execution result
        """
        tool = self.tools.get(tool_name)
        if not tool:
            error_msg = f"Tool {tool_name} not available to {self.capability.name}"
            logger.error(error_msg)
            return {
                "success": False,
                "data": None,
                "error": error_msg
            }

        try:
            logger.debug(f"Calling tool {tool_name} with params: {params}")
            start_time = time.time()

            result = await tool.execute(params)

            latency_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Tool {tool_name} completed in {latency_ms}ms, success={result.get('success')}")

            return result

        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}", exc_info=True)
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    def _has_tool(self, tool_name: str) -> bool:
        """Check if agent has access to a tool"""
        return tool_name in self.tools

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get schemas for all tools (for LLM function calling)"""
        return [tool.get_schema() for tool in self.tools.values()]
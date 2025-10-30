"""Tool registry for plugin-based tool system"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class ToolMetadata(BaseModel):
    """Metadata for a tool"""
    name: str
    description: str
    category: str  # "graph", "metrics", "logs", "code", "context"
    requires_auth: bool = False
    rate_limit_per_min: int = 60
    cost_per_call: float = 0.0
    version: str = "1.0.0"


class BaseTool(ABC):
    """Base class for all tools"""

    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        """Return tool metadata"""
        pass

    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the tool with given parameters

        Returns:
            {
                "success": bool,
                "data": Any,
                "error": Optional[str]
            }
        """
        pass

    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """
        Return JSON schema for LLM function calling

        Format follows OpenAI function calling schema:
        {
            "type": "function",
            "function": {
                "name": "tool_name",
                "description": "Tool description",
                "parameters": {...}
            }
        }
        """
        pass

    def validate_params(self, params: Dict[str, Any]) -> bool:
        """Validate parameters against schema"""
        # TODO: Implement JSON schema validation
        return True


class ToolRegistry:
    """Singleton registry for all tools"""

    _instance: Optional['ToolRegistry'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: Dict[str, BaseTool] = {}
            cls._instance._initialized = False
        return cls._instance

    def register(self, tool: BaseTool) -> None:
        """Register a tool"""
        name = tool.metadata.name
        if name in self._tools:
            logger.warning(f"Tool {name} already registered, overwriting")

        self._tools[name] = tool
        logger.info(f"✓ Registered tool: {name} (category: {tool.metadata.category})")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name"""
        return self._tools.get(name)

    def get_tools_by_category(self, category: str) -> List[BaseTool]:
        """Get all tools in a category"""
        return [
            tool for tool in self._tools.values()
            if tool.metadata.category == category
        ]

    def get_all_tools(self) -> List[BaseTool]:
        """Get all registered tools"""
        return list(self._tools.values())

    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """Get schemas for all tools (for LLM function calling)"""
        return [tool.get_schema() for tool in self._tools.values()]

    def get_tool_names(self) -> List[str]:
        """Get all tool names"""
        return list(self._tools.keys())

    def get_categories(self) -> List[str]:
        """Get all unique categories"""
        return list(set(tool.metadata.category for tool in self._tools.values()))

    def list_tools(self) -> Dict[str, List[str]]:
        """List all tools grouped by category"""
        result = {}
        for category in self.get_categories():
            result[category] = [
                tool.metadata.name for tool in self.get_tools_by_category(category)
            ]
        return result

    def clear(self) -> None:
        """Clear all registered tools (for testing)"""
        self._tools.clear()
        logger.info("Cleared all tools from registry")


# Global singleton instance
tool_registry = ToolRegistry()
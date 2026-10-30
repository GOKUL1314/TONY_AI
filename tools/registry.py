"""
Central Tool Registry for TONY AI (Stage 5).
Maintains the catalog of approved, registered tools and prevents unauthorized tool execution.
"""
import logging
from typing import Any

from tools.base import BaseTool
from tools.schemas import ToolDefinition

# Import all tool implementations
from tools.system.applications import OpenApplicationTool
from tools.system.volume import VolumeUpTool, VolumeDownTool, VolumeMuteTool, VolumeUnmuteTool, GetVolumeTool
from tools.system.media import MediaPlayPauseTool, MediaNextTool, MediaPrevTool
from tools.browser.browser import OpenWebsiteTool
from tools.filesystem.folders import CreateFolderTool, OpenFolderTool, DeleteFolderTool
from tools.filesystem.files import CreateFileTool, OpenFileTool, CopyFileTool, MoveFileTool, RenameFileTool, DeleteFileTool
from tools.filesystem.search import SearchFilesTool
from tools.utilities.datetime_tool import GetSystemTimeTool
from tools.utilities.clipboard import GetClipboardTool, SetClipboardTool

logger = logging.getLogger("tony.tools.registry")


class ToolRegistry:
    """Central catalog of permitted tools."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register_tool(self, tool: BaseTool) -> None:
        """Register a new tool instance in the registry."""
        name = tool.definition.name.lower().strip()
        if name in self._tools:
            logger.debug(f"Overwriting registered tool: '{name}'")
        self._tools[name] = tool
        logger.debug(f"Registered tool: '{name}' [{tool.definition.category}]")

    def register(self, tool: BaseTool) -> None:
        """Alias for register_tool."""
        self.register_tool(tool)

    def get_tool(self, tool_name: str) -> BaseTool | None:
        """Retrieve a registered tool by name."""
        if not tool_name:
            return None
        return self._tools.get(tool_name.lower().strip())

    def is_registered(self, tool_name: str) -> bool:
        """Check if a tool is registered."""
        if not tool_name:
            return False
        return tool_name.lower().strip() in self._tools

    def get_definition(self, tool_name: str) -> ToolDefinition | None:
        """Retrieve definition of a registered tool."""
        tool = self.get_tool(tool_name)
        return tool.definition if tool else None

    def list_tools(self) -> list[ToolDefinition]:
        """Return definitions of all registered tools."""
        return [tool.definition for tool in self._tools.values()]

    def get_tool_names(self) -> list[str]:
        """Return names of all registered tools."""
        return list(self._tools.keys())

    def get_tools_by_category(self, category: str) -> list[ToolDefinition]:
        """Return definitions filtered by category."""
        clean_cat = category.lower().strip()
        return [t.definition for t in self._tools.values() if t.definition.category.lower() == clean_cat]

    def count(self) -> int:
        """Total number of registered tools."""
        return len(self._tools)


def create_default_registry() -> ToolRegistry:
    """Application factory helper: instantiates and populates the default tool registry."""
    registry = ToolRegistry()

    # 1. System Applications
    registry.register_tool(OpenApplicationTool())

    # 2. System Volume & Audio
    registry.register_tool(VolumeUpTool())
    registry.register_tool(VolumeDownTool())
    registry.register_tool(VolumeMuteTool())
    registry.register_tool(VolumeUnmuteTool())
    registry.register_tool(GetVolumeTool())

    # 3. Media Controls
    registry.register_tool(MediaPlayPauseTool())
    registry.register_tool(MediaNextTool())
    registry.register_tool(MediaPrevTool())

    # 4. Web Browser
    registry.register_tool(OpenWebsiteTool())

    # 5. Filesystem Folders
    registry.register_tool(CreateFolderTool())
    registry.register_tool(OpenFolderTool())
    registry.register_tool(DeleteFolderTool())

    # 6. Filesystem Files & Search
    registry.register_tool(CreateFileTool())
    registry.register_tool(OpenFileTool())
    registry.register_tool(CopyFileTool())
    registry.register_tool(MoveFileTool())
    registry.register_tool(RenameFileTool())
    registry.register_tool(DeleteFileTool())
    registry.register_tool(SearchFilesTool())

    # 7. Utilities (Time & Clipboard)
    registry.register_tool(GetSystemTimeTool())
    registry.register_tool(GetClipboardTool())
    registry.register_tool(SetClipboardTool())

    logger.info(f"Initialized ToolRegistry with {registry.count()} tools across 4 categories.")
    return registry

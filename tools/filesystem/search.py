"""
File search tool for TONY AI (Stage 5).
Safely searches user directories (Desktop, Documents, Downloads, etc.) for matching files.
"""
import logging
import os
from pathlib import Path
from typing import Any

from tools.base import BaseTool
from tools.permissions import PermissionManager, SAFE_BASE_NAMES
from tools.schemas import ToolDefinition, ToolParameter, ToolExecutionResult, RiskLevel

logger = logging.getLogger("tony.tools.filesystem.search")


class SearchFilesTool(BaseTool):
    """Safely searches configured user directories for files matching a query."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_files",
            description="Search your computer's safe user directories (Desktop, Documents, Downloads) for files matching a query.",
            category="filesystem",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={
                "query": ToolParameter(
                    name="query",
                    type="string",
                    description="The search keyword or filename pattern (e.g. 'resume.pdf', 'invoice', '.py').",
                    required=True
                ),
                "location": ToolParameter(
                    name="location",
                    type="string",
                    description="Optional specific directory to search (e.g. 'Desktop', 'Documents', 'Downloads', or 'all').",
                    required=False,
                    default="all"
                ),
                "limit": ToolParameter(
                    name="limit",
                    type="integer",
                    description="Maximum number of search results to return (default: 10, max: 50).",
                    required=False,
                    default=10
                )
            },
            examples=[
                "Tony, find my resume",
                "Search my computer for Python files",
                "Where is report.pdf",
                "Find budget in Documents"
            ]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        query = str(parameters.get("query") or parameters.get("target") or "").strip().lower()
        if not query:
            return self.failure("Search query is required.", error_code="INVALID_PARAMETER")

        location = str(parameters.get("location") or "all").strip().lower()
        limit = min(50, max(1, int(parameters.get("limit") or 10)))

        # Determine target search roots
        search_roots: list[Path] = []
        if location in SAFE_BASE_NAMES:
            root = SAFE_BASE_NAMES[location]
            if root.exists():
                search_roots.append(root)
        else:
            # Search all available safe user directories
            for root in SAFE_BASE_NAMES.values():
                if root.exists():
                    search_roots.append(root)

        matches: list[dict[str, Any]] = []

        # Recursively search directories up to a max depth of 4 to prevent slow deep traversal
        for root in search_roots:
            if len(matches) >= limit:
                break
            try:
                for dirpath, dirnames, filenames in os.walk(str(root)):
                    # Don't traverse hidden folders (.git, .vscode, node_modules, etc.)
                    dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in {"node_modules", "AppData", "venv"}]

                    rel_depth = len(Path(dirpath).relative_to(root).parts)
                    if rel_depth > 4:
                        continue

                    for fname in filenames:
                        if query in fname.lower():
                            full_p = Path(dirpath) / fname
                            matches.append({
                                "filename": fname,
                                "path": str(full_p),
                                "directory": dirpath,
                                "size_bytes": full_p.stat().st_size if full_p.exists() else 0
                            })
                            if len(matches) >= limit:
                                break
                    if len(matches) >= limit:
                        break
            except Exception as e:
                logger.debug(f"Error scanning directory '{root}': {e}")

        logger.info(f"File search for '{query}' found {len(matches)} matches.")

        if not matches:
            return self.success(
                f"No files matching '{query}' were found in your safe user directories.",
                data={"query": query, "count": 0, "results": []}
            )

        # Format clean, readable summary
        result_lines = [f"I found {len(matches)} matching file{'s' if len(matches) != 1 else ''}:"]
        for idx, m in enumerate(matches, start=1):
            result_lines.append(f"{idx}. {m['filename']} (in {m['directory']})")

        return self.success(
            "\n".join(result_lines),
            data={"query": query, "count": len(matches), "results": matches}
        )

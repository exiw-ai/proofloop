"""Use case for selecting MCP servers based on task analysis."""

import json

from loguru import logger

from src.application.prompts import workspace_restriction_prompt
from src.domain.entities.task import Task
from src.domain.ports.agent_port import AgentPort, MessageCallback
from src.domain.value_objects.mcp_types import MCPServerRegistry, MCPServerTemplate
from src.infrastructure.utils import extract_json


class MCPSuggestion:
    """Suggestion for an MCP server to use."""

    def __init__(
        self,
        server_name: str,
        reason: str,
        confidence: float = 0.5,
        template: MCPServerTemplate | None = None,
    ) -> None:
        self.server_name = server_name
        self.reason = reason
        self.confidence = confidence
        self.template = template


class SelectMCPServers:
    """Use case for analyzing task and suggesting relevant MCP servers."""

    def __init__(
        self,
        agent: AgentPort,
        registry: MCPServerRegistry,
    ) -> None:
        self.agent = agent
        self.registry = registry

    async def analyze_and_suggest(
        self,
        task: Task,
        on_message: MessageCallback | None = None,
    ) -> list[MCPSuggestion]:
        """Analyze task and suggest relevant MCP servers.

        Args:
            task: The task to analyze.
            on_message: Optional callback for real-time messages.

        Returns:
            List of MCP server suggestions with reasons.
        """
        # Build available servers description
        available_servers = []
        for template in self.registry.list_all():
            available_servers.append(
                {
                    "name": template.name,
                    "description": template.description,
                    "category": template.category,
                    "requires_credentials": bool(template.required_credentials),
                }
            )

        workspace = task.sources[0] if task.sources else "."
        prompt = f"""{workspace_restriction_prompt(workspace)}Analyze this task and determine which MCP (Model Context Protocol) servers would be helpful.

Task: {task.description}
Goals: {task.goals}
Constraints: {task.constraints}

Available MCP servers:
{json.dumps(available_servers, indent=2)}

Consider:
1. Does the task involve web browsing/testing? → playwright or puppeteer
2. Does it need external API data (Jira, GitHub, GitLab)? → corresponding servers
3. Does it involve database operations? → postgres or sqlite
4. Does it need web search or fetch? → brave-search or fetch
5. Does it involve file operations outside the workspace? → filesystem

Return JSON array of suggested servers (empty if none needed):
[
    {{
        "name": "server_name",
        "reason": "Brief explanation why this server would help",
        "confidence": 0.8
    }}
]

Only suggest servers that would CLEARLY help with the task.
Confidence should be 0.0-1.0 (0.8+ = highly recommended, 0.5-0.8 = useful, <0.5 = optional).
If the task can be completed with standard file operations, return empty array []."""

        result = await self.agent.execute(
            prompt=prompt,
            allowed_tools=["Read", "Glob", "Grep"],
            cwd=workspace,
            on_message=on_message,
        )

        try:
            data = extract_json(result.final_response)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse MCP suggestions, proceeding without")
            return []

        suggestions: list[MCPSuggestion] = []
        for item in data:
            server_name = item.get("name", "")
            maybe_template = self.registry.get(server_name)

            if maybe_template is None:
                logger.warning(f"Suggested MCP server '{server_name}' not in registry")
                continue

            suggestions.append(
                MCPSuggestion(
                    server_name=server_name,
                    reason=item.get("reason", ""),
                    confidence=item.get("confidence", 0.5),
                    template=maybe_template,
                )
            )

        logger.info(f"MCP analysis suggested {len(suggestions)} servers for task {task.id}")
        return suggestions

    def get_template(self, server_name: str) -> MCPServerTemplate | None:
        """Get template by name."""
        return self.registry.get(server_name)

    def list_available(self) -> list[MCPServerTemplate]:
        """List all available MCP server templates."""
        return self.registry.list_all()

    def list_by_category(self, category: str) -> list[MCPServerTemplate]:
        """List templates in a category."""
        return self.registry.list_by_category(category)

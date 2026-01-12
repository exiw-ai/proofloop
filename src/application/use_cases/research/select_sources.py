from dataclasses import dataclass

from src.domain.entities import Task
from src.domain.ports.agent_port import AgentPort, MessageCallback
from src.domain.value_objects import ResearchType, TaskStatus
from src.infrastructure.utils.agent_json import parse_agent_json


@dataclass
class SourceSelectionResult:
    source_types: list[str]
    strategy: str
    reasoning: str


RESEARCH_TYPE_SOURCES = {
    ResearchType.ACADEMIC: ["arxiv", "semantic_scholar", "web"],
    ResearchType.MARKET: ["web", "github"],
    ResearchType.TECHNICAL: ["github", "web", "arxiv"],
    ResearchType.GENERAL: ["web", "arxiv", "github"],
}


class SelectSources:
    """Use case for selecting source types for research."""

    def __init__(self, agent: AgentPort):
        self.agent = agent

    async def run(
        self,
        task: Task,
        research_type: ResearchType,
        on_message: MessageCallback | None = None,
    ) -> SourceSelectionResult:
        """Select appropriate source types based on research type and task."""
        task.transition_to(TaskStatus.RESEARCH_SOURCE_SELECTION)

        default_sources = RESEARCH_TYPE_SOURCES.get(research_type, ["web", "arxiv", "github"])

        prompt = f"""Analyze this research task and confirm or adjust the source selection.

Task: {task.description}
Goals: {task.goals}
Research Type: {research_type.value}

Default sources for this research type: {default_sources}

Available source types:
- arxiv: Academic papers and preprints
- semantic_scholar: Academic paper search with citations
- web: General web search
- github: Code repositories and documentation

Respond with JSON:
{{
    "source_types": ["list", "of", "sources"],
    "strategy": "Brief description of search strategy",
    "reasoning": "Why these sources are appropriate"
}}"""

        from src.application.services.tool_gating import get_research_tools

        result = await self.agent.execute(
            prompt=prompt,
            allowed_tools=get_research_tools(task.status),
            cwd=".",
            on_message=on_message,
        )

        data = parse_agent_json(
            result.final_response,
            {
                "source_types": default_sources,
                "strategy": "Default strategy based on research type",
                "reasoning": "Using default sources for research type",
            },
        )
        return SourceSelectionResult(
            source_types=list(data.get("source_types", default_sources)),
            strategy=str(data.get("strategy", "")),
            reasoning=str(data.get("reasoning", "")),
        )

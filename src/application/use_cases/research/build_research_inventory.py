from datetime import UTC, datetime
from uuid import uuid4

from src.domain.entities import ResearchInventory, Task
from src.domain.ports.agent_port import AgentPort, MessageCallback
from src.domain.value_objects import ResearchPreset, ResearchType, TaskStatus
from src.infrastructure.utils.agent_json import parse_agent_json


class BuildResearchInventory:
    """Use case for building the research inventory."""

    def __init__(self, agent: AgentPort):
        self.agent = agent

    async def run(
        self,
        task: Task,
        research_type: ResearchType,
        preset: ResearchPreset,
        source_types: list[str],
        on_message: MessageCallback | None = None,
    ) -> ResearchInventory:
        """Build research inventory with queries, topics, and sections."""
        task.transition_to(TaskStatus.RESEARCH_INVENTORY)

        prompt = f"""Based on this research task, generate a comprehensive research inventory.

Task: {task.description}
Goals: {task.goals}
Research Type: {research_type.value}
Selected Sources: {source_types}

Generate:
1. Search queries to find relevant sources (5-15 queries)
2. Required topics that must be covered (3-10 topics)
3. Topic synonyms for flexible matching
4. Report sections to generate

Respond with JSON:
{{
    "queries": ["search query 1", "search query 2", ...],
    "required_topics": ["topic1", "topic2", ...],
    "topic_synonyms": {{"topic1": ["synonym1", "alt_name"], ...}},
    "sections": ["section1", "section2", ...]
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
                "queries": [task.description],
                "required_topics": [],
                "topic_synonyms": {},
                "sections": ["executive_summary", "findings", "recommendations"],
            },
        )

        inventory = ResearchInventory(
            id=uuid4(),
            task_id=task.id,
            queries=data.get("queries", []),
            required_topics=data.get("required_topics", []),
            topic_synonyms=data.get("topic_synonyms", {}),
            sections=data.get("sections", []),
            research_type=research_type,
            preset=preset,
            created_at=datetime.now(UTC),
        )

        task.research_inventory = inventory
        return inventory

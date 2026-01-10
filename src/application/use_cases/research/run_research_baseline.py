import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.domain.entities import Task
from src.domain.ports.agent_port import AgentPort, MessageCallback
from src.domain.value_objects import TaskStatus


class RunResearchBaseline:
    """Use case for capturing baseline search results."""

    def __init__(self, agent: AgentPort, base_path: Path):
        self.agent = agent
        self.base_path = base_path

    async def run(
        self,
        task: Task,
        on_message: MessageCallback | None = None,
    ) -> dict[str, Any]:
        """Run initial search queries and capture baseline results."""
        task.transition_to(TaskStatus.RESEARCH_BASELINE)

        if not task.research_inventory:
            return {"error": "No research inventory"}

        queries = task.research_inventory.queries[:5]  # First 5 queries for baseline

        prompt = f"""Run these initial search queries to establish a baseline:

Queries:
{json.dumps(queries, indent=2)}

For each query:
1. Use WebSearch to find initial results
2. Note the number of results found
3. Identify key sources that appear

Respond with JSON:
{{
    "baseline_results": [
        {{
            "query": "the query",
            "results_count": 42,
            "top_sources": ["source1", "source2"],
            "notes": "observations"
        }}
    ],
    "initial_sources_identified": ["list", "of", "urls"],
    "baseline_timestamp": "ISO8601"
}}"""

        from src.application.services.tool_gating import get_research_tools

        result = await self.agent.execute(
            prompt=prompt,
            allowed_tools=get_research_tools(task.status),
            cwd=str(self.base_path),
            on_message=on_message,
        )

        try:
            from src.infrastructure.utils.json_extractor import extract_json

            data = extract_json(result.final_response)

            baseline = {
                "task_id": str(task.id),
                "queries": queries,
                "baseline_results": data.get("baseline_results", []),
                "initial_sources": data.get("initial_sources_identified", []),
                "timestamp": datetime.now(UTC).isoformat(),
            }

            baseline_dir = self.base_path / "baseline"
            baseline_dir.mkdir(parents=True, exist_ok=True)
            (baseline_dir / "baseline.json").write_text(
                json.dumps(baseline, indent=2), encoding="utf-8"
            )

            return baseline

        except Exception as e:
            return {"error": str(e)}

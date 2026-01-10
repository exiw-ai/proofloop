import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.domain.entities import Iteration, Task
from src.domain.entities.iteration import IterationDecision
from src.domain.ports.agent_port import AgentPort, MessageCallback
from src.domain.value_objects import PRESET_PARAMS, TaskStatus
from src.infrastructure.research import KnowledgeBaseStore


@dataclass
class DeepeningResult:
    synthesis_passes: int
    themes_identified: int
    gaps_identified: int
    trends_identified: int


class ExecuteDeepening:
    """Use case for executing synthesis and deepening passes."""

    def __init__(
        self,
        agent: AgentPort,
        kb_store: KnowledgeBaseStore,
        base_path: Path,
    ):
        self.agent = agent
        self.kb_store = kb_store
        self.base_path = base_path

    async def run(
        self,
        task: Task,
        on_message: MessageCallback | None = None,
    ) -> DeepeningResult:
        """Execute synthesis passes to deepen research."""
        task.transition_to(TaskStatus.RESEARCH_DEEPENING)

        if not task.research_inventory:
            raise ValueError("No research inventory")

        preset_params = PRESET_PARAMS[task.research_inventory.preset]
        required_passes = preset_params.synthesis_passes

        synthesis_dir = self.base_path / "knowledge_base" / "synthesis"
        synthesis_dir.mkdir(parents=True, exist_ok=True)

        synthesis_log = []
        total_themes = 0
        total_gaps = 0
        total_trends = 0

        for pass_num in range(1, required_passes + 1):
            sources = await self.kb_store.list_sources()
            findings = await self.kb_store.list_findings()

            prompt = f"""Perform synthesis pass {pass_num}/{required_passes}.

Available data:
- {len(sources)} sources
- {len(findings)} findings

Research topics: {task.research_inventory.required_topics}

Tasks:
1. Identify key themes across findings
2. Identify gaps in the research
3. Identify emerging trends
4. Suggest additional queries if needed

Respond with JSON:
{{
    "themes": [
        {{"name": "theme name", "description": "description", "supporting_findings": ["finding summary 1"]}}
    ],
    "gaps": [
        {{"topic": "topic name", "description": "what's missing"}}
    ],
    "trends": [
        {{"name": "trend name", "description": "description", "evidence": ["evidence 1"]}}
    ],
    "suggested_queries": ["additional query if gaps found"],
    "synthesis_notes": "Summary of this synthesis pass"
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

                themes = data.get("themes", [])
                gaps = data.get("gaps", [])
                trends = data.get("trends", [])

                total_themes += len(themes)
                total_gaps += len(gaps)
                total_trends += len(trends)

                pass_result = {
                    "pass_number": pass_num,
                    "started_at": datetime.now(UTC).isoformat(),
                    "completed_at": datetime.now(UTC).isoformat(),
                    "themes_identified": len(themes),
                    "gaps_identified": len(gaps),
                    "trends_identified": len(trends),
                    "themes": themes,
                    "gaps": gaps,
                    "trends": trends,
                    "suggested_queries": data.get("suggested_queries", []),
                    "notes": data.get("synthesis_notes", ""),
                }

                synthesis_log.append(pass_result)

                # Save pass results
                (synthesis_dir / f"pass_{pass_num}.json").write_text(
                    json.dumps(pass_result, indent=2), encoding="utf-8"
                )

                task.add_iteration(
                    Iteration(
                        number=len(task.iterations) + 1,
                        goal=f"Synthesis pass {pass_num}",
                        changes=[
                            f"Identified {len(themes)} themes, {len(gaps)} gaps, {len(trends)} trends"
                        ],
                        decision=IterationDecision.CONTINUE,
                        decision_reason=f"Completed synthesis pass {pass_num}",
                        metrics={
                            "themes": float(total_themes),
                            "gaps": float(total_gaps),
                            "trends": float(total_trends),
                        },
                    )
                )

            except Exception as e:
                synthesis_log.append(
                    {
                        "pass_number": pass_num,
                        "error": str(e),
                        "started_at": datetime.now(UTC).isoformat(),
                    }
                )

        # Save synthesis log
        (synthesis_dir / "synthesis_log.json").write_text(
            json.dumps(
                {
                    "checked_at": datetime.now(UTC).isoformat(),
                    "required_passes": required_passes,
                    "completed_passes": len(synthesis_log),
                    "passes": synthesis_log,
                    "passed": len(synthesis_log) >= required_passes,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        return DeepeningResult(
            synthesis_passes=len(synthesis_log),
            themes_identified=total_themes,
            gaps_identified=total_gaps,
            trends_identified=total_trends,
        )

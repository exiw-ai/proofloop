from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from src.application.prompts import workspace_restriction_prompt
from src.domain.entities import (
    ContextRefPayload,
    KeyFinding,
    LLMHandoff,
    SourceReference,
    Task,
)
from src.domain.ports.agent_port import AgentPort, MessageCallback
from src.domain.value_objects import ArtifactKind
from src.infrastructure.research import (
    KnowledgeBaseStore,
    LLMHandoffStore,
    RepoContextStore,
    ReportPackStore,
)
from src.infrastructure.utils.agent_json import parse_agent_json


class GenerateLLMHandoff:
    """Use case for generating LLM handoff payload."""

    def __init__(
        self,
        agent: AgentPort,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        handoff_store: LLMHandoffStore,
        repo_context_store: RepoContextStore,
    ):
        self.agent = agent
        self.kb_store = kb_store
        self.report_store = report_store
        self.handoff_store = handoff_store
        self.repo_context_store = repo_context_store

    async def run(
        self,
        task: Task,
        workspace_path: Path,
        on_message: MessageCallback | None = None,
    ) -> str:
        """Generate the LLM handoff payload.

        Returns path to derive_payload.json
        """
        # Load data
        sources = await self.kb_store.list_sources()
        findings = await self.kb_store.list_findings()

        # Generate headline and approach using agent
        prompt = f"""{workspace_restriction_prompt(str(workspace_path))}Based on this research, generate a summary for code implementation.

Research Task: {task.description}
Goals: {task.goals}

Findings Summary:
{chr(10).join([f"- {f.content[:200]}" for f in findings[:20]])}

Generate JSON:
{{
    "headline": "One-line summary of what to implement",
    "recommended_approach": "Brief description of recommended implementation approach",
    "risks": ["list", "of", "risks"],
    "assumptions": ["list", "of", "assumptions"]
}}"""

        from src.application.services.tool_gating import get_research_tools

        result = await self.agent.execute(
            prompt=prompt,
            allowed_tools=get_research_tools(task.status),
            cwd=str(workspace_path),
            on_message=on_message,
        )

        agent_data = parse_agent_json(
            result.final_response,
            {
                "headline": task.description,
                "recommended_approach": "",
                "risks": [],
                "assumptions": [],
            },
        )

        # Build key findings
        key_findings = []
        for f in findings[:10]:
            source = next((s for s in sources if s.id == f.source_id), None)
            if source:
                # Parse excerpt_id from excerpt_ref
                excerpt_id = f.excerpt_ref.split("/")[-1].replace(".json", "")
                try:
                    excerpt_uuid = UUID(excerpt_id)
                except Exception:
                    excerpt_uuid = f.id

                key_findings.append(
                    KeyFinding(
                        finding_id=f.id,
                        summary=f.content[:200],
                        source_key=f.source_key,
                        excerpt_id=excerpt_uuid,
                    )
                )

        # Build source references
        source_refs = [
            SourceReference(
                source_key=s.source_key,
                title=s.title,
                url=s.url,
                content_hash=s.content_hash,
            )
            for s in sources[:30]
        ]

        # Build context refs
        context_refs = [
            ContextRefPayload(kind=ArtifactKind.REPORTS.value, rel_path="manifest.json"),
        ]

        if self.repo_context_store.context_exists():
            context_refs.append(
                ContextRefPayload(kind=ArtifactKind.REPO_CONTEXT.value, rel_path="manifest.json")
            )

        # Create handoff
        handoff = LLMHandoff(
            schema_version="1.0",
            research_task_id=task.id,
            created_at=datetime.now(UTC),
            headline=agent_data.get("headline", task.description),
            goals=task.goals,
            constraints=task.constraints,
            recommended_approach=agent_data.get("recommended_approach", ""),
            key_findings=key_findings,
            source_references=source_refs,
            context_refs=context_refs,
            suggested_blocking_conditions=["tests_pass", "lint_pass", "typecheck_pass"],
            recommended_checks=["test", "lint", "typecheck"],
            risks=agent_data.get("risks", []),
            assumptions=agent_data.get("assumptions", []),
            target_workspace_hint=str(workspace_path),
        )

        return await self.handoff_store.save_handoff(handoff)

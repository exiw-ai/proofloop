from dataclasses import dataclass
from uuid import uuid4

from loguru import logger

from src.domain.entities import Excerpt, Finding, Iteration, Task
from src.domain.entities.iteration import IterationDecision
from src.domain.ports.agent_port import AgentPort, MessageCallback
from src.domain.value_objects import PRESET_PARAMS, TaskStatus
from src.infrastructure.research import KnowledgeBaseStore
from src.infrastructure.utils.agent_json import parse_agent_json


@dataclass
class DiscoveryMetrics:
    sources_count: int
    findings_count: int
    coverage: float
    iteration: int


class ExecuteDiscovery:
    """Use case for executing the discovery loop."""

    def __init__(
        self,
        agent: AgentPort,
        kb_store: KnowledgeBaseStore,
    ):
        self.agent = agent
        self.kb_store = kb_store

    async def run(
        self,
        task: Task,
        max_iterations: int | None = None,
        on_message: MessageCallback | None = None,
    ) -> DiscoveryMetrics:
        """Execute the discovery loop until conditions are met."""
        task.transition_to(TaskStatus.RESEARCH_DISCOVERY)

        if not task.research_inventory:
            raise ValueError("No research inventory")

        preset_params = PRESET_PARAMS[task.research_inventory.preset]
        min_sources = preset_params.min_sources
        target_coverage = preset_params.coverage
        max_iter = max_iterations or preset_params.max_iterations

        iteration = 0
        prev_sources_count = 0
        stall_iterations = 0  # Track iterations without meaningful progress

        while iteration < max_iter:
            iteration += 1

            sources = await self.kb_store.list_sources()
            findings = await self.kb_store.list_findings()

            current_coverage = self._calculate_coverage(
                findings, task.research_inventory.required_topics
            )

            # Track progress
            sources_added = len(sources) - prev_sources_count
            if sources_added < 2:
                stall_iterations += 1
            else:
                stall_iterations = 0
            prev_sources_count = len(sources)

            metrics = {
                "sources_count": float(len(sources)),
                "findings_count": float(len(findings)),
                "coverage": current_coverage,
            }

            # Check if we've met conditions
            if len(sources) >= min_sources and current_coverage >= target_coverage:
                task.add_iteration(
                    Iteration(
                        number=iteration,
                        goal="Discovery complete",
                        changes=["Met all discovery conditions"],
                        decision=IterationDecision.DONE,
                        decision_reason="Met minimum sources and coverage threshold",
                        metrics=metrics,
                    )
                )
                break

            # Smart early exit: full coverage with reasonable sources
            if current_coverage >= 1.0 and len(sources) >= min_sources // 2:
                logger.info(
                    f"Early exit: 100% coverage achieved with {len(sources)} sources "
                    f"(minimum {min_sources // 2} for early exit)"
                )
                task.add_iteration(
                    Iteration(
                        number=iteration,
                        goal="Discovery complete (early exit)",
                        changes=["Full coverage achieved"],
                        decision=IterationDecision.DONE,
                        decision_reason="100% coverage with sufficient sources",
                        metrics=metrics,
                    )
                )
                break

            # Smart early exit: stalled progress with good coverage
            if stall_iterations >= 3 and current_coverage >= target_coverage:
                logger.info(
                    f"Early exit: stalled at {len(sources)} sources "
                    f"with {current_coverage:.1%} coverage after {stall_iterations} stall iterations"
                )
                task.add_iteration(
                    Iteration(
                        number=iteration,
                        goal="Discovery complete (stalled)",
                        changes=["Progress stalled with sufficient coverage"],
                        decision=IterationDecision.DONE,
                        decision_reason=f"Stalled for {stall_iterations} iterations with {current_coverage:.1%} coverage",
                        metrics=metrics,
                    )
                )
                break

            # Run discovery iteration
            uncovered = self._get_uncovered_topics(
                findings, task.research_inventory.required_topics
            )

            # Get already fetched URLs to avoid duplicates
            fetched_urls = [s.url for s in sources if s.url]
            fetched_urls_text = "\n".join(f"- {url}" for url in fetched_urls[:50])  # Limit to 50

            prompt = f"""Continue research discovery.

Current status:
- Sources: {len(sources)} / {min_sources} required
- Coverage: {current_coverage:.1%} / {target_coverage:.1%} required
- Uncovered topics: {uncovered}

Research queries: {task.research_inventory.queries}
Required topics: {task.research_inventory.required_topics}

Already fetched URLs (do NOT fetch these again):
{fetched_urls_text if fetched_urls else "(none yet)"}

Tasks:
1. Use WebSearch to find more sources
2. Use WebFetch to retrieve content from promising URLs (skip already fetched)
3. Extract findings that cover uncovered topics
4. Report what you found

Respond with JSON:
{{
    "fetched_pages": [
        {{
            "url": "https://...",
            "title": "Page Title",
            "content_summary": "Brief summary of content",
            "source_type": "web|arxiv|github"
        }}
    ],
    "findings": [
        {{
            "content": "The finding text",
            "source_url": "https://...",
            "topics": ["topic1", "topic2"],
            "finding_type": "fact|trend|gap|recommendation",
            "confidence": 0.8,
            "excerpt": "Supporting quote from source"
        }}
    ],
    "notes": "What was searched and found"
}}"""

            from src.application.services.tool_gating import get_research_tools

            result = await self.agent.execute(
                prompt=prompt,
                allowed_tools=get_research_tools(task.status),
                cwd=".",
                on_message=on_message,
            )

            data = parse_agent_json(result.final_response, None)

            if data is None:
                task.add_iteration(
                    Iteration(
                        number=iteration,
                        goal=f"Discovery iteration {iteration}",
                        changes=["Error: Failed to parse agent response"],
                        decision=IterationDecision.CONTINUE,
                        decision_reason="Error occurred: Failed to parse agent response",
                        metrics=metrics,
                    )
                )
                continue

            # Process fetched pages
            for page in data.get("fetched_pages", []):
                url = page.get("url", "")
                if not url:
                    continue

                # Save source (the store handles dedup and content extraction)
                await self.kb_store.save_source(
                    url=url,
                    content=page.get("content_summary", "").encode("utf-8"),
                    source_type=page.get("source_type", "web"),
                    title=page.get("title", ""),
                )

            # Process findings
            sources = await self.kb_store.list_sources()
            source_by_url = {s.url: s for s in sources}

            for finding_data in data.get("findings", []):
                source_url = finding_data.get("source_url", "")
                source = source_by_url.get(source_url)

                if not source:
                    continue

                # Create excerpt
                excerpt = Excerpt(
                    id=uuid4(),
                    source_id=source.id,
                    text=finding_data.get("excerpt", ""),
                    location="extracted",
                )
                await self.kb_store.save_excerpt(excerpt)

                # Create finding
                finding = Finding(
                    id=uuid4(),
                    source_id=source.id,
                    source_key=source.source_key,
                    excerpt_ref=f"excerpts/{excerpt.id}.json",
                    content=finding_data.get("content", ""),
                    finding_type=finding_data.get("finding_type", "fact"),
                    confidence=finding_data.get("confidence", 0.5),
                    topics=finding_data.get("topics", []),
                )
                await self.kb_store.save_finding(finding)

            task.add_iteration(
                Iteration(
                    number=iteration,
                    goal=f"Discovery iteration {iteration}",
                    changes=[data.get("notes", "Searched and processed sources")],
                    decision=IterationDecision.CONTINUE,
                    decision_reason="Continuing discovery",
                    metrics=metrics,
                )
            )

        # Final metrics
        sources = await self.kb_store.list_sources()
        findings = await self.kb_store.list_findings()
        final_coverage = self._calculate_coverage(findings, task.research_inventory.required_topics)

        return DiscoveryMetrics(
            sources_count=len(sources),
            findings_count=len(findings),
            coverage=final_coverage,
            iteration=iteration,
        )

    def _calculate_coverage(self, findings: list[Finding], required_topics: list[str]) -> float:
        if not required_topics:
            return 1.0

        covered = set()
        for finding in findings:
            for topic in finding.topics:
                topic_lower = topic.lower()
                for req in required_topics:
                    if req.lower() in topic_lower or topic_lower in req.lower():
                        covered.add(req.lower())

        return len(covered) / len(required_topics)

    def _get_uncovered_topics(
        self, findings: list[Finding], required_topics: list[str]
    ) -> list[str]:
        covered = set()
        for finding in findings:
            for topic in finding.topics:
                topic_lower = topic.lower()
                for req in required_topics:
                    if req.lower() in topic_lower or topic_lower in req.lower():
                        covered.add(req.lower())

        return [t for t in required_topics if t.lower() not in covered]

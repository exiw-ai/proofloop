"""Research pipeline orchestrator extracted from main Orchestrator."""

import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger

from src.application.dto.task_input import TaskInput
from src.application.use_cases.intake_task import IntakeTask
from src.domain.entities.research_result import ResearchResult
from src.domain.ports.agent_port import AgentPort, MessageCallback
from src.domain.ports.task_repo_port import TaskRepoPort
from src.domain.value_objects.task_status import TaskStatus
from src.domain.value_objects.task_type import TaskType

StageCallback = Callable[[str, bool, float], None]

__all__ = [
    "ResearchOrchestrator",
    "ResearchTaskInput",
]


class ResearchTaskInput(TaskInput):
    """Extended task input for research pipeline."""

    research_type: Any = None
    preset: Any = None
    template: Any = None
    repo_context: str = "off"

    def model_post_init(self, __context: object) -> None:
        """Set default values for research-specific fields."""
        from src.domain.value_objects import ReportPackTemplate, ResearchPreset, ResearchType

        super().model_post_init(__context)

        if self.research_type is None:
            object.__setattr__(self, "research_type", ResearchType.GENERAL)
        if self.preset is None:
            object.__setattr__(self, "preset", ResearchPreset.STANDARD)
        if self.template is None:
            object.__setattr__(self, "template", ReportPackTemplate.GENERAL_DEFAULT)
        if not self.goals:
            object.__setattr__(self, "goals", [self.description])


class ResearchOrchestrator:
    """Pipeline orchestrator for research tasks.

    Pipeline:
    Intake -> Strategy -> SourceSelection -> [RepoContext] -> Inventory ->
    Planning -> Conditions -> Approval -> [Baseline] -> Discovery Loop ->
    Deepening -> CitationValidate -> ReportGeneration -> Finalize
    """

    def __init__(
        self,
        agent: AgentPort,
        task_repo: TaskRepoPort,
        state_dir: Path,
    ) -> None:
        self.agent = agent
        self.task_repo = task_repo
        self.state_dir = state_dir

        # Initialize use cases
        self.intake = IntakeTask(task_repo)

    async def run_research(
        self,
        input: ResearchTaskInput,
        on_agent_message: MessageCallback | None = None,
        on_stage: StageCallback | None = None,
    ) -> ResearchResult:
        """Run the research pipeline.

        Pipeline:
        Intake -> Strategy -> SourceSelection -> [RepoContext] -> Inventory ->
        Planning -> Conditions -> Approval -> [Baseline] -> Discovery Loop ->
        Deepening -> CitationValidate -> ReportGeneration -> Finalize

        Args:
            input: Research task input parameters
            on_agent_message: Optional callback for real-time tool action display
            on_stage: Optional callback for stage progress display
        """
        from src.application.use_cases.research import (
            BuildResearchInventory,
            CaptureRepoContext,
            ExecuteDeepening,
            ExecuteDiscovery,
            FinalizeResearch,
            GenerateLLMHandoff,
            GenerateReportPack,
            RunResearchBaseline,
            SelectSources,
            ValidateCitations,
            VerifyResearchConditions,
        )
        from src.infrastructure.research import (
            KnowledgeBaseStore,
            LLMHandoffStore,
            RepoContextStore,
            ReportPackStore,
            VerificationEvidenceStore,
        )

        logger.info(f"Starting research task: {input.description}")

        def stage_start(name: str) -> float:
            if on_stage:
                on_stage(name, True, 0)
            return time.time()

        def stage_end(name: str, start_time: float) -> None:
            if on_stage:
                on_stage(name, False, time.time() - start_time)

        # Setup paths
        research_path = input.workspace_path / ".proofloop" / "research"
        research_path.mkdir(parents=True, exist_ok=True)

        # Initialize stores
        kb_store = KnowledgeBaseStore(research_path)
        report_store = ReportPackStore(research_path)
        handoff_store = LLMHandoffStore(research_path)
        repo_context_store = RepoContextStore(research_path)
        evidence_store = VerificationEvidenceStore(research_path)

        # 1. Intake - create research task
        t = stage_start("research_intake")
        task = await self.intake.execute(input)
        task.task_type = TaskType.RESEARCH
        task.transition_to(TaskStatus.RESEARCH_INTAKE)
        await self.task_repo.save(task)
        stage_end("research_intake", t)
        logger.info(f"Research task created: {task.id}")

        # 2. Strategy / Source Selection
        t = stage_start("research_strategy")
        select_sources = SelectSources(self.agent)
        source_result = await select_sources.run(
            task,
            input.research_type,
            on_message=on_agent_message,
        )
        stage_end("research_strategy", t)
        logger.info(f"Sources selected: {source_result.source_types}")

        # 3. Optional Repo Context
        if input.repo_context != "off":
            t = stage_start("research_repo_context")
            capture_context = CaptureRepoContext(self.agent, repo_context_store)
            await capture_context.run(
                task, input.workspace_path, input.repo_context, on_message=on_agent_message
            )
            stage_end("research_repo_context", t)
            logger.info("Repo context captured")

        # 4. Build Research Inventory
        t = stage_start("research_inventory")
        build_inventory = BuildResearchInventory(self.agent)
        inventory = await build_inventory.run(
            task,
            input.research_type,
            input.preset,
            source_result.source_types,
            on_message=on_agent_message,
        )
        await self.task_repo.save(task)
        stage_end("research_inventory", t)
        logger.info(f"Research inventory built: {len(inventory.queries)} queries")

        # 5. Optional Baseline
        if input.baseline:
            t = stage_start("research_baseline")
            run_baseline = RunResearchBaseline(self.agent, kb_store, research_path)
            await run_baseline.run(task, on_message=on_agent_message)
            stage_end("research_baseline", t)
            logger.info("Research baseline captured")

        # 6. Discovery Loop
        t = stage_start("research_discovery")
        execute_discovery = ExecuteDiscovery(self.agent, kb_store)
        discovery_metrics = await execute_discovery.run(task, on_message=on_agent_message)
        await self.task_repo.save(task)
        stage_end("research_discovery", t)
        logger.info(
            f"Discovery complete: {discovery_metrics.sources_count} sources, "
            f"{discovery_metrics.coverage:.1%} coverage"
        )

        # 7. Deepening / Synthesis
        t = stage_start("research_deepening")
        execute_deepening = ExecuteDeepening(self.agent, kb_store)
        deepening_result = await execute_deepening.run(task, on_message=on_agent_message)
        await self.task_repo.save(task)
        stage_end("research_deepening", t)
        logger.info(
            f"Deepening complete: {deepening_result.synthesis_passes} passes, "
            f"{deepening_result.themes_identified} themes"
        )

        # 8. Report Generation
        t = stage_start("research_report_generation")
        generate_report = GenerateReportPack(self.agent, kb_store, report_store)
        await generate_report.run(task, input.template, on_message=on_agent_message)
        stage_end("research_report_generation", t)
        logger.info("Report pack generated")

        # 9. Citation Validation
        t = stage_start("research_citation_validate")
        validate_citations = ValidateCitations(kb_store, report_store, evidence_store)
        citations_valid = await validate_citations.run(task)
        stage_end("research_citation_validate", t)
        logger.info(f"Citations valid: {citations_valid}")

        # 10. Verify All Conditions
        t = stage_start("research_conditions")
        verify_conditions = VerifyResearchConditions(kb_store, report_store, evidence_store)
        conditions_results = await verify_conditions.run(task)
        stage_end("research_conditions", t)
        logger.info(f"Conditions verified: {conditions_results}")

        # 11. Generate LLM Handoff
        t = stage_start("research_handoff")
        generate_handoff = GenerateLLMHandoff(
            self.agent, kb_store, report_store, handoff_store, repo_context_store
        )
        handoff_path = await generate_handoff.run(
            task, input.workspace_path, on_message=on_agent_message
        )
        stage_end("research_handoff", t)
        logger.info(f"LLM handoff generated: {handoff_path}")

        # 12. Finalize
        t = stage_start("research_finalize")
        finalize_research = FinalizeResearch(kb_store, report_store, research_path)
        result = await finalize_research.run(task, conditions_results)
        await self.task_repo.save(task)
        stage_end("research_finalize", t)
        logger.info(f"Research finalized: {result.status.value}")

        # Copy report to working directory for easy access
        output_dir = input.workspace_path / "research-output"
        output_dir.mkdir(exist_ok=True)
        reports_path = research_path / "reports"
        if reports_path.exists():
            for report_file in reports_path.glob("*.md"):
                shutil.copy(report_file, output_dir / report_file.name)
            logger.info(f"Report copied to: {output_dir}")

        return result

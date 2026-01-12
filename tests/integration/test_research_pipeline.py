"""Integration test for research pipeline completing to report generation."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.orchestrator import Orchestrator
from src.application.research_orchestrator import ResearchTaskInput
from src.domain.ports.agent_port import AgentResult
from src.domain.value_objects import ReportPackTemplate, ResearchPreset, ResearchType


def create_mock_agent_response(content: str) -> AgentResult:
    """Create a mock agent response with the given JSON content."""
    return AgentResult(
        messages=[],
        final_response=content,
        tools_used=[],
    )


@pytest.fixture
def mock_agent() -> AsyncMock:
    """Create a mock agent that returns canned responses for each pipeline
    stage."""
    agent = AsyncMock()

    # Source selection response
    source_selection_response = create_mock_agent_response("""
    {
        "source_types": ["web"],
        "strategy": "Basic web search",
        "reasoning": "Web sources are sufficient for this test"
    }
    """)

    # Inventory response
    inventory_response = create_mock_agent_response("""
    {
        "queries": ["test query"],
        "required_topics": ["topic1"],
        "topic_synonyms": {},
        "sections": ["executive_summary", "findings"]
    }
    """)

    # Discovery response - includes fetched pages and findings that cover our topic
    discovery_response = create_mock_agent_response("""
    {
        "fetched_pages": [
            {
                "url": "https://example.com/test",
                "title": "Test Page",
                "content_summary": "Test content about topic1",
                "source_type": "web"
            }
        ],
        "findings": [
            {
                "source_url": "https://example.com/test",
                "excerpt": "This is a test excerpt",
                "content": "Key finding about topic1",
                "finding_type": "fact",
                "confidence": 0.9,
                "topics": ["topic1"]
            }
        ],
        "notes": "Found relevant sources"
    }
    """)

    # Deepening/synthesis response
    deepening_response = create_mock_agent_response("""
    {
        "themes": [
            {"name": "Theme 1", "description": "Test theme", "supporting_findings": ["finding1"]}
        ],
        "gaps": [],
        "trends": [],
        "suggested_queries": [],
        "synthesis_notes": "Synthesis complete"
    }
    """)

    # Report generation response (simple markdown content)
    report_response = create_mock_agent_response(
        "This is the report section content with a citation [@test_page]."
    )

    # Handoff response
    handoff_response = create_mock_agent_response("""
    {
        "headline": "Test implementation summary",
        "recommended_approach": "Use the findings to guide implementation",
        "risks": ["No major risks"],
        "assumptions": ["Test assumptions"]
    }
    """)

    # Configure the mock to return different responses based on call order
    # The pipeline makes multiple calls, so we use side_effect to cycle through responses
    agent.execute.side_effect = [
        source_selection_response,  # SelectSources
        inventory_response,  # BuildResearchInventory
        discovery_response,  # ExecuteDiscovery (1st iteration - may need multiple)
        deepening_response,  # ExecuteDeepening
        report_response,  # GenerateReportPack - executive_summary
        report_response,  # GenerateReportPack - findings
        report_response,  # GenerateReportPack - recommendations
        report_response,  # GenerateReportPack - sources
        handoff_response,  # GenerateLLMHandoff
    ]

    return agent


@pytest.fixture
def mock_verification_port() -> MagicMock:
    """Create a mock verification port."""
    port = MagicMock()
    port.analyze_project = AsyncMock(return_value=MagicMock(checks=[]))
    return port


@pytest.fixture
def mock_check_runner() -> MagicMock:
    """Create a mock check runner."""
    runner = MagicMock()
    runner.run_checks = AsyncMock(return_value=[])
    return runner


@pytest.fixture
def mock_diff_port() -> MagicMock:
    """Create a mock diff port."""
    port = MagicMock()
    port.get_diff = AsyncMock(return_value="")
    port.stash_all_repos = AsyncMock(return_value=[])
    port.rollback_all = AsyncMock(return_value=[])
    return port


@pytest.fixture
def mock_task_repo() -> MagicMock:
    """Create a mock task repository."""
    repo = MagicMock()
    repo.save = AsyncMock()
    repo.save_plan_approval = AsyncMock()
    repo.save_conditions_approval = AsyncMock()
    return repo


class TestResearchPipelineIntegration:
    @pytest.mark.asyncio
    async def test_research_pipeline_completes_to_report_generation(
        self,
        mock_agent: AsyncMock,
        mock_verification_port: MagicMock,
        mock_check_runner: MagicMock,
        mock_diff_port: MagicMock,
        mock_task_repo: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that the research pipeline completes end-to-end and generates
        report files."""
        # Setup
        state_dir = tmp_path / ".proofloop"
        state_dir.mkdir()

        orchestrator = Orchestrator(
            agent=mock_agent,
            verification_port=mock_verification_port,
            check_runner=mock_check_runner,
            diff_port=mock_diff_port,
            task_repo=mock_task_repo,
            state_dir=state_dir,
        )

        research_input = ResearchTaskInput(
            description="Test research task",
            workspace_path=tmp_path,
            preset=ResearchPreset.MINIMAL,  # Use MINIMAL preset for faster test
            research_type=ResearchType.GENERAL,
            template=ReportPackTemplate.GENERAL_DEFAULT,
            auto_approve=True,
        )

        # Execute
        result = await orchestrator.run_research(research_input)

        # Verify result structure
        assert result is not None
        assert result.task_id is not None
        assert result.report_pack_path == "reports/"
        assert result.handoff_payload_path == "derive_payload.json"

        # Verify report files were generated
        reports_path = tmp_path / ".proofloop" / "research" / "reports"
        assert reports_path.exists(), "Reports directory should exist"

        # Check for expected report files (GENERAL_DEFAULT template)
        expected_files = [
            "executive_summary.md",
            "findings.md",
            "recommendations.md",
            "sources.md",
        ]
        for filename in expected_files:
            file_path = reports_path / filename
            assert file_path.exists(), f"Report file {filename} should exist"
            content = file_path.read_text()
            assert len(content) > 0, f"Report file {filename} should have content"

        # Verify manifest exists
        manifest_path = reports_path / "manifest.json"
        assert manifest_path.exists(), "Manifest should exist"

        # Verify handoff payload exists
        handoff_path = tmp_path / ".proofloop" / "research" / "derive_payload.json"
        assert handoff_path.exists(), "Handoff payload should exist"

        # Verify knowledge base was created
        kb_path = tmp_path / ".proofloop" / "research" / "knowledge_base"
        assert kb_path.exists(), "Knowledge base directory should exist"
        assert (kb_path / "sources").exists(), "Sources directory should exist"

    @pytest.mark.asyncio
    async def test_research_pipeline_with_stage_callback(
        self,
        mock_agent: AsyncMock,
        mock_verification_port: MagicMock,
        mock_check_runner: MagicMock,
        mock_diff_port: MagicMock,
        mock_task_repo: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that stage callbacks are invoked during research pipeline."""
        state_dir = tmp_path / ".proofloop"
        state_dir.mkdir()

        orchestrator = Orchestrator(
            agent=mock_agent,
            verification_port=mock_verification_port,
            check_runner=mock_check_runner,
            diff_port=mock_diff_port,
            task_repo=mock_task_repo,
            state_dir=state_dir,
        )

        research_input = ResearchTaskInput(
            description="Test research task with callbacks",
            workspace_path=tmp_path,
            preset=ResearchPreset.MINIMAL,
            research_type=ResearchType.GENERAL,
            template=ReportPackTemplate.GENERAL_DEFAULT,
            auto_approve=True,
        )

        # Track stage callbacks
        stages_started: list[str] = []
        stages_completed: list[str] = []

        def stage_callback(stage_name: str, is_starting: bool, duration: float) -> None:
            if is_starting:
                stages_started.append(stage_name)
            else:
                stages_completed.append(stage_name)

        # Execute with callback
        await orchestrator.run_research(research_input, on_stage=stage_callback)

        # Verify key stages were executed
        expected_stages = [
            "research_intake",
            "research_strategy",
            "research_inventory",
            "research_discovery",
            "research_deepening",
            "research_report_generation",
            "research_citation_validate",
            "research_conditions",
            "research_handoff",
            "research_finalize",
        ]

        for stage in expected_stages:
            assert stage in stages_started, f"Stage {stage} should have started"
            assert stage in stages_completed, f"Stage {stage} should have completed"

    @pytest.mark.asyncio
    async def test_research_pipeline_generates_metrics(
        self,
        mock_agent: AsyncMock,
        mock_verification_port: MagicMock,
        mock_check_runner: MagicMock,
        mock_diff_port: MagicMock,
        mock_task_repo: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that research pipeline generates proper metrics."""
        state_dir = tmp_path / ".proofloop"
        state_dir.mkdir()

        orchestrator = Orchestrator(
            agent=mock_agent,
            verification_port=mock_verification_port,
            check_runner=mock_check_runner,
            diff_port=mock_diff_port,
            task_repo=mock_task_repo,
            state_dir=state_dir,
        )

        research_input = ResearchTaskInput(
            description="Test research metrics",
            workspace_path=tmp_path,
            preset=ResearchPreset.MINIMAL,
            research_type=ResearchType.GENERAL,
            template=ReportPackTemplate.GENERAL_DEFAULT,
            auto_approve=True,
        )

        result = await orchestrator.run_research(research_input)

        # Verify metrics are present
        assert "sources_count" in result.metrics
        assert "findings_count" in result.metrics
        assert "coverage" in result.metrics
        assert result.iterations_count >= 0

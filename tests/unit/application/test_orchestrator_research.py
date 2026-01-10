"""Unit tests for Orchestrator.run_research method and ResearchTaskInput."""

from src.application.orchestrator import ResearchTaskInput
from src.domain.value_objects import ReportPackTemplate, ResearchPreset, ResearchType


class TestResearchTaskInput:
    def test_research_task_input_defaults(self, tmp_path):
        """ResearchTaskInput should have correct defaults."""
        input_obj = ResearchTaskInput(
            description="Test",
            workspace_path=tmp_path,
        )

        assert input_obj.repo_context == "off"
        assert input_obj.description == "Test"
        assert input_obj.workspace_path == tmp_path

    def test_research_task_input_with_all_fields(self, tmp_path):
        """ResearchTaskInput should accept all fields."""
        input_obj = ResearchTaskInput(
            description="Test research",
            workspace_path=tmp_path,
            preset=ResearchPreset.STANDARD,
            research_type=ResearchType.TECHNICAL,
            template=ReportPackTemplate.GENERAL_DEFAULT,
            repo_context="scan",
            auto_approve=True,
        )

        assert input_obj.preset == ResearchPreset.STANDARD
        assert input_obj.research_type == ResearchType.TECHNICAL
        assert input_obj.repo_context == "scan"
        assert input_obj.auto_approve is True
        assert input_obj.template == ReportPackTemplate.GENERAL_DEFAULT

    def test_research_task_input_minimal_preset(self, tmp_path):
        """ResearchTaskInput should accept minimal preset."""
        input_obj = ResearchTaskInput(
            description="Quick research",
            workspace_path=tmp_path,
            preset=ResearchPreset.MINIMAL,
            research_type=ResearchType.GENERAL,
        )

        assert input_obj.preset == ResearchPreset.MINIMAL
        assert input_obj.research_type == ResearchType.GENERAL

    def test_research_task_input_inherits_from_task_input(self, tmp_path):
        """ResearchTaskInput should inherit TaskInput fields."""
        input_obj = ResearchTaskInput(
            description="Test",
            workspace_path=tmp_path,
            goals=["Goal 1", "Goal 2"],
            constraints=["Constraint 1"],
            auto_approve=True,
            baseline=True,
        )

        assert input_obj.goals == ["Goal 1", "Goal 2"]
        assert input_obj.constraints == ["Constraint 1"]
        assert input_obj.baseline is True

    def test_research_task_input_sources(self, tmp_path):
        """ResearchTaskInput should accept sources."""
        input_obj = ResearchTaskInput(
            description="Test",
            workspace_path=tmp_path,
            sources=[str(tmp_path / "file1.py"), str(tmp_path / "file2.py")],
        )

        assert len(input_obj.sources) == 2

    def test_research_task_input_thorough_preset(self, tmp_path):
        """ResearchTaskInput should accept thorough preset."""
        input_obj = ResearchTaskInput(
            description="Deep research",
            workspace_path=tmp_path,
            preset=ResearchPreset.THOROUGH,
        )

        assert input_obj.preset == ResearchPreset.THOROUGH

    def test_research_task_input_academic_type(self, tmp_path):
        """ResearchTaskInput should accept academic research type."""
        input_obj = ResearchTaskInput(
            description="Academic research on X",
            workspace_path=tmp_path,
            research_type=ResearchType.ACADEMIC,
        )

        assert input_obj.research_type == ResearchType.ACADEMIC

    def test_research_task_input_market_type(self, tmp_path):
        """ResearchTaskInput should accept market research type."""
        input_obj = ResearchTaskInput(
            description="Market analysis for X",
            workspace_path=tmp_path,
            research_type=ResearchType.MARKET,
        )

        assert input_obj.research_type == ResearchType.MARKET

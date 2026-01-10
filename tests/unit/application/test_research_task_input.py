"""Tests for ResearchTaskInput."""

from pathlib import Path

from src.application.orchestrator import ResearchTaskInput
from src.domain.value_objects.report_pack_template import ReportPackTemplate
from src.domain.value_objects.research_preset import ResearchPreset
from src.domain.value_objects.research_type import ResearchType


class TestResearchTaskInput:
    def test_default_values(self, tmp_path: Path) -> None:
        input_ = ResearchTaskInput(
            description="Research topic",
            workspace_path=tmp_path,
        )
        assert input_.research_type == ResearchType.GENERAL
        assert input_.preset == ResearchPreset.STANDARD
        assert input_.template == ReportPackTemplate.GENERAL_DEFAULT
        assert input_.repo_context == "off"

    def test_custom_research_type(self, tmp_path: Path) -> None:
        input_ = ResearchTaskInput(
            description="Research topic",
            workspace_path=tmp_path,
            research_type=ResearchType.TECHNICAL,
        )
        assert input_.research_type == ResearchType.TECHNICAL

    def test_custom_preset(self, tmp_path: Path) -> None:
        input_ = ResearchTaskInput(
            description="Research topic",
            workspace_path=tmp_path,
            preset=ResearchPreset.MINIMAL,
        )
        assert input_.preset == ResearchPreset.MINIMAL

    def test_custom_template(self, tmp_path: Path) -> None:
        input_ = ResearchTaskInput(
            description="Research topic",
            workspace_path=tmp_path,
            template=ReportPackTemplate.TECHNICAL_BEST_PRACTICES,
        )
        assert input_.template == ReportPackTemplate.TECHNICAL_BEST_PRACTICES

    def test_repo_context_modes(self, tmp_path: Path) -> None:
        for mode in ["off", "light", "full"]:
            input_ = ResearchTaskInput(
                description="Research topic",
                workspace_path=tmp_path,
                repo_context=mode,
            )
            assert input_.repo_context == mode

    def test_baseline_enabled(self, tmp_path: Path) -> None:
        input_ = ResearchTaskInput(
            description="Research topic",
            workspace_path=tmp_path,
            baseline=True,
        )
        assert input_.baseline is True

    def test_goals_default_to_description(self, tmp_path: Path) -> None:
        input_ = ResearchTaskInput(
            description="Research topic",
            workspace_path=tmp_path,
        )
        assert input_.goals == ["Research topic"]

    def test_sources_default_to_workspace(self, tmp_path: Path) -> None:
        input_ = ResearchTaskInput(
            description="Research topic",
            workspace_path=tmp_path,
        )
        assert str(tmp_path) in input_.sources[0]

    def test_inherits_from_task_input(self, tmp_path: Path) -> None:
        input_ = ResearchTaskInput(
            description="Research topic",
            workspace_path=tmp_path,
            auto_approve=True,
            timeout_minutes=60,
        )
        assert input_.description == "Research topic"
        assert input_.auto_approve is True
        assert input_.timeout_minutes == 60

    def test_with_custom_goals(self, tmp_path: Path) -> None:
        input_ = ResearchTaskInput(
            description="Research topic",
            workspace_path=tmp_path,
            goals=["Custom goal 1", "Custom goal 2"],
        )
        assert input_.goals == ["Custom goal 1", "Custom goal 2"]

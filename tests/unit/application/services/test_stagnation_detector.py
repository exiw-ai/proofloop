"""Tests for StagnationDetector."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from src.application.services.stagnation_detector import (
    StagnationDetector,
    handle_stagnation,
    is_research_stagnant,
)
from src.domain.entities import Iteration, ResearchInventory, Task
from src.domain.entities.iteration import IterationDecision
from src.domain.value_objects import ResearchPreset, ResearchType, TaskStatus
from src.domain.value_objects.condition_enums import CheckStatus
from src.domain.value_objects.stagnation_action import StagnationAction

# Use fixed UUIDs for check IDs in tests
CHECK_ID_1 = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def detector() -> StagnationDetector:
    return StagnationDetector(limit=3)


def make_iteration(
    changes: list[str] | None = None,
    check_results: dict[UUID, CheckStatus] | None = None,
    metrics: dict[str, float] | None = None,
    number: int = 1,
) -> Iteration:
    return Iteration(
        number=number,
        goal="test",
        changes=changes or [],
        decision=IterationDecision.CONTINUE,
        decision_reason="test",
        check_results=check_results or {},
        metrics=metrics or {},
    )


class TestStagnationDetectorIsStagnating:
    def test_not_stagnating_when_few_iterations(self, detector: StagnationDetector) -> None:
        iterations = [make_iteration(), make_iteration()]
        assert not detector.is_stagnating(iterations)

    def test_not_stagnating_when_has_changes(self, detector: StagnationDetector) -> None:
        iterations = [
            make_iteration(changes=["change1"]),
            make_iteration(changes=["change2"]),
            make_iteration(changes=["change3"]),
        ]
        assert not detector.is_stagnating(iterations)

    def test_stagnating_when_no_changes_no_improvement(self, detector: StagnationDetector) -> None:
        iterations = [
            make_iteration(changes=[], check_results={CHECK_ID_1: CheckStatus.FAIL}),
            make_iteration(changes=[], check_results={CHECK_ID_1: CheckStatus.FAIL}),
            make_iteration(changes=[], check_results={CHECK_ID_1: CheckStatus.FAIL}),
        ]
        assert detector.is_stagnating(iterations)

    def test_not_stagnating_when_check_improved(self, detector: StagnationDetector) -> None:
        iterations = [
            make_iteration(changes=[], check_results={CHECK_ID_1: CheckStatus.FAIL}),
            make_iteration(changes=[], check_results={CHECK_ID_1: CheckStatus.FAIL}),
            make_iteration(changes=[], check_results={CHECK_ID_1: CheckStatus.PASS}),
        ]
        assert not detector.is_stagnating(iterations)


class TestStagnationDetectorGetStagnationCount:
    def test_zero_when_all_have_changes(self, detector: StagnationDetector) -> None:
        iterations = [make_iteration(changes=["change"])]
        assert detector.get_stagnation_count(iterations) == 0

    def test_counts_consecutive_stagnation(self, detector: StagnationDetector) -> None:
        iterations = [
            make_iteration(changes=["change"]),
            make_iteration(changes=[]),
            make_iteration(changes=[]),
        ]
        assert detector.get_stagnation_count(iterations) == 2

    def test_counts_only_recent_stagnation(self, detector: StagnationDetector) -> None:
        iterations = [
            make_iteration(changes=[]),
            make_iteration(changes=["change"]),
            make_iteration(changes=[]),
        ]
        assert detector.get_stagnation_count(iterations) == 1

    def test_counts_with_passing_check(self, detector: StagnationDetector) -> None:
        iterations = [
            make_iteration(changes=[], check_results={CHECK_ID_1: CheckStatus.PASS}),
        ]
        assert detector.get_stagnation_count(iterations) == 0


class TestHasCheckImprovement:
    def test_detects_improvement(self, detector: StagnationDetector) -> None:
        iterations = [
            make_iteration(check_results={CHECK_ID_1: CheckStatus.FAIL}),
            make_iteration(check_results={CHECK_ID_1: CheckStatus.PASS}),
        ]
        assert detector._has_check_improvement(iterations, iterations[1])

    def test_no_improvement_when_still_failing(self, detector: StagnationDetector) -> None:
        iterations = [
            make_iteration(check_results={CHECK_ID_1: CheckStatus.FAIL}),
            make_iteration(check_results={CHECK_ID_1: CheckStatus.FAIL}),
        ]
        assert not detector._has_check_improvement(iterations, iterations[1])

    def test_no_improvement_for_first_iteration(self, detector: StagnationDetector) -> None:
        iterations = [make_iteration(check_results={CHECK_ID_1: CheckStatus.PASS})]
        assert not detector._has_check_improvement(iterations, iterations[0])


class TestIsResearchStagnant:
    def test_not_stagnant_when_few_iterations(self) -> None:
        iterations = [make_iteration(metrics={"sources_count": 5})]
        assert not is_research_stagnant(iterations)

    def test_not_stagnant_when_growing(self) -> None:
        iterations = [
            make_iteration(metrics={"sources_count": 5.0, "coverage": 0.3, "findings_count": 5.0}),
            make_iteration(metrics={"sources_count": 8.0, "coverage": 0.5, "findings_count": 8.0}),
            make_iteration(
                metrics={"sources_count": 12.0, "coverage": 0.6, "findings_count": 12.0}
            ),
            make_iteration(
                metrics={"sources_count": 18.0, "coverage": 0.7, "findings_count": 15.0}
            ),
            make_iteration(
                metrics={"sources_count": 25.0, "coverage": 0.8, "findings_count": 20.0}
            ),
        ]
        assert not is_research_stagnant(iterations)

    def test_stagnant_when_not_growing(self) -> None:
        iterations = [
            make_iteration(
                metrics={"sources_count": 10.0, "coverage": 0.5, "findings_count": 10.0}
            ),
            make_iteration(
                metrics={"sources_count": 10.0, "coverage": 0.5, "findings_count": 10.0}
            ),
            make_iteration(
                metrics={"sources_count": 10.0, "coverage": 0.5, "findings_count": 10.0}
            ),
            make_iteration(
                metrics={"sources_count": 10.0, "coverage": 0.5, "findings_count": 10.0}
            ),
            make_iteration(
                metrics={"sources_count": 10.0, "coverage": 0.5, "findings_count": 10.0}
            ),
        ]
        assert is_research_stagnant(iterations)

    def test_not_stagnant_when_no_metrics(self) -> None:
        iterations = [
            make_iteration(metrics={}),
            make_iteration(metrics={}),
            make_iteration(metrics={}),
            make_iteration(metrics={}),
            make_iteration(metrics={}),
        ]
        assert not is_research_stagnant(iterations)


class TestHandleStagnation:
    @pytest.fixture
    def task_with_inventory(self) -> Task:
        t = Task(
            id=uuid4(),
            description="Test",
            goals=[],
            sources=[],
            status=TaskStatus.RESEARCH_DISCOVERY,
        )
        t.research_inventory = ResearchInventory(
            id=uuid4(),
            task_id=t.id,
            queries=["query"],
            required_topics=["topic"],
            topic_synonyms={},
            sections=["intro"],
            research_type=ResearchType.TECHNICAL,
            preset=ResearchPreset.STANDARD,  # 0.8 coverage threshold
            created_at=datetime.now(UTC),
        )
        return t

    def test_continue_when_not_stagnant(self, task_with_inventory: Task) -> None:
        iterations = [make_iteration(metrics={"sources_count": 5.0, "coverage": 0.3})]
        result = handle_stagnation(task_with_inventory, iterations)
        assert result == StagnationAction.CONTINUE

    def test_continue_when_empty_iterations(self, task_with_inventory: Task) -> None:
        result = handle_stagnation(task_with_inventory, [])
        assert result == StagnationAction.CONTINUE

    def test_finalize_partial_when_close_to_target(self, task_with_inventory: Task) -> None:
        # With STANDARD preset (0.8 coverage threshold), 0.75 is within 90%
        iterations = [
            make_iteration(
                metrics={"sources_count": 10.0, "coverage": 0.75, "findings_count": 10.0}
            ),
            make_iteration(
                metrics={"sources_count": 10.0, "coverage": 0.75, "findings_count": 10.0}
            ),
            make_iteration(
                metrics={"sources_count": 10.0, "coverage": 0.75, "findings_count": 10.0}
            ),
            make_iteration(
                metrics={"sources_count": 10.0, "coverage": 0.75, "findings_count": 10.0}
            ),
            make_iteration(
                metrics={"sources_count": 10.0, "coverage": 0.75, "findings_count": 10.0}
            ),
        ]
        result = handle_stagnation(task_with_inventory, iterations)
        assert result == StagnationAction.FINALIZE_PARTIAL

    def test_relax_conditions_first_time(self, task_with_inventory: Task) -> None:
        iterations = [
            make_iteration(metrics={"sources_count": 5.0, "coverage": 0.2, "findings_count": 5.0}),
            make_iteration(metrics={"sources_count": 5.0, "coverage": 0.2, "findings_count": 5.0}),
            make_iteration(metrics={"sources_count": 5.0, "coverage": 0.2, "findings_count": 5.0}),
            make_iteration(metrics={"sources_count": 5.0, "coverage": 0.2, "findings_count": 5.0}),
            make_iteration(metrics={"sources_count": 5.0, "coverage": 0.2, "findings_count": 5.0}),
        ]
        result = handle_stagnation(task_with_inventory, iterations)
        assert result == StagnationAction.RELAX_CONDITIONS

    def test_escalate_when_already_relaxed(self, task_with_inventory: Task) -> None:
        task_with_inventory.conditions_relaxed = True
        iterations = [
            make_iteration(metrics={"sources_count": 5.0, "coverage": 0.2, "findings_count": 5.0}),
            make_iteration(metrics={"sources_count": 5.0, "coverage": 0.2, "findings_count": 5.0}),
            make_iteration(metrics={"sources_count": 5.0, "coverage": 0.2, "findings_count": 5.0}),
            make_iteration(metrics={"sources_count": 5.0, "coverage": 0.2, "findings_count": 5.0}),
            make_iteration(metrics={"sources_count": 5.0, "coverage": 0.2, "findings_count": 5.0}),
        ]
        result = handle_stagnation(task_with_inventory, iterations)
        assert result == StagnationAction.ESCALATE_TO_USER

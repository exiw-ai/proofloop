"""Tests for StagnationDetector service."""

from uuid import UUID, uuid4

import pytest

from src.application.services.stagnation_detector import StagnationDetector
from src.domain.entities.iteration import Iteration, IterationDecision
from src.domain.value_objects.condition_enums import CheckStatus


@pytest.fixture
def detector() -> StagnationDetector:
    return StagnationDetector(limit=3)


# Use fixed UUIDs for testing
TEST_CHECK_ID = uuid4()
TEST_CHECK_ID2 = uuid4()


def make_iteration(
    iteration_num: int,
    changes: list[str] | None = None,
    check_results: dict[UUID, CheckStatus] | None = None,
) -> Iteration:
    """Helper to create test iterations."""
    return Iteration(
        number=iteration_num,
        goal="Test goal",
        changes=changes if changes is not None else [],
        check_results=check_results or {},
        decision=IterationDecision.CONTINUE,
        decision_reason="test",
    )


class TestIsStagnating:
    """Tests for is_stagnating method."""

    def test_not_stagnating_with_few_iterations(self, detector: StagnationDetector) -> None:
        """Test not stagnating when less than limit iterations."""
        iterations = [make_iteration(1), make_iteration(2)]
        assert detector.is_stagnating(iterations) is False

    def test_not_stagnating_with_recent_changes(self, detector: StagnationDetector) -> None:
        """Test not stagnating when recent iterations have changes."""
        iterations = [
            make_iteration(1, changes=[]),
            make_iteration(2, changes=[]),
            make_iteration(3, changes=["file.py"]),
        ]
        assert detector.is_stagnating(iterations) is False

    def test_stagnating_with_no_changes(self, detector: StagnationDetector) -> None:
        """Test stagnating when no recent changes."""
        iterations = [
            make_iteration(1, changes=[]),
            make_iteration(2, changes=[]),
            make_iteration(3, changes=[]),
        ]
        assert detector.is_stagnating(iterations) is True

    def test_not_stagnating_with_check_improvement(self, detector: StagnationDetector) -> None:
        """Test not stagnating when check improves from fail to pass."""
        iterations = [
            make_iteration(1, changes=[], check_results={TEST_CHECK_ID: CheckStatus.FAIL}),
            make_iteration(2, changes=[], check_results={TEST_CHECK_ID: CheckStatus.PASS}),
            make_iteration(3, changes=[], check_results={TEST_CHECK_ID: CheckStatus.PASS}),
        ]
        assert detector.is_stagnating(iterations) is False


class TestGetStagnationCount:
    """Tests for get_stagnation_count method."""

    def test_zero_count_with_recent_changes(self, detector: StagnationDetector) -> None:
        """Test zero count when most recent has changes."""
        iterations = [
            make_iteration(1, changes=[]),
            make_iteration(2, changes=["file.py"]),
        ]
        assert detector.get_stagnation_count(iterations) == 0

    def test_count_consecutive_stagnation(self, detector: StagnationDetector) -> None:
        """Test counting consecutive stagnant iterations."""
        iterations = [
            make_iteration(1, changes=["file.py"]),
            make_iteration(2, changes=[]),
            make_iteration(3, changes=[]),
        ]
        assert detector.get_stagnation_count(iterations) == 2

    def test_count_stops_at_passing_check(self, detector: StagnationDetector) -> None:
        """Test count stops when iteration has passing check."""
        iterations = [
            make_iteration(1, changes=[]),
            make_iteration(2, changes=[], check_results={TEST_CHECK_ID: CheckStatus.PASS}),
            make_iteration(3, changes=[]),
        ]
        assert detector.get_stagnation_count(iterations) == 1


class TestHasCheckImprovement:
    """Tests for _has_check_improvement method."""

    def test_improvement_from_fail_to_pass(self, detector: StagnationDetector) -> None:
        """Test detecting improvement from fail to pass."""
        iterations = [
            make_iteration(1, check_results={TEST_CHECK_ID: CheckStatus.FAIL}),
            make_iteration(2, check_results={TEST_CHECK_ID: CheckStatus.PASS}),
        ]
        assert detector._has_check_improvement(iterations, iterations[1]) is True

    def test_no_improvement_both_fail(self, detector: StagnationDetector) -> None:
        """Test no improvement when both fail."""
        iterations = [
            make_iteration(1, check_results={TEST_CHECK_ID: CheckStatus.FAIL}),
            make_iteration(2, check_results={TEST_CHECK_ID: CheckStatus.FAIL}),
        ]
        assert detector._has_check_improvement(iterations, iterations[1]) is False

    def test_no_improvement_first_iteration(self, detector: StagnationDetector) -> None:
        """Test no improvement possible for first iteration."""
        iterations = [
            make_iteration(1, check_results={TEST_CHECK_ID: CheckStatus.PASS}),
        ]
        assert detector._has_check_improvement(iterations, iterations[0]) is False

    def test_improvement_with_new_check(self, detector: StagnationDetector) -> None:
        """Test no improvement when check is new."""
        iterations = [
            make_iteration(1, check_results={}),
            make_iteration(2, check_results={TEST_CHECK_ID: CheckStatus.PASS}),
        ]
        # New check passing is not considered improvement from fail
        assert detector._has_check_improvement(iterations, iterations[1]) is False


class TestHasAnyPass:
    """Tests for _has_any_pass method."""

    def test_has_pass(self, detector: StagnationDetector) -> None:
        """Test detecting any passing check."""
        iteration = make_iteration(
            1,
            check_results={
                TEST_CHECK_ID: CheckStatus.FAIL,
                TEST_CHECK_ID2: CheckStatus.PASS,
            },
        )
        assert detector._has_any_pass(iteration) is True

    def test_no_pass(self, detector: StagnationDetector) -> None:
        """Test no passing checks."""
        iteration = make_iteration(
            1,
            check_results={
                TEST_CHECK_ID: CheckStatus.FAIL,
                TEST_CHECK_ID2: CheckStatus.FAIL,
            },
        )
        assert detector._has_any_pass(iteration) is False

    def test_empty_results(self, detector: StagnationDetector) -> None:
        """Test with no check results."""
        iteration = make_iteration(1, check_results={})
        assert detector._has_any_pass(iteration) is False

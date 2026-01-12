import time
from collections.abc import Callable
from typing import ClassVar

from pydantic import BaseModel


# Default clock uses time.time(), can be overridden for testing
def _default_clock() -> float:
    return time.time()


class Budget(BaseModel):
    wall_time_limit_s: int = 36000  # 10 hours default
    stagnation_limit: int = 3
    max_iterations: int = 50
    quality_loop_limit: int = 3

    elapsed_s: int = 0
    iteration_count: int = 0
    stagnation_count: int = 0
    quality_loop_count: int = 0
    start_timestamp: float = 0.0  # Set when delivery starts

    # Class-level clock for testability (not serialized)
    _clock: ClassVar[Callable[[], float]] = _default_clock

    @classmethod
    def set_clock(cls, clock: Callable[[], float]) -> None:
        """Set custom clock for testing."""
        cls._clock = clock

    @classmethod
    def reset_clock(cls) -> None:
        """Reset to default clock."""
        cls._clock = _default_clock

    def is_exhausted(self) -> bool:
        return (
            self.elapsed_s >= self.wall_time_limit_s
            or self.iteration_count >= self.max_iterations
            or self.stagnation_count >= self.stagnation_limit
            or self.quality_loop_count >= self.quality_loop_limit
        )

    def start_tracking(self) -> None:
        """Start tracking wall time.

        Call once when delivery begins.
        """
        self.start_timestamp = Budget._clock()

    def record_iteration(self, is_progress: bool) -> None:
        """Record iteration and update elapsed time automatically."""
        if self.start_timestamp > 0:
            self.elapsed_s = int(Budget._clock() - self.start_timestamp)
        self.iteration_count += 1
        if is_progress:
            self.stagnation_count = 0
        else:
            self.stagnation_count += 1

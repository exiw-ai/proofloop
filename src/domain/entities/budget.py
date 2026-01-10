import time

from pydantic import BaseModel


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
        self.start_timestamp = time.time()

    def record_iteration(self, is_progress: bool) -> None:
        """Record iteration and update elapsed time automatically."""
        if self.start_timestamp > 0:
            self.elapsed_s = int(time.time() - self.start_timestamp)
        self.iteration_count += 1
        if is_progress:
            self.stagnation_count = 0
        else:
            self.stagnation_count += 1

from pathlib import Path
from uuid import UUID


class TaskPathBuilder:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir

    def task_dir(self, task_id: UUID) -> Path:
        return self.state_dir / "tasks" / task_id.hex

    def lock_path(self, task_id: UUID) -> Path:
        return self.task_dir(task_id) / ".lock"

    def iteration_dir(self, task_id: UUID, iteration_num: int) -> Path:
        return self.task_dir(task_id) / "iterations" / f"{iteration_num:04d}"

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

import aiofiles
from filelock import FileLock
from loguru import logger

from src.domain.ports.task_repo_port import TaskRepoPort

if TYPE_CHECKING:
    from src.domain.entities.condition import Condition
    from src.domain.entities.plan import Plan
    from src.domain.entities.task import Task
    from src.domain.entities.verification_inventory import VerificationInventory


class JsonTaskRepo(TaskRepoPort):
    """File-based JSON storage implementation of TaskRepoPort."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir

    def _task_dir(self, task_id: UUID) -> Path:
        return self.state_dir / "tasks" / task_id.hex

    def _lock_path(self, task_id: UUID) -> Path:
        return self._task_dir(task_id) / ".lock"

    async def _atomic_write(self, path: Path, content: str) -> None:
        """Atomic write: write to temp file, then rename."""
        path.parent.mkdir(parents=True, exist_ok=True)

        # Create temp file in same directory to ensure same filesystem for rename
        fd, temp_path_str = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=".tmp_",
            suffix=".json",
        )
        temp_path = Path(temp_path_str)

        try:
            async with aiofiles.open(fd, mode="w", encoding="utf-8", closefd=True) as f:
                await f.write(content)
            # Atomic rename
            await asyncio.to_thread(temp_path.rename, path)
            logger.debug("Atomic write completed: {}", path)
        except Exception:
            # Clean up temp file on failure
            if temp_path.exists():
                temp_path.unlink()
            raise

    async def _read_json(self, path: Path) -> dict[str, Any] | None:
        """Read JSON file, return None if not exists."""
        if not path.exists():
            return None
        async with aiofiles.open(path, encoding="utf-8") as f:
            content = await f.read()
        return json.loads(content)  # type: ignore[no-any-return]

    async def save(self, task: Task) -> None:
        """Save task snapshot for resume.

        Uses atomic write with file lock.
        """
        task_dir = self._task_dir(task.id)
        task_dir.mkdir(parents=True, exist_ok=True)

        lock = FileLock(self._lock_path(task.id))
        with lock:
            task_path = task_dir / "task.json"
            await self._atomic_write(task_path, task.model_dump_json(indent=2))
            logger.info("Saved task snapshot: {}", task.id)

    async def load(self, task_id: UUID) -> Task | None:
        """Load task by ID."""
        from src.domain.entities.task import Task

        task_dir = self._task_dir(task_id)
        task_path = task_dir / "task.json"

        if not task_path.exists():
            logger.debug("Task not found: {}", task_id)
            return None

        lock = FileLock(self._lock_path(task_id))
        with lock:
            data = await self._read_json(task_path)
            if data is None:
                return None
            return Task.model_validate(data)

    async def list_tasks(self) -> list[UUID]:
        """List all task IDs."""
        tasks_dir = self.state_dir / "tasks"
        if not tasks_dir.exists():
            return []

        task_ids: list[UUID] = []
        for task_dir in tasks_dir.iterdir():
            if task_dir.is_dir() and (task_dir / "task.json").exists():
                try:
                    task_ids.append(UUID(hex=task_dir.name))
                except ValueError:
                    logger.warning("Invalid task directory name: {}", task_dir.name)
        return task_ids

    async def save_conditions_approval(
        self,
        task_id: UUID,
        conditions: list[Condition],
    ) -> None:
        """Save conditions approval state with versioning."""
        task_dir = self._task_dir(task_id)
        approvals_dir = task_dir / "approvals"
        approvals_dir.mkdir(parents=True, exist_ok=True)

        lock = FileLock(self._lock_path(task_id))
        with lock:
            conditions_path = approvals_dir / "conditions.json"

            # Load existing versioned data
            existing = await self._read_json(conditions_path)
            if existing is None:
                existing = {
                    "current_version": 0,
                    "approved_version": None,
                    "versions": [],
                }

            # Increment version
            new_version = existing["current_version"] + 1

            # Serialize conditions
            conditions_data = [c.model_dump(mode="json") for c in conditions]

            # Check if any condition is approved
            has_approved = any(c.approval_status.value == "approved" for c in conditions)

            # Add new version
            existing["versions"].append(
                {
                    "version": new_version,
                    "data": conditions_data,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            existing["current_version"] = new_version

            if has_approved:
                existing["approved_version"] = new_version

            await self._atomic_write(conditions_path, json.dumps(existing, indent=2))
            logger.info("Saved conditions approval v{} for task {}", new_version, task_id)

    async def save_plan_approval(self, task_id: UUID, plan: Plan) -> None:
        """Save plan approval state with versioning."""
        task_dir = self._task_dir(task_id)
        approvals_dir = task_dir / "approvals"
        approvals_dir.mkdir(parents=True, exist_ok=True)

        lock = FileLock(self._lock_path(task_id))
        with lock:
            plan_path = approvals_dir / "plan.json"

            # Load existing versioned data
            existing = await self._read_json(plan_path)
            if existing is None:
                existing = {
                    "current_version": 0,
                    "approved_version": None,
                    "versions": [],
                }

            # Increment version
            new_version = existing["current_version"] + 1

            # Add new version
            existing["versions"].append(
                {
                    "version": new_version,
                    "data": plan.model_dump(mode="json"),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            existing["current_version"] = new_version

            # Check if plan is approved
            if plan.approved:
                existing["approved_version"] = new_version

            await self._atomic_write(plan_path, json.dumps(existing, indent=2))
            logger.info("Saved plan approval v{} for task {}", new_version, task_id)

    async def save_inventory(
        self,
        task_id: UUID,
        inventory: VerificationInventory,
    ) -> None:
        """Save verification inventory."""
        task_dir = self._task_dir(task_id)
        inventory_dir = task_dir / "inventory"
        inventory_dir.mkdir(parents=True, exist_ok=True)

        lock = FileLock(self._lock_path(task_id))
        with lock:
            inventory_path = inventory_dir / "inventory.json"
            await self._atomic_write(inventory_path, inventory.model_dump_json(indent=2))
            logger.info("Saved inventory for task {}", task_id)

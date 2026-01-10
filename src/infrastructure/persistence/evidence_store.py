from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import aiofiles
from filelock import FileLock
from loguru import logger


class EvidenceStore:
    """Storage for check evidence artifacts."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir

    def _task_dir(self, task_id: UUID) -> Path:
        return self.state_dir / "tasks" / task_id.hex

    def _lock_path(self, task_id: UUID) -> Path:
        return self._task_dir(task_id) / ".lock"

    def _iteration_dir(self, task_id: UUID, iteration_num: int) -> Path:
        return self._task_dir(task_id) / "iterations" / f"{iteration_num:04d}"

    def _timestamp_str(self) -> str:
        return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")

    async def _atomic_write(self, path: Path, content: str) -> None:
        """Atomic write: write to temp file, then rename."""
        path.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_path_str = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=".tmp_",
            suffix=path.suffix,
        )
        temp_path = Path(temp_path_str)

        try:
            async with aiofiles.open(fd, mode="w", encoding="utf-8", closefd=True) as f:
                await f.write(content)
            await asyncio.to_thread(temp_path.rename, path)
            logger.debug("Atomic write completed: {}", path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    async def save_check_evidence(
        self,
        task_id: UUID,
        iteration_num: int,
        condition_id: UUID,
        result: dict[str, Any],
        log_content: str,
    ) -> tuple[str, str]:
        """
        Save check evidence to: iterations/<n>/checks/<condition_id>/<ts>.json and .log

        Also updates last.json index.

        Returns:
            Tuple of (artifact_path_rel, log_path_rel) relative to state_dir
        """
        iteration_dir = self._iteration_dir(task_id, iteration_num)
        checks_dir = iteration_dir / "checks" / condition_id.hex
        checks_dir.mkdir(parents=True, exist_ok=True)

        ts = self._timestamp_str()
        result_filename = f"{ts}.json"
        log_filename = f"{ts}.log"

        lock = FileLock(self._lock_path(task_id))
        with lock:
            # Save result JSON
            result_path = checks_dir / result_filename
            await self._atomic_write(result_path, json.dumps(result, indent=2))

            # Save log content
            log_path = checks_dir / log_filename
            await self._atomic_write(log_path, log_content)

            # Update last.json index
            last_index = {
                "latest_result": result_filename,
                "latest_log": log_filename,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            last_path = checks_dir / "last.json"
            await self._atomic_write(last_path, json.dumps(last_index, indent=2))

            logger.info(
                "Saved check evidence for condition {} in iteration {}",
                condition_id,
                iteration_num,
            )

        # Return paths relative to state_dir
        artifact_path_rel = str(result_path.relative_to(self.state_dir))
        log_path_rel = str(log_path.relative_to(self.state_dir))

        return artifact_path_rel, log_path_rel

    async def save_baseline_evidence(
        self,
        task_id: UUID,
        check_id: UUID,
        result: dict[str, Any],
        log_content: str,
    ) -> tuple[str, str]:
        """
        Save baseline evidence to: inventory/baseline/<check_id>/<ts>.json and .log

        Returns:
            Tuple of (artifact_path_rel, log_path_rel) relative to state_dir
        """
        task_dir = self._task_dir(task_id)
        baseline_dir = task_dir / "inventory" / "baseline" / check_id.hex
        baseline_dir.mkdir(parents=True, exist_ok=True)

        ts = self._timestamp_str()
        result_filename = f"{ts}.json"
        log_filename = f"{ts}.log"

        lock = FileLock(self._lock_path(task_id))
        with lock:
            # Save result JSON
            result_path = baseline_dir / result_filename
            await self._atomic_write(result_path, json.dumps(result, indent=2))

            # Save log content
            log_path = baseline_dir / log_filename
            await self._atomic_write(log_path, log_content)

            logger.info("Saved baseline evidence for check {}", check_id)

        # Return paths relative to state_dir
        artifact_path_rel = str(result_path.relative_to(self.state_dir))
        log_path_rel = str(log_path.relative_to(self.state_dir))

        return artifact_path_rel, log_path_rel

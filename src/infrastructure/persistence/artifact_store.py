from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

import aiofiles
from filelock import FileLock
from loguru import logger


class ArtifactStore:
    """Storage for task artifacts: timeline, iterations, diffs, transcripts, cache."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir

    def _task_dir(self, task_id: UUID) -> Path:
        return self.state_dir / "tasks" / task_id.hex

    def _lock_path(self, task_id: UUID) -> Path:
        return self._task_dir(task_id) / ".lock"

    def _iteration_dir(self, task_id: UUID, iteration_num: int) -> Path:
        return self._task_dir(task_id) / "iterations" / f"{iteration_num:04d}"

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

    async def _append_line(self, path: Path, line: str) -> None:
        """Append a line to a file with file lock."""
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, mode="a", encoding="utf-8") as f:
            await f.write(line + "\n")

    async def append_timeline(self, task_id: UUID, event: dict[str, Any]) -> None:
        """Append event to timeline.jsonl."""
        task_dir = self._task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)

        lock = FileLock(self._lock_path(task_id))
        with lock:
            timeline_path = task_dir / "timeline.jsonl"
            line = json.dumps(event, separators=(",", ":"))
            await self._append_line(timeline_path, line)
            logger.debug("Appended timeline event for task {}", task_id)

    async def save_iteration(
        self,
        task_id: UUID,
        iteration_num: int,
        data: dict[str, Any],
    ) -> None:
        """Save iteration data to iterations/<n>/iteration.json."""
        iteration_dir = self._iteration_dir(task_id, iteration_num)

        lock = FileLock(self._lock_path(task_id))
        with lock:
            iteration_path = iteration_dir / "iteration.json"
            await self._atomic_write(iteration_path, json.dumps(data, indent=2))
            logger.info("Saved iteration {} for task {}", iteration_num, task_id)

    async def save_agent_events(
        self,
        task_id: UUID,
        iteration_num: int,
        events: list[dict[str, Any]],
    ) -> None:
        """Save agent events to iterations/<n>/agent/events.jsonl."""
        iteration_dir = self._iteration_dir(task_id, iteration_num)
        agent_dir = iteration_dir / "agent"
        agent_dir.mkdir(parents=True, exist_ok=True)

        lock = FileLock(self._lock_path(task_id))
        with lock:
            events_path = agent_dir / "events.jsonl"
            lines = [json.dumps(event, separators=(",", ":")) for event in events]
            await self._atomic_write(events_path, "\n".join(lines) + "\n")
            logger.debug("Saved {} agent events for iteration {}", len(events), iteration_num)

    async def save_agent_transcript(
        self,
        task_id: UUID,
        iteration_num: int,
        transcript: str,
    ) -> None:
        """Save agent transcript to iterations/<n>/agent/transcript.md."""
        iteration_dir = self._iteration_dir(task_id, iteration_num)
        agent_dir = iteration_dir / "agent"
        agent_dir.mkdir(parents=True, exist_ok=True)

        lock = FileLock(self._lock_path(task_id))
        with lock:
            transcript_path = agent_dir / "transcript.md"
            await self._atomic_write(transcript_path, transcript)
            logger.debug("Saved transcript for iteration {}", iteration_num)

    async def save_diff(
        self,
        task_id: UUID,
        iteration_num: int,
        diff: str,
        patch: str,
    ) -> None:
        """Save diff and patch to iterations/<n>/diffs/worktree.diff and
        .patch."""
        iteration_dir = self._iteration_dir(task_id, iteration_num)
        diffs_dir = iteration_dir / "diffs"
        diffs_dir.mkdir(parents=True, exist_ok=True)

        lock = FileLock(self._lock_path(task_id))
        with lock:
            diff_path = diffs_dir / "worktree.diff"
            patch_path = diffs_dir / "worktree.patch"
            await self._atomic_write(diff_path, diff)
            await self._atomic_write(patch_path, patch)
            logger.debug("Saved diff/patch for iteration {}", iteration_num)

    async def save_final_result(
        self,
        task_id: UUID,
        result: dict[str, Any],
        diff: str,
        patch: str,
    ) -> None:
        """Save final result to final/final_result.json, final.diff,
        final.patch."""
        task_dir = self._task_dir(task_id)
        final_dir = task_dir / "final"
        final_dir.mkdir(parents=True, exist_ok=True)

        lock = FileLock(self._lock_path(task_id))
        with lock:
            result_path = final_dir / "final_result.json"
            diff_path = final_dir / "final.diff"
            patch_path = final_dir / "final.patch"

            await self._atomic_write(result_path, json.dumps(result, indent=2))
            await self._atomic_write(diff_path, diff)
            await self._atomic_write(patch_path, patch)
            logger.info("Saved final result for task {}", task_id)

    async def save_cache(self, task_id: UUID, key: str, data: dict[str, Any]) -> None:
        """Save cache data to cache/<key>.json."""
        task_dir = self._task_dir(task_id)
        cache_dir = task_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        lock = FileLock(self._lock_path(task_id))
        with lock:
            cache_path = cache_dir / f"{key}.json"
            await self._atomic_write(cache_path, json.dumps(data, indent=2))
            logger.debug("Saved cache '{}' for task {}", key, task_id)

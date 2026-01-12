from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import aiofiles
from loguru import logger

from src.infrastructure.persistence._paths import TaskPathBuilder
from src.infrastructure.persistence.atomic_io import atomic_write


class ArtifactStore:
    """Storage for task artifacts: timeline, iterations, diffs, transcripts, cache."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self._paths = TaskPathBuilder(self.state_dir)

    async def _append_line(self, path: Path, line: str) -> None:
        """Append a line to a file with file lock."""
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, mode="a", encoding="utf-8") as f:
            await f.write(line + "\n")

    async def append_timeline(self, task_id: UUID, event: dict[str, Any]) -> None:
        """Append event to timeline.jsonl."""
        task_dir = self._paths.task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)

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
        iteration_dir = self._paths.iteration_dir(task_id, iteration_num)

        iteration_path = iteration_dir / "iteration.json"
        await atomic_write(iteration_path, json.dumps(data, indent=2))
        logger.info("Saved iteration {} for task {}", iteration_num, task_id)

    async def save_agent_events(
        self,
        task_id: UUID,
        iteration_num: int,
        events: list[dict[str, Any]],
    ) -> None:
        """Save agent events to iterations/<n>/agent/events.jsonl."""
        iteration_dir = self._paths.iteration_dir(task_id, iteration_num)
        agent_dir = iteration_dir / "agent"
        agent_dir.mkdir(parents=True, exist_ok=True)

        events_path = agent_dir / "events.jsonl"
        lines = [json.dumps(event, separators=(",", ":")) for event in events]
        await atomic_write(events_path, "\n".join(lines) + "\n")
        logger.debug("Saved {} agent events for iteration {}", len(events), iteration_num)

    async def save_agent_transcript(
        self,
        task_id: UUID,
        iteration_num: int,
        transcript: str,
    ) -> None:
        """Save agent transcript to iterations/<n>/agent/transcript.md."""
        iteration_dir = self._paths.iteration_dir(task_id, iteration_num)
        agent_dir = iteration_dir / "agent"
        agent_dir.mkdir(parents=True, exist_ok=True)

        transcript_path = agent_dir / "transcript.md"
        await atomic_write(transcript_path, transcript)
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
        iteration_dir = self._paths.iteration_dir(task_id, iteration_num)
        diffs_dir = iteration_dir / "diffs"
        diffs_dir.mkdir(parents=True, exist_ok=True)

        diff_path = diffs_dir / "worktree.diff"
        patch_path = diffs_dir / "worktree.patch"
        await atomic_write(diff_path, diff)
        await atomic_write(patch_path, patch)
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
        task_dir = self._paths.task_dir(task_id)
        final_dir = task_dir / "final"
        final_dir.mkdir(parents=True, exist_ok=True)

        result_path = final_dir / "final_result.json"
        diff_path = final_dir / "final.diff"
        patch_path = final_dir / "final.patch"

        await atomic_write(result_path, json.dumps(result, indent=2))
        await atomic_write(diff_path, diff)
        await atomic_write(patch_path, patch)
        logger.info("Saved final result for task {}", task_id)

    async def save_cache(self, task_id: UUID, key: str, data: dict[str, Any]) -> None:
        """Save cache data to cache/<key>.json."""
        # Validate key to prevent path traversal
        if "/" in key or "\\" in key or ".." in key:
            raise ValueError(f"Invalid cache key contains path separators: {key}")

        task_dir = self._paths.task_dir(task_id)
        cache_dir = task_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        cache_path = cache_dir / f"{key}.json"
        await atomic_write(cache_path, json.dumps(data, indent=2))
        logger.debug("Saved cache '{}' for task {}", key, task_id)

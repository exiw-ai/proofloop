"""Tests for ArtifactStore infrastructure component."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from src.infrastructure.persistence.artifact_store import ArtifactStore
from src.infrastructure.persistence.atomic_io import atomic_write


@pytest.fixture
def artifact_store(tmp_path: Path) -> ArtifactStore:
    """Create an artifact store with temporary directory."""
    return ArtifactStore(state_dir=tmp_path)


class TestArtifactStorePaths:
    """Tests for internal path methods."""

    def test_task_dir(self, artifact_store: ArtifactStore, tmp_path: Path) -> None:
        """Test _paths.task_dir returns correct path."""
        task_id = uuid4()
        expected = tmp_path / "tasks" / task_id.hex
        assert artifact_store._paths.task_dir(task_id) == expected

    def test_lock_path(self, artifact_store: ArtifactStore, tmp_path: Path) -> None:
        """Test _paths.lock_path returns correct path."""
        task_id = uuid4()
        expected = tmp_path / "tasks" / task_id.hex / ".lock"
        assert artifact_store._paths.lock_path(task_id) == expected

    def test_iteration_dir(self, artifact_store: ArtifactStore, tmp_path: Path) -> None:
        """Test _paths.iteration_dir returns correct path."""
        task_id = uuid4()
        expected = tmp_path / "tasks" / task_id.hex / "iterations" / "0001"
        assert artifact_store._paths.iteration_dir(task_id, 1) == expected

    def test_iteration_dir_formatting(self, artifact_store: ArtifactStore, tmp_path: Path) -> None:
        """Test iteration directory uses 4-digit formatting."""
        task_id = uuid4()
        # Iteration 99 should be 0099
        expected = tmp_path / "tasks" / task_id.hex / "iterations" / "0099"
        assert artifact_store._paths.iteration_dir(task_id, 99) == expected


class TestAppendTimeline:
    """Tests for timeline appending."""

    @pytest.mark.asyncio
    async def test_append_timeline_creates_file(self, artifact_store: ArtifactStore) -> None:
        """Test appending timeline creates file and directories."""
        task_id = uuid4()
        event = {"type": "test", "timestamp": "2024-01-01T00:00:00Z"}

        await artifact_store.append_timeline(task_id, event)

        timeline_path = artifact_store._paths.task_dir(task_id) / "timeline.jsonl"
        assert timeline_path.exists()
        content = timeline_path.read_text()
        assert '"type":"test"' in content

    @pytest.mark.asyncio
    async def test_append_timeline_multiple_events(self, artifact_store: ArtifactStore) -> None:
        """Test appending multiple timeline events."""
        task_id = uuid4()

        await artifact_store.append_timeline(task_id, {"type": "event1"})
        await artifact_store.append_timeline(task_id, {"type": "event2"})

        timeline_path = artifact_store._paths.task_dir(task_id) / "timeline.jsonl"
        lines = timeline_path.read_text().strip().split("\n")
        assert len(lines) == 2


class TestSaveIteration:
    """Tests for saving iteration data."""

    @pytest.mark.asyncio
    async def test_save_iteration(self, artifact_store: ArtifactStore) -> None:
        """Test saving iteration data."""
        task_id = uuid4()
        data = {"iteration": 1, "status": "completed", "tools_used": ["Read", "Edit"]}

        await artifact_store.save_iteration(task_id, 1, data)

        iteration_path = artifact_store._paths.iteration_dir(task_id, 1) / "iteration.json"
        assert iteration_path.exists()

        saved_data = json.loads(iteration_path.read_text())
        assert saved_data["iteration"] == 1
        assert saved_data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_save_multiple_iterations(self, artifact_store: ArtifactStore) -> None:
        """Test saving multiple iterations."""
        task_id = uuid4()

        await artifact_store.save_iteration(task_id, 1, {"iteration": 1})
        await artifact_store.save_iteration(task_id, 2, {"iteration": 2})

        iter1_path = artifact_store._paths.iteration_dir(task_id, 1) / "iteration.json"
        iter2_path = artifact_store._paths.iteration_dir(task_id, 2) / "iteration.json"

        assert iter1_path.exists()
        assert iter2_path.exists()


class TestSaveAgentEvents:
    """Tests for saving agent events."""

    @pytest.mark.asyncio
    async def test_save_agent_events(self, artifact_store: ArtifactStore) -> None:
        """Test saving agent events."""
        task_id = uuid4()
        events = [
            {"type": "tool_use", "tool": "Read"},
            {"type": "message", "content": "Done"},
        ]

        await artifact_store.save_agent_events(task_id, 1, events)

        events_path = artifact_store._paths.iteration_dir(task_id, 1) / "agent" / "events.jsonl"
        assert events_path.exists()

        lines = events_path.read_text().strip().split("\n")
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_save_agent_events_empty(self, artifact_store: ArtifactStore) -> None:
        """Test saving empty events list."""
        task_id = uuid4()

        await artifact_store.save_agent_events(task_id, 1, [])

        events_path = artifact_store._paths.iteration_dir(task_id, 1) / "agent" / "events.jsonl"
        assert events_path.exists()


class TestSaveAgentTranscript:
    """Tests for saving agent transcripts."""

    @pytest.mark.asyncio
    async def test_save_agent_transcript(self, artifact_store: ArtifactStore) -> None:
        """Test saving agent transcript."""
        task_id = uuid4()
        transcript = "# Transcript\n\n## User\nFix the bug\n\n## Agent\nI'll fix it."

        await artifact_store.save_agent_transcript(task_id, 1, transcript)

        transcript_path = (
            artifact_store._paths.iteration_dir(task_id, 1) / "agent" / "transcript.md"
        )
        assert transcript_path.exists()
        assert transcript_path.read_text() == transcript


class TestSaveDiff:
    """Tests for saving diffs."""

    @pytest.mark.asyncio
    async def test_save_diff(self, artifact_store: ArtifactStore) -> None:
        """Test saving diff and patch."""
        task_id = uuid4()
        diff = "diff --git a/file.py b/file.py\n..."
        patch = "--- a/file.py\n+++ b/file.py\n..."

        await artifact_store.save_diff(task_id, 1, diff, patch)

        diffs_dir = artifact_store._paths.iteration_dir(task_id, 1) / "diffs"
        diff_path = diffs_dir / "worktree.diff"
        patch_path = diffs_dir / "worktree.patch"

        assert diff_path.exists()
        assert patch_path.exists()
        assert diff_path.read_text() == diff
        assert patch_path.read_text() == patch


class TestSaveFinalResult:
    """Tests for saving final results."""

    @pytest.mark.asyncio
    async def test_save_final_result(self, artifact_store: ArtifactStore) -> None:
        """Test saving final result."""
        task_id = uuid4()
        result = {"status": "done", "summary": "Task completed successfully"}
        diff = "final diff"
        patch = "final patch"

        await artifact_store.save_final_result(task_id, result, diff, patch)

        final_dir = artifact_store._paths.task_dir(task_id) / "final"
        result_path = final_dir / "final_result.json"
        diff_path = final_dir / "final.diff"
        patch_path = final_dir / "final.patch"

        assert result_path.exists()
        assert diff_path.exists()
        assert patch_path.exists()

        saved_result = json.loads(result_path.read_text())
        assert saved_result["status"] == "done"


class TestSaveCache:
    """Tests for saving cache data."""

    @pytest.mark.asyncio
    async def test_save_cache(self, artifact_store: ArtifactStore) -> None:
        """Test saving cache data."""
        task_id = uuid4()
        key = "analysis"
        data = {"files": ["a.py", "b.py"], "complexity": "medium"}

        await artifact_store.save_cache(task_id, key, data)

        cache_path = artifact_store._paths.task_dir(task_id) / "cache" / f"{key}.json"
        assert cache_path.exists()

        saved_data = json.loads(cache_path.read_text())
        assert saved_data["files"] == ["a.py", "b.py"]

    @pytest.mark.asyncio
    async def test_save_multiple_caches(self, artifact_store: ArtifactStore) -> None:
        """Test saving multiple cache entries."""
        task_id = uuid4()

        await artifact_store.save_cache(task_id, "cache1", {"key": "value1"})
        await artifact_store.save_cache(task_id, "cache2", {"key": "value2"})

        cache_dir = artifact_store._paths.task_dir(task_id) / "cache"
        assert (cache_dir / "cache1.json").exists()
        assert (cache_dir / "cache2.json").exists()


class TestAtomicWrite:
    """Tests for atomic write functionality."""

    @pytest.mark.asyncio
    async def test_atomic_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Test atomic write creates parent directories."""
        path = tmp_path / "nested" / "deep" / "file.txt"

        await atomic_write(path, "content")

        assert path.exists()
        assert path.read_text() == "content"

    @pytest.mark.asyncio
    async def test_atomic_write_overwrites(self, tmp_path: Path) -> None:
        """Test atomic write overwrites existing file."""
        path = tmp_path / "file.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("old content")

        await atomic_write(path, "new content")

        assert path.read_text() == "new content"

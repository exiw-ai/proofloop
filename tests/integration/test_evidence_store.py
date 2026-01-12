"""Integration tests for EvidenceStore."""

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from src.infrastructure.persistence.evidence_store import EvidenceStore


@pytest.fixture
def temp_state_dir() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def store(temp_state_dir: Path) -> EvidenceStore:
    return EvidenceStore(temp_state_dir)


class TestSaveCheckEvidence:
    async def test_saves_result_and_log_files(
        self,
        store: EvidenceStore,
        temp_state_dir: Path,
    ) -> None:
        task_id = uuid4()
        condition_id = uuid4()
        result = {"status": "pass", "exit_code": 0}
        log_content = "Test output\nAll tests passed"

        artifact_path, log_path = await store.save_check_evidence(
            task_id=task_id,
            iteration_num=1,
            condition_id=condition_id,
            result=result,
            log_content=log_content,
        )

        # Check files exist
        assert (temp_state_dir / artifact_path).exists()
        assert (temp_state_dir / log_path).exists()

        # Verify content
        with open(temp_state_dir / artifact_path) as f:
            saved_result = json.load(f)
        assert saved_result == result

        with open(temp_state_dir / log_path) as f:
            saved_log = f.read()
        assert saved_log == log_content

    async def test_creates_last_json_index(
        self,
        store: EvidenceStore,
        temp_state_dir: Path,
    ) -> None:
        task_id = uuid4()
        condition_id = uuid4()

        await store.save_check_evidence(
            task_id=task_id,
            iteration_num=1,
            condition_id=condition_id,
            result={"status": "pass"},
            log_content="log",
        )

        last_path = (
            temp_state_dir
            / "tasks"
            / task_id.hex
            / "iterations"
            / "0001"
            / "checks"
            / condition_id.hex
            / "last.json"
        )
        assert last_path.exists()

        with open(last_path) as f:
            last_data = json.load(f)

        assert "latest_result" in last_data
        assert "latest_log" in last_data
        assert "timestamp" in last_data

    async def test_multiple_saves_create_multiple_files(
        self,
        store: EvidenceStore,
        temp_state_dir: Path,
    ) -> None:
        task_id = uuid4()
        condition_id = uuid4()

        # Save twice
        path1, _ = await store.save_check_evidence(
            task_id=task_id,
            iteration_num=1,
            condition_id=condition_id,
            result={"attempt": 1},
            log_content="first",
        )

        path2, _ = await store.save_check_evidence(
            task_id=task_id,
            iteration_num=1,
            condition_id=condition_id,
            result={"attempt": 2},
            log_content="second",
        )

        # Both files should exist
        assert (temp_state_dir / path1).exists()
        assert (temp_state_dir / path2).exists()
        assert path1 != path2

    async def test_iteration_number_formatting(
        self,
        store: EvidenceStore,
        temp_state_dir: Path,
    ) -> None:
        task_id = uuid4()
        condition_id = uuid4()

        # Iteration 1 -> 0001
        await store.save_check_evidence(
            task_id=task_id,
            iteration_num=1,
            condition_id=condition_id,
            result={},
            log_content="",
        )

        iter_dir = temp_state_dir / "tasks" / task_id.hex / "iterations" / "0001"
        assert iter_dir.exists()

        # Iteration 42 -> 0042
        await store.save_check_evidence(
            task_id=task_id,
            iteration_num=42,
            condition_id=condition_id,
            result={},
            log_content="",
        )

        iter_dir = temp_state_dir / "tasks" / task_id.hex / "iterations" / "0042"
        assert iter_dir.exists()


class TestSaveBaselineEvidence:
    async def test_saves_baseline_to_inventory_dir(
        self,
        store: EvidenceStore,
        temp_state_dir: Path,
    ) -> None:
        task_id = uuid4()
        check_id = uuid4()
        result = {"baseline": True, "exit_code": 0}
        log_content = "Baseline check output"

        artifact_path, log_path = await store.save_baseline_evidence(
            task_id=task_id,
            check_id=check_id,
            result=result,
            log_content=log_content,
        )

        # Check path structure
        assert "inventory/baseline" in artifact_path
        assert check_id.hex in artifact_path

        # Check files exist
        assert (temp_state_dir / artifact_path).exists()
        assert (temp_state_dir / log_path).exists()

        # Verify content
        with open(temp_state_dir / artifact_path) as f:
            saved_result = json.load(f)
        assert saved_result == result

    async def test_baseline_path_structure(
        self,
        store: EvidenceStore,
        temp_state_dir: Path,
    ) -> None:
        task_id = uuid4()
        check_id = uuid4()

        await store.save_baseline_evidence(
            task_id=task_id,
            check_id=check_id,
            result={},
            log_content="",
        )

        baseline_dir = (
            temp_state_dir / "tasks" / task_id.hex / "inventory" / "baseline" / check_id.hex
        )
        assert baseline_dir.exists()
        assert any(baseline_dir.glob("*.json"))
        assert any(baseline_dir.glob("*.log"))


class TestEvidenceStorePaths:
    async def test_returned_paths_are_relative(
        self,
        store: EvidenceStore,
    ) -> None:
        task_id = uuid4()
        condition_id = uuid4()

        artifact_path, log_path = await store.save_check_evidence(
            task_id=task_id,
            iteration_num=1,
            condition_id=condition_id,
            result={},
            log_content="",
        )

        # Paths should be relative (not start with /)
        assert not artifact_path.startswith("/")
        assert not log_path.startswith("/")

        # Should start with tasks/
        assert artifact_path.startswith("tasks/")
        assert log_path.startswith("tasks/")

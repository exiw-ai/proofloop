"""Tests for CaptureRepoContext use case."""

from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.use_cases.research.capture_repo_context import CaptureRepoContext
from src.domain.entities import Task
from src.domain.ports.agent_port import AgentResult
from src.domain.value_objects import TaskStatus
from src.infrastructure.research import RepoContextStore


@pytest.fixture
def mock_agent() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo_context_store(tmp_path: Path) -> RepoContextStore:
    return RepoContextStore(tmp_path)


@pytest.fixture
def task() -> Task:
    return Task(
        id=uuid4(),
        description="Research authentication patterns",
        goals=["Understand patterns"],
        sources=[],
        status=TaskStatus.RESEARCH_INVENTORY,
    )


class TestCaptureRepoContextRun:
    @pytest.mark.asyncio
    async def test_skips_when_mode_off(
        self,
        mock_agent: AsyncMock,
        repo_context_store: RepoContextStore,
        task: Task,
        tmp_path: Path,
    ) -> None:
        use_case = CaptureRepoContext(mock_agent, repo_context_store)
        result = await use_case.run(task, tmp_path, mode="off")

        assert result is False
        mock_agent.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_transitions_to_repo_context_status(
        self,
        mock_agent: AsyncMock,
        repo_context_store: RepoContextStore,
        task: Task,
        tmp_path: Path,
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"repos": [], "stats": {}}',
            tools_used=[],
        )

        use_case = CaptureRepoContext(mock_agent, repo_context_store)
        await use_case.run(task, tmp_path, mode="light")

        assert task.status == TaskStatus.RESEARCH_REPO_CONTEXT

    @pytest.mark.asyncio
    async def test_captures_context_from_agent_response(
        self,
        mock_agent: AsyncMock,
        repo_context_store: RepoContextStore,
        task: Task,
        tmp_path: Path,
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="""{
                "repos": [
                    {
                        "name": "proofloop",
                        "path": ".",
                        "commit": "abc123",
                        "branch": "main",
                        "dirty": false,
                        "dirty_files": [],
                        "files_analyzed": 50,
                        "excerpts": [{"file": "src/main.py", "text": "def main():", "purpose": "Entry point"}]
                    }
                ],
                "stats": {"total_files_analyzed": 50, "analysis_duration_ms": 1000}
            }""",
            tools_used=[],
        )

        use_case = CaptureRepoContext(mock_agent, repo_context_store)
        result = await use_case.run(task, tmp_path, mode="light")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_invalid_json(
        self,
        mock_agent: AsyncMock,
        repo_context_store: RepoContextStore,
        task: Task,
        tmp_path: Path,
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="This is not valid JSON",
            tools_used=[],
        )

        use_case = CaptureRepoContext(mock_agent, repo_context_store)
        result = await use_case.run(task, tmp_path, mode="light")

        assert result is False

    @pytest.mark.asyncio
    async def test_light_mode_limits(
        self,
        mock_agent: AsyncMock,
        repo_context_store: RepoContextStore,
        task: Task,
        tmp_path: Path,
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"repos": [], "stats": {}}',
            tools_used=[],
        )

        use_case = CaptureRepoContext(mock_agent, repo_context_store)
        await use_case.run(task, tmp_path, mode="light")

        call_args = mock_agent.execute.call_args
        prompt = call_args.kwargs.get("prompt", "")
        assert "max_files" in prompt
        assert "50" in prompt  # light mode max_files

    @pytest.mark.asyncio
    async def test_full_mode_limits(
        self,
        mock_agent: AsyncMock,
        repo_context_store: RepoContextStore,
        task: Task,
        tmp_path: Path,
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"repos": [], "stats": {}}',
            tools_used=[],
        )

        use_case = CaptureRepoContext(mock_agent, repo_context_store)
        await use_case.run(task, tmp_path, mode="full")

        call_args = mock_agent.execute.call_args
        prompt = call_args.kwargs.get("prompt", "")
        assert "max_files" in prompt
        assert "500" in prompt  # full mode max_files

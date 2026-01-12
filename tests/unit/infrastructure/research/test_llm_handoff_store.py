"""Tests for LLMHandoffStore."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from src.domain.entities import LLMHandoff
from src.infrastructure.research.llm_handoff_store import LLMHandoffStore


@pytest.fixture
def store(tmp_path: Path) -> LLMHandoffStore:
    return LLMHandoffStore(base_path=tmp_path / "research")


@pytest.fixture
def sample_handoff() -> LLMHandoff:
    return LLMHandoff(
        schema_version="1.0",
        research_task_id=uuid4(),
        created_at=datetime.now(UTC),
        headline="Implement authentication",
        goals=["Secure login", "Token handling"],
        constraints=["Must use JWT"],
        recommended_approach="Use PyJWT library",
        key_findings=[],
        source_references=[],
        context_refs=[],
        suggested_blocking_conditions=["tests_pass"],
        recommended_checks=["lint"],
        risks=["Complexity"],
        assumptions=["Python 3.11+"],
        target_workspace_hint="/tmp/project",
    )


class TestSaveHandoff:
    @pytest.mark.asyncio
    async def test_saves_handoff_file(
        self, store: LLMHandoffStore, sample_handoff: LLMHandoff
    ) -> None:
        path = await store.save_handoff(sample_handoff)

        assert "derive_payload.json" in path
        assert (store.base_path / "derive_payload.json").exists()

    @pytest.mark.asyncio
    async def test_creates_parent_directories(
        self, store: LLMHandoffStore, sample_handoff: LLMHandoff
    ) -> None:
        # Base path doesn't exist yet
        assert not store.base_path.exists()

        await store.save_handoff(sample_handoff)

        assert store.base_path.exists()


class TestLoadHandoff:
    @pytest.mark.asyncio
    async def test_loads_saved_handoff(
        self, store: LLMHandoffStore, sample_handoff: LLMHandoff
    ) -> None:
        await store.save_handoff(sample_handoff)

        loaded = await store.load_handoff()

        assert loaded is not None
        assert loaded.headline == sample_handoff.headline
        assert loaded.goals == sample_handoff.goals

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_file(self, store: LLMHandoffStore) -> None:
        loaded = await store.load_handoff()

        assert loaded is None


class TestCreateHandoff:
    @pytest.mark.asyncio
    async def test_creates_handoff_with_all_fields(self, store: LLMHandoffStore) -> None:
        task_id = uuid4()

        handoff = await store.create_handoff(
            research_task_id=task_id,
            headline="Test headline",
            goals=["goal1", "goal2"],
            constraints=["constraint1"],
            recommended_approach="Test approach",
            key_findings=[],
            source_references=[],
            context_refs=[],
            suggested_blocking_conditions=["tests_pass"],
            recommended_checks=["lint"],
            risks=["risk1"],
            assumptions=["assumption1"],
            target_workspace_hint="/tmp/test",
        )

        assert handoff.research_task_id == task_id
        assert handoff.headline == "Test headline"
        assert handoff.schema_version == "1.0"
        assert handoff.target_workspace_hint == "/tmp/test"

    @pytest.mark.asyncio
    async def test_creates_handoff_without_workspace_hint(self, store: LLMHandoffStore) -> None:
        handoff = await store.create_handoff(
            research_task_id=uuid4(),
            headline="Test",
            goals=[],
            constraints=[],
            recommended_approach="",
            key_findings=[],
            source_references=[],
            context_refs=[],
            suggested_blocking_conditions=[],
            recommended_checks=[],
            risks=[],
            assumptions=[],
        )

        assert handoff.target_workspace_hint is None


class TestHandoffExists:
    @pytest.mark.asyncio
    async def test_returns_false_when_not_exists(self, store: LLMHandoffStore) -> None:
        assert not store.handoff_exists()

    @pytest.mark.asyncio
    async def test_returns_true_when_exists(
        self, store: LLMHandoffStore, sample_handoff: LLMHandoff
    ) -> None:
        await store.save_handoff(sample_handoff)

        assert store.handoff_exists()

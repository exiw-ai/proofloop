"""Tests for RepoContextStore."""

from pathlib import Path

import pytest

from src.infrastructure.research.repo_context_store import RepoContextStore


@pytest.fixture
def store(tmp_path: Path) -> RepoContextStore:
    return RepoContextStore(base_path=tmp_path)


class TestSaveRepoAnalysis:
    @pytest.mark.asyncio
    async def test_saves_repo_analysis(self, store: RepoContextStore) -> None:
        await store.save_repo_analysis(
            repo_name="backend",
            repo_path="/path/to/backend",
            commit="abc123",
            branch="main",
            dirty=False,
            dirty_files=[],
            files_analyzed=50,
            excerpts=[{"file": "main.py", "text": "def main(): pass", "location": "1-5"}],
        )

        analysis_file = store.context_path / "repos" / "backend" / "analysis.json"
        excerpts_file = store.context_path / "repos" / "backend" / "excerpts.json"

        assert analysis_file.exists()
        assert excerpts_file.exists()

    @pytest.mark.asyncio
    async def test_redacts_secrets_from_excerpts(self, store: RepoContextStore) -> None:
        await store.save_repo_analysis(
            repo_name="backend",
            repo_path="/path",
            commit="abc",
            branch="main",
            dirty=False,
            dirty_files=[],
            files_analyzed=1,
            excerpts=[{"file": "config.py", "text": "API_KEY = 'sk-abc123def456ghi789jkl012'"}],
        )

        import json

        excerpts_file = store.context_path / "repos" / "backend" / "excerpts.json"
        excerpts = json.loads(excerpts_file.read_text())

        # Secret should be redacted
        assert "sk-" not in excerpts[0]["text"]
        assert "[REDACTED]" in excerpts[0]["text"]

    @pytest.mark.asyncio
    async def test_excludes_forbidden_files(self, store: RepoContextStore) -> None:
        await store.save_repo_analysis(
            repo_name="backend",
            repo_path="/path",
            commit="abc",
            branch="main",
            dirty=False,
            dirty_files=[],
            files_analyzed=2,
            excerpts=[
                {"file": ".env", "text": "SECRET=value"},
                {"file": "main.py", "text": "print('hello')"},
            ],
        )

        import json

        excerpts_file = store.context_path / "repos" / "backend" / "excerpts.json"
        excerpts = json.loads(excerpts_file.read_text())

        # .env should be excluded
        assert len(excerpts) == 1
        assert excerpts[0]["file"] == "main.py"

    @pytest.mark.asyncio
    async def test_creates_redaction_log(self, store: RepoContextStore) -> None:
        await store.save_repo_analysis(
            repo_name="backend",
            repo_path="/path",
            commit="abc",
            branch="main",
            dirty=False,
            dirty_files=[],
            files_analyzed=1,
            excerpts=[
                {"file": ".env.local", "text": "SECRET=value"},
            ],
        )

        import json

        log_file = store.context_path / "redaction_log.json"
        assert log_file.exists()

        log = json.loads(log_file.read_text())
        assert len(log) == 1
        assert log[0]["reason"] == "forbidden_file"


class TestSaveManifest:
    @pytest.mark.asyncio
    async def test_saves_manifest(self, store: RepoContextStore) -> None:
        await store.save_manifest(
            mode="full",
            workspace_root="/path/to/workspace",
            repos=[{"name": "backend", "path": "backend/"}],
            limits={"max_files": 500},
            stats={"total_files": 100},
        )

        manifest_file = store.context_path / "manifest.json"
        assert manifest_file.exists()

        import json

        manifest = json.loads(manifest_file.read_text())
        assert manifest["mode"] == "full"
        assert manifest["workspace_root"] == "/path/to/workspace"


class TestLoadManifest:
    @pytest.mark.asyncio
    async def test_loads_manifest(self, store: RepoContextStore) -> None:
        await store.save_manifest(
            mode="light",
            workspace_root="/test",
            repos=[],
            limits={},
            stats={},
        )

        manifest = await store.load_manifest()

        assert manifest is not None
        assert manifest["mode"] == "light"

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_manifest(self, store: RepoContextStore) -> None:
        manifest = await store.load_manifest()
        assert manifest is None


class TestListRepos:
    @pytest.mark.asyncio
    async def test_lists_repos(self, store: RepoContextStore) -> None:
        await store.save_repo_analysis(
            repo_name="repo1",
            repo_path="/",
            commit="a",
            branch="main",
            dirty=False,
            dirty_files=[],
            files_analyzed=1,
            excerpts=[],
        )
        await store.save_repo_analysis(
            repo_name="repo2",
            repo_path="/",
            commit="b",
            branch="main",
            dirty=False,
            dirty_files=[],
            files_analyzed=1,
            excerpts=[],
        )

        repos = await store.list_repos()

        assert "repo1" in repos
        assert "repo2" in repos

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_repos(self, store: RepoContextStore) -> None:
        repos = await store.list_repos()
        assert repos == []


class TestLoadRepoExcerpts:
    @pytest.mark.asyncio
    async def test_loads_excerpts(self, store: RepoContextStore) -> None:
        await store.save_repo_analysis(
            repo_name="backend",
            repo_path="/",
            commit="abc",
            branch="main",
            dirty=False,
            dirty_files=[],
            files_analyzed=1,
            excerpts=[{"file": "main.py", "text": "code"}],
        )

        excerpts = await store.load_repo_excerpts("backend")

        assert len(excerpts) == 1
        assert excerpts[0]["file"] == "main.py"

    @pytest.mark.asyncio
    async def test_returns_empty_for_missing_repo(self, store: RepoContextStore) -> None:
        excerpts = await store.load_repo_excerpts("nonexistent")
        assert excerpts == []


class TestContextExists:
    @pytest.mark.asyncio
    async def test_returns_false_when_not_exists(self, store: RepoContextStore) -> None:
        assert not store.context_exists()

    @pytest.mark.asyncio
    async def test_returns_true_when_exists(self, store: RepoContextStore) -> None:
        await store.save_manifest(
            mode="full",
            workspace_root="/",
            repos=[],
            limits={},
            stats={},
        )

        assert store.context_exists()

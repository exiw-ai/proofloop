"""Tests for DiffPort domain value objects."""

from unittest.mock import AsyncMock

import pytest

from src.domain.ports.diff_port import DiffResult, MultiRepoDiffResult, StashResult


class TestDiffResult:
    """Tests for DiffResult value object."""

    def test_create_diff_result(self) -> None:
        """Test creating a DiffResult."""
        result = DiffResult(
            diff="diff content",
            patch="patch content",
            files_changed=["file1.py", "file2.py"],
            insertions=10,
            deletions=5,
        )

        assert result.diff == "diff content"
        assert result.patch == "patch content"
        assert len(result.files_changed) == 2
        assert result.insertions == 10
        assert result.deletions == 5


class TestMultiRepoDiffResult:
    """Tests for MultiRepoDiffResult value object."""

    def test_from_single(self) -> None:
        """Test creating MultiRepoDiffResult from single repo."""
        diff_result = DiffResult(
            diff="diff",
            patch="patch",
            files_changed=["file1.py", "file2.py"],
            insertions=10,
            deletions=5,
        )

        result = MultiRepoDiffResult.from_single("/path/to/repo", diff_result)

        assert len(result.repo_diffs) == 1
        assert "/path/to/repo" in result.repo_diffs
        assert result.total_files_changed == 2
        assert result.total_insertions == 10
        assert result.total_deletions == 5

    def test_merge_multiple_repos(self) -> None:
        """Test merging multiple repo results."""
        results = {
            "/path/repo1": DiffResult(
                diff="diff1",
                patch="patch1",
                files_changed=["a.py", "b.py"],
                insertions=10,
                deletions=5,
            ),
            "/path/repo2": DiffResult(
                diff="diff2",
                patch="patch2",
                files_changed=["c.py"],
                insertions=20,
                deletions=10,
            ),
        }

        result = MultiRepoDiffResult.merge(results)

        assert len(result.repo_diffs) == 2
        assert result.total_files_changed == 3  # 2 + 1
        assert result.total_insertions == 30  # 10 + 20
        assert result.total_deletions == 15  # 5 + 10

    def test_merge_empty(self) -> None:
        """Test merging empty results."""
        result = MultiRepoDiffResult.merge({})

        assert len(result.repo_diffs) == 0
        assert result.total_files_changed == 0
        assert result.total_insertions == 0
        assert result.total_deletions == 0


class TestStashResult:
    """Tests for StashResult value object."""

    def test_create_success_stash(self) -> None:
        """Test creating a successful stash result."""
        result = StashResult(
            repo_path="/path/to/repo",
            success=True,
            stash_ref="stash@{0}",
        )

        assert result.repo_path == "/path/to/repo"
        assert result.success is True
        assert result.stash_ref == "stash@{0}"
        assert result.error is None

    def test_create_failed_stash(self) -> None:
        """Test creating a failed stash result."""
        result = StashResult(
            repo_path="/path/to/repo",
            success=False,
            error="Failed to stash",
        )

        assert result.repo_path == "/path/to/repo"
        assert result.success is False
        assert result.stash_ref is None
        assert result.error == "Failed to stash"


class TestDiffPortMultiRepoOperations:
    """Tests for DiffPort multi-repo operations (default implementations)."""

    @pytest.fixture
    def mock_diff_port(self) -> AsyncMock:
        """Create a mock DiffPort with basic methods."""
        from src.domain.ports.diff_port import DiffPort

        mock = AsyncMock(spec=DiffPort)
        mock.get_worktree_diff.return_value = DiffResult(
            diff="diff",
            patch="patch",
            files_changed=["file.py"],
            insertions=5,
            deletions=2,
        )
        mock.stash_changes.return_value = "stash@{0}"
        mock.pop_stash.return_value = None
        return mock

    @pytest.mark.asyncio
    async def test_get_worktree_diff_all(self, mock_diff_port: AsyncMock) -> None:
        """Test getting diffs from all repos."""
        # Create a concrete implementation for testing
        from src.domain.ports.diff_port import DiffPort

        class ConcreteDiffPort(DiffPort):
            async def get_worktree_diff(self, _repo_path: str) -> DiffResult:
                return DiffResult(
                    diff="diff",
                    patch="patch",
                    files_changed=["file.py"],
                    insertions=5,
                    deletions=2,
                )

            async def get_staged_diff(self, _repo_path: str) -> DiffResult:
                return DiffResult(
                    diff="",
                    patch="",
                    files_changed=[],
                    insertions=0,
                    deletions=0,
                )

            async def stash_changes(self, _repo_path: str, _message: str) -> str:
                return "stash@{0}"

            async def pop_stash(self, _repo_path: str) -> None:
                pass

        port = ConcreteDiffPort()
        result = await port.get_worktree_diff_all(["/repo1", "/repo2"])

        assert len(result.repo_diffs) == 2
        assert result.total_files_changed == 2

    @pytest.mark.asyncio
    async def test_stash_all_repos(self) -> None:
        """Test stashing changes in all repos."""
        from src.domain.ports.diff_port import DiffPort

        class ConcreteDiffPort(DiffPort):
            async def get_worktree_diff(self, _repo_path: str) -> DiffResult:
                return DiffResult(
                    diff="",
                    patch="",
                    files_changed=[],
                    insertions=0,
                    deletions=0,
                )

            async def get_staged_diff(self, _repo_path: str) -> DiffResult:
                return DiffResult(
                    diff="",
                    patch="",
                    files_changed=[],
                    insertions=0,
                    deletions=0,
                )

            async def stash_changes(self, repo_path: str, _message: str) -> str:
                return f"stash@{repo_path}"

            async def pop_stash(self, _repo_path: str) -> None:
                pass

        port = ConcreteDiffPort()
        results = await port.stash_all_repos(["/repo1", "/repo2"], "test message")

        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_stash_all_repos_with_error(self) -> None:
        """Test stashing with one repo failing."""
        from src.domain.ports.diff_port import DiffPort

        class ConcreteDiffPort(DiffPort):
            async def get_worktree_diff(self, _repo_path: str) -> DiffResult:
                return DiffResult(
                    diff="",
                    patch="",
                    files_changed=[],
                    insertions=0,
                    deletions=0,
                )

            async def get_staged_diff(self, _repo_path: str) -> DiffResult:
                return DiffResult(
                    diff="",
                    patch="",
                    files_changed=[],
                    insertions=0,
                    deletions=0,
                )

            async def stash_changes(self, repo_path: str, _message: str) -> str:
                if repo_path == "/repo2":
                    raise RuntimeError("Stash failed")
                return f"stash@{repo_path}"

            async def pop_stash(self, _repo_path: str) -> None:
                pass

        port = ConcreteDiffPort()
        results = await port.stash_all_repos(["/repo1", "/repo2"], "test message")

        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False
        assert results[1].error == "Stash failed"

    @pytest.mark.asyncio
    async def test_pop_all_repos(self) -> None:
        """Test popping stash from all repos."""
        from src.domain.ports.diff_port import DiffPort

        class ConcreteDiffPort(DiffPort):
            async def get_worktree_diff(self, _repo_path: str) -> DiffResult:
                return DiffResult(
                    diff="",
                    patch="",
                    files_changed=[],
                    insertions=0,
                    deletions=0,
                )

            async def get_staged_diff(self, _repo_path: str) -> DiffResult:
                return DiffResult(
                    diff="",
                    patch="",
                    files_changed=[],
                    insertions=0,
                    deletions=0,
                )

            async def stash_changes(self, _repo_path: str, _message: str) -> str:
                return "stash@{0}"

            async def pop_stash(self, _repo_path: str) -> None:
                pass

        port = ConcreteDiffPort()
        results = await port.pop_all_repos(["/repo1", "/repo2"])

        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_rollback_all(self) -> None:
        """Test rolling back changes in all repos."""
        from src.domain.ports.diff_port import DiffPort

        class ConcreteDiffPort(DiffPort):
            async def get_worktree_diff(self, _repo_path: str) -> DiffResult:
                return DiffResult(
                    diff="",
                    patch="",
                    files_changed=[],
                    insertions=0,
                    deletions=0,
                )

            async def get_staged_diff(self, _repo_path: str) -> DiffResult:
                return DiffResult(
                    diff="",
                    patch="",
                    files_changed=[],
                    insertions=0,
                    deletions=0,
                )

            async def stash_changes(self, _repo_path: str, _message: str) -> str:
                return "stash@{0}"

            async def pop_stash(self, _repo_path: str) -> None:
                pass

        port = ConcreteDiffPort()
        results = await port.rollback_all(["/repo1", "/repo2"], "rollback test")

        assert len(results) == 2
        assert all(r.success for r in results)

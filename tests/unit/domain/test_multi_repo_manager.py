"""Tests for MultiRepoManager domain service."""

import tempfile
from pathlib import Path

import pytest

from src.domain.services.multi_repo_manager import MultiRepoManager, WorkspaceInfo


@pytest.fixture
def temp_workspace() -> Path:
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmp:
        # Resolve symlinks (e.g., /var -> /private/var on macOS)
        yield Path(tmp).resolve()


@pytest.fixture
def single_repo(temp_workspace: Path) -> Path:
    """Create a single git repository."""
    import subprocess

    subprocess.run(["git", "init"], cwd=temp_workspace, check=True, capture_output=True)
    return temp_workspace


@pytest.fixture
def multi_repo_workspace(temp_workspace: Path) -> Path:
    """Create a workspace with multiple repositories."""
    import subprocess

    # Create repo1
    repo1 = temp_workspace / "repo1"
    repo1.mkdir()
    subprocess.run(["git", "init"], cwd=repo1, check=True, capture_output=True)

    # Create repo2
    repo2 = temp_workspace / "repo2"
    repo2.mkdir()
    subprocess.run(["git", "init"], cwd=repo2, check=True, capture_output=True)

    # Create non-repo directory
    other = temp_workspace / "other"
    other.mkdir()
    (other / "file.txt").write_text("test")

    return temp_workspace


@pytest.fixture
def nested_repo_workspace(temp_workspace: Path) -> Path:
    """Create a workspace with nested repositories."""
    import subprocess

    # Create parent repo
    parent = temp_workspace / "parent"
    parent.mkdir()
    subprocess.run(["git", "init"], cwd=parent, check=True, capture_output=True)

    # Create nested repo (shouldn't be found as it's inside parent)
    nested = parent / "nested"
    nested.mkdir()
    subprocess.run(["git", "init"], cwd=nested, check=True, capture_output=True)

    # Create sibling repo
    sibling = temp_workspace / "sibling"
    sibling.mkdir()
    subprocess.run(["git", "init"], cwd=sibling, check=True, capture_output=True)

    return temp_workspace


class TestMultiRepoManager:
    """Tests for MultiRepoManager."""

    async def test_discover_single_repo(self, single_repo: Path) -> None:
        """Test discovering a single repository."""
        manager = MultiRepoManager()
        info = await manager.discover_repos(single_repo)

        assert info.is_workspace is False
        assert len(info.repos) == 1
        assert info.repos[0] == single_repo
        assert info.root == single_repo
        assert info.is_single_repo is True

    async def test_discover_multi_repo_workspace(self, multi_repo_workspace: Path) -> None:
        """Test discovering multiple repositories in a workspace."""
        manager = MultiRepoManager()
        info = await manager.discover_repos(multi_repo_workspace)

        assert info.is_workspace is True
        assert len(info.repos) == 2
        assert multi_repo_workspace / "repo1" in info.repos
        assert multi_repo_workspace / "repo2" in info.repos
        assert info.root == multi_repo_workspace
        assert info.is_single_repo is False

    async def test_discover_no_repos(self, temp_workspace: Path) -> None:
        """Test discovering workspace with no repositories."""
        manager = MultiRepoManager()
        info = await manager.discover_repos(temp_workspace)

        assert info.is_workspace is True
        assert len(info.repos) == 0
        assert info.root == temp_workspace

    async def test_nested_repo_handling(self, nested_repo_workspace: Path) -> None:
        """Test that nested repos are handled correctly (parent repo
        returned)."""
        manager = MultiRepoManager()
        info = await manager.discover_repos(nested_repo_workspace)

        # Should find parent and sibling, not nested (it's inside parent)
        assert info.is_workspace is True
        assert len(info.repos) == 2
        assert nested_repo_workspace / "parent" in info.repos
        assert nested_repo_workspace / "sibling" in info.repos

    async def test_repos_property(self, multi_repo_workspace: Path) -> None:
        """Test repos property returns discovered repos."""
        manager = MultiRepoManager()
        await manager.discover_repos(multi_repo_workspace)

        repos = manager.repos
        assert len(repos) == 2
        assert multi_repo_workspace / "repo1" in repos
        assert multi_repo_workspace / "repo2" in repos

    async def test_max_depth_limit(self, temp_workspace: Path) -> None:
        """Test max depth limits search."""
        import subprocess

        # Create deeply nested repo
        deep = temp_workspace / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        subprocess.run(["git", "init"], cwd=deep, check=True, capture_output=True)

        manager = MultiRepoManager(max_depth=2)
        info = await manager.discover_repos(temp_workspace)

        # Should not find the deep repo
        assert deep not in info.repos

    async def test_get_status_all(self, multi_repo_workspace: Path) -> None:
        """Test getting status of all repos."""
        manager = MultiRepoManager()
        await manager.discover_repos(multi_repo_workspace)

        statuses = await manager.get_status_all()

        assert len(statuses) == 2
        for status in statuses:
            assert status.error is None
            assert status.has_changes is False  # Empty repos have no changes

    async def test_get_status_with_changes(self, single_repo: Path) -> None:
        """Test status detection for repos with changes."""
        # Create a file
        (single_repo / "test.txt").write_text("test content")

        manager = MultiRepoManager()
        await manager.discover_repos(single_repo)
        statuses = await manager.get_status_all()

        assert len(statuses) == 1
        assert statuses[0].has_changes is True

    async def test_stash_all_no_changes(self, multi_repo_workspace: Path) -> None:
        """Test stashing when no changes exist."""
        manager = MultiRepoManager()
        await manager.discover_repos(multi_repo_workspace)

        results = await manager.stash_all("test stash")

        # Should succeed but not actually stash anything
        assert len(results) == 2
        for result in results:
            assert result.error is None

    async def test_stash_and_pop(self, single_repo: Path) -> None:
        """Test stashing and popping changes."""
        import subprocess

        # Create and commit a file first (needed for stash to work)
        (single_repo / "initial.txt").write_text("initial")
        subprocess.run(["git", "add", "."], cwd=single_repo, check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=test@test.com",
                "-c",
                "user.name=Test",
                "commit",
                "-m",
                "initial",
            ],
            cwd=single_repo,
            check=True,
            capture_output=True,
        )

        # Create a change
        (single_repo / "test.txt").write_text("test content")

        manager = MultiRepoManager()
        await manager.discover_repos(single_repo)

        # Stash
        stash_results = await manager.stash_all("test stash")
        assert len(stash_results) == 1
        assert stash_results[0].stash_ref is not None

        # Verify file is gone
        assert not (single_repo / "test.txt").exists()

        # Pop
        pop_results = await manager.pop_all()
        assert len(pop_results) == 1

        # Verify file is back
        assert (single_repo / "test.txt").exists()

    async def test_rollback_all(self, single_repo: Path) -> None:
        """Test rollback all repos."""
        import subprocess

        # Setup repo with initial commit
        (single_repo / "initial.txt").write_text("initial")
        subprocess.run(["git", "add", "."], cwd=single_repo, check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=test@test.com",
                "-c",
                "user.name=Test",
                "commit",
                "-m",
                "initial",
            ],
            cwd=single_repo,
            check=True,
            capture_output=True,
        )

        # Create change
        (single_repo / "change.txt").write_text("change")

        manager = MultiRepoManager()
        await manager.discover_repos(single_repo)

        # Rollback
        results = await manager.rollback_all()
        assert len(results) == 1

        # Verify change is stashed
        assert not (single_repo / "change.txt").exists()

    async def test_clear_stash_tracking(self, single_repo: Path) -> None:
        """Test clearing stash tracking."""
        manager = MultiRepoManager()
        await manager.discover_repos(single_repo)

        # Manually set some stash refs
        manager._stash_refs[single_repo] = "stash@{0}"

        assert len(manager.get_stash_refs()) == 1
        manager.clear_stash_tracking()
        assert len(manager.get_stash_refs()) == 0


class TestWorkspaceInfo:
    """Tests for WorkspaceInfo value object."""

    def test_is_single_repo_true(self) -> None:
        """Test is_single_repo returns True for single repo."""
        info = WorkspaceInfo(
            is_workspace=False,
            repos=[Path("/test/repo")],
            root=Path("/test/repo"),
        )
        assert info.is_single_repo is True

    def test_is_single_repo_false_workspace(self) -> None:
        """Test is_single_repo returns False for workspace."""
        info = WorkspaceInfo(
            is_workspace=True,
            repos=[Path("/test/repo1"), Path("/test/repo2")],
            root=Path("/test"),
        )
        assert info.is_single_repo is False

    def test_is_single_repo_false_empty(self) -> None:
        """Test is_single_repo returns False for empty workspace."""
        info = WorkspaceInfo(
            is_workspace=True,
            repos=[],
            root=Path("/test"),
        )
        assert info.is_single_repo is False

    def test_frozen(self) -> None:
        """Test WorkspaceInfo is frozen (immutable)."""
        from pydantic import ValidationError

        info = WorkspaceInfo(
            is_workspace=False,
            repos=[Path("/test")],
            root=Path("/test"),
        )
        with pytest.raises(ValidationError):
            info.is_workspace = True  # type: ignore

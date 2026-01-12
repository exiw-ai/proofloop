import tempfile
from pathlib import Path

import pytest

from src.infrastructure.git.repo_root import (
    get_default_state_dir,
    get_repo_root,
    get_workspace_info,
    get_xdg_data_home,
    is_git_repo,
    scan_for_repos,
)


async def test_get_repo_root_returns_path(tmp_path: Path) -> None:
    """get_repo_root returns the repository root for a valid git repo."""
    # Initialize a git repo in tmp_path
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        "git",
        "init",
        cwd=str(tmp_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    result = await get_repo_root(tmp_path)

    assert result == tmp_path


async def test_get_repo_root_from_subdirectory(tmp_path: Path) -> None:
    """get_repo_root works from a subdirectory within the repo."""
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        "git",
        "init",
        cwd=str(tmp_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    subdir = tmp_path / "src" / "nested"
    subdir.mkdir(parents=True)

    result = await get_repo_root(subdir)

    assert result == tmp_path


async def test_get_repo_root_initializes_git_for_non_repo() -> None:
    """get_repo_root initializes git when not in a repository."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp).resolve()  # Resolve symlinks (macOS /var -> /private/var)
        result = await get_repo_root(tmp_path)
        assert result == tmp_path
        assert (tmp_path / ".git").exists()


async def test_get_default_state_dir(tmp_path: Path) -> None:
    """get_default_state_dir returns XDG state directory."""
    result = await get_default_state_dir(tmp_path)

    # Should return global XDG path, not repo-local path
    assert result == get_xdg_data_home() / "proofloop"
    assert ".proofloop" not in str(result)


async def test_get_default_state_dir_ignores_path_param() -> None:
    """get_default_state_dir ignores the path parameter."""
    result1 = await get_default_state_dir("/some/path")
    result2 = await get_default_state_dir("/another/path")

    assert result1 == result2


def test_get_xdg_data_home_default() -> None:
    """get_xdg_data_home returns ~/.local/share by default."""
    import os

    # Clear XDG_DATA_HOME if set
    original = os.environ.pop("XDG_DATA_HOME", None)
    try:
        result = get_xdg_data_home()
        assert result == Path.home() / ".local" / "share"
    finally:
        if original:
            os.environ["XDG_DATA_HOME"] = original


def test_get_xdg_data_home_custom(tmp_path: Path) -> None:
    """get_xdg_data_home respects XDG_DATA_HOME environment variable."""
    import os

    original = os.environ.get("XDG_DATA_HOME")
    try:
        os.environ["XDG_DATA_HOME"] = str(tmp_path)
        result = get_xdg_data_home()
        assert result == tmp_path
    finally:
        if original:
            os.environ["XDG_DATA_HOME"] = original
        else:
            os.environ.pop("XDG_DATA_HOME", None)


class TestIsGitRepo:
    """Tests for is_git_repo function."""

    @pytest.mark.asyncio
    async def test_is_git_repo_true(self, tmp_path: Path) -> None:
        """is_git_repo returns True for a git repository."""
        import asyncio

        proc = await asyncio.create_subprocess_exec(
            "git",
            "init",
            cwd=str(tmp_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        result = await is_git_repo(tmp_path)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_git_repo_false(self, tmp_path: Path) -> None:
        """is_git_repo returns False for non-git directory."""
        result = await is_git_repo(tmp_path)

        assert result is False


class TestScanForRepos:
    """Tests for scan_for_repos function."""

    @pytest.mark.asyncio
    async def test_scan_for_repos_empty_dir(self, tmp_path: Path) -> None:
        """scan_for_repos returns empty list for empty directory."""
        result = await scan_for_repos(tmp_path)

        assert result == []

    @pytest.mark.asyncio
    async def test_scan_for_repos_single_repo(self, tmp_path: Path) -> None:
        """scan_for_repos finds a single repository."""
        import asyncio

        repo_path = tmp_path / "my-repo"
        repo_path.mkdir()

        proc = await asyncio.create_subprocess_exec(
            "git",
            "init",
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        result = await scan_for_repos(tmp_path)

        assert len(result) == 1
        assert repo_path in result

    @pytest.mark.asyncio
    async def test_scan_for_repos_multiple_repos(self, tmp_path: Path) -> None:
        """scan_for_repos finds multiple repositories."""
        import asyncio

        for name in ["repo-a", "repo-b", "repo-c"]:
            repo_path = tmp_path / name
            repo_path.mkdir()
            proc = await asyncio.create_subprocess_exec(
                "git",
                "init",
                cwd=str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

        result = await scan_for_repos(tmp_path)

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_scan_for_repos_max_depth(self, tmp_path: Path) -> None:
        """scan_for_repos respects max_depth parameter."""
        import asyncio

        # Create deeply nested repo
        deep_path = tmp_path / "a" / "b" / "c" / "d" / "repo"
        deep_path.mkdir(parents=True)
        proc = await asyncio.create_subprocess_exec(
            "git",
            "init",
            cwd=str(deep_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # With max_depth=2, should not find deeply nested repo
        result = await scan_for_repos(tmp_path, max_depth=2)

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_scan_skips_hidden_dirs(self, tmp_path: Path) -> None:
        """scan_for_repos skips hidden directories."""
        import asyncio

        hidden_path = tmp_path / ".hidden" / "repo"
        hidden_path.mkdir(parents=True)
        proc = await asyncio.create_subprocess_exec(
            "git",
            "init",
            cwd=str(hidden_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        result = await scan_for_repos(tmp_path)

        assert len(result) == 0


class TestGetWorkspaceInfo:
    """Tests for get_workspace_info function."""

    @pytest.mark.asyncio
    async def test_single_repo_at_root(self, tmp_path: Path) -> None:
        """get_workspace_info returns single repo info when path is a repo."""
        import asyncio

        proc = await asyncio.create_subprocess_exec(
            "git",
            "init",
            cwd=str(tmp_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        result = await get_workspace_info(tmp_path)

        assert result.is_workspace is False
        assert result.is_single_repo is True
        assert len(result.repos) == 1
        assert tmp_path in result.repos

    @pytest.mark.asyncio
    async def test_workspace_with_multiple_repos(self, tmp_path: Path) -> None:
        """get_workspace_info returns workspace info for multi-repo
        directory."""
        import asyncio

        for name in ["frontend", "backend"]:
            repo_path = tmp_path / name
            repo_path.mkdir()
            proc = await asyncio.create_subprocess_exec(
                "git",
                "init",
                cwd=str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

        result = await get_workspace_info(tmp_path)

        assert result.is_workspace is True
        assert result.is_single_repo is False
        assert len(result.repos) == 2
        assert result.root == tmp_path

    @pytest.mark.asyncio
    async def test_workspace_empty_dir(self, tmp_path: Path) -> None:
        """get_workspace_info returns workspace with no repos for empty dir."""
        result = await get_workspace_info(tmp_path)

        assert result.is_workspace is True
        assert len(result.repos) == 0
        assert result.root == tmp_path

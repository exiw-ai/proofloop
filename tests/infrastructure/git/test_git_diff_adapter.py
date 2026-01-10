import asyncio
from pathlib import Path

import pytest

from src.infrastructure.git.git_diff_adapter import GitDiffAdapter


async def run_git(cwd: Path, *args: str) -> None:
    """Run a git command and wait for completion."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Git failed: {stderr.decode()}")


@pytest.fixture
async def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository with initial commit."""
    await run_git(tmp_path, "init")
    await run_git(tmp_path, "config", "user.email", "test@test.com")
    await run_git(tmp_path, "config", "user.name", "Test User")

    # Create initial file and commit
    (tmp_path / "initial.txt").write_text("initial content\n")
    await run_git(tmp_path, "add", ".")
    await run_git(tmp_path, "commit", "-m", "Initial commit")

    return tmp_path


async def test_get_worktree_diff_empty(git_repo: Path) -> None:
    """get_worktree_diff returns empty diff when no changes."""
    adapter = GitDiffAdapter()

    result = await adapter.get_worktree_diff(str(git_repo))

    assert result.diff == ""
    assert result.patch == ""
    assert result.files_changed == []
    assert result.insertions == 0
    assert result.deletions == 0


async def test_get_worktree_diff_with_unstaged_changes(git_repo: Path) -> None:
    """get_worktree_diff includes unstaged changes."""
    adapter = GitDiffAdapter()

    # Modify the file
    (git_repo / "initial.txt").write_text("modified content\n")

    result = await adapter.get_worktree_diff(str(git_repo))

    assert "initial.txt" in result.files_changed
    assert result.insertions == 1
    assert result.deletions == 1
    assert "modified content" in result.diff


async def test_get_worktree_diff_with_staged_changes(git_repo: Path) -> None:
    """get_worktree_diff includes staged changes."""
    adapter = GitDiffAdapter()

    # Add a new file and stage it
    (git_repo / "new_file.txt").write_text("new content\n")
    await run_git(git_repo, "add", "new_file.txt")

    result = await adapter.get_worktree_diff(str(git_repo))

    assert "new_file.txt" in result.files_changed
    assert result.insertions == 1
    assert "new content" in result.diff


async def test_get_staged_diff_empty(git_repo: Path) -> None:
    """get_staged_diff returns empty diff when nothing staged."""
    adapter = GitDiffAdapter()

    result = await adapter.get_staged_diff(str(git_repo))

    assert result.diff == ""
    assert result.patch == ""
    assert result.files_changed == []
    assert result.insertions == 0
    assert result.deletions == 0


async def test_get_staged_diff_excludes_unstaged(git_repo: Path) -> None:
    """get_staged_diff excludes unstaged changes."""
    adapter = GitDiffAdapter()

    # Modify file but don't stage
    (git_repo / "initial.txt").write_text("unstaged change\n")

    result = await adapter.get_staged_diff(str(git_repo))

    assert result.diff == ""
    assert result.files_changed == []


async def test_get_staged_diff_with_staged_changes(git_repo: Path) -> None:
    """get_staged_diff returns only staged changes."""
    adapter = GitDiffAdapter()

    # Create and stage a new file
    (git_repo / "staged.txt").write_text("staged content\n")
    await run_git(git_repo, "add", "staged.txt")

    # Create unstaged file (not added to git)
    (git_repo / "unstaged.txt").write_text("unstaged content\n")

    result = await adapter.get_staged_diff(str(git_repo))

    assert "staged.txt" in result.files_changed
    assert "unstaged.txt" not in result.files_changed
    assert result.insertions == 1


async def test_get_worktree_diff_multiple_files(git_repo: Path) -> None:
    """get_worktree_diff handles multiple changed files."""
    adapter = GitDiffAdapter()

    # Create multiple files and stage them
    (git_repo / "file1.txt").write_text("content 1\n")
    (git_repo / "file2.txt").write_text("content 2\nline 2\n")
    (git_repo / "file3.txt").write_text("content 3\n")
    await run_git(git_repo, "add", ".")

    result = await adapter.get_worktree_diff(str(git_repo))

    assert len(result.files_changed) == 3
    assert "file1.txt" in result.files_changed
    assert "file2.txt" in result.files_changed
    assert "file3.txt" in result.files_changed
    assert result.insertions == 4  # 1 + 2 + 1


async def test_git_diff_adapter_invalid_repo() -> None:
    """GitDiffAdapter raises RuntimeError for invalid repository."""
    import tempfile

    adapter = GitDiffAdapter()

    with (
        tempfile.TemporaryDirectory() as tmp,
        pytest.raises(RuntimeError, match="Git command failed"),
    ):
        await adapter.get_worktree_diff(tmp)


# ===== Tests for stash_changes() =====


class TestStashChanges:
    async def test_stash_modified_files(self, git_repo: Path) -> None:
        """Modified tracked files are saved in stash."""
        adapter = GitDiffAdapter()

        # Modify a tracked file
        (git_repo / "initial.txt").write_text("modified content\n")

        # Stash changes
        result = await adapter.stash_changes(str(git_repo), "Test stash")

        # Check that stash was created
        assert "Saved working directory" in result or result == ""

        # Verify file is restored to original
        content = (git_repo / "initial.txt").read_text()
        assert content == "initial content\n"

    async def test_stash_includes_untracked_files(self, git_repo: Path) -> None:
        """Untracked files (new) are included in stash with -u."""
        adapter = GitDiffAdapter()

        # Create a new untracked file
        (git_repo / "new_file.txt").write_text("new content\n")
        assert (git_repo / "new_file.txt").exists()

        # Stash changes
        await adapter.stash_changes(str(git_repo), "Test stash untracked")

        # Verify untracked file is gone
        assert not (git_repo / "new_file.txt").exists()

    async def test_stash_excludes_gitignored_files(self, git_repo: Path) -> None:
        """Ignored files (.venv, __pycache__) do NOT get into stash."""
        adapter = GitDiffAdapter()

        # Create .gitignore
        (git_repo / ".gitignore").write_text("ignored_dir/\n")
        await run_git(git_repo, "add", ".gitignore")
        await run_git(git_repo, "commit", "-m", "Add gitignore")

        # Create ignored directory with file
        (git_repo / "ignored_dir").mkdir()
        (git_repo / "ignored_dir" / "ignored_file.txt").write_text("ignored\n")

        # Create non-ignored file
        (git_repo / "normal_file.txt").write_text("normal\n")

        # Stash changes
        await adapter.stash_changes(str(git_repo), "Test stash ignore")

        # Ignored file should still exist (not stashed)
        assert (git_repo / "ignored_dir" / "ignored_file.txt").exists()
        # Normal file should be gone (stashed)
        assert not (git_repo / "normal_file.txt").exists()

    async def test_stash_returns_ref(self, git_repo: Path) -> None:
        """Returns stash ref for later restoration."""
        adapter = GitDiffAdapter()

        # Create changes
        (git_repo / "initial.txt").write_text("modified\n")

        result = await adapter.stash_changes(str(git_repo), "Test stash ref")

        # Should return some output (stash message or empty if nothing to stash)
        assert isinstance(result, str)

    async def test_stash_with_message(self, git_repo: Path) -> None:
        """Stash is created with the specified message."""
        adapter = GitDiffAdapter()

        # Create changes
        (git_repo / "initial.txt").write_text("modified for message test\n")

        message = "proofloop: rollback iteration 1"
        await adapter.stash_changes(str(git_repo), message)

        # Check stash list contains our message
        proc = await asyncio.create_subprocess_exec(
            "git",
            "stash",
            "list",
            cwd=str(git_repo),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        stash_list = stdout.decode()

        assert message in stash_list


# ===== Tests for pop_stash() =====


class TestPopStash:
    async def test_pop_restores_changes(self, git_repo: Path) -> None:
        """pop_stash() restores changes from stash."""
        adapter = GitDiffAdapter()

        # Create and stash changes
        (git_repo / "initial.txt").write_text("modified content\n")
        await adapter.stash_changes(str(git_repo), "Test pop")

        # Verify file is restored to original
        assert (git_repo / "initial.txt").read_text() == "initial content\n"

        # Pop stash
        await adapter.pop_stash(str(git_repo))

        # Verify changes are restored
        assert (git_repo / "initial.txt").read_text() == "modified content\n"

    async def test_pop_restores_untracked_files(self, git_repo: Path) -> None:
        """pop_stash() restores untracked files."""
        adapter = GitDiffAdapter()

        # Create and stash untracked file
        (git_repo / "new_file.txt").write_text("new content\n")
        await adapter.stash_changes(str(git_repo), "Test pop untracked")

        # File should be gone
        assert not (git_repo / "new_file.txt").exists()

        # Pop stash
        await adapter.pop_stash(str(git_repo))

        # File should be restored
        assert (git_repo / "new_file.txt").exists()
        assert (git_repo / "new_file.txt").read_text() == "new content\n"

    async def test_pop_removes_stash_entry(self, git_repo: Path) -> None:
        """After pop, stash entry is removed."""
        adapter = GitDiffAdapter()

        # Create and stash changes
        (git_repo / "initial.txt").write_text("modified\n")
        await adapter.stash_changes(str(git_repo), "Test remove")

        # Pop stash
        await adapter.pop_stash(str(git_repo))

        # Check stash list is empty
        proc = await asyncio.create_subprocess_exec(
            "git",
            "stash",
            "list",
            cwd=str(git_repo),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        stash_list = stdout.decode().strip()

        assert stash_list == ""

    async def test_pop_empty_stash_raises(self, git_repo: Path) -> None:
        """Pop from empty stash raises error."""
        adapter = GitDiffAdapter()

        # No stash created
        with pytest.raises(RuntimeError, match="Git command failed"):
            await adapter.pop_stash(str(git_repo))

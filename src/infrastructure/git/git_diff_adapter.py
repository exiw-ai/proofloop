import asyncio
import re

from loguru import logger

from src.domain.ports.diff_port import DiffPort, DiffResult


class GitDiffAdapter(DiffPort):
    """Git implementation of DiffPort using subprocess calls."""

    async def get_worktree_diff(self, repo_path: str) -> DiffResult:
        """Get diff of current worktree changes (unstaged + staged).

        Uses: git diff HEAD -- . (scoped to current directory only).
        Returns empty result for non-git directories.
        """
        if not await self._is_git_repo(repo_path):
            logger.debug(f"Not a git repository: {repo_path}")
            return DiffResult(
                diff="",
                patch="",
                files_changed=[],
                insertions=0,
                deletions=0,
            )

        has_head = await self._has_head(repo_path)

        if has_head:
            # Use "-- ." to scope diff to only changes in workspace directory
            diff = await self._run_git(repo_path, ["diff", "HEAD", "--", "."])
            patch = await self._run_git(repo_path, ["diff", "HEAD", "--patch", "--", "."])
            stats = await self._run_git(repo_path, ["diff", "HEAD", "--stat", "--", "."])
            files = await self._run_git(repo_path, ["diff", "HEAD", "--name-only", "--", "."])
        else:
            # Empty repo - show all files as new
            logger.debug("Empty repository (no HEAD), showing all files as new")
            files_list = await self._run_git(
                repo_path, ["ls-files", "--others", "--exclude-standard"]
            )
            files = files_list
            diff = f"# New repository - {len(self._parse_files(files))} untracked files"
            patch = ""
            stats = ""

        return DiffResult(
            diff=diff,
            patch=patch,
            files_changed=self._parse_files(files),
            insertions=self._parse_insertions(stats),
            deletions=self._parse_deletions(stats),
        )

    async def _is_git_repo(self, repo_path: str) -> bool:
        """Check if directory is a git repository."""
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "--git-dir",
            cwd=repo_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        return proc.returncode == 0

    async def _has_head(self, repo_path: str) -> bool:
        """Check if repository has any commits (HEAD exists)."""
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "HEAD",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0

    async def get_staged_diff(self, repo_path: str) -> DiffResult:
        """Get diff of staged changes only.

        Uses: git diff --cached -- . (scoped to current directory only).
        Returns empty result for non-git directories.
        """
        if not await self._is_git_repo(repo_path):
            logger.debug(f"Not a git repository: {repo_path}")
            return DiffResult(
                diff="",
                patch="",
                files_changed=[],
                insertions=0,
                deletions=0,
            )

        # Use "-- ." to scope diff to only changes in workspace directory
        diff = await self._run_git(repo_path, ["diff", "--cached", "--", "."])
        patch = await self._run_git(repo_path, ["diff", "--cached", "--patch", "--", "."])
        stats = await self._run_git(repo_path, ["diff", "--cached", "--stat", "--", "."])
        files = await self._run_git(repo_path, ["diff", "--cached", "--name-only", "--", "."])

        return DiffResult(
            diff=diff,
            patch=patch,
            files_changed=self._parse_files(files),
            insertions=self._parse_insertions(stats),
            deletions=self._parse_deletions(stats),
        )

    async def _run_git(self, repo_path: str, args: list[str]) -> str:
        """Execute a git command and return stdout."""
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            error_msg = stderr.decode(errors="replace").strip()
            logger.error(f"Git command failed: git {' '.join(args)} - {error_msg}")
            raise RuntimeError(f"Git command failed: {error_msg}")
        return stdout.decode(errors="replace")

    def _parse_files(self, files_output: str) -> list[str]:
        """Parse file list from git diff --name-only output."""
        return [f for f in files_output.strip().split("\n") if f]

    def _parse_insertions(self, stats: str) -> int:
        """Parse insertions count from git diff --stat summary line."""
        # Example: " 3 files changed, 42 insertions(+), 10 deletions(-)"
        match = re.search(r"(\d+) insertion", stats)
        return int(match.group(1)) if match else 0

    def _parse_deletions(self, stats: str) -> int:
        """Parse deletions count from git diff --stat summary line."""
        # Example: " 3 files changed, 42 insertions(+), 10 deletions(-)"
        match = re.search(r"(\d+) deletion", stats)
        return int(match.group(1)) if match else 0

    async def stash_changes(self, repo_path: str, message: str) -> str:
        """Stash all changes including untracked files (respects
        .gitignore)."""
        output = await self._run_git(
            repo_path,
            ["stash", "push", "-u", "-m", message],
        )
        return output.strip()

    async def pop_stash(self, repo_path: str) -> None:
        """Restore stashed changes and remove stash entry."""
        await self._run_git(repo_path, ["stash", "pop"])

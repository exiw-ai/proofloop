"""Multi-repository management service."""

import asyncio
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, Field


class WorkspaceInfo(BaseModel, frozen=True):
    """Information about a workspace containing git repositories."""

    is_workspace: bool = Field(
        description="True if path contains multiple repos, False if single repo"
    )
    repos: list[Path] = Field(description="List of repository root paths")
    root: Path = Field(description="Workspace root path")

    @property
    def is_single_repo(self) -> bool:
        """True if workspace contains exactly one repo at root."""
        return not self.is_workspace and len(self.repos) == 1


class RepoStatus(BaseModel):
    """Status of a single repository."""

    path: Path
    has_changes: bool = False
    stash_ref: str | None = None
    error: str | None = None


class MultiRepoManager:
    """Service for managing multiple git repositories in a workspace.

    Supports:
    - Detecting git repositories in a directory tree
    - Stashing/popping changes across all repos
    - Getting status of all repos
    """

    def __init__(self, max_depth: int = 3) -> None:
        """Initialize manager.

        Args:
            max_depth: Maximum directory depth to search for .git folders.
        """
        self.max_depth = max_depth
        self._repos: list[Path] = []
        self._stash_refs: dict[Path, str] = {}

    async def discover_repos(self, workspace_path: Path) -> WorkspaceInfo:
        """Discover git repositories in a workspace path.

        Args:
            workspace_path: Root path to scan for repositories.

        Returns:
            WorkspaceInfo with discovered repositories.
        """
        workspace_path = workspace_path.resolve()
        self._repos = []

        # Check if workspace_path itself is a git repo
        if await self._is_git_repo(workspace_path):
            self._repos = [workspace_path]
            return WorkspaceInfo(
                is_workspace=False,
                repos=[workspace_path],
                root=workspace_path,
            )

        # Scan for git repos in subdirectories
        repos = await self._scan_for_repos(workspace_path, depth=0)
        self._repos = sorted(repos)

        return WorkspaceInfo(
            is_workspace=len(repos) != 1 or repos[0] != workspace_path,
            repos=self._repos,
            root=workspace_path,
        )

    async def _is_git_repo(self, path: Path) -> bool:
        """Check if path is a git repository root."""
        git_dir = path / ".git"
        return git_dir.exists() and git_dir.is_dir()

    async def _scan_for_repos(self, path: Path, depth: int) -> list[Path]:
        """Recursively scan for git repositories."""
        if depth > self.max_depth:
            return []

        repos: list[Path] = []

        # Check if current path is a repo
        if await self._is_git_repo(path):
            return [path]

        # Skip symlinks to avoid infinite loops
        if path.is_symlink():
            return []

        # Scan subdirectories
        try:
            for child in path.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    child_repos = await self._scan_for_repos(child, depth + 1)
                    repos.extend(child_repos)
        except PermissionError:
            logger.warning(f"Permission denied scanning {path}")

        return repos

    @property
    def repos(self) -> list[Path]:
        """Get list of discovered repositories."""
        return self._repos

    async def get_status_all(self) -> list[RepoStatus]:
        """Get status of all discovered repositories."""
        statuses: list[RepoStatus] = []

        for repo in self._repos:
            status = await self._get_repo_status(repo)
            statuses.append(status)

        return statuses

    async def _get_repo_status(self, repo_path: Path) -> RepoStatus:
        """Get status of a single repository."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "status",
                "--porcelain",
                cwd=str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return RepoStatus(
                    path=repo_path,
                    error=stderr.decode(errors="replace").strip(),
                )

            has_changes = bool(stdout.decode(errors="replace").strip())
            stash_ref = self._stash_refs.get(repo_path)

            return RepoStatus(
                path=repo_path,
                has_changes=has_changes,
                stash_ref=stash_ref,
            )
        except Exception as e:
            return RepoStatus(
                path=repo_path,
                error=str(e),
            )

    async def stash_all(self, message: str = "proofloop: auto-stash") -> list[RepoStatus]:
        """Stash changes in all repositories with uncommitted changes.

        Args:
            message: Stash message to use.

        Returns:
            List of RepoStatus for repos where stash was attempted.
        """
        results: list[RepoStatus] = []

        for repo in self._repos:
            status = await self._get_repo_status(repo)
            if status.error:
                results.append(status)
                continue

            if not status.has_changes:
                results.append(status)
                continue

            # Stash changes
            stash_result = await self._stash_repo(repo, message)
            results.append(stash_result)

        return results

    async def _stash_repo(self, repo_path: Path, message: str) -> RepoStatus:
        """Stash changes in a single repository."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "stash",
                "push",
                "-u",
                "-m",
                message,
                cwd=str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return RepoStatus(
                    path=repo_path,
                    error=f"Stash failed: {stderr.decode(errors='replace').strip()}",
                )

            # Parse stash reference from output
            output = stdout.decode(errors="replace").strip()
            stash_ref = "stash@{0}"  # Default
            if "Saved working directory" in output:
                self._stash_refs[repo_path] = stash_ref

            logger.info(f"Stashed changes in {repo_path}")
            return RepoStatus(
                path=repo_path,
                has_changes=False,
                stash_ref=stash_ref,
            )
        except Exception as e:
            return RepoStatus(
                path=repo_path,
                error=str(e),
            )

    async def pop_all(self) -> list[RepoStatus]:
        """Pop stashed changes in all repositories.

        Returns:
            List of RepoStatus for repos where pop was attempted.
        """
        results: list[RepoStatus] = []

        for repo in self._repos:
            if repo not in self._stash_refs:
                continue

            pop_result = await self._pop_repo(repo)
            results.append(pop_result)

        return results

    async def _pop_repo(self, repo_path: Path) -> RepoStatus:
        """Pop stashed changes in a single repository."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "stash",
                "pop",
                cwd=str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return RepoStatus(
                    path=repo_path,
                    error=f"Pop failed: {stderr.decode(errors='replace').strip()}",
                )

            # Remove from tracking
            self._stash_refs.pop(repo_path, None)

            logger.info(f"Popped stash in {repo_path}")
            status = await self._get_repo_status(repo_path)
            return status
        except Exception as e:
            return RepoStatus(
                path=repo_path,
                error=str(e),
            )

    async def rollback_all(self) -> list[RepoStatus]:
        """Rollback changes in all repositories by stashing.

        This is used for error recovery - stashes current changes
        so agent can try fresh.

        Returns:
            List of RepoStatus after rollback.
        """
        return await self.stash_all(message="proofloop: rollback")

    def get_stash_refs(self) -> dict[Path, str]:
        """Get mapping of repos to their stash references."""
        return dict(self._stash_refs)

    def clear_stash_tracking(self) -> None:
        """Clear internal stash reference tracking."""
        self._stash_refs.clear()

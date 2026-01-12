from abc import ABC, abstractmethod

from pydantic import BaseModel


class DiffResult(BaseModel):
    """Result of generating a diff."""

    diff: str  # git diff output
    patch: str  # git format-patch output
    files_changed: list[str]
    insertions: int
    deletions: int


class MultiRepoDiffResult(BaseModel):
    """Result of generating diffs across multiple repositories."""

    repo_diffs: dict[str, DiffResult]  # repo_path -> DiffResult
    total_files_changed: int
    total_insertions: int
    total_deletions: int

    @classmethod
    def from_single(cls, repo_path: str, result: DiffResult) -> "MultiRepoDiffResult":
        """Create from single repo result."""
        return cls(
            repo_diffs={repo_path: result},
            total_files_changed=len(result.files_changed),
            total_insertions=result.insertions,
            total_deletions=result.deletions,
        )

    @classmethod
    def merge(cls, results: dict[str, DiffResult]) -> "MultiRepoDiffResult":
        """Merge multiple repo results."""
        total_files = sum(len(r.files_changed) for r in results.values())
        total_ins = sum(r.insertions for r in results.values())
        total_del = sum(r.deletions for r in results.values())
        return cls(
            repo_diffs=results,
            total_files_changed=total_files,
            total_insertions=total_ins,
            total_deletions=total_del,
        )


class StashResult(BaseModel):
    """Result of stashing changes in a repository."""

    repo_path: str
    success: bool
    stash_ref: str | None = None
    error: str | None = None


class DiffPort(ABC):
    """Port for generating diffs."""

    @abstractmethod
    async def get_worktree_diff(self, repo_path: str) -> DiffResult:
        """Get diff of current worktree changes."""

    @abstractmethod
    async def get_staged_diff(self, repo_path: str) -> DiffResult:
        """Get diff of staged changes."""

    @abstractmethod
    async def stash_changes(self, repo_path: str, message: str) -> str:
        """Stash all changes including untracked files (respects .gitignore).

        Returns stash reference for later restoration.
        """

    @abstractmethod
    async def pop_stash(self, repo_path: str) -> None:
        """Restore stashed changes and remove stash entry."""

    # Multi-repo operations with default implementations

    async def get_worktree_diff_all(self, repo_paths: list[str]) -> MultiRepoDiffResult:
        """Get diff of current worktree changes across multiple repos."""
        results: dict[str, DiffResult] = {}
        for path in repo_paths:
            results[path] = await self.get_worktree_diff(path)
        return MultiRepoDiffResult.merge(results)

    async def stash_all_repos(self, repo_paths: list[str], message: str) -> list[StashResult]:
        """Stash changes in multiple repositories."""
        results: list[StashResult] = []
        for path in repo_paths:
            try:
                stash_ref = await self.stash_changes(path, message)
                results.append(StashResult(repo_path=path, success=True, stash_ref=stash_ref))
            except Exception as e:
                results.append(StashResult(repo_path=path, success=False, error=str(e)))
        return results

    async def pop_all_repos(self, repo_paths: list[str]) -> list[StashResult]:
        """Pop stashed changes in multiple repositories."""
        results: list[StashResult] = []
        for path in repo_paths:
            try:
                await self.pop_stash(path)
                results.append(StashResult(repo_path=path, success=True))
            except Exception as e:
                results.append(StashResult(repo_path=path, success=False, error=str(e)))
        return results

    async def rollback_all(
        self, repo_paths: list[str], message: str = "proofloop: rollback"
    ) -> list[StashResult]:
        """Rollback changes in all repos by stashing them."""
        return await self.stash_all_repos(repo_paths, message)

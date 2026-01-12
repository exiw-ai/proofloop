"""Workspace management for multi-repository operations."""

from pathlib import Path

from loguru import logger

from src.domain.ports.diff_port import DiffPort
from src.domain.services.multi_repo_manager import MultiRepoManager, WorkspaceInfo


class WorkspaceManager:
    """Manages workspace discovery and repository operations."""

    def __init__(
        self,
        multi_repo_manager: MultiRepoManager,
        diff_port: DiffPort,
    ) -> None:
        self._multi_repo_manager = multi_repo_manager
        self._diff_port = diff_port
        self._workspace_info: WorkspaceInfo | None = None

    @property
    def workspace_info(self) -> WorkspaceInfo | None:
        """Get current workspace info."""
        return self._workspace_info

    async def discover_workspace(self, workspace_path: Path) -> WorkspaceInfo:
        """Discover repositories in workspace."""
        self._workspace_info = await self._multi_repo_manager.discover_repos(workspace_path)
        logger.info(
            f"Discovered workspace: {len(self._workspace_info.repos)} repos, "
            f"is_workspace={self._workspace_info.is_workspace}"
        )
        return self._workspace_info

    async def stash_all_repos(self, message: str) -> None:
        """Stash changes in all repos."""
        if self._workspace_info:
            repo_paths = [str(r) for r in self._workspace_info.repos]
            results = await self._diff_port.stash_all_repos(repo_paths, message)
            for r in results:
                if r.success:
                    logger.debug(f"Stashed {r.repo_path}")
                else:
                    logger.warning(f"Failed to stash {r.repo_path}: {r.error}")

    async def rollback_all_repos(self, message: str) -> None:
        """Rollback changes in all repos by stashing."""
        if self._workspace_info:
            repo_paths = [str(r) for r in self._workspace_info.repos]
            await self._diff_port.rollback_all(repo_paths, message)

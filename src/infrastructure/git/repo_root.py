import asyncio
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, Field


class WorkspaceInfo(BaseModel, frozen=True):
    """Information about a workspace containing git repositories."""

    is_workspace: bool = Field(
        description="True if path contains multiple repos or is not directly a repo"
    )
    repos: list[Path] = Field(description="List of repository root paths")
    root: Path = Field(description="Workspace root path")

    @property
    def is_single_repo(self) -> bool:
        """True if workspace contains exactly one repo at root."""
        return not self.is_workspace and len(self.repos) == 1


async def get_repo_root(path: str | Path = ".") -> Path:
    """Get git repository root using 'git rev-parse --show-toplevel'.

    If not a git repo, initializes one automatically.
    """
    path = Path(path).resolve()

    proc = await asyncio.create_subprocess_exec(
        "git",
        "rev-parse",
        "--show-toplevel",
        cwd=str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        # Not a git repo - initialize one
        logger.info(f"Initializing git repository at {path}")
        init_proc = await asyncio.create_subprocess_exec(
            "git",
            "init",
            cwd=str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await init_proc.communicate()
        if init_proc.returncode != 0:
            raise RuntimeError(f"Failed to initialize git repository at {path}")
        return path

    return Path(stdout.decode(errors="replace").strip())


async def get_default_state_dir(path: str | Path = ".") -> Path:
    """Return <repo_root>/.proofloop as default state directory."""
    repo_root = await get_repo_root(path)
    return repo_root / ".proofloop"


async def is_git_repo(path: Path) -> bool:
    """Check if path is inside a git repository."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        "rev-parse",
        "--show-toplevel",
        cwd=str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    return proc.returncode == 0


async def scan_for_repos(path: Path, max_depth: int = 3) -> list[Path]:
    """Scan directory for git repositories.

    Args:
        path: Root path to scan.
        max_depth: Maximum depth to search.

    Returns:
        List of paths to git repository roots.
    """

    async def _scan(p: Path, depth: int) -> list[Path]:
        if depth > max_depth:
            return []

        repos: list[Path] = []

        # Check if current path is a repo
        git_dir = p / ".git"
        if git_dir.exists() and git_dir.is_dir():
            return [p]

        # Skip symlinks
        if p.is_symlink():
            return []

        # Scan subdirectories
        try:
            for child in p.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    child_repos = await _scan(child, depth + 1)
                    repos.extend(child_repos)
        except PermissionError:
            logger.warning(f"Permission denied scanning {p}")

        return repos

    return await _scan(path, 0)


async def get_workspace_info(path: str | Path = ".") -> WorkspaceInfo:
    """Get information about a workspace.

    If path is a git repo, returns single repo info.
    Otherwise, scans for child repositories.

    Args:
        path: Workspace root path.

    Returns:
        WorkspaceInfo with discovered repositories.
    """
    path = Path(path).resolve()

    # Check if path itself is a git repo
    if await is_git_repo(path):
        repo_root = await get_repo_root(path)
        return WorkspaceInfo(
            is_workspace=False,
            repos=[repo_root],
            root=path,
        )

    # Scan for child repos
    repos = await scan_for_repos(path)
    repos = sorted(repos)

    return WorkspaceInfo(
        is_workspace=True,
        repos=repos,
        root=path,
    )

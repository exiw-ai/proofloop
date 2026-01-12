from pathlib import Path
from typing import Protocol


class GitPort(Protocol):
    async def status(self, repo_path: Path) -> str:
        """Get git status --porcelain output."""
        ...

    async def stash_push(self, repo_path: Path, message: str) -> str:
        """Push changes to stash with message."""
        ...

    async def stash_pop(self, repo_path: Path) -> str:
        """Pop last stash."""
        ...

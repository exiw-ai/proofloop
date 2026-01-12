import asyncio
from pathlib import Path


class GitAdapter:
    async def status(self, repo_path: Path) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "status",
            "--porcelain",
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip()

    async def stash_push(self, repo_path: Path, message: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "stash",
            "push",
            "-m",
            message,
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip()

    async def stash_pop(self, repo_path: Path) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "stash",
            "pop",
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip()

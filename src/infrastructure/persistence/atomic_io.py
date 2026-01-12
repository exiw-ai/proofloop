from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import aiofiles
from loguru import logger


async def atomic_write(path: Path, content: str, suffix: str | None = None) -> None:
    """Write content to file atomically using temp file + rename pattern."""
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path_str = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=".tmp_",
        suffix=suffix or path.suffix,
    )
    temp_path = Path(temp_path_str)

    try:
        async with aiofiles.open(fd, mode="w", encoding="utf-8", closefd=True) as f:
            await f.write(content)
        await asyncio.to_thread(temp_path.rename, path)
        logger.debug("Atomic write completed: {}", path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise

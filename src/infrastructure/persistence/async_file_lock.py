"""Async-safe file lock wrapper.

Wraps filelock.FileLock to avoid blocking the asyncio event loop.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from filelock import FileLock


@asynccontextmanager
async def async_file_lock(lock_path: Path) -> AsyncIterator[None]:
    """Async context manager for file locking.

    Acquires and releases the lock in a thread pool to avoid
    blocking the event loop.

    Usage:
        async with async_file_lock(lock_path):
            await do_something()
    """
    lock = FileLock(lock_path)

    # Acquire lock in thread pool to avoid blocking event loop
    await asyncio.to_thread(lock.acquire)
    try:
        yield
    finally:
        # Release lock in thread pool
        await asyncio.to_thread(lock.release)

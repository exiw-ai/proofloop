import asyncio
import time
from dataclasses import dataclass

from src.application.services.tool_gating import (
    ToolGatingError,
    validate_research_bash,
)


@dataclass
class BashResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


class SafeBashExecutor:
    """Execute bash commands with research pipeline safety validation."""

    def __init__(self, cwd: str | None = None, timeout_s: int = 60):
        self.cwd = cwd
        self.timeout_s = timeout_s

    async def execute(self, command: str) -> BashResult:
        """Execute a command after validating it's safe for research
        pipeline."""
        if not validate_research_bash(command):
            raise ToolGatingError(f"Command not allowed in research pipeline: '{command}'")

        start = time.monotonic()

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout_s,
                )
            except TimeoutError as e:
                process.kill()
                await process.wait()
                raise TimeoutError(f"Command timed out after {self.timeout_s}s: {command}") from e

            duration_ms = int((time.monotonic() - start) * 1000)

            return BashResult(
                command=command,
                exit_code=process.returncode or 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                duration_ms=duration_ms,
            )

        except OSError as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            return BashResult(
                command=command,
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
            )

    def execute_sync(self, command: str) -> BashResult:
        """Synchronous wrapper for execute."""
        return asyncio.run(self.execute(command))

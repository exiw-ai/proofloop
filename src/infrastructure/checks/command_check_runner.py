import asyncio
import os
import re
import signal
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from src.domain.ports.check_runner_port import CheckRunnerPort, CheckRunResult
from src.domain.value_objects.check_types import CheckSpec
from src.domain.value_objects.condition_enums import CheckStatus

# Dangerous command patterns that should never be executed
DANGEROUS_COMMAND_PATTERNS = [
    r"rm\s+-rf\s+/",  # rm -rf /
    r"rm\s+-rf\s+~",  # rm -rf ~
    r"rm\s+-rf\s+\*",  # rm -rf *
    r"mkfs\.",  # filesystem format
    r"dd\s+if=.*of=/dev/",  # disk overwrite
    r">\s*/dev/sd",  # overwrite disk
    r"curl.*\|\s*(ba)?sh",  # curl pipe to shell
    r"wget.*\|\s*(ba)?sh",  # wget pipe to shell
]


def _is_dangerous_command(command: str) -> str | None:
    """Check if a command matches any dangerous patterns.

    Returns the matched pattern if dangerous, None otherwise.
    """
    for pattern in DANGEROUS_COMMAND_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return pattern
    return None


class CommandCheckRunner(CheckRunnerPort):
    async def run_check(
        self,
        check: CheckSpec,
        cwd: str,
    ) -> CheckRunResult:
        start = datetime.now(UTC)

        # Security check: reject dangerous commands
        dangerous_pattern = _is_dangerous_command(check.command)
        if dangerous_pattern:
            logger.error(
                "Check '{}' blocked: command matches dangerous pattern '{}'",
                check.name,
                dangerous_pattern,
            )
            return CheckRunResult(
                check_id=check.id,
                status=CheckStatus.FAIL,
                exit_code=-1,
                stdout="",
                stderr=f"Command blocked: matches dangerous pattern '{dangerous_pattern}'",
                duration_ms=0,
                timestamp=start,
            )

        env = dict(os.environ)
        env.update(check.env)

        work_dir = Path(check.cwd) if check.cwd else Path(cwd)

        try:
            proc = await asyncio.create_subprocess_shell(
                check.command,
                cwd=str(work_dir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,  # Create new process group for proper cleanup
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=check.timeout_s,
                )
            except TimeoutError:
                # Kill entire process group to ensure child processes are terminated
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    # Process already terminated
                    proc.kill()
                await proc.wait()
                logger.warning(
                    "Check '{}' timed out after {}s",
                    check.name,
                    check.timeout_s,
                )
                return CheckRunResult(
                    check_id=check.id,
                    status=CheckStatus.FAIL,
                    exit_code=-1,
                    stdout="",
                    stderr=f"Timeout after {check.timeout_s}s",
                    duration_ms=check.timeout_s * 1000,
                    timestamp=start,
                )

            end = datetime.now(UTC)
            duration_ms = int((end - start).total_seconds() * 1000)

            return CheckRunResult(
                check_id=check.id,
                status=CheckStatus.PASS if proc.returncode == 0 else CheckStatus.FAIL,
                exit_code=proc.returncode or 0,
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                duration_ms=duration_ms,
                timestamp=start,
            )

        except Exception as e:
            end = datetime.now(UTC)
            duration_ms = int((end - start).total_seconds() * 1000)
            logger.error(
                "Check '{}' failed with error: {}",
                check.name,
                e,
            )
            return CheckRunResult(
                check_id=check.id,
                status=CheckStatus.FAIL,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
                timestamp=start,
            )

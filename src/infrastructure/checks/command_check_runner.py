import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from src.domain.ports.check_runner_port import CheckRunnerPort, CheckRunResult
from src.domain.value_objects.check_types import CheckSpec
from src.domain.value_objects.condition_enums import CheckStatus


class CommandCheckRunner(CheckRunnerPort):
    async def run_check(
        self,
        check: CheckSpec,
        cwd: str,
    ) -> CheckRunResult:
        start = datetime.now(UTC)

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
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=check.timeout_s,
                )
            except TimeoutError:
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

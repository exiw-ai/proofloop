from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.domain.value_objects.check_types import CheckSpec
from src.domain.value_objects.condition_enums import CheckStatus


class CheckRunResult(BaseModel):
    """Result of running a check."""

    check_id: UUID
    status: CheckStatus
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timestamp: datetime


class CheckRunnerPort(ABC):
    """Port for running checks."""

    @abstractmethod
    async def run_check(
        self,
        check: CheckSpec,
        cwd: str,
    ) -> CheckRunResult:
        """Run a single check and return result."""

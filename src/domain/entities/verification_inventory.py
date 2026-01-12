from typing import Any
from uuid import UUID

from pydantic import BaseModel

from src.domain.ports.check_runner_port import CheckRunResult
from src.domain.value_objects import CheckSpec


class VerificationInventory(BaseModel):
    checks: list[CheckSpec]
    baseline: dict[UUID, CheckRunResult] | None = None
    project_structure: dict[str, Any]
    conventions: list[str]

    def get_check(self, check_id: UUID) -> CheckSpec | None:
        for check in self.checks:
            if check.id == check_id:
                return check
        return None

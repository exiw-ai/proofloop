from typing import Any
from uuid import UUID

from pydantic import BaseModel

from src.domain.value_objects import CheckSpec, EvidenceRef


class VerificationInventory(BaseModel):
    checks: list[CheckSpec]
    baseline: dict[UUID, EvidenceRef] | None = None
    project_structure: dict[str, Any]
    conventions: list[str]

    def get_check(self, check_id: UUID) -> CheckSpec | None:
        for check in self.checks:
            if check.id == check_id:
                return check
        return None

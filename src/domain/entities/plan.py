from uuid import UUID

from pydantic import BaseModel


class PlanStep(BaseModel):
    number: int
    description: str
    target_files: list[str] = []
    related_conditions: list[UUID] = []


class Plan(BaseModel):
    goal: str
    approach: str | None = None
    boundaries: list[str]
    steps: list[PlanStep]
    risks: list[str] = []
    assumptions: list[str] = []
    replan_conditions: list[str] = []
    version: int = 1
    approved: bool = False

    def approve(self) -> None:
        self.approved = True

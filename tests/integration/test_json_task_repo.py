"""Integration tests for JsonTaskRepo persistence."""

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from src.domain.entities.budget import Budget
from src.domain.entities.condition import Condition
from src.domain.entities.plan import Plan, PlanStep
from src.domain.entities.task import Task
from src.domain.entities.verification_inventory import VerificationInventory
from src.domain.value_objects.check_types import CheckKind, CheckSpec
from src.domain.value_objects.condition_enums import ApprovalStatus, ConditionRole
from src.domain.value_objects.task_status import TaskStatus
from src.infrastructure.persistence.json_task_repo import JsonTaskRepo


@pytest.fixture
def temp_state_dir() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def repo(temp_state_dir: Path) -> JsonTaskRepo:
    return JsonTaskRepo(temp_state_dir)


@pytest.fixture
def sample_task() -> Task:
    return Task(
        id=uuid4(),
        description="Test task",
        goals=["Goal 1", "Goal 2"],
        sources=["/tmp/project"],
        constraints=["No breaking changes"],
        status=TaskStatus.INTAKE,
        budget=Budget(),
        conditions=[],
        iterations=[],
    )


class TestJsonTaskRepoSaveLoad:
    async def test_save_and_load_task(
        self,
        repo: JsonTaskRepo,
        sample_task: Task,
    ) -> None:
        await repo.save(sample_task)
        loaded = await repo.load(sample_task.id)

        assert loaded is not None
        assert loaded.id == sample_task.id
        assert loaded.description == sample_task.description
        assert loaded.goals == sample_task.goals
        assert loaded.status == sample_task.status

    async def test_load_nonexistent_task_returns_none(
        self,
        repo: JsonTaskRepo,
    ) -> None:
        result = await repo.load(uuid4())
        assert result is None

    async def test_list_tasks_empty(
        self,
        repo: JsonTaskRepo,
    ) -> None:
        tasks = await repo.list_tasks()
        assert tasks == []

    async def test_list_tasks_returns_saved_tasks(
        self,
        repo: JsonTaskRepo,
        sample_task: Task,
    ) -> None:
        task2 = Task(
            id=uuid4(),
            description="Task 2",
            goals=[],
            sources=["/tmp"],
            constraints=[],
            status=TaskStatus.INTAKE,
            budget=Budget(),
            conditions=[],
            iterations=[],
        )

        await repo.save(sample_task)
        await repo.save(task2)

        task_ids = await repo.list_tasks()

        assert len(task_ids) == 2
        assert sample_task.id in task_ids
        assert task2.id in task_ids

    async def test_save_overwrites_existing_task(
        self,
        repo: JsonTaskRepo,
        sample_task: Task,
    ) -> None:
        await repo.save(sample_task)

        sample_task.description = "Updated description"
        sample_task.status = TaskStatus.EXECUTING
        await repo.save(sample_task)

        loaded = await repo.load(sample_task.id)

        assert loaded is not None
        assert loaded.description == "Updated description"
        assert loaded.status == TaskStatus.EXECUTING


class TestJsonTaskRepoConditions:
    async def test_save_conditions_approval(
        self,
        repo: JsonTaskRepo,
        sample_task: Task,
    ) -> None:
        check_id = uuid4()
        conditions = [
            Condition(
                id=uuid4(),
                description="Tests must pass",
                role=ConditionRole.BLOCKING,
                approval_status=ApprovalStatus.APPROVED,
                check_id=check_id,
            ),
            Condition(
                id=uuid4(),
                description="Lint warnings",
                role=ConditionRole.SIGNAL,
                approval_status=ApprovalStatus.PROPOSED,
            ),
        ]

        await repo.save(sample_task)
        await repo.save_conditions_approval(sample_task.id, conditions)

        # Verify file exists
        conditions_path = repo._paths.task_dir(sample_task.id) / "approvals" / "conditions.json"
        assert conditions_path.exists()

    async def test_conditions_versioning(
        self,
        repo: JsonTaskRepo,
        sample_task: Task,
    ) -> None:
        await repo.save(sample_task)

        conditions_v1 = [
            Condition(
                id=uuid4(),
                description="V1 condition",
                role=ConditionRole.BLOCKING,
                approval_status=ApprovalStatus.DRAFT,
            ),
        ]
        await repo.save_conditions_approval(sample_task.id, conditions_v1)

        conditions_v2 = [
            Condition(
                id=uuid4(),
                description="V2 condition",
                role=ConditionRole.BLOCKING,
                approval_status=ApprovalStatus.APPROVED,
                check_id=uuid4(),
            ),
        ]
        await repo.save_conditions_approval(sample_task.id, conditions_v2)

        # Read raw file to check versioning
        import json

        conditions_path = repo._paths.task_dir(sample_task.id) / "approvals" / "conditions.json"
        with open(conditions_path) as f:
            data = json.load(f)

        assert data["current_version"] == 2
        assert data["approved_version"] == 2
        assert len(data["versions"]) == 2


class TestJsonTaskRepoPlan:
    async def test_save_plan_approval(
        self,
        repo: JsonTaskRepo,
        sample_task: Task,
    ) -> None:
        plan = Plan(
            goal="Implement feature",
            boundaries=["Only modify src/"],
            steps=[
                PlanStep(number=1, description="Create module"),
                PlanStep(number=2, description="Add tests"),
            ],
            risks=["May affect performance"],
            assumptions=["Python 3.11+"],
            replan_conditions=["If tests fail"],
        )

        await repo.save(sample_task)
        await repo.save_plan_approval(sample_task.id, plan)

        plan_path = repo._paths.task_dir(sample_task.id) / "approvals" / "plan.json"
        assert plan_path.exists()


class TestJsonTaskRepoInventory:
    async def test_save_inventory(
        self,
        repo: JsonTaskRepo,
        sample_task: Task,
    ) -> None:
        inventory = VerificationInventory(
            checks=[
                CheckSpec(
                    id=uuid4(),
                    name="test",
                    kind=CheckKind.TEST,
                    command="pytest",
                    cwd="/tmp",
                ),
                CheckSpec(
                    id=uuid4(),
                    name="lint",
                    kind=CheckKind.LINT,
                    command="ruff check",
                    cwd="/tmp",
                ),
            ],
            baseline=None,
            project_structure={"type": "python"},
            conventions=["PEP8", "Type hints"],
        )

        await repo.save(sample_task)
        await repo.save_inventory(sample_task.id, inventory)

        inventory_path = repo._paths.task_dir(sample_task.id) / "inventory" / "inventory.json"
        assert inventory_path.exists()

    async def test_task_with_inventory_saves_correctly(
        self,
        repo: JsonTaskRepo,
    ) -> None:
        check_id = uuid4()
        inventory = VerificationInventory(
            checks=[
                CheckSpec(
                    id=check_id,
                    name="test",
                    kind=CheckKind.TEST,
                    command="pytest",
                    cwd="/tmp",
                ),
            ],
            baseline=None,
            project_structure={},
            conventions=[],
        )

        task = Task(
            id=uuid4(),
            description="Task with inventory",
            goals=[],
            sources=["/tmp"],
            constraints=[],
            status=TaskStatus.VERIFICATION_INVENTORY,
            budget=Budget(),
            conditions=[],
            iterations=[],
            verification_inventory=inventory,
        )

        await repo.save(task)
        loaded = await repo.load(task.id)

        assert loaded is not None
        assert loaded.verification_inventory is not None
        assert len(loaded.verification_inventory.checks) == 1
        assert loaded.verification_inventory.checks[0].id == check_id

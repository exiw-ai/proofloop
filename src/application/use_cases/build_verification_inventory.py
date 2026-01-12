from uuid import UUID, uuid4

from loguru import logger

from src.domain.entities.task import Task
from src.domain.entities.verification_inventory import VerificationInventory
from src.domain.ports.agent_port import MessageCallback
from src.domain.ports.check_runner_port import CheckRunnerPort, CheckRunResult
from src.domain.ports.task_repo_port import TaskRepoPort
from src.domain.ports.verification_port import VerificationPort
from src.domain.value_objects.check_types import CheckKind, CheckSpec
from src.domain.value_objects.task_status import TaskStatus


class BuildVerificationInventory:
    def __init__(
        self,
        verification_port: VerificationPort,
        check_runner: CheckRunnerPort,
        task_repo: TaskRepoPort,
    ) -> None:
        self.verification_port = verification_port
        self.check_runner = check_runner
        self.task_repo = task_repo

    async def execute(
        self,
        task: Task,
        run_baseline: bool = False,
        on_message: MessageCallback | None = None,
    ) -> VerificationInventory:
        """Analyze project and build verification inventory.

        Must complete before any code changes.
        """
        source = task.sources[0]
        analysis = await self.verification_port.analyze_project(source, on_message)

        checks: list[CheckSpec] = []
        for kind_str, command in analysis.commands.items():
            if command:
                kind = self._map_kind(kind_str)
                checks.append(
                    CheckSpec(
                        id=uuid4(),
                        name=f"{kind_str}_check",
                        kind=kind,
                        command=command,
                        cwd=source,
                    )
                )

        inventory = VerificationInventory(
            checks=checks,
            baseline=None,
            project_structure=analysis.structure,
            conventions=analysis.conventions,
        )

        if run_baseline:
            baseline: dict[UUID, CheckRunResult] = {}
            for check in checks:
                result = await self.check_runner.run_check(check, source)
                baseline[check.id] = result
                logger.debug("Baseline check {} completed", check.name)
            inventory.baseline = baseline

        task.verification_inventory = inventory
        task.transition_to(TaskStatus.VERIFICATION_INVENTORY)
        await self.task_repo.save_inventory(task.id, inventory)
        await self.task_repo.save(task)

        logger.info(
            "Verification inventory built for task {}: {} checks discovered",
            task.id,
            len(checks),
        )

        return inventory

    def _map_kind(self, kind_str: str) -> CheckKind:
        mapping = {
            "test": CheckKind.TEST,
            "lint": CheckKind.LINT,
            "build": CheckKind.BUILD,
            "typecheck": CheckKind.TYPECHECK,
        }
        return mapping.get(kind_str, CheckKind.CUSTOM)

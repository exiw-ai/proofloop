from src.application.services.tool_gating import get_allowed_tools
from src.domain.entities.task import Task
from src.domain.ports.agent_port import AgentPort, MessageCallback
from src.domain.ports.check_runner_port import CheckRunnerPort
from src.domain.ports.task_repo_port import TaskRepoPort
from src.domain.value_objects.task_status import TaskStatus


class RunQualityLoop:
    def __init__(
        self,
        agent: AgentPort,
        check_runner: CheckRunnerPort,
        task_repo: TaskRepoPort,
    ):
        self.agent = agent
        self.check_runner = check_runner
        self.task_repo = task_repo

    async def execute(
        self,
        task: Task,
        max_iterations: int = 3,
        on_message: MessageCallback | None = None,
    ) -> bool:
        """Run quality improvement loop.

        Returns True if quality checks pass. Limited by max_iterations.
        """
        task.transition_to(TaskStatus.QUALITY)

        for _ in range(max_iterations):
            prompt = f"""Review the changes made for this task: {task.description}

Check for:
- Code quality and conventions
- Edge cases
- Potential issues

If improvements are needed, make them. Otherwise respond with "QUALITY_OK"."""

            result = await self.agent.execute(
                prompt=prompt,
                allowed_tools=get_allowed_tools(task.status),
                cwd=task.sources[0],
                on_message=on_message,
            )

            if "QUALITY_OK" in result.final_response:
                return True

            task.budget.quality_loop_count += 1
            if task.budget.quality_loop_count >= task.budget.quality_loop_limit:
                break

        await self.task_repo.save(task)
        return True

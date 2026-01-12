from pathlib import Path

from loguru import logger

from src.application.use_cases.hydrate_external_context import HydrateExternalContext
from src.domain.entities.plan import Plan, PlanStep
from src.domain.entities.task import Task
from src.domain.ports.agent_port import AgentPort, MessageCallback
from src.domain.ports.task_repo_port import TaskRepoPort
from src.domain.value_objects.clarification import (
    DECIDE_FOR_ME_OPTION,
    ClarificationAnswer,
    ClarificationOption,
    ClarificationQuestion,
)
from src.domain.value_objects.task_status import TaskStatus
from src.infrastructure.utils import extract_json
from src.infrastructure.utils.agent_json import parse_agent_json

# Tools allowed during planning (includes web access for research)
PLANNING_ALLOWED_TOOLS = ["Read", "Glob", "Grep", "WebSearch", "WebFetch"]


class CreatePlan:
    def __init__(self, agent: AgentPort, task_repo: TaskRepoPort) -> None:
        self.agent = agent
        self.task_repo = task_repo

    async def ask_clarifications(
        self,
        task: Task,
        on_message: MessageCallback | None = None,
    ) -> list[ClarificationQuestion]:
        """Ask agent to identify ambiguous decisions that need user
        clarification."""
        conventions = []
        frameworks = []
        if task.verification_inventory:
            conventions = task.verification_inventory.conventions
            frameworks = task.verification_inventory.project_structure.get("frameworks", [])

        prompt = f"""Analyze this task and identify key decisions that need user clarification.

Task: {task.description}
Goals: {task.goals}
Constraints: {task.constraints}
Project conventions: {conventions}
Frameworks in use: {frameworks}

IMPORTANT - Before generating questions:
1. Extract key domain terms from the task description
2. Search for existing implementation:
   - Use Grep to search code CONTENT (classes, functions, patterns)
   - Use Glob to find files BY NAME (e.g., "docker-compose*", "alembic.ini", "*config*")
3. Read any existing implementation files you find
4. Determine task intent:
   - MODIFICATION (keywords: "change", "migrate", "replace", "switch", "refactor")
     → Ask questions about desired changes even if implementation exists
   - CONTINUATION (keywords: "create", "add", "implement", "extend", "complete")
     → Do NOT ask about already implemented parts, use existing code

Only ask about genuinely ambiguous decisions based on the determined intent.

Return JSON array (empty if task is clear or existing code answers the questions):
[
    {{
        "id": "unique_id",
        "question": "What should X be?",
        "context": "Brief explanation why this matters",
        "options": [
            {{"key": "opt1", "label": "Option 1", "description": "What this means"}},
            {{"key": "opt2", "label": "Option 2", "description": "What this means"}}
        ]
    }}
]

Return ONLY questions about genuinely ambiguous decisions.
If the task is clear - return empty array [].
Limit to 3-5 most important questions."""

        result = await self.agent.execute(
            prompt=prompt,
            allowed_tools=PLANNING_ALLOWED_TOOLS,
            cwd=task.sources[0],
            on_message=on_message,
        )

        data = parse_agent_json(result.final_response, None)
        if data is None:
            logger.warning("Failed to parse clarification questions, proceeding without")
            return []

        questions = []
        for q in data:
            options = [ClarificationOption(**opt) for opt in q.get("options", [])]
            # Add "decide for me" option to each question
            options.append(DECIDE_FOR_ME_OPTION)

            questions.append(
                ClarificationQuestion(
                    id=q["id"],
                    question=q["question"],
                    context=q.get("context", ""),
                    options=options,
                    default_option="_auto",
                )
            )

        logger.info(f"Generated {len(questions)} clarification questions for task {task.id}")
        return questions

    async def execute(
        self,
        task: Task,
        clarifications: list[ClarificationAnswer] | None = None,
        on_message: MessageCallback | None = None,
    ) -> Plan:
        """Use agent to create execution plan.

        Transitions task to PLANNING status.
        """
        # Extract project context from verification inventory
        conventions = []
        project_structure = {}
        frameworks = []
        if task.verification_inventory:
            conventions = task.verification_inventory.conventions
            project_structure = task.verification_inventory.project_structure
            # Extract frameworks if available in project_structure
            frameworks = project_structure.get("frameworks", [])

        # Format clarification answers if provided
        clarification_section = ""
        if clarifications:
            answers_text = []
            for ans in clarifications:
                if ans.selected_option == "_auto":
                    answers_text.append(f"- {ans.question_id}: Let agent decide (best practices)")
                elif ans.selected_option == "custom" and ans.custom_value:
                    answers_text.append(f"- {ans.question_id}: {ans.custom_value}")
                else:
                    answers_text.append(f"- {ans.question_id}: {ans.selected_option}")
            clarification_section = f"""
User decisions on ambiguous points:
{chr(10).join(answers_text)}

These decisions are REQUIREMENTS - incorporate them into the plan.
"""

        # Format project context section
        project_context = ""
        if project_structure:
            structure_text = []
            if project_structure.get("root_files"):
                structure_text.append(
                    f"Root files: {', '.join(project_structure['root_files'][:10])}"
                )
            if project_structure.get("src_dirs"):
                structure_text.append(f"Source dirs: {', '.join(project_structure['src_dirs'])}")
            if project_structure.get("test_dirs"):
                structure_text.append(f"Test dirs: {', '.join(project_structure['test_dirs'])}")
            if frameworks:
                structure_text.append(f"Frameworks: {', '.join(frameworks)}")
            if structure_text:
                project_context = f"""
Project structure (pre-analyzed):
{chr(10).join(structure_text)}
"""

        prompt = f"""Create an execution plan for this task:

Description: {task.description}
Goals: {task.goals}
Constraints: {task.constraints}
Project conventions: {conventions}
{project_context}{clarification_section}
IMPORTANT - Before creating the plan:
1. Extract key domain terms from the task description
2. Search for existing implementation:
   - Use Grep to search code CONTENT (classes, functions, patterns)
   - Use Glob to find files BY NAME (e.g., "docker-compose*", "alembic.ini", "*config*")
3. Read any existing implementation files you find
4. Determine task intent:
   - MODIFICATION (keywords: "change", "migrate", "replace", "switch", "refactor")
     → Plan should modify/replace existing implementation
   - CONTINUATION (keywords: "create", "add", "implement", "extend", "complete")
     → Plan should BUILD ON existing code, not recreate it

If no existing implementation found:
- Treat as greenfield and create from scratch
{self._get_research_context_hint(task)}
Return JSON:
{{
    "goal": "main objective",
    "approach": "2-3 sentences explaining your reasoning and what will be done",
    "boundaries": ["what we will NOT do"],
    "steps": [
        {{"number": 1, "description": "...", "target_files": [...]}},
        ...
    ],
    "risks": ["potential issues"],
    "assumptions": ["what we assume"],
    "replan_conditions": ["when to replan"]
}}"""

        result = await self.agent.execute(
            prompt=prompt,
            allowed_tools=PLANNING_ALLOWED_TOOLS,
            cwd=task.sources[0],
            on_message=on_message,
        )

        data = extract_json(result.final_response)
        plan = Plan(
            goal=data["goal"],
            approach=data.get("approach"),
            boundaries=data.get("boundaries", []),
            steps=[PlanStep(**s) for s in data["steps"]],
            risks=data.get("risks", []),
            assumptions=data.get("assumptions", []),
            replan_conditions=data.get("replan_conditions", []),
        )

        task.plan = plan
        task.transition_to(TaskStatus.PLANNING)
        await self.task_repo.save(task)

        logger.info("Plan created for task {} with {} steps", task.id, len(plan.steps))

        return plan

    async def refine(
        self,
        task: Task,
        feedback: str,
        on_message: MessageCallback | None = None,
    ) -> Plan:
        """Refine existing plan based on user feedback."""
        if not task.plan:
            return await self.execute(task, on_message=on_message)

        current_plan = task.plan
        conventions = task.verification_inventory.conventions if task.verification_inventory else []

        prompt = f"""Refine the execution plan based on user feedback.

Current plan:
Goal: {current_plan.goal}
Steps:
{chr(10).join(f"  {s.number}. {s.description}" for s in current_plan.steps)}

User feedback:
{feedback}

Task description: {task.description}
Project conventions: {conventions}

Return an UPDATED JSON plan addressing the feedback:
{{
    "goal": "main objective",
    "boundaries": ["what we will NOT do"],
    "steps": [
        {{"number": 1, "description": "...", "target_files": [...]}},
        ...
    ],
    "risks": ["potential issues"],
    "assumptions": ["what we assume"],
    "replan_conditions": ["when to replan"]
}}"""

        result = await self.agent.execute(
            prompt=prompt,
            allowed_tools=PLANNING_ALLOWED_TOOLS,
            cwd=task.sources[0],
            on_message=on_message,
        )

        data = extract_json(result.final_response)
        plan = Plan(
            goal=data["goal"],
            approach=data.get("approach"),
            boundaries=data.get("boundaries", []),
            steps=[PlanStep(**s) for s in data["steps"]],
            risks=data.get("risks", []),
            assumptions=data.get("assumptions", []),
            replan_conditions=data.get("replan_conditions", []),
            version=current_plan.version + 1,
        )

        task.plan = plan
        await self.task_repo.save(task)

        logger.info(
            "Plan refined for task {} (v{}): {} steps", task.id, plan.version, len(plan.steps)
        )

        return plan

    def _get_research_context_hint(self, task: Task) -> str:
        """Get hint about available research context."""
        if not task.sources:
            return ""

        workspace_path = Path(task.sources[0])
        hydrator = HydrateExternalContext()
        context_info = hydrator.discover_research_context(workspace_path)

        if context_info.exists:
            return context_info.prompt_injection

        return ""

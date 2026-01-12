from pathlib import Path

from src.domain.entities import Task
from src.domain.ports.agent_port import AgentPort, MessageCallback
from src.domain.value_objects import TaskStatus
from src.infrastructure.research import RepoContextStore
from src.infrastructure.utils.agent_json import parse_agent_json


class CaptureRepoContext:
    """Use case for capturing repository context."""

    def __init__(
        self,
        agent: AgentPort,
        repo_context_store: RepoContextStore,
    ):
        self.agent = agent
        self.repo_context_store = repo_context_store

    async def run(
        self,
        task: Task,
        workspace_path: Path,
        mode: str = "light",
        on_message: MessageCallback | None = None,
    ) -> bool:
        """Capture repository context for research.

        Args:
            task: The research task
            workspace_path: Path to workspace
            mode: "off", "light", or "full"

        Returns:
            True if context was captured, False if skipped
        """
        if mode == "off":
            return False

        task.transition_to(TaskStatus.RESEARCH_REPO_CONTEXT)

        limits = {
            "light": {"max_files": 50, "max_excerpts": 20, "max_bytes": 5000},
            "full": {"max_files": 500, "max_excerpts": 50, "max_bytes": 10000},
        }.get(mode, {"max_files": 50, "max_excerpts": 20, "max_bytes": 5000})

        prompt = f"""Analyze the codebase structure to provide context for research.

Workspace: {workspace_path}
Mode: {mode}
Limits: {limits}

Tasks:
1. Identify key source files and their purpose
2. Find relevant documentation
3. Understand project structure and patterns
4. Extract relevant code excerpts that inform the research

Focus on files relevant to the research task:
{task.description}

Use Read, Glob, and Grep tools to explore the codebase.
Do NOT modify any files.

Respond with JSON:
{{
    "repos": [
        {{
            "name": "repo_name",
            "path": "relative/path",
            "commit": "abc123",
            "branch": "main",
            "dirty": false,
            "dirty_files": [],
            "files_analyzed": 42,
            "excerpts": [
                {{"file": "path/to/file.py", "text": "relevant code...", "purpose": "why relevant"}}
            ]
        }}
    ],
    "stats": {{
        "total_files_analyzed": 42,
        "analysis_duration_ms": 1234
    }}
}}"""

        from src.application.services.tool_gating import get_research_tools

        result = await self.agent.execute(
            prompt=prompt,
            allowed_tools=get_research_tools(task.status),
            cwd=str(workspace_path),
            on_message=on_message,
        )

        data = parse_agent_json(result.final_response, None)

        if data is None:
            return False

        repos_info = []
        for repo_data in data.get("repos", []):
            await self.repo_context_store.save_repo_analysis(
                repo_name=repo_data.get("name", "workspace"),
                repo_path=repo_data.get("path", str(workspace_path)),
                commit=repo_data.get("commit", "unknown"),
                branch=repo_data.get("branch", "main"),
                dirty=repo_data.get("dirty", False),
                dirty_files=repo_data.get("dirty_files", []),
                files_analyzed=repo_data.get("files_analyzed", 0),
                excerpts=repo_data.get("excerpts", []),
            )
            repos_info.append(
                {
                    "name": repo_data.get("name", "workspace"),
                    "path": repo_data.get("path", str(workspace_path)),
                    "commit": repo_data.get("commit", "unknown"),
                    "branch": repo_data.get("branch", "main"),
                    "dirty": repo_data.get("dirty", False),
                    "dirty_files": repo_data.get("dirty_files", []),
                    "files_analyzed": repo_data.get("files_analyzed", 0),
                    "excerpts_extracted": len(repo_data.get("excerpts", [])),
                }
            )

        await self.repo_context_store.save_manifest(
            mode=mode,
            workspace_root=str(workspace_path),
            repos=repos_info,
            limits=limits,
            stats=data.get("stats", {}),
        )

        return True

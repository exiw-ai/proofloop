import json

from loguru import logger

from src.domain.ports.agent_port import AgentPort, MessageCallback
from src.domain.ports.verification_port import ProjectAnalysis, VerificationPort
from src.infrastructure.utils import extract_json


class ProjectAnalyzer(VerificationPort):
    """Implementation of VerificationPort that uses an agent to analyze
    projects.

    Discovers project structure, verification commands, and conventions
    by letting the agent read configuration files.
    """

    def __init__(self, agent: AgentPort) -> None:
        self._agent = agent

    async def analyze_project(
        self,
        path: str,
        on_message: MessageCallback | None = None,
    ) -> ProjectAnalysis:
        """Use agent to analyze project structure and discover verification
        commands.

        The agent reads configuration files (pyproject.toml,
        package.json, Makefile, etc.) to identify test, lint, build, and
        typecheck commands along with project conventions.
        """
        prompt = f"""Analyze the project at {path} and return a JSON with:
{{
    "structure": {{"root_files": [...], "src_dirs": [...], "test_dirs": [...]}},
    "commands": {{
        "test": "<command>" or null,
        "lint": "<command>" or null,
        "build": "<command>" or null,
        "typecheck": "<command>" or null
    }},
    "conventions": ["<discovered convention>", ...],
    "frameworks": ["<discovered framework>", ...]
}}

Read project config files to discover actual commands, conventions and frameworks used.
Return ONLY the JSON, no explanation or markdown code blocks."""

        logger.debug(f"Analyzing project at: {path}")

        result = await self._agent.execute(
            prompt=prompt,
            allowed_tools=["Read", "Glob", "Grep", "Bash"],
            cwd=path,
            on_message=on_message,
        )

        return self._parse_response(result.final_response)

    def _parse_response(self, response: str) -> ProjectAnalysis:
        """Parse JSON response from agent into ProjectAnalysis."""
        try:
            data = extract_json(response)

            return ProjectAnalysis(
                structure=data.get("structure", {}),
                commands=data.get("commands", {}),
                conventions=data.get("conventions", []),
                frameworks=data.get("frameworks", []),
            )
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse agent response as JSON: {e}")
            return ProjectAnalysis(
                structure={},
                commands={},
                conventions=[],
                frameworks=[],
            )

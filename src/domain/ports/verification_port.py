from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from src.domain.ports.agent_port import AgentMessage

# Callback for observing agent messages
MessageCallback = Callable[["AgentMessage"], None]


class ProjectAnalysis(BaseModel):
    """Result of project analysis."""

    structure: dict[str, object]  # directory tree, entry points
    commands: dict[str, str | None]  # test_cmd, lint_cmd, build_cmd, etc.
    conventions: list[str]  # detected conventions
    frameworks: list[str]  # detected frameworks


class VerificationPort(ABC):
    """Port for project verification discovery."""

    @abstractmethod
    async def analyze_project(
        self,
        path: str,
        on_message: MessageCallback | None = None,
    ) -> ProjectAnalysis:
        """Analyze project to discover checks and conventions."""

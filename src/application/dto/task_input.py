from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class TaskInput(BaseModel):
    """Input parameters for task execution."""

    description: str
    goals: list[str] = []
    sources: list[str] = Field(default_factory=list)
    constraints: list[str] = []
    user_conditions: list[str] = []

    # Workspace configuration
    workspace_path: Path = Field(description="Workspace root path (required)")

    # MCP configuration
    mcp_enabled: bool = Field(default=False, description="Enable MCP server support")
    mcp_servers: list[str] = Field(
        default_factory=list, description="Pre-selected MCP server names"
    )

    # Execution options
    auto_approve: bool = False
    baseline: bool = False
    timeout_minutes: int = 600  # 10 hours
    max_iterations: int = 50

    @field_validator("workspace_path", mode="before")
    @classmethod
    def validate_workspace_path(cls, v: Path | str) -> Path:
        """Ensure workspace_path is a Path and exists."""
        path = Path(v) if isinstance(v, str) else v
        if not path.exists():
            raise ValueError(f"Workspace path does not exist: {path}")
        return path.resolve()

    def model_post_init(self, __context: object) -> None:
        """Set sources from workspace_path if not provided."""
        if not self.sources:
            self.sources = [str(self.workspace_path)]

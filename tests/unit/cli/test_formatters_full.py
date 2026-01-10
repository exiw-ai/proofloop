"""Comprehensive tests for CLI formatters."""

from io import StringIO
from uuid import uuid4

from rich.console import Console

from src.cli.formatters.stage_formatter import (
    format_conditions,
    format_plan,
    format_stage_complete,
)
from src.cli.formatters.tool_formatter import (
    _get_tool_argument,
    format_tool_result,
    format_tool_use,
)
from src.domain.entities.condition import Condition
from src.domain.entities.plan import Plan, PlanStep
from src.domain.ports.agent_port import AgentMessage
from src.domain.value_objects.condition_enums import ConditionRole


def make_console() -> Console:
    return Console(file=StringIO(), force_terminal=True, width=80)


def get_output(console: Console) -> str:
    console.file.seek(0)
    return console.file.read()


# ===== Tool Formatter Tests =====


class TestGetToolArgument:
    def test_bash_returns_command(self):
        """_get_tool_argument should return command for Bash."""
        result = _get_tool_argument("Bash", {"command": "ls -la"})
        assert result == "ls -la"

    def test_read_returns_file_path(self):
        """_get_tool_argument should return file_path for Read."""
        result = _get_tool_argument("Read", {"file_path": "/path/to/file.py"})
        assert result == "/path/to/file.py"

    def test_write_returns_file_path(self):
        """_get_tool_argument should return file_path for Write."""
        result = _get_tool_argument("Write", {"file_path": "/path/to/file.py", "content": "..."})
        assert result == "/path/to/file.py"

    def test_edit_returns_file_path(self):
        """_get_tool_argument should return file_path for Edit."""
        result = _get_tool_argument(
            "Edit", {"file_path": "/path/to/file.py", "old_string": "old", "new_string": "new"}
        )
        assert result == "/path/to/file.py"

    def test_glob_returns_pattern(self):
        """_get_tool_argument should return pattern for Glob."""
        result = _get_tool_argument("Glob", {"pattern": "**/*.py"})
        assert result == "**/*.py"

    def test_grep_returns_pattern(self):
        """_get_tool_argument should return pattern for Grep."""
        result = _get_tool_argument("Grep", {"pattern": "def test_"})
        assert "def test_" in result  # Pattern is included (with quotes)

    def test_unknown_tool_returns_empty(self):
        """_get_tool_argument should return empty for unknown tool."""
        result = _get_tool_argument("UnknownTool", {"foo": "bar"})
        assert result == ""

    def test_missing_key_returns_empty(self):
        """_get_tool_argument should return empty if key is missing."""
        result = _get_tool_argument("Bash", {})
        assert result == ""


class TestFormatToolUse:
    def test_formats_bash(self):
        """format_tool_use should format Bash command."""
        console = make_console()
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="Bash",
            tool_input={"command": "pytest tests/"},
        )

        format_tool_use(console, msg)
        output = get_output(console)

        assert "Run" in output
        assert "pytest tests/" in output

    def test_formats_read(self):
        """format_tool_use should format Read."""
        console = make_console()
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="Read",
            tool_input={"file_path": "/src/main.py"},
        )

        format_tool_use(console, msg)
        output = get_output(console)

        assert "Read" in output
        assert "/src/main.py" in output

    def test_formats_write(self):
        """format_tool_use should format Write."""
        console = make_console()
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="Write",
            tool_input={"file_path": "/src/new.py", "content": "# new file"},
        )

        format_tool_use(console, msg)
        output = get_output(console)

        assert "Write" in output
        assert "/src/new.py" in output

    def test_formats_edit(self):
        """format_tool_use should format Edit."""
        console = make_console()
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="Edit",
            tool_input={
                "file_path": "/src/main.py",
                "old_string": "old",
                "new_string": "new",
            },
        )

        format_tool_use(console, msg)
        output = get_output(console)

        assert "Update" in output  # Edit is displayed as "Update"
        assert "/src/main.py" in output

    def test_formats_glob(self):
        """format_tool_use should format Glob."""
        console = make_console()
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="Glob",
            tool_input={"pattern": "src/**/*.py"},
        )

        format_tool_use(console, msg)
        output = get_output(console)

        assert "Search" in output
        assert "src/**/*.py" in output

    def test_formats_grep(self):
        """format_tool_use should format Grep."""
        console = make_console()
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="Grep",
            tool_input={"pattern": "class Test"},
        )

        format_tool_use(console, msg)
        output = get_output(console)

        assert "Search" in output  # Grep is displayed as "Search"
        assert "class Test" in output

    def test_truncates_long_argument(self):
        """format_tool_use should truncate long arguments."""
        console = make_console()
        long_cmd = "python -c '" + "x" * 100 + "'"
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="Bash",
            tool_input={"command": long_cmd},
        )

        format_tool_use(console, msg)
        output = get_output(console)

        assert "..." in output

    def test_skips_no_tool_name(self):
        """format_tool_use should skip if no tool name."""
        console = make_console()
        msg = AgentMessage(role="tool_use", content="", tool_name=None)

        format_tool_use(console, msg)
        output = get_output(console)

        assert output == ""

    def test_formats_todowrite(self):
        """format_tool_use should format TodoWrite."""
        console = make_console()
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="TodoWrite",
            tool_input={
                "todos": [
                    {"content": "Task 1", "status": "completed", "activeForm": "Doing task 1"},
                    {"content": "Task 2", "status": "in_progress", "activeForm": "Working on 2"},
                    {"content": "Task 3", "status": "pending", "activeForm": "Pending task 3"},
                ]
            },
        )

        format_tool_use(console, msg)
        output = get_output(console)

        assert "Todo" in output
        # Check that at least some task content is shown
        assert "3 items" in output  # Shows count

    def test_formats_task(self):
        """format_tool_use should format Task tool."""
        console = make_console()
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="Task",
            tool_input={
                "description": "Search codebase",
                "prompt": "Find all test files",
            },
        )

        format_tool_use(console, msg)
        output = get_output(console)

        assert "Agent" in output  # Task is displayed as "Agent"
        assert "Search codebase" in output

    def test_formats_websearch(self):
        """format_tool_use should format WebSearch tool."""
        console = make_console()
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="WebSearch",
            tool_input={"query": "python best practices"},
        )

        format_tool_use(console, msg)
        output = get_output(console)

        assert "Search" in output  # WebSearch is displayed as "Search"
        assert "python best practices" in output

    def test_formats_webfetch(self):
        """format_tool_use should format WebFetch tool."""
        console = make_console()
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="WebFetch",
            tool_input={"url": "https://example.com"},
        )

        format_tool_use(console, msg)
        output = get_output(console)

        assert "Fetch" in output  # WebFetch is displayed as "Fetch"
        assert "https://example.com" in output


class TestFormatToolResult:
    def test_formats_glob_result(self):
        """format_tool_result should format Glob result."""
        console = make_console()
        msg = AgentMessage(
            role="tool_result",
            content="file1.py\nfile2.py\nfile3.py",
        )

        format_tool_result(console, msg, tool_name="Glob")
        output = get_output(console)

        # Minimal format: "↳ 3 files"
        assert "3" in output
        assert "files" in output

    def test_formats_bash_success_result(self):
        """format_tool_result should not show Bash result (cleaner output)."""
        console = make_console()
        msg = AgentMessage(
            role="tool_result",
            content="All tests passed",
        )

        format_tool_result(console, msg, tool_name="Bash")
        output = get_output(console)

        # Bash results are not shown for cleaner output
        assert output == ""

    def test_formats_multiline_result(self):
        """format_tool_result should not show multiline Bash results."""
        console = make_console()
        msg = AgentMessage(
            role="tool_result",
            content="line1\nline2\nline3\nline4\nline5\nline6",
        )

        format_tool_result(console, msg, tool_name="Bash")
        output = get_output(console)

        # Bash results are not shown for cleaner output
        assert output == ""

    def test_skips_empty_result(self):
        """format_tool_result should skip empty results."""
        console = make_console()
        msg = AgentMessage(role="tool_result", content="")

        format_tool_result(console, msg)
        output = get_output(console)

        assert output == ""

    def test_formats_read_result(self):
        """format_tool_result should not show Read result (cleaner output)."""
        console = make_console()
        msg = AgentMessage(
            role="tool_result",
            content="def main():\n    pass\n",
        )

        format_tool_result(console, msg, tool_name="Read")
        output = get_output(console)

        # Read results are not shown for cleaner output
        assert output == ""

    def test_formats_grep_result(self):
        """format_tool_result should format Grep result."""
        console = make_console()
        msg = AgentMessage(
            role="tool_result",
            content="src/main.py:10:def foo():\nsrc/test.py:5:def test_foo():",
        )

        format_tool_result(console, msg, tool_name="Grep")
        output = get_output(console)

        # Shows count
        assert len(output) > 0


# ===== Stage Formatter Tests =====


class TestFormatPlan:
    def test_formats_plan_with_steps(self):
        """format_plan should format plan with steps."""
        console = make_console()
        plan = Plan(
            goal="Implement feature",
            boundaries=["No breaking changes"],
            steps=[
                PlanStep(number=1, description="Step 1"),
                PlanStep(number=2, description="Step 2"),
            ],
        )

        format_plan(console, plan)
        output = get_output(console)

        assert "Implement feature" in output
        assert "Step 1" in output
        assert "Step 2" in output

    def test_formats_plan_with_boundaries(self):
        """format_plan should show boundaries."""
        console = make_console()
        plan = Plan(
            goal="Goal",
            boundaries=["No changes to API", "Keep backwards compatible"],
            steps=[PlanStep(number=1, description="Step")],
        )

        format_plan(console, plan)
        output = get_output(console)

        assert "No changes to API" in output or "boundaries" in output.lower()

    def test_formats_plan_with_risks(self):
        """format_plan should show risks if present."""
        console = make_console()
        plan = Plan(
            goal="Goal",
            boundaries=[],
            steps=[PlanStep(number=1, description="Step")],
            risks=["May break tests"],
        )

        format_plan(console, plan)
        output = get_output(console)

        assert "May break tests" in output or "risk" in output.lower()


class TestFormatConditions:
    def test_formats_blocking_conditions(self):
        """format_conditions should format blocking conditions."""
        console = make_console()
        conditions = [
            Condition(
                id=uuid4(),
                description="Tests pass",
                role=ConditionRole.BLOCKING,
            ),
            Condition(
                id=uuid4(),
                description="Lint passes",
                role=ConditionRole.BLOCKING,
            ),
        ]

        format_conditions(console, conditions)
        output = get_output(console)

        assert "Tests pass" in output
        assert "Lint passes" in output

    def test_formats_signal_conditions(self):
        """format_conditions should format signal conditions."""
        console = make_console()
        conditions = [
            Condition(
                id=uuid4(),
                description="Coverage > 80%",
                role=ConditionRole.SIGNAL,
            ),
        ]

        format_conditions(console, conditions)
        output = get_output(console)

        assert "Coverage" in output

    def test_handles_empty_conditions(self):
        """format_conditions should handle empty list."""
        console = make_console()
        format_conditions(console, [])
        # Should not raise


class TestFormatStageComplete:
    def test_formats_with_short_duration(self):
        """format_stage_complete should format short duration."""
        console = make_console()
        format_stage_complete(console, "Planning", 0.5)
        output = get_output(console)

        assert "Planning" in output

    def test_formats_with_long_duration(self):
        """format_stage_complete should format long duration."""
        console = make_console()
        format_stage_complete(console, "Executing", 125.5)
        output = get_output(console)

        assert "Executing" in output

    def test_formats_with_zero_duration(self):
        """format_stage_complete should handle zero duration."""
        console = make_console()
        format_stage_complete(console, "Intake", 0.0)
        output = get_output(console)

        assert "Intake" in output

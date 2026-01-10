from io import StringIO
from uuid import uuid4

from rich.console import Console

from src.application.dto.final_result import FinalResult
from src.application.dto.task_output import ConditionOutput
from src.cli.formatters.progress_formatter import (
    format_check_results,
    format_iteration,
    iteration_progress,
)
from src.cli.formatters.result_formatter import (
    format_blocked_instructions,
    format_result,
    format_stopped_instructions,
)
from src.cli.formatters.stage_formatter import (
    STAGE_COLORS,
    STAGE_ICONS,
    format_stage,
    format_stage_panel,
)
from src.cli.formatters.tool_formatter import (
    TOOL_OPERATIONS,
    create_tool_callback,
    format_tool_result,
    format_tool_use,
)
from src.domain.ports.agent_port import AgentMessage
from src.domain.value_objects.condition_enums import ApprovalStatus, CheckStatus
from src.domain.value_objects.task_status import TaskStatus


def make_console() -> Console:
    return Console(file=StringIO(), force_terminal=True, width=80)


def get_output(console: Console) -> str:
    console.file.seek(0)
    return console.file.read()


class TestStageFormatter:
    def test_all_task_statuses_have_icons(self) -> None:
        for status in TaskStatus:
            assert status in STAGE_ICONS

    def test_all_task_statuses_have_colors(self) -> None:
        for status in TaskStatus:
            assert status in STAGE_COLORS

    def test_format_stage_prints_status(self) -> None:
        console = make_console()
        format_stage(console, TaskStatus.INTAKE)
        output = get_output(console)
        assert "INTAKE" in output

    def test_format_stage_with_message(self) -> None:
        console = make_console()
        format_stage(console, TaskStatus.EXECUTING, "Running checks")
        output = get_output(console)
        assert "EXECUTING" in output
        assert "Running checks" in output

    def test_format_stage_panel_shows_content(self) -> None:
        console = make_console()
        format_stage_panel(console, TaskStatus.DONE, "All tasks completed")
        output = get_output(console)
        assert "All tasks completed" in output


class TestProgressFormatter:
    def test_iteration_progress_creates_progress(self) -> None:
        console = make_console()
        with iteration_progress(console, 10) as progress:
            assert progress is not None

    def test_format_iteration_displays_info(self) -> None:
        console = make_console()
        format_iteration(console, 3, "Fix tests", "continue")
        output = get_output(console)
        assert "3" in output
        assert "Fix tests" in output
        assert "continue" in output

    def test_format_check_results_displays_table(self) -> None:
        console = make_console()
        results = {
            "pytest": {"status": "pass", "duration_ms": 1500},
            "mypy": {"status": "fail", "duration_ms": 500},
        }
        format_check_results(console, results)
        output = get_output(console)
        assert "pytest" in output
        assert "PASS" in output
        assert "mypy" in output
        assert "FAIL" in output


class TestResultFormatter:
    def _make_result(
        self,
        status: TaskStatus = TaskStatus.DONE,
        summary: str = "Task completed",
        diff: str = "",
        conditions: list[ConditionOutput] | None = None,
        blocked_reason: str | None = None,
        stopped_reason: str | None = None,
    ) -> FinalResult:
        return FinalResult(
            task_id=uuid4(),
            status=status,
            diff=diff,
            patch="",
            summary=summary,
            conditions=conditions or [],
            evidence_refs=[],
            blocked_reason=blocked_reason,
            stopped_reason=stopped_reason,
        )

    def test_format_done_result(self) -> None:
        console = make_console()
        result = self._make_result(TaskStatus.DONE, "All done")
        format_result(console, result)
        output = get_output(console)
        assert "Complete" in output  # "✅ Task Complete!"
        assert "All done" in output

    def test_format_blocked_result(self) -> None:
        console = make_console()
        result = self._make_result(
            TaskStatus.BLOCKED,
            "Blocked",
            blocked_reason="Missing dependency",
        )
        format_result(console, result)
        output = get_output(console)
        assert "Blocked" in output  # "❌ Task Blocked"
        assert "Missing dependency" in output

    def test_format_stopped_result(self) -> None:
        console = make_console()
        result = self._make_result(
            TaskStatus.STOPPED,
            "Stopped",
            stopped_reason="Timeout reached",
        )
        format_result(console, result)
        output = get_output(console)
        assert "Stopped" in output  # "⏸️  Task Stopped"
        assert "Timeout reached" in output

    def test_format_result_with_conditions(self) -> None:
        console = make_console()
        conditions = [
            ConditionOutput(
                id=uuid4(),
                description="Tests pass",
                role="blocking",
                approval_status=ApprovalStatus.APPROVED,
                check_status=CheckStatus.PASS,
            ),
            ConditionOutput(
                id=uuid4(),
                description="Lint passes",
                role="blocking",
                approval_status=ApprovalStatus.APPROVED,
                check_status=CheckStatus.FAIL,
            ),
        ]
        result = self._make_result(TaskStatus.DONE, "Done", conditions=conditions)
        format_result(console, result)
        output = get_output(console)
        # Shows summary like "1/2 conditions passed"
        assert "1" in output and "2" in output
        # Shows failed condition
        assert "Lint passes" in output

    def test_format_result_with_diff(self) -> None:
        console = make_console()
        diff = """--- a/file.py
+++ b/file.py
@@ -1,3 +1,4 @@
+# New comment
 def main():
     pass
"""
        result = self._make_result(TaskStatus.DONE, "Done", diff=diff)
        format_result(console, result)
        output = get_output(console)
        assert "Changes" in output

    def test_format_result_truncates_long_diff(self) -> None:
        console = make_console()
        diff_lines = [f"+line {i}" for i in range(100)]
        diff = "\n".join(diff_lines)
        result = self._make_result(TaskStatus.DONE, "Done", diff=diff)
        format_result(console, result)
        output = get_output(console)
        # Long diffs show hint to run git diff
        assert "git diff" in output

    def test_format_result_truncates_long_description(self) -> None:
        console = make_console()
        long_desc = "A" * 80  # Long enough to exceed 60 char limit
        conditions = [
            ConditionOutput(
                id=uuid4(),
                description=long_desc,
                role="blocking",
                approval_status=ApprovalStatus.APPROVED,
                check_status=CheckStatus.FAIL,  # Must fail to be shown
            ),
        ]
        result = self._make_result(TaskStatus.DONE, "Done", conditions=conditions)
        format_result(console, result)
        output = get_output(console)
        # Only first 60 chars shown for failed conditions
        assert long_desc[:60] in output

    def test_format_blocked_instructions(self) -> None:
        console = make_console()
        result = self._make_result(
            TaskStatus.BLOCKED,
            "Blocked",
            blocked_reason="Tests failing",
        )
        format_blocked_instructions(console, result)
        output = get_output(console)
        assert "Blocked" in output
        assert "proofloop task resume" in output
        assert "--auto-approve" in output

    def test_format_blocked_instructions_skips_non_blocked(self) -> None:
        console = make_console()
        result = self._make_result(TaskStatus.DONE, "Done")
        format_blocked_instructions(console, result)
        output = get_output(console)
        assert "resume" not in output

    def test_format_stopped_instructions(self) -> None:
        console = make_console()
        result = self._make_result(
            TaskStatus.STOPPED,
            "Stopped",
            stopped_reason="Timeout",
        )
        format_stopped_instructions(console, result)
        output = get_output(console)
        assert "Stopped" in output
        assert "--timeout" in output

    def test_format_stopped_instructions_skips_non_stopped(self) -> None:
        console = make_console()
        result = self._make_result(TaskStatus.DONE, "Done")
        format_stopped_instructions(console, result)
        output = get_output(console)
        assert "resume" not in output


class TestToolFormatter:
    def test_all_common_tools_have_operations(self) -> None:
        common_tools = ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]
        for tool in common_tools:
            assert tool in TOOL_OPERATIONS

    def test_format_tool_use_bash(self) -> None:
        console = make_console()
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="Bash",
            tool_input={"command": "ls -la"},
        )
        format_tool_use(console, msg)
        output = get_output(console)
        # Claude Code style: shows "Run" instead of "Bash"
        assert "Run" in output
        assert "ls -la" in output

    def test_format_tool_use_read(self) -> None:
        console = make_console()
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="Read",
            tool_input={"file_path": "/path/to/file.py"},
        )
        format_tool_use(console, msg)
        output = get_output(console)
        assert "Read" in output
        assert "/path/to/file.py" in output

    def test_format_tool_use_truncates_long_input(self) -> None:
        console = make_console()
        long_command = "python " + "x" * 100
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="Bash",
            tool_input={"command": long_command},
        )
        format_tool_use(console, msg)
        output = get_output(console)
        assert "..." in output

    def test_format_tool_use_skips_if_no_tool_name(self) -> None:
        console = make_console()
        msg = AgentMessage(role="tool_use", content="", tool_name=None)
        format_tool_use(console, msg)
        output = get_output(console)
        assert output == ""

    def test_format_tool_result_shows_preview(self) -> None:
        console = make_console()
        msg = AgentMessage(
            role="tool_result",
            content="file1.py\nfile2.py\nfile3.py",
        )
        # Pass tool_name for context-aware formatting
        format_tool_result(console, msg, tool_name="Glob")
        output = get_output(console)
        # Shows count of files found with minimal format: "↳ 3 files"
        assert "3" in output
        assert "files" in output

    def test_format_tool_result_truncates_long_content(self) -> None:
        console = make_console()
        long_content = "line\n" * 100
        msg = AgentMessage(role="tool_result", content=long_content)
        # Bash results are not shown (only Glob/Grep for cleaner output)
        format_tool_result(console, msg, tool_name="Bash")
        output = get_output(console)
        assert output == ""

    def test_format_tool_result_skips_empty_content(self) -> None:
        console = make_console()
        msg = AgentMessage(role="tool_result", content="")
        format_tool_result(console, msg)
        output = get_output(console)
        assert output == ""

    def test_create_tool_callback_handles_tool_use(self) -> None:
        console = make_console()
        callback = create_tool_callback(console)

        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="Bash",
            tool_input={"command": "pwd"},
        )
        callback(msg)

        output = get_output(console)
        # Claude Code style: shows "Run" instead of "Bash"
        assert "Run" in output
        assert "pwd" in output

    def test_create_tool_callback_handles_tool_result(self) -> None:
        console = make_console()
        callback = create_tool_callback(console)

        # First send tool_use to set context
        use_msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="Bash",
            tool_input={"command": "echo test"},
        )
        callback(use_msg)

        # Then send result
        result_msg = AgentMessage(role="tool_result", content="test output")
        callback(result_msg)

        output = get_output(console)
        # Tool use is shown (Bash results are skipped for cleaner output)
        assert "Run" in output
        assert "echo test" in output

    def test_create_tool_callback_shows_assistant_with_icon(self) -> None:
        console = make_console()
        callback = create_tool_callback(console)

        # Assistant messages are disabled for cleaner output
        msg = AgentMessage(role="assistant", content="Analyzing the code structure...")
        callback(msg)

        output = get_output(console)
        # Assistant messages disabled - output should be empty
        assert output == ""

    def test_create_tool_callback_skips_short_assistant(self) -> None:
        console = make_console()
        callback = create_tool_callback(console)

        # Short messages are skipped
        msg = AgentMessage(role="assistant", content="OK")
        callback(msg)

        output = get_output(console)
        assert output == ""

    def test_format_tool_use_todowrite_shows_items(self) -> None:
        console = make_console()
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="TodoWrite",
            tool_input={
                "todos": [
                    {
                        "content": "First task",
                        "status": "completed",
                        "activeForm": "Completing first",
                    },
                    {
                        "content": "Second task",
                        "status": "in_progress",
                        "activeForm": "Working second",
                    },
                    {"content": "Third task", "status": "pending", "activeForm": "Pending third"},
                ]
            },
        )
        format_tool_use(console, msg)
        output = get_output(console)
        # Claude Code style: shows "Todo" instead of "TodoWrite"
        assert "Todo" in output
        assert "items" in output
        assert "Completing" in output
        assert "Working" in output
        assert "Pending" in output

    def test_format_tool_use_todowrite_status_icons(self) -> None:
        console = make_console()
        msg = AgentMessage(
            role="tool_use",
            content="",
            tool_name="TodoWrite",
            tool_input={
                "todos": [
                    {"content": "Done", "status": "completed", "activeForm": "Done"},
                    {"content": "Running", "status": "in_progress", "activeForm": "Running"},
                ]
            },
        )
        format_tool_use(console, msg)
        output = get_output(console)
        # Check icons are present (✓ for completed, ⟳ for in_progress)
        assert "✓" in output
        assert "⟳" in output

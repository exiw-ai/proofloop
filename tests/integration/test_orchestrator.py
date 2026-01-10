"""Integration tests for Orchestrator tool gating."""

import pytest

from src.application.services.tool_gating import (
    DANGEROUS_COMMANDS,
    DELIVERY_STAGES,
    PRE_DELIVERY_STAGES,
    ToolGatingError,
    get_allowed_tools,
    validate_bash_command,
)
from src.domain.value_objects.task_status import TaskStatus


class TestGetAllowedTools:
    def test_pre_delivery_stages_have_limited_tools(self) -> None:
        for status in PRE_DELIVERY_STAGES:
            tools = get_allowed_tools(status)
            assert "Read" in tools
            assert "Glob" in tools
            assert "Grep" in tools
            assert "Bash" in tools
            assert "Write" not in tools
            assert "Edit" not in tools

    def test_delivery_stages_have_full_tools(self) -> None:
        for status in DELIVERY_STAGES:
            tools = get_allowed_tools(status)
            assert "Read" in tools
            assert "Write" in tools
            assert "Edit" in tools
            assert "Bash" in tools
            assert "Glob" in tools
            assert "Grep" in tools


class TestValidateBashCommand:
    # Pre-delivery safe commands
    @pytest.mark.parametrize(
        "command",
        [
            "git status",
            "git log --oneline",
            "git diff HEAD~1",
            "ls -la",
            "cat file.py",
            "head -n 10 file.py",
            "tail -f log.txt",
            "find . -name '*.py'",
            "grep -r 'pattern' .",
            "rg pattern",
            "pwd",
            "which python",
            "echo $HOME",
            "echo $PATH",
            "python --version",
            "pip list",
            "wc -l file.py",
        ],
    )
    def test_safe_commands_allowed_in_pre_delivery(self, command: str) -> None:
        # Should not raise
        validate_bash_command(command, TaskStatus.PLANNING)

    # Pre-delivery forbidden operators
    @pytest.mark.parametrize(
        "command",
        [
            "echo test > file.txt",
            "cat file >> output.txt",
            "cmd1 ; cmd2",
            "cmd1 && cmd2",
            "cmd1 || cmd2",
            "echo `whoami`",
            "echo $(pwd)",
        ],
    )
    def test_forbidden_operators_blocked_in_pre_delivery(self, command: str) -> None:
        with pytest.raises(ToolGatingError):
            validate_bash_command(command, TaskStatus.PLANNING)

    # Pre-delivery unlisted commands
    @pytest.mark.parametrize(
        "command",
        [
            "rm file.txt",
            "mv old.py new.py",
            "touch new_file.py",
            "mkdir new_dir",
            "chmod 755 script.sh",
            "git add .",
            "git commit -m 'msg'",
            "npm install",
        ],
    )
    def test_unlisted_commands_blocked_in_pre_delivery(self, command: str) -> None:
        with pytest.raises(ToolGatingError):
            validate_bash_command(command, TaskStatus.INTAKE)

    # Delivery stage allows more
    def test_commands_allowed_in_delivery(self) -> None:
        # These would be blocked in pre-delivery but allowed in delivery
        validate_bash_command("rm file.txt", TaskStatus.EXECUTING)
        validate_bash_command("git add .", TaskStatus.EXECUTING)
        validate_bash_command("npm install", TaskStatus.EXECUTING)
        validate_bash_command("echo test > file.txt", TaskStatus.EXECUTING)

    # Always dangerous commands
    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf /",
            "rm -rf .",
            "git reset --hard HEAD",
            "git clean -fdx",
        ],
    )
    def test_dangerous_commands_always_blocked(self, command: str) -> None:
        # Blocked in pre-delivery
        with pytest.raises(ToolGatingError):
            validate_bash_command(command, TaskStatus.PLANNING)

        # Also blocked in delivery
        with pytest.raises(ToolGatingError):
            validate_bash_command(command, TaskStatus.EXECUTING)

    def test_dangerous_commands_allowed_with_flag(self) -> None:
        # With allow_dangerous=True, these pass
        validate_bash_command(
            "rm -rf /tmp/test",
            TaskStatus.EXECUTING,
            allow_dangerous=True,
        )
        validate_bash_command(
            "git reset --hard HEAD",
            TaskStatus.EXECUTING,
            allow_dangerous=True,
        )

    # Pipe handling
    def test_pipes_with_safe_commands_allowed(self) -> None:
        validate_bash_command("cat file.py | grep pattern", TaskStatus.PLANNING)
        validate_bash_command("ls -la | head -n 5", TaskStatus.PLANNING)
        validate_bash_command("find . -name '*.py' | wc -l", TaskStatus.PLANNING)

    def test_pipes_with_unsafe_command_blocked(self) -> None:
        with pytest.raises(ToolGatingError):
            validate_bash_command("cat file.py | rm file.txt", TaskStatus.PLANNING)


class TestToolGatingStages:
    def test_all_pre_delivery_stages_defined(self) -> None:
        expected = {
            TaskStatus.INTAKE,
            TaskStatus.STRATEGY,
            TaskStatus.VERIFICATION_INVENTORY,
            TaskStatus.PLANNING,
            TaskStatus.CONDITIONS,
            TaskStatus.APPROVAL_CONDITIONS,
            TaskStatus.APPROVAL_PLAN,
        }
        assert expected == PRE_DELIVERY_STAGES

    def test_all_delivery_stages_defined(self) -> None:
        expected = {
            TaskStatus.EXECUTING,
            TaskStatus.QUALITY,
            TaskStatus.FINALIZE,
        }
        assert expected == DELIVERY_STAGES

    def test_stages_are_mutually_exclusive(self) -> None:
        intersection = PRE_DELIVERY_STAGES & DELIVERY_STAGES
        assert len(intersection) == 0

    def test_terminal_statuses_not_in_either(self) -> None:
        terminal = {TaskStatus.DONE, TaskStatus.BLOCKED, TaskStatus.STOPPED}
        assert len(terminal & PRE_DELIVERY_STAGES) == 0
        assert len(terminal & DELIVERY_STAGES) == 0


class TestDangerousCommands:
    """Test DANGEROUS_COMMANDS list is complete per contract."""

    def test_dangerous_commands_list_exists(self) -> None:
        assert len(DANGEROUS_COMMANDS) > 0

    @pytest.mark.parametrize(
        "command",
        [
            "rm file.txt",
            "mv old.py new.py",
            "touch new.py",
            "mkdir new_dir",
            "chmod 755 file.sh",
            "chown user file.txt",
            "git add .",
            "git commit -m 'msg'",
            "git push origin main",
            "git checkout branch",
        ],
    )
    def test_dangerous_commands_blocked_in_pre_delivery(self, command: str) -> None:
        with pytest.raises(ToolGatingError):
            validate_bash_command(command, TaskStatus.PLANNING)

    @pytest.mark.parametrize(
        "command",
        [
            "rm file.txt",
            "mv old.py new.py",
            "touch new.py",
            "mkdir new_dir",
            "git add .",
            "git commit -m 'msg'",
        ],
    )
    def test_dangerous_commands_allowed_in_delivery(self, command: str) -> None:
        # These are allowed in delivery stages
        validate_bash_command(command, TaskStatus.EXECUTING)

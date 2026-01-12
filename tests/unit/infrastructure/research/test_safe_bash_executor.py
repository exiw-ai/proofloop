"""Tests for SafeBashExecutor."""

import pytest

from src.application.services.tool_gating import ToolGatingError
from src.infrastructure.research.safe_bash_executor import SafeBashExecutor


@pytest.fixture
def executor(tmp_path) -> SafeBashExecutor:
    return SafeBashExecutor(cwd=str(tmp_path), timeout_s=5)


class TestExecute:
    @pytest.mark.asyncio
    async def test_execute_ls(self, executor: SafeBashExecutor, tmp_path) -> None:
        # Create a test file
        (tmp_path / "test.txt").write_text("hello")

        result = await executor.execute("ls")

        assert result.exit_code == 0
        assert "test.txt" in result.stdout
        assert result.command == "ls"
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_cat(self, executor: SafeBashExecutor, tmp_path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        result = await executor.execute(f"cat {test_file}")

        assert result.exit_code == 0
        assert "hello world" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_curl(self, executor: SafeBashExecutor) -> None:
        # Just test that curl command is allowed (don't actually fetch)
        result = await executor.execute("curl --version")

        assert result.exit_code == 0
        assert "curl" in result.stdout.lower()

    @pytest.mark.asyncio
    async def test_execute_git_status(self, executor: SafeBashExecutor) -> None:
        result = await executor.execute("git status")

        # Will fail if not in a git repo, but command should be allowed
        # The command runs and returns some result
        assert isinstance(result.exit_code, int)

    @pytest.mark.asyncio
    async def test_execute_piped_command(self, executor: SafeBashExecutor, tmp_path) -> None:
        test_file = tmp_path / "numbers.txt"
        test_file.write_text("3\n1\n2")

        result = await executor.execute(f"cat {test_file} | sort")

        assert result.exit_code == 0
        assert "1\n2\n3" in result.stdout

    @pytest.mark.asyncio
    async def test_rejects_rm_command(self, executor: SafeBashExecutor) -> None:
        with pytest.raises(ToolGatingError, match="not allowed"):
            await executor.execute("rm test.txt")

    @pytest.mark.asyncio
    async def test_rejects_mv_command(self, executor: SafeBashExecutor) -> None:
        with pytest.raises(ToolGatingError, match="not allowed"):
            await executor.execute("mv a b")

    @pytest.mark.asyncio
    async def test_rejects_git_push(self, executor: SafeBashExecutor) -> None:
        with pytest.raises(ToolGatingError, match="not allowed"):
            await executor.execute("git push")

    @pytest.mark.asyncio
    async def test_rejects_echo_redirect(self, executor: SafeBashExecutor) -> None:
        with pytest.raises(ToolGatingError, match="not allowed"):
            await executor.execute("echo test > file.txt")

    @pytest.mark.asyncio
    async def test_handles_stderr(self, executor: SafeBashExecutor) -> None:
        result = await executor.execute("ls /nonexistent_path_12345")

        assert result.exit_code != 0
        assert "No such file" in result.stderr or "cannot access" in result.stderr

    @pytest.mark.asyncio
    async def test_rejects_sleep(self, executor: SafeBashExecutor) -> None:
        with pytest.raises(ToolGatingError, match="not allowed"):
            await executor.execute("sleep 10")

    @pytest.mark.asyncio
    async def test_handles_invalid_command(self, executor: SafeBashExecutor) -> None:
        # Test command that will fail
        result = await executor.execute("ls --invalid-option-12345")

        assert result.exit_code != 0


class TestExecuteSync:
    def test_execute_sync_ls(self, executor: SafeBashExecutor, tmp_path) -> None:
        (tmp_path / "sync_test.txt").write_text("sync content")

        result = executor.execute_sync("ls")

        assert result.exit_code == 0
        assert "sync_test.txt" in result.stdout

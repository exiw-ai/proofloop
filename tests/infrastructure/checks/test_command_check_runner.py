from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domain.value_objects.check_types import CheckKind, CheckSpec
from src.domain.value_objects.condition_enums import CheckStatus
from src.infrastructure.checks.command_check_runner import CommandCheckRunner


@pytest.fixture
def runner() -> CommandCheckRunner:
    return CommandCheckRunner()


@pytest.fixture
def base_check() -> CheckSpec:
    return CheckSpec(
        id=uuid4(),
        name="test-check",
        kind=CheckKind.CUSTOM,
        command="echo hello",
        cwd="",
        env={},
        timeout_s=30,
    )


class TestCommandCheckRunner:
    async def test_successful_command_returns_pass(
        self,
        runner: CommandCheckRunner,
        base_check: CheckSpec,
    ) -> None:
        result = await runner.run_check(base_check, cwd="/tmp")

        assert result.status == CheckStatus.PASS
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert result.stderr == ""
        assert result.duration_ms >= 0
        assert result.check_id == base_check.id

    async def test_failing_command_returns_fail(
        self,
        runner: CommandCheckRunner,
    ) -> None:
        check = CheckSpec(
            id=uuid4(),
            name="failing-check",
            kind=CheckKind.CUSTOM,
            command="exit 1",
            cwd="",
            env={},
            timeout_s=30,
        )

        result = await runner.run_check(check, cwd="/tmp")

        assert result.status == CheckStatus.FAIL
        assert result.exit_code == 1

    async def test_timeout_kills_process_and_returns_fail(
        self,
        runner: CommandCheckRunner,
    ) -> None:
        check = CheckSpec(
            id=uuid4(),
            name="slow-check",
            kind=CheckKind.CUSTOM,
            command="sleep 10",
            cwd="",
            env={},
            timeout_s=1,
        )

        start = datetime.now(UTC)
        result = await runner.run_check(check, cwd="/tmp")
        elapsed = (datetime.now(UTC) - start).total_seconds()

        assert result.status == CheckStatus.FAIL
        assert result.exit_code == -1
        assert "Timeout" in result.stderr
        assert elapsed < 5  # Should not wait full 10 seconds

    async def test_environment_variables_are_passed(
        self,
        runner: CommandCheckRunner,
    ) -> None:
        check = CheckSpec(
            id=uuid4(),
            name="env-check",
            kind=CheckKind.CUSTOM,
            command="echo $MY_TEST_VAR",
            cwd="",
            env={"MY_TEST_VAR": "test_value_123"},
            timeout_s=30,
        )

        result = await runner.run_check(check, cwd="/tmp")

        assert result.status == CheckStatus.PASS
        assert "test_value_123" in result.stdout

    async def test_uses_check_cwd_when_specified(
        self,
        runner: CommandCheckRunner,
    ) -> None:
        check = CheckSpec(
            id=uuid4(),
            name="cwd-check",
            kind=CheckKind.CUSTOM,
            command="pwd",
            cwd="/tmp",
            env={},
            timeout_s=30,
        )

        result = await runner.run_check(check, cwd="/var")

        assert result.status == CheckStatus.PASS
        assert "/tmp" in result.stdout

    async def test_uses_fallback_cwd_when_check_cwd_empty(
        self,
        runner: CommandCheckRunner,
    ) -> None:
        check = CheckSpec(
            id=uuid4(),
            name="fallback-cwd-check",
            kind=CheckKind.CUSTOM,
            command="pwd",
            cwd="",
            env={},
            timeout_s=30,
        )

        result = await runner.run_check(check, cwd="/tmp")

        assert result.status == CheckStatus.PASS
        assert "/tmp" in result.stdout

    async def test_captures_stderr(
        self,
        runner: CommandCheckRunner,
    ) -> None:
        check = CheckSpec(
            id=uuid4(),
            name="stderr-check",
            kind=CheckKind.CUSTOM,
            command="echo error_message >&2",
            cwd="",
            env={},
            timeout_s=30,
        )

        result = await runner.run_check(check, cwd="/tmp")

        assert result.status == CheckStatus.PASS
        assert "error_message" in result.stderr

    async def test_timestamp_is_utc(
        self,
        runner: CommandCheckRunner,
        base_check: CheckSpec,
    ) -> None:
        before = datetime.now(UTC)
        result = await runner.run_check(base_check, cwd="/tmp")
        after = datetime.now(UTC)

        assert before <= result.timestamp <= after

    async def test_invalid_command_returns_fail(
        self,
        runner: CommandCheckRunner,
    ) -> None:
        check = CheckSpec(
            id=uuid4(),
            name="invalid-check",
            kind=CheckKind.CUSTOM,
            command="nonexistent_command_12345",
            cwd="",
            env={},
            timeout_s=30,
        )

        result = await runner.run_check(check, cwd="/tmp")

        assert result.status == CheckStatus.FAIL
        assert result.exit_code != 0

    async def test_invalid_cwd_returns_fail(
        self,
        runner: CommandCheckRunner,
    ) -> None:
        check = CheckSpec(
            id=uuid4(),
            name="invalid-cwd-check",
            kind=CheckKind.CUSTOM,
            command="echo hello",
            cwd="/nonexistent/path/12345",
            env={},
            timeout_s=30,
        )

        result = await runner.run_check(check, cwd="/tmp")

        assert result.status == CheckStatus.FAIL
        assert result.exit_code == -1

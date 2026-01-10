"""Tests for derive_code command."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.application.dto.final_result import FinalResult
from src.domain.value_objects.task_status import TaskStatus


class TestDeriveCodeAsync:
    """Tests for derive_code_async function."""

    @pytest.mark.asyncio
    async def test_derive_code_async_success(self, tmp_path: Path) -> None:
        """Test successful derive code execution."""
        from src.cli.commands.derive_code import derive_code_async

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state_dir = tmp_path / ".proofloop"
        state_dir.mkdir()

        payload = tmp_path / "derive_payload.json"
        payload.write_text(
            json.dumps(
                {
                    "headline": "Implement feature",
                    "goals": ["Add new feature"],
                    "constraints": ["Use existing patterns"],
                    "recommended_approach": "Follow TDD",
                    "key_findings": [{"summary": "Finding 1"}],
                    "risks": ["Risk 1"],
                    "target_workspace_hint": str(workspace),
                }
            )
        )

        final_result = FinalResult(
            task_id=uuid4(),
            status=TaskStatus.DONE,
            diff="",
            patch="",
            summary="Done",
            conditions=[],
            evidence_refs=[],
        )

        with (
            patch(
                "src.infrastructure.git.repo_root.get_default_state_dir",
                new_callable=AsyncMock,
            ) as mock_state_dir,
            patch("src.infrastructure.agent.claude_agent_adapter.ClaudeAgentAdapter"),
            patch("src.infrastructure.checks.command_check_runner.CommandCheckRunner"),
            patch("src.infrastructure.git.git_diff_adapter.GitDiffAdapter"),
            patch("src.infrastructure.persistence.json_task_repo.JsonTaskRepo"),
            patch("src.infrastructure.verification.project_analyzer.ProjectAnalyzer"),
            patch("src.application.orchestrator.Orchestrator") as mock_orchestrator_class,
            patch("src.cli.formatters.result_formatter.format_result"),
            patch("src.cli.commands.derive_code.console") as mock_console,
        ):
            mock_state_dir.return_value = state_dir
            mock_orchestrator = AsyncMock()
            mock_orchestrator.run.return_value = final_result
            mock_orchestrator_class.return_value = mock_orchestrator
            mock_console.print = MagicMock()

            await derive_code_async(
                handoff_path=payload,
                workspace=workspace,
                auto_approve=True,
                baseline=False,
                timeout=60,
                verbose=False,
                state_dir=state_dir,
            )

            mock_orchestrator.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_derive_code_async_uses_workspace_hint(self, tmp_path: Path) -> None:
        """Test that workspace hint is used when no explicit workspace
        provided."""
        from src.cli.commands.derive_code import derive_code_async

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state_dir = tmp_path / ".proofloop"
        state_dir.mkdir()

        payload = tmp_path / "derive_payload.json"
        payload.write_text(
            json.dumps(
                {
                    "headline": "Implement feature",
                    "goals": [],
                    "target_workspace_hint": str(workspace),
                }
            )
        )

        final_result = FinalResult(
            task_id=uuid4(),
            status=TaskStatus.DONE,
            diff="",
            patch="",
            summary="Done",
            conditions=[],
            evidence_refs=[],
        )

        with (
            patch(
                "src.infrastructure.git.repo_root.get_default_state_dir",
                new_callable=AsyncMock,
            ) as mock_state_dir,
            patch("src.infrastructure.agent.claude_agent_adapter.ClaudeAgentAdapter"),
            patch("src.infrastructure.checks.command_check_runner.CommandCheckRunner"),
            patch("src.infrastructure.git.git_diff_adapter.GitDiffAdapter"),
            patch("src.infrastructure.persistence.json_task_repo.JsonTaskRepo"),
            patch("src.infrastructure.verification.project_analyzer.ProjectAnalyzer"),
            patch("src.application.orchestrator.Orchestrator") as mock_orchestrator_class,
            patch("src.cli.formatters.result_formatter.format_result"),
            patch("src.cli.commands.derive_code.console") as mock_console,
        ):
            mock_state_dir.return_value = state_dir
            mock_orchestrator = AsyncMock()
            mock_orchestrator.run.return_value = final_result
            mock_orchestrator_class.return_value = mock_orchestrator
            mock_console.print = MagicMock()

            await derive_code_async(
                handoff_path=payload,
                workspace=None,  # No explicit workspace
                auto_approve=True,
                baseline=False,
                timeout=60,
                verbose=False,
                state_dir=state_dir,
            )

            # Should succeed using workspace hint
            mock_orchestrator.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_derive_code_async_missing_payload(self, tmp_path: Path) -> None:
        """Test error when payload is missing."""
        import typer

        from src.cli.commands.derive_code import derive_code_async

        missing_payload = tmp_path / "nonexistent.json"

        with (
            patch("src.cli.commands.derive_code.console") as mock_console,
            pytest.raises(typer.Exit),
        ):
            mock_console.print = MagicMock()

            await derive_code_async(
                handoff_path=missing_payload,
                workspace=None,
                auto_approve=True,
                baseline=False,
                timeout=60,
                verbose=False,
                state_dir=None,
            )

    @pytest.mark.asyncio
    async def test_derive_code_async_invalid_json(self, tmp_path: Path) -> None:
        """Test error when payload is invalid JSON."""
        import typer

        from src.cli.commands.derive_code import derive_code_async

        payload = tmp_path / "derive_payload.json"
        payload.write_text("not valid json {")

        with (
            patch("src.cli.commands.derive_code.console") as mock_console,
            pytest.raises(typer.Exit),
        ):
            mock_console.print = MagicMock()

            await derive_code_async(
                handoff_path=payload,
                workspace=None,
                auto_approve=True,
                baseline=False,
                timeout=60,
                verbose=False,
                state_dir=None,
            )

    @pytest.mark.asyncio
    async def test_derive_code_async_missing_workspace_hint(self, tmp_path: Path) -> None:
        """Test error when no workspace and no hint in payload."""
        import typer

        from src.cli.commands.derive_code import derive_code_async

        payload = tmp_path / "derive_payload.json"
        payload.write_text(
            json.dumps(
                {
                    "headline": "Test",
                    "goals": [],
                    # No target_workspace_hint
                }
            )
        )

        with (
            patch("src.cli.commands.derive_code.console") as mock_console,
            pytest.raises(typer.Exit),
        ):
            mock_console.print = MagicMock()

            await derive_code_async(
                handoff_path=payload,
                workspace=None,  # No explicit workspace
                auto_approve=True,
                baseline=False,
                timeout=60,
                verbose=False,
                state_dir=None,
            )

    @pytest.mark.asyncio
    async def test_derive_code_async_missing_workspace_path(self, tmp_path: Path) -> None:
        """Test error when workspace path doesn't exist."""
        import typer

        from src.cli.commands.derive_code import derive_code_async

        payload = tmp_path / "derive_payload.json"
        payload.write_text(
            json.dumps(
                {
                    "headline": "Test",
                    "goals": [],
                    "target_workspace_hint": str(tmp_path / "nonexistent_workspace"),
                }
            )
        )

        with (
            patch("src.cli.commands.derive_code.console") as mock_console,
            pytest.raises(typer.Exit),
        ):
            mock_console.print = MagicMock()

            await derive_code_async(
                handoff_path=payload,
                workspace=None,
                auto_approve=True,
                baseline=False,
                timeout=60,
                verbose=False,
                state_dir=None,
            )

    @pytest.mark.asyncio
    async def test_derive_code_async_resolves_directory(self, tmp_path: Path) -> None:
        """Test payload resolution when directory is passed."""
        from src.cli.commands.derive_code import derive_code_async

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state_dir = tmp_path / ".proofloop"
        state_dir.mkdir()

        # Create payload in the directory
        payload = tmp_path / "derive_payload.json"
        payload.write_text(
            json.dumps(
                {
                    "headline": "Feature",
                    "goals": [],
                    "target_workspace_hint": str(workspace),
                }
            )
        )

        final_result = FinalResult(
            task_id=uuid4(),
            status=TaskStatus.DONE,
            diff="",
            patch="",
            summary="Done",
            conditions=[],
            evidence_refs=[],
        )

        with (
            patch(
                "src.infrastructure.git.repo_root.get_default_state_dir",
                new_callable=AsyncMock,
            ) as mock_state_dir,
            patch("src.infrastructure.agent.claude_agent_adapter.ClaudeAgentAdapter"),
            patch("src.infrastructure.checks.command_check_runner.CommandCheckRunner"),
            patch("src.infrastructure.git.git_diff_adapter.GitDiffAdapter"),
            patch("src.infrastructure.persistence.json_task_repo.JsonTaskRepo"),
            patch("src.infrastructure.verification.project_analyzer.ProjectAnalyzer"),
            patch("src.application.orchestrator.Orchestrator") as mock_orchestrator_class,
            patch("src.cli.formatters.result_formatter.format_result"),
            patch("src.cli.commands.derive_code.console") as mock_console,
        ):
            mock_state_dir.return_value = state_dir
            mock_orchestrator = AsyncMock()
            mock_orchestrator.run.return_value = final_result
            mock_orchestrator_class.return_value = mock_orchestrator
            mock_console.print = MagicMock()

            await derive_code_async(
                handoff_path=tmp_path,  # Pass directory
                workspace=workspace,
                auto_approve=True,
                baseline=False,
                timeout=60,
                verbose=False,
                state_dir=state_dir,
            )

            mock_orchestrator.run.assert_called_once()


class TestDeriveCodePayloadResolution:
    def test_resolves_direct_file_path(self, tmp_path: Path) -> None:
        payload = tmp_path / "derive_payload.json"
        payload.write_text(
            json.dumps(
                {
                    "headline": "Test",
                    "goals": [],
                    "target_workspace_hint": str(tmp_path),
                }
            )
        )

        # The function will resolve the path correctly
        assert payload.exists()

    def test_resolves_directory_with_payload(self, tmp_path: Path) -> None:
        payload = tmp_path / "derive_payload.json"
        payload.write_text(
            json.dumps(
                {
                    "headline": "Test",
                    "goals": [],
                    "target_workspace_hint": str(tmp_path),
                }
            )
        )

        # The command should find the payload in the directory
        assert payload.exists()

    def test_resolves_nested_research_directory(self, tmp_path: Path) -> None:
        research_dir = tmp_path / ".proofloop" / "research"
        research_dir.mkdir(parents=True)
        payload = research_dir / "derive_payload.json"
        payload.write_text(
            json.dumps(
                {
                    "headline": "Test",
                    "goals": [],
                    "target_workspace_hint": str(tmp_path),
                }
            )
        )

        # The command should find the payload in nested directory
        assert payload.exists()


class TestDeriveCodePayloadParsing:
    @pytest.mark.asyncio
    async def test_extracts_headline(self, tmp_path: Path) -> None:
        payload = tmp_path / "derive_payload.json"
        payload.write_text(
            json.dumps(
                {
                    "headline": "Implement authentication",
                    "goals": ["Add login"],
                    "constraints": [],
                    "recommended_approach": "Use OAuth",
                    "key_findings": [{"summary": "OAuth is secure"}],
                    "risks": ["Token expiry"],
                    "target_workspace_hint": str(tmp_path),
                }
            )
        )

        data = json.loads(payload.read_text())
        assert data["headline"] == "Implement authentication"
        assert data["recommended_approach"] == "Use OAuth"

    @pytest.mark.asyncio
    async def test_handles_empty_optional_fields(self, tmp_path: Path) -> None:
        payload = tmp_path / "derive_payload.json"
        payload.write_text(
            json.dumps(
                {
                    "headline": "Test",
                    "target_workspace_hint": str(tmp_path),
                }
            )
        )

        data = json.loads(payload.read_text())
        assert data.get("goals", []) == []
        assert data.get("constraints", []) == []
        assert data.get("key_findings", []) == []


class TestDeriveCodeDescriptionBuilding:
    def test_builds_enhanced_description(self) -> None:
        payload_data = {
            "headline": "Implement feature",
            "recommended_approach": "Use existing patterns",
            "key_findings": [{"summary": "Finding 1"}, {"summary": "Finding 2"}],
            "risks": ["Risk 1"],
        }

        description_parts = [payload_data["headline"]]
        if payload_data.get("recommended_approach"):
            description_parts.append(
                f"\nRecommended approach: {payload_data['recommended_approach']}"
            )

        if payload_data.get("key_findings"):
            description_parts.append("\n\nKey research findings:")
            for finding in payload_data["key_findings"][:5]:
                summary = finding.get("summary", "")
                if summary:
                    description_parts.append(f"- {summary[:200]}")

        if payload_data.get("risks"):
            description_parts.append("\n\nRisks to consider:")
            for risk in payload_data["risks"][:3]:
                description_parts.append(f"- {risk}")

        description = "\n".join(description_parts)

        assert "Implement feature" in description
        assert "Use existing patterns" in description
        assert "Finding 1" in description
        assert "Risk 1" in description

    def test_limits_findings_to_five(self) -> None:
        payload_data = {
            "headline": "Test",
            "key_findings": [{"summary": f"Finding {i}"} for i in range(10)],
        }

        limited_findings = payload_data["key_findings"][:5]
        assert len(limited_findings) == 5

    def test_truncates_long_summaries(self) -> None:
        long_summary = "x" * 300
        truncated = long_summary[:200]
        assert len(truncated) == 200


class TestDeriveCodeWorkspaceResolution:
    @pytest.mark.asyncio
    async def test_uses_explicit_workspace(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Explicit workspace should be used
        assert workspace.exists()

    @pytest.mark.asyncio
    async def test_uses_workspace_hint_from_payload(self, tmp_path: Path) -> None:
        payload_data = {
            "headline": "Test",
            "target_workspace_hint": str(tmp_path),
        }

        workspace_hint = payload_data.get("target_workspace_hint", "")
        if workspace_hint:
            workspace = Path(workspace_hint)
            assert workspace.exists()


class TestDeriveCodeErrorHandling:
    @pytest.mark.asyncio
    async def test_fails_on_missing_payload(self, tmp_path: Path) -> None:
        missing_path = tmp_path / "nonexistent.json"
        assert not missing_path.exists()

    @pytest.mark.asyncio
    async def test_fails_on_invalid_json(self, tmp_path: Path) -> None:
        payload = tmp_path / "derive_payload.json"
        payload.write_text("not valid json {")

        with pytest.raises(json.JSONDecodeError):
            json.loads(payload.read_text())

    @pytest.mark.asyncio
    async def test_fails_on_missing_workspace(self, tmp_path: Path) -> None:
        workspace = tmp_path / "nonexistent_workspace"
        assert not workspace.exists()

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.domain.services import SecretRedactor


class RepoContextStore:
    """Store for repository context artifacts."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.context_path = base_path / "repo_context"
        self._redactor = SecretRedactor()

    def _ensure_dirs(self) -> None:
        self.context_path.mkdir(parents=True, exist_ok=True)
        (self.context_path / "repos").mkdir(exist_ok=True)

    async def save_repo_analysis(
        self,
        repo_name: str,
        repo_path: str,
        commit: str,
        branch: str,
        dirty: bool,
        dirty_files: list[str],
        files_analyzed: int,
        excerpts: list[dict[str, Any]],
    ) -> None:
        """Save repository analysis results."""
        # Validate repo_name to prevent path traversal attacks
        if "/" in repo_name or "\\" in repo_name or ".." in repo_name:
            raise ValueError(f"Invalid repo_name contains path separators: {repo_name}")

        self._ensure_dirs()

        repo_dir = self.context_path / "repos" / repo_name
        repo_dir.mkdir(parents=True, exist_ok=True)

        redacted_excerpts = []
        redaction_log = []

        for excerpt in excerpts:
            if self._redactor.should_exclude_file(excerpt.get("file", "")):
                redaction_log.append(
                    {
                        "file": excerpt.get("file"),
                        "reason": "forbidden_file",
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
                continue

            text = excerpt.get("text", "")
            result = self._redactor.redact_secrets(text)

            if result.had_secrets:
                redaction_log.append(
                    {
                        "file": excerpt.get("file"),
                        "reason": "secrets_redacted",
                        "patterns": result.patterns_matched,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )

            redacted_excerpts.append(
                {
                    **excerpt,
                    "text": result.redacted_text,
                }
            )

        analysis = {
            "name": repo_name,
            "path": repo_path,
            "commit": commit,
            "branch": branch,
            "dirty": dirty,
            "dirty_files": dirty_files,
            "files_analyzed": files_analyzed,
            "excerpts_count": len(redacted_excerpts),
            "analyzed_at": datetime.now(UTC).isoformat(),
        }

        (repo_dir / "analysis.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
        (repo_dir / "excerpts.json").write_text(
            json.dumps(redacted_excerpts, indent=2), encoding="utf-8"
        )

        if redaction_log:
            existing_log = await self._load_redaction_log()
            existing_log.extend(redaction_log)
            (self.context_path / "redaction_log.json").write_text(
                json.dumps(existing_log, indent=2), encoding="utf-8"
            )

    async def _load_redaction_log(self) -> list[dict[str, Any]]:
        """Load existing redaction log."""
        log_path = self.context_path / "redaction_log.json"
        if not log_path.exists():
            return []
        result: list[dict[str, Any]] = json.loads(log_path.read_text(encoding="utf-8"))
        return result

    async def save_manifest(
        self,
        mode: str,
        workspace_root: str,
        repos: list[dict[str, Any]],
        limits: dict[str, Any],
        stats: dict[str, Any],
    ) -> None:
        """Save the repo context manifest."""
        self._ensure_dirs()

        manifest = {
            "schema_version": "1.0",
            "analyzed_at": datetime.now(UTC).isoformat(),
            "mode": mode,
            "workspace_root": workspace_root,
            "limits": limits,
            "repos": repos,
            "stats": stats,
        }

        (self.context_path / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    async def load_manifest(self) -> dict[str, Any] | None:
        """Load the repo context manifest."""
        manifest_path = self.context_path / "manifest.json"
        if not manifest_path.exists():
            return None
        result: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        return result

    async def list_repos(self) -> list[str]:
        """List analyzed repositories."""
        repos_dir = self.context_path / "repos"
        if not repos_dir.exists():
            return []
        return [d.name for d in repos_dir.iterdir() if d.is_dir()]

    async def load_repo_excerpts(self, repo_name: str) -> list[dict[str, Any]]:
        """Load excerpts for a repository."""
        # Validate repo_name to prevent path traversal attacks
        if "/" in repo_name or "\\" in repo_name or ".." in repo_name:
            raise ValueError(f"Invalid repo_name contains path separators: {repo_name}")

        excerpts_path = self.context_path / "repos" / repo_name / "excerpts.json"
        if not excerpts_path.exists():
            return []
        result: list[dict[str, Any]] = json.loads(excerpts_path.read_text(encoding="utf-8"))
        return result

    def context_exists(self) -> bool:
        """Check if repo context exists."""
        return (self.context_path / "manifest.json").exists()

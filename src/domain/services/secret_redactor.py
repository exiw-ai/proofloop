import re
from dataclasses import dataclass
from fnmatch import fnmatch

SECRET_PATTERNS = [
    # API keys with specific prefixes (high confidence)
    r"sk-[a-zA-Z0-9]{20,}",  # OpenAI
    r"sk-ant-[a-zA-Z0-9\-]{20,}",  # Anthropic
    r"ghp_[a-zA-Z0-9]{36}",  # GitHub PAT
    r"gho_[a-zA-Z0-9]{36}",  # GitHub OAuth
    r"AKIA[0-9A-Z]{16}",  # AWS Access Key ID
    r"(?i)bearer\s+[a-zA-Z0-9\-_\.]{20,}",  # Bearer tokens
    # Generic secrets (require key= or key: context)
    r"(?i)(api_key|apikey|secret_key|secretkey|access_token|auth_token|private_key)\s*[=:]\s*['\"]?[a-zA-Z0-9\-_\.]{16,}['\"]?",
    r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"][^'\"]{8,}['\"]",
    # Connection strings
    r"(?i)(mysql|postgres|mongodb|redis)://[^\s]+",
]

FORBIDDEN_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "credentials.json",
    "secrets.yaml",
    "secrets.yml",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "id_ed25519",
}


@dataclass
class RedactionResult:
    original_text: str
    redacted_text: str
    had_secrets: bool
    patterns_matched: list[str]


class SecretRedactor:
    def __init__(
        self,
        patterns: list[str] | None = None,
        forbidden_files: set[str] | None = None,
    ) -> None:
        self._patterns = [re.compile(p) for p in (patterns or SECRET_PATTERNS)]
        self._forbidden_files = forbidden_files or FORBIDDEN_FILES

    def redact_secrets(self, text: str) -> RedactionResult:
        had_secrets = False
        patterns_matched: list[str] = []
        redacted = text

        for pattern in self._patterns:
            if pattern.search(redacted):
                had_secrets = True
                patterns_matched.append(pattern.pattern)
                redacted = pattern.sub("[REDACTED]", redacted)

        return RedactionResult(
            original_text=text,
            redacted_text=redacted,
            had_secrets=had_secrets,
            patterns_matched=patterns_matched,
        )

    def should_exclude_file(self, path: str) -> bool:
        from pathlib import Path

        filename = Path(path).name
        return any(fnmatch(filename, forbidden) for forbidden in self._forbidden_files)

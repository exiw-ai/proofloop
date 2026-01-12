"""Tests for SecretRedactor."""

import pytest

from src.domain.services.secret_redactor import SecretRedactor


@pytest.fixture
def redactor() -> SecretRedactor:
    return SecretRedactor()


class TestRedactSecrets:
    def test_no_secrets(self, redactor: SecretRedactor) -> None:
        text = "This is normal text without any secrets."
        result = redactor.redact_secrets(text)
        assert not result.had_secrets
        assert result.redacted_text == text
        assert result.patterns_matched == []

    def test_openai_key(self, redactor: SecretRedactor) -> None:
        text = "Using key: sk-abc123def456ghi789jkl012mnopqrstuvwxyz"
        result = redactor.redact_secrets(text)
        assert result.had_secrets
        assert "sk-" not in result.redacted_text
        assert "[REDACTED]" in result.redacted_text

    def test_anthropic_key(self, redactor: SecretRedactor) -> None:
        text = "key=sk-ant-api03-abc123def456ghi789jkl012mnopqrst"
        result = redactor.redact_secrets(text)
        assert result.had_secrets
        assert "sk-ant-" not in result.redacted_text

    def test_github_pat(self, redactor: SecretRedactor) -> None:
        text = "GITHUB_TOKEN=ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        result = redactor.redact_secrets(text)
        assert result.had_secrets
        assert "ghp_" not in result.redacted_text

    def test_aws_access_key(self, redactor: SecretRedactor) -> None:
        text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        result = redactor.redact_secrets(text)
        assert result.had_secrets
        assert "AKIA" not in result.redacted_text

    def test_bearer_token(self, redactor: SecretRedactor) -> None:
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWI"
        result = redactor.redact_secrets(text)
        assert result.had_secrets
        assert "Bearer" not in result.redacted_text

    def test_api_key_assignment(self, redactor: SecretRedactor) -> None:
        text = "api_key = 'abcdef1234567890ghijklmno'"
        result = redactor.redact_secrets(text)
        assert result.had_secrets
        assert "abcdef" not in result.redacted_text

    def test_password_assignment(self, redactor: SecretRedactor) -> None:
        text = "password = 'supersecret123'"
        result = redactor.redact_secrets(text)
        assert result.had_secrets
        assert "supersecret" not in result.redacted_text

    def test_database_connection_string(self, redactor: SecretRedactor) -> None:
        text = "DB_URL=postgres://user:pass@localhost:5432/db"
        result = redactor.redact_secrets(text)
        assert result.had_secrets
        assert "postgres://" not in result.redacted_text

    def test_multiple_secrets(self, redactor: SecretRedactor) -> None:
        text = "key1=sk-abc123def456ghi789jkl012mnop password='test1234'"
        result = redactor.redact_secrets(text)
        assert result.had_secrets
        assert len(result.patterns_matched) >= 1
        assert result.redacted_text.count("[REDACTED]") >= 1

    def test_preserves_original_text(self, redactor: SecretRedactor) -> None:
        text = "secret: sk-abc123def456ghi789jkl012mnop"
        result = redactor.redact_secrets(text)
        assert result.original_text == text
        assert result.redacted_text != result.original_text


class TestShouldExcludeFile:
    def test_env_file(self, redactor: SecretRedactor) -> None:
        assert redactor.should_exclude_file(".env")
        assert redactor.should_exclude_file("/path/to/.env")

    def test_env_local(self, redactor: SecretRedactor) -> None:
        assert redactor.should_exclude_file(".env.local")

    def test_credentials_json(self, redactor: SecretRedactor) -> None:
        assert redactor.should_exclude_file("credentials.json")
        assert redactor.should_exclude_file("/path/credentials.json")

    def test_secrets_yaml(self, redactor: SecretRedactor) -> None:
        assert redactor.should_exclude_file("secrets.yaml")
        assert redactor.should_exclude_file("secrets.yml")

    def test_pem_files(self, redactor: SecretRedactor) -> None:
        assert redactor.should_exclude_file("server.pem")
        assert redactor.should_exclude_file("private.key")

    def test_ssh_keys(self, redactor: SecretRedactor) -> None:
        assert redactor.should_exclude_file("id_rsa")
        assert redactor.should_exclude_file("id_ed25519")

    def test_normal_file_allowed(self, redactor: SecretRedactor) -> None:
        assert not redactor.should_exclude_file("main.py")
        assert not redactor.should_exclude_file("README.md")
        assert not redactor.should_exclude_file("config.json")

    def test_env_in_path_but_not_filename(self, redactor: SecretRedactor) -> None:
        assert not redactor.should_exclude_file("/env/test.py")


class TestCustomPatterns:
    def test_custom_patterns(self) -> None:
        custom_redactor = SecretRedactor(
            patterns=[r"CUSTOM_[A-Z0-9]+"],
            forbidden_files={"custom.txt"},
        )

        result = custom_redactor.redact_secrets("Token: CUSTOM_ABC123")
        assert result.had_secrets
        assert "CUSTOM_" not in result.redacted_text

    def test_custom_forbidden_files(self) -> None:
        custom_redactor = SecretRedactor(
            forbidden_files={"myconfig.txt"},
        )

        assert custom_redactor.should_exclude_file("myconfig.txt")
        assert not custom_redactor.should_exclude_file(".env")  # Default overridden

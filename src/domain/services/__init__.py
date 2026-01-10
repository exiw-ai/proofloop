"""Domain services."""

from src.domain.services.citation_validator import (
    CitationValidationResult,
    CitationValidator,
    SourceCheck,
)
from src.domain.services.coverage_calculator import (
    CoverageCalculator,
    CoverageResult,
    TopicDetail,
)
from src.domain.services.multi_repo_manager import MultiRepoManager, WorkspaceInfo
from src.domain.services.secret_redactor import RedactionResult, SecretRedactor
from src.domain.services.source_deduplicator import SourceDeduplicator
from src.domain.services.source_key_generator import SourceKeyGenerator

__all__ = [
    "CitationValidationResult",
    "CitationValidator",
    "CoverageCalculator",
    "CoverageResult",
    "MultiRepoManager",
    "RedactionResult",
    "SecretRedactor",
    "SourceCheck",
    "SourceDeduplicator",
    "SourceKeyGenerator",
    "TopicDetail",
    "WorkspaceInfo",
]

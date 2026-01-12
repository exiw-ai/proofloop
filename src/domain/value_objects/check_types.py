from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class CheckKind(str, Enum):
    # CODE pipeline check kinds
    TEST = "test"
    LINT = "lint"
    BUILD = "build"
    TYPECHECK = "typecheck"
    CUSTOM = "custom"

    # RESEARCH pipeline check kinds
    RESEARCH_COVERAGE = "research_coverage"
    RESEARCH_CITATIONS = "research_citations"
    RESEARCH_SYNTHESIS = "research_synthesis"
    RESEARCH_MIN_SOURCES = "research_min_sources"
    RESEARCH_REPORT_ARTIFACTS = "research_report_artifacts"


class CheckSpec(BaseModel, frozen=True):
    id: UUID
    name: str
    kind: CheckKind
    command: str
    cwd: str
    env: dict[str, str] = {}
    timeout_s: int = 300


class CheckResultSummary(BaseModel, frozen=True):
    check_id: UUID
    exit_code: int
    duration_ms: int
    output_tail: str

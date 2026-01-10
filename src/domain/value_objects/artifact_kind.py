from enum import Enum


class ArtifactKind(str, Enum):
    LLM_HANDOFF = "llm_handoff"
    REPO_CONTEXT = "repo_context"
    REPORTS = "reports"
    KNOWLEDGE_BASE = "knowledge_base"
    EVIDENCE = "evidence"
    BASELINE = "baseline"
    LOGS = "logs"

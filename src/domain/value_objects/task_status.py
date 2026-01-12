from enum import Enum


class TaskStatus(str, Enum):
    # CODE pipeline statuses
    INTAKE = "intake"
    STRATEGY = "strategy"
    VERIFICATION_INVENTORY = "verification_inventory"
    PLANNING = "planning"
    CONDITIONS = "conditions"
    APPROVAL_CONDITIONS = "approval_conditions"
    APPROVAL_PLAN = "approval_plan"
    EXECUTING = "executing"
    QUALITY = "quality"
    FINALIZE = "finalize"
    DONE = "done"
    BLOCKED = "blocked"
    STOPPED = "stopped"

    # RESEARCH pipeline statuses
    RESEARCH_INTAKE = "research_intake"
    RESEARCH_STRATEGY = "research_strategy"
    RESEARCH_SOURCE_SELECTION = "research_source_selection"
    RESEARCH_REPO_CONTEXT = "research_repo_context"
    RESEARCH_INVENTORY = "research_inventory"
    RESEARCH_PLANNING = "research_planning"
    RESEARCH_CONDITIONS = "research_conditions"
    RESEARCH_APPROVAL = "research_approval"
    RESEARCH_BASELINE = "research_baseline"
    RESEARCH_DISCOVERY = "research_discovery"
    RESEARCH_DEEPENING = "research_deepening"
    RESEARCH_CITATION_VALIDATE = "research_citation_validate"
    RESEARCH_REPORT_GENERATION = "research_report_generation"
    RESEARCH_FINALIZED = "research_finalized"
    RESEARCH_FAILED = "research_failed"
    RESEARCH_STAGNATED = "research_stagnated"


def is_research_status(status: TaskStatus) -> bool:
    return status.value.startswith("research_")

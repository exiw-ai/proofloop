"""Educational hints explaining why each stage matters to the user."""

# Code pipeline hints - explain the PURPOSE of each stage (why it matters)
# These are shown optionally to help users understand the workflow
CODE_STAGE_HINTS: dict[str, str] = {
    "intake": "Understanding your request to ensure we solve the right problem.",
    "strategy": "Choosing the best approach before diving into implementation.",
    "inventory": "Finding existing tests, linters, and checks.\nThese will verify our changes are correct.",
    "verification_inventory": "Finding existing tests, linters, and checks.\nThese will verify our changes are correct.",
    "mcp_selection": "Checking if external tools (GitHub, Slack, etc.) could help.",
    "clarification": "Gathering any missing information before proceeding.",
    "planning": "Creating a step-by-step plan you can review and approve.",
    "conditions": "Defining what 'done' means.\nBLOCKING conditions must pass; SIGNAL conditions inform.",
    "approval_conditions": "Your chance to add, remove, or edit success criteria.",
    "approval_plan": "Your chance to review the plan and suggest changes.",
    "delivery": "Implementing changes and running checks until all conditions pass.",
    "executing": "Implementing changes and running checks until all conditions pass.",
    "quality": "Final verification that all conditions are satisfied.",
    "finalize": "All conditions passed. Saving results and cleaning up.",
    "done": "Task completed successfully!",
    "blocked": "Task hit an obstacle that requires your input.",
    "stopped": "Task was stopped before completion.",
}

# Research pipeline hints
RESEARCH_STAGE_HINTS: dict[str, str] = {
    "research_intake": "Understanding what you want to learn.",
    "research_strategy": "Deciding which sources will best answer your questions.",
    "research_source_selection": "Evaluating available sources for relevance.",
    "research_repo_context": "Understanding your codebase to give context-aware answers.",
    "research_inventory": "Planning what to search for and where.",
    "research_planning": "Creating a structured research approach.",
    "research_conditions": "Defining what makes the research complete.",
    "research_approval": "Your chance to refine the research plan.",
    "research_baseline": "Capturing initial knowledge before deep diving.",
    "research_discovery": "Actively searching and collecting information.",
    "research_deepening": "Connecting findings and filling knowledge gaps.",
    "research_citation_validate": "Ensuring all sources are accurate and accessible.",
    "research_report_generation": "Writing the final report with your findings.",
    "research_finalized": "Research complete and report ready.",
    "research_failed": "Research could not be completed.",
    "research_stagnated": "Research is stuck and needs direction.",
}


def get_stage_hint(stage: str) -> str | None:
    """Get educational hint for a stage."""
    stage_lower = stage.lower().replace("taskstatus.", "")
    return CODE_STAGE_HINTS.get(stage_lower) or RESEARCH_STAGE_HINTS.get(stage_lower)

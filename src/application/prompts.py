"""Shared prompt templates for agent interactions."""

WORKSPACE_RESTRICTION = """
## WORKSPACE RESTRICTION
You MUST only search and read files within the workspace directory.
- DO NOT access parent directories using "../" or absolute paths outside workspace
- DO NOT use Bash commands (ls, cat, find, etc.) to access files outside workspace
- If the workspace is empty or has no relevant files, report that - do not search elsewhere
- All file paths should be relative to or within the workspace

"""


def workspace_restriction_prompt(workspace: str) -> str:
    """Generate workspace restriction prompt with specific path."""
    return f"""## WORKSPACE RESTRICTION
You MUST only search and read files within: {workspace}
- DO NOT access parent directories using "../" or absolute paths outside workspace
- DO NOT use Bash commands (ls, cat, find, etc.) to access files outside workspace
- If the workspace is empty or has no relevant files, report that - do not search elsewhere
- All file paths should be relative to or within the workspace

"""

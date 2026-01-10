"""Tool gating service per contract 1.5.

Ensures Write/Edit are blocked before verification inventory is
complete.
"""

import re

from src.domain.value_objects.task_status import TaskStatus, is_research_status

# Tool gating constants (per contract 1.5)
PRE_DELIVERY_STAGES = frozenset(
    {
        TaskStatus.INTAKE,
        TaskStatus.STRATEGY,
        TaskStatus.VERIFICATION_INVENTORY,
        TaskStatus.PLANNING,
        TaskStatus.CONDITIONS,
        TaskStatus.APPROVAL_CONDITIONS,
        TaskStatus.APPROVAL_PLAN,
    }
)

DELIVERY_STAGES = frozenset(
    {
        TaskStatus.EXECUTING,
        TaskStatus.QUALITY,
        TaskStatus.FINALIZE,
    }
)

# Research pipeline stages
RESEARCH_PRE_DISCOVERY_STAGES = frozenset(
    {
        TaskStatus.RESEARCH_INTAKE,
        TaskStatus.RESEARCH_STRATEGY,
        TaskStatus.RESEARCH_SOURCE_SELECTION,
        TaskStatus.RESEARCH_REPO_CONTEXT,
        TaskStatus.RESEARCH_INVENTORY,
        TaskStatus.RESEARCH_PLANNING,
        TaskStatus.RESEARCH_CONDITIONS,
        TaskStatus.RESEARCH_APPROVAL,
        TaskStatus.RESEARCH_BASELINE,
    }
)

RESEARCH_ACTIVE_STAGES = frozenset(
    {
        TaskStatus.RESEARCH_DISCOVERY,
        TaskStatus.RESEARCH_DEEPENING,
        TaskStatus.RESEARCH_CITATION_VALIDATE,
        TaskStatus.RESEARCH_REPORT_GENERATION,
    }
)

RESEARCH_TERMINAL_STAGES = frozenset(
    {
        TaskStatus.RESEARCH_FINALIZED,
        TaskStatus.RESEARCH_FAILED,
        TaskStatus.RESEARCH_STAGNATED,
    }
)

# Research allowed tools (read-only, no Write/Edit)
RESEARCH_ALLOWED_TOOLS = ["WebSearch", "WebFetch", "Read", "Glob", "Grep", "Bash"]

# Bash command validation patterns
FORBIDDEN_OPERATORS = [r">", r"2>", r"&>", r";", r"&&", r"\|\|", r"`", r"\$\(", r"\n"]

ALWAYS_DANGEROUS = [
    r"rm\s+-rf\s+",
    r"git\s+reset\s+--hard",
    r"git\s+clean\s+-fdx",
]

SAFE_BASH_PATTERNS = [
    r"git\s+(status|log|diff|show|branch|remote|rev-parse)(\s+.+)?",
    r"ls(\s+.+)?",
    r"cat\s+.+",
    r"head(\s+.+)?",
    r"tail(\s+.+)?",
    r"find\s+.+",
    r"grep\s+.+",
    r"rg\s+.+",
    r"pwd",
    r"which\s+.+",
    r"echo\s+\$.+",  # Only echo $VAR
    r"python\s+--version",
    r"node\s+--version",
    r"npm\s+(list|ls|--version)(\s+.+)?",
    r"pip\s+(list|show|--version)(\s+.+)?",
    r"wc(\s+.+)?",
    r"sort(\s+.+)?",
    r"uniq(\s+.+)?",
]

# Dangerous commands (blocked even without operators in pre-delivery)
DANGEROUS_COMMANDS = [
    r"rm\s+.+",
    r"mv\s+.+",
    r"touch\s+.+",
    r"mkdir\s+.+",
    r"chmod\s+.+",
    r"chown\s+.+",
    r"git\s+(add|commit|push|checkout|reset|rebase)(\s+.+)?",
]


# Research bash whitelist (read-only commands only)
RESEARCH_WHITELIST_COMMANDS = frozenset(
    {
        "ls",
        "cat",
        "head",
        "tail",
        "find",
        "wc",
        "sort",
        "uniq",
        "grep",
        "tree",
        "file",
        "stat",
        "du",
        "df",
        "curl",
        "wget",
        "jq",
    }
)

RESEARCH_GIT_ALLOWED_SUBCOMMANDS = frozenset(
    {"status", "log", "diff", "show", "branch", "remote", "tag"}
)

# BNF Grammar forbidden tokens for research bash
RESEARCH_FORBIDDEN_TOKENS = frozenset(
    {";", "&&", "||", ">", ">>", "<", "<<", "2>", "&>", "$(", "`", "<(", ">(", "\n"}
)


class ToolGatingError(Exception):
    """Raised when tool access is denied due to gating rules."""


class BashParseError(Exception):
    """Raised when bash command fails BNF grammar validation."""


def get_allowed_tools(task_status: TaskStatus) -> list[str]:
    """Get allowed tools based on task status (contract 1.5).

    PRE_DELIVERY stages: Read, Glob, Grep, Bash (validated via whitelist)
    DELIVERY stages: Read, Write, Edit, Bash, Glob, Grep (full access)
    RESEARCH stages: WebSearch, WebFetch, Read, Glob, Grep, Bash (read-only)
    """
    if is_research_status(task_status):
        return RESEARCH_ALLOWED_TOOLS.copy()

    if task_status in PRE_DELIVERY_STAGES:
        return ["Read", "Glob", "Grep", "Bash"]
    return ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]


def get_research_tools(status: TaskStatus) -> list[str]:  # noqa: ARG001
    """Get allowed tools for research pipeline stages."""
    return RESEARCH_ALLOWED_TOOLS.copy()


def _tokenize_bash(command: str) -> list[str]:
    """Simple tokenizer for bash command validation."""
    tokens: list[str] = []
    current = ""
    in_quote: str | None = None
    i = 0

    while i < len(command):
        char = command[i]

        # Handle quoting
        if char in ('"', "'") and in_quote is None:
            in_quote = char
            current += char
        elif char == in_quote:
            current += char
            in_quote = None
        elif in_quote:
            current += char
        # Handle special tokens
        elif char in " \t":
            if current:
                tokens.append(current)
                current = ""
        elif char == "|" and i + 1 < len(command) and command[i + 1] == "|":
            if current:
                tokens.append(current)
                current = ""
            tokens.append("||")
            i += 1
        elif char == "|":
            if current:
                tokens.append(current)
                current = ""
            tokens.append("|")
        elif char == "&" and i + 1 < len(command) and command[i + 1] == "&":
            if current:
                tokens.append(current)
                current = ""
            tokens.append("&&")
            i += 1
        elif char == "&" and i + 1 < len(command) and command[i + 1] == ">":
            if current:
                tokens.append(current)
                current = ""
            tokens.append("&>")
            i += 1
        elif char == ">" and i + 1 < len(command) and command[i + 1] == ">":
            if current:
                tokens.append(current)
                current = ""
            tokens.append(">>")
            i += 1
        elif char == "2" and i + 1 < len(command) and command[i + 1] == ">":
            if current:
                tokens.append(current)
                current = ""
            tokens.append("2>")
            i += 1
        elif char == "<" and i + 1 < len(command) and command[i + 1] == "<":
            if current:
                tokens.append(current)
                current = ""
            tokens.append("<<")
            i += 1
        elif char == "<" and i + 1 < len(command) and command[i + 1] == "(":
            if current:
                tokens.append(current)
                current = ""
            tokens.append("<(")
            i += 1
        elif char == ">" and i + 1 < len(command) and command[i + 1] == "(":
            if current:
                tokens.append(current)
                current = ""
            tokens.append(">(")
            i += 1
        elif char == "$" and i + 1 < len(command) and command[i + 1] == "(":
            if current:
                tokens.append(current)
                current = ""
            tokens.append("$(")
            i += 1
        elif char in ";><`\n":
            if current:
                tokens.append(current)
                current = ""
            tokens.append(char)
        else:
            current += char

        i += 1

    if current:
        tokens.append(current)

    return tokens


def validate_research_bash(command: str) -> bool:
    """Validate bash command for research pipeline using BNF grammar.

    Grammar:
        command     := simple_cmd (PIPE simple_cmd)*
        simple_cmd  := WHITELIST_CMD arg*
                    |  "git" GIT_SUBCOMMAND arg*
        arg         := WORD | QUOTED_STRING | GLOB_PATTERN
        PIPE        := "|"

    Returns True if valid, False otherwise.
    """
    tokens = _tokenize_bash(command)

    # Check for forbidden tokens
    for token in tokens:
        if token in RESEARCH_FORBIDDEN_TOKENS:
            return False

    # Split by pipe and validate each segment
    segments: list[list[str]] = []
    current_segment: list[str] = []

    for token in tokens:
        if token == "|":
            if current_segment:
                segments.append(current_segment)
                current_segment = []
        else:
            current_segment.append(token)

    if current_segment:
        segments.append(current_segment)

    if not segments:
        return False

    for segment in segments:
        if not segment:
            return False

        cmd = segment[0]

        # Handle git subcommands
        if cmd == "git":
            if len(segment) < 2:
                return False
            subcommand = segment[1]
            if subcommand not in RESEARCH_GIT_ALLOWED_SUBCOMMANDS:
                return False
        # Handle whitelist commands
        elif cmd not in RESEARCH_WHITELIST_COMMANDS:
            return False

    return True


def validate_bash_command(
    command: str,
    task_status: TaskStatus,
    allow_dangerous: bool = False,
) -> None:
    """Validate bash command against gating rules.

    Raises ToolGatingError if command is not allowed.
    """
    # Always check dangerous commands (even in DELIVERY stages)
    if not allow_dangerous:
        for pattern in ALWAYS_DANGEROUS:
            if re.search(pattern, command):
                raise ToolGatingError(f"Dangerous command blocked: '{command}'")

    # Research pipeline: use strict BNF validation
    if is_research_status(task_status):
        if not validate_research_bash(command):
            raise ToolGatingError(f"Command not allowed in research pipeline: '{command}'")
        return

    # In DELIVERY stages, only dangerous check applies
    if task_status in DELIVERY_STAGES:
        return

    # In PRE_DELIVERY stages: check forbidden operators
    for op in FORBIDDEN_OPERATORS:
        if re.search(op, command):
            raise ToolGatingError(f"Operator '{op}' forbidden in {task_status}")

    # Split by pipe and validate each segment
    segments = [s.strip() for s in command.split("|")]
    for segment in segments:
        # Check dangerous commands (per-segment)
        for pattern in DANGEROUS_COMMANDS:
            if re.fullmatch(pattern, segment):
                raise ToolGatingError(f"Dangerous command: '{segment}'")

        # Check whitelist
        if not any(re.fullmatch(p, segment) for p in SAFE_BASH_PATTERNS):
            raise ToolGatingError(f"Command not in whitelist: '{segment}'")

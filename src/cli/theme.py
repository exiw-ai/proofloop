"""CLI theme configuration - all colors in one place.

Modify these values to customize the terminal color scheme.
Colors use Rich markup syntax (e.g., "green", "bold red", "dim italic").
"""


class Theme:
    """Terminal color theme for proofloop CLI."""

    # -------------------------------------------------------------------------
    # Status colors (for success/error/warning indicators)
    # -------------------------------------------------------------------------
    SUCCESS = "green"
    SUCCESS_BOLD = "bold green"
    ERROR = "red"
    ERROR_BOLD = "bold red"
    WARNING = "yellow"
    WARNING_BOLD = "bold yellow"
    INFO = "cyan"
    INFO_BOLD = "bold cyan"

    # -------------------------------------------------------------------------
    # Text styles
    # -------------------------------------------------------------------------
    HEADER = "bold"
    HEADER_SECTION = "bold magenta"
    DIM = "grey62"
    DIM_ITALIC = "grey62 italic"
    TEXT = "white"

    # -------------------------------------------------------------------------
    # Interactive elements (prompts, options)
    # -------------------------------------------------------------------------
    PROMPT = "cyan"
    OPTION_APPROVE = "green"
    OPTION_REJECT = "yellow"
    OPTION_FEEDBACK = "cyan"
    OPTION_EDIT = "magenta"

    # -------------------------------------------------------------------------
    # Table columns
    # -------------------------------------------------------------------------
    TABLE_ID = "cyan"
    TABLE_LABEL = "grey62"
    TABLE_VALUE = "bold"
    TABLE_SECONDARY = "grey62"

    # -------------------------------------------------------------------------
    # Diff display
    # -------------------------------------------------------------------------
    DIFF_ADD = "green"
    DIFF_REMOVE = "red"

    # -------------------------------------------------------------------------
    # Task status
    # -------------------------------------------------------------------------
    STATUS_DONE = "bold green"
    STATUS_BLOCKED = "bold red"
    STATUS_STOPPED = "bold yellow"
    STATUS_EXECUTING = "bold yellow"
    STATUS_PLANNING = "cyan"
    STATUS_VERIFYING = "magenta"

    # -------------------------------------------------------------------------
    # Conditions
    # -------------------------------------------------------------------------
    BLOCKING = "bold red"
    SIGNAL = "yellow"

    # -------------------------------------------------------------------------
    # Panel borders
    # -------------------------------------------------------------------------
    BORDER_INFO = "blue"
    BORDER_ERROR = "red"
    BORDER_WARNING = "yellow"

    # -------------------------------------------------------------------------
    # Todo states
    # -------------------------------------------------------------------------
    TODO_COMPLETED = "green"
    TODO_IN_PROGRESS = "yellow"
    TODO_PENDING = "grey62"

    # -------------------------------------------------------------------------
    # Tool display
    # -------------------------------------------------------------------------
    TOOL_OPERATION = "light_steel_blue"
    TOOL_ARGS = "grey74"

    # -------------------------------------------------------------------------
    # MCP servers
    # -------------------------------------------------------------------------
    MCP_NAME = "cyan"
    MCP_CATEGORY = "magenta"
    MCP_CREDENTIALS = "yellow"
    MCP_CONFIDENCE_HIGH = "green"
    MCP_CONFIDENCE_LOW = "yellow"


# Default theme instance - import this in other modules
theme = Theme()

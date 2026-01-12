"""CLI utility functions."""


def sanitize_terminal_input(text: str) -> str:
    """Remove surrogate characters that can't be encoded as UTF-8.

    Terminal input can sometimes contain surrogate characters (U+D800 to U+DFFF)
    due to encoding issues. These characters are invalid in UTF-8 and cause
    errors when sent to APIs.

    Args:
        text: Raw input text that may contain surrogates

    Returns:
        Sanitized text with surrogates removed
    """
    return text.encode("utf-8", "ignore").decode("utf-8")

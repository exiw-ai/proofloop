def format_duration(seconds: int) -> str:
    """Convert seconds to human-readable duration string like '2h 30m 15s'."""
    if seconds < 0:
        raise ValueError("seconds must be non-negative")

    if seconds == 0:
        return "0s"

    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs:
        parts.append(f"{secs}s")

    return " ".join(parts)

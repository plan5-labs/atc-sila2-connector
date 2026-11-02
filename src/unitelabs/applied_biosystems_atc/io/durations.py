import datetime


def format_duration(duration: datetime.timedelta) -> str:
    """
    Format a duration as `hh:mm:ss`.

    Hours keep counting past 24 instead of rolling over into days.

    Args:
      duration: The duration to format, rounded down to whole seconds.

    Returns:
      The formatted duration, e.g. `01:02:05`.
    """

    minutes, seconds = divmod(int(duration.total_seconds()), 60)
    hours, minutes = divmod(minutes, 60)

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

from dataclasses import dataclass


@dataclass
class WaitTimes:
    """Wait times in seconds for various operations."""

    ACTIVITY_CYCLE = 50
    SHORT_WAIT = 5
    VERY_SHORT_WAIT = 2

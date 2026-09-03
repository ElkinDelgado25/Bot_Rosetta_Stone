from dataclasses import dataclass


@dataclass
class Timeouts:
    """Timeout values in milliseconds."""

    DEFAULT_TIMEOUT = 5000
    LONG_TIMEOUT = 10000
    VERY_LONG_TIMEOUT = 60000
    SHORT_TIMEOUT = 3000
    VERY_SHORT_TIMEOUT = 1500

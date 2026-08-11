from enum import Enum


class ActivityType(str, Enum):
    SELECT_DROPDOWN = "select_dropdown"
    WRITE = "write"
    SPEAK = "speak"
    LISTEN = "listen"
    MATCH = "match"

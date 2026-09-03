from enum import Enum


class SelectorKind(Enum):
    ROLE = "role"
    TEST_ID = "test_id"
    LABEL = "label"
    PLACEHOLDER = "placeholder"
    TEXT = "text"
    CSS = "css"

import re


def compile_case_insensitive(pattern: str) -> re.Pattern:
    """
    Utility function to compile regex patterns with case-insensitive flag.

    Args:
        pattern: The regex pattern string

    Returns:
        Compiled regex pattern with IGNORECASE flag
    """
    return re.compile(pattern, re.IGNORECASE)

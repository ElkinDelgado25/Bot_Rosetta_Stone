"""Regex utilities for Playwright selectors."""

import re
from typing import Optional, Pattern


def compile_slash_regex(s: str) -> Optional[Pattern]:
    """
    Accepts "/.../flags" and returns a compiled re.Pattern.
    Supported flags: i (IGNORECASE), m (MULTILINE), s (DOTALL)

    Args:
        s: String potentially containing regex pattern in slash notation

    Returns:
        Compiled regex pattern or None if not a valid slash notation

    Examples:
        >>> compile_slash_regex("/test/i")
        re.compile('test', re.IGNORECASE)
        >>> compile_slash_regex("regular string")
        None
    """
    if not isinstance(s, str):
        return None

    m = re.fullmatch(r"/(.+)/([a-z]*)", s.strip())
    if not m:
        return None

    flags = 0
    f = m.group(2)
    if "i" in f:
        flags |= re.IGNORECASE
    if "m" in f:
        flags |= re.MULTILINE
    if "s" in f:
        flags |= re.DOTALL

    return re.compile(m.group(1), flags)

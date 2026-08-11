from dataclasses import dataclass

# Import new pattern infrastructure for backward compatibility
from rosseta_stone_script_a.infrastructure.adapters.web.playwright.patterns import (
    AuthPatterns,
)



@dataclass
class CompiledPatterns:
    """
    Pre-compiled regex patterns for better performance.

    DEPRECATED: Use patterns from common_patterns.py instead.
    This class is maintained for backward compatibility only.
    """

    # Login patterns - use AuthPatterns instead
    SIGNIN = AuthPatterns.SIGN_IN
    LOGIN_PAGE = AuthPatterns.LOGIN_PAGE



@dataclass
class Selectors:
    """CSS selectors used throughout the application."""

    # Login selectors
    EMAIL_SELECTORS = [
        "input[type='email']",
        "input[name='email']",
        "input#email",
        "input[autocomplete='username']",
        "input[autocomplete='email']",
        "input[placeholder='Email address']",
        "[data-qa='Email']",
        "input[type='text'][name='email']",
        "input[type='text'][autocomplete='username']",
    ]

    PASSWORD_SELECTORS = [
        "input[type='password']",
        "input[name='password']",
        "input#password",
        "input[autocomplete='current-password']",
        "[data-qa='Password']",
        "input[placeholder='Password']",
    ]

    LOGIN_BUTTON_SELECTORS = [
        "[data-qa='SignInButton']",
        "button[type='submit']",
        "input[type='submit']",
    ]


@dataclass
class URLs:
    """URLs used by the application."""

    LOGIN_URL = "https://login.rosettastone.com/login"


@dataclass
class TextPatterns:
    """Regular expression patterns for text matching."""

    # Login patterns
    SIGNIN_PATTERNS = r"sign\s*in|iniciar\s*sesión|acceder|entrar|login"
    LOGIN_PAGE_PATTERNS = r"login|signin|acceder|entrar|iniciar"

    FOUNDATIONS_PATTERNS = r"foundations|fundamentos"


@dataclass
class Timeouts:
    """Timeout values in milliseconds."""

    DEFAULT_TIMEOUT = 5000
    LONG_TIMEOUT = 10000
    VERY_LONG_TIMEOUT = 60000
    SHORT_TIMEOUT = 3000
    VERY_SHORT_TIMEOUT = 1500


@dataclass
class WaitTimes:
    """Wait times in seconds for various operations."""

    ACTIVITY_CYCLE = 50
    SHORT_WAIT = 5
    VERY_SHORT_WAIT = 2

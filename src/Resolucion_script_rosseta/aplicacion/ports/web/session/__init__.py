"""Session management ports for web automation."""

from .browser_provider_port import BrowserProviderPort
from .web_session_port import IWebSession

__all__ = [
    "BrowserProviderPort",
    "IWebSession",
]

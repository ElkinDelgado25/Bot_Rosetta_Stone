"""Page-specific ports for web application interfaces."""

from .auth_port import AuthPort
from .dashboard_port import DashboardPagePort
from .stories_page_port import StoriesPagePort


__all__ = [
    "AuthPort",
    "DashboardPagePort",
    "StoriesPagePort",
]

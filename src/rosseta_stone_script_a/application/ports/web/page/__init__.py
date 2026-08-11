"""Page-specific ports for web application interfaces."""

from .auth_port import AuthPort
from .dashboard_port import DashboardPagePort


__all__ = [
    "AuthPort",
    "DashboardPagePort",
]

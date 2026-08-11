"""
Orchestrators package - Composes atomic use cases into workflows.

Orchestrators follow Clean Architecture principles:
- Depend only on application layer ports/interfaces
- Receive use cases via dependency injection
- Handle control flow, branching, retries and events
- Provide idempotent operations with structured logging
- Use SubjectVerb naming convention
"""

from .open_fundations import OpenFundations


__all__ = [
    "OpenFundations",
]

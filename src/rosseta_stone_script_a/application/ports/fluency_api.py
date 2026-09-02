from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from rosseta_stone_script_a.domain.entities.fluency_catalog import FluencyCatalog
from rosseta_stone_script_a.domain.entities.fluency_sequence import FluencySequence
from rosseta_stone_script_a.domain.values.fluency_progress_result import (
    FluencyProgressResult,
)


class FluencyApiPort(ABC):
    """Port for the Rosetta Stone Fluency Builder API (gaia-server)."""

    @abstractmethod
    async def get_catalog(
        self, authorization: str, locale: Optional[str] = None
    ) -> FluencyCatalog:
        """Fetch assigned courses with per-lesson progress (getCoursesAndProgress)."""
        ...

    @abstractmethod
    async def get_sequence(
        self,
        authorization: str,
        course_id: str,
        sequence_id: str,
        locale: Optional[str] = None,
    ) -> FluencySequence:
        """Fetch one lesson's full activity/step tree, including correct answers."""
        ...

    @abstractmethod
    async def add_progress(
        self,
        authorization: str,
        user_id: Optional[str],
        messages: List[Dict[str, Any]],
    ) -> FluencyProgressResult:
        """Submit one or more ProgressMessages (AddProgress mutation)."""
        ...

    @abstractmethod
    async def add_usage_overhead(
        self,
        authorization: str,
        user_id: Optional[str],
        messages: List[Dict[str, Any]],
    ) -> FluencyProgressResult:
        """Submit usage-time telemetry (AddUsageOverhead mutation).

        Schema captured from the real player (see docs/FLUENCY_BUILDER.md): the
        mutation takes ``$messages`` only — no ``userId`` — and ``usageOverhead``
        returns a scalar, so it takes no selection set. Each message carries
        ``id``, ``userAgent``, ``learningContext``, ``durationMs`` and
        ``endTimestamp``. Still best-effort: lesson completion is confirmed to
        work through ``add_progress`` alone, so callers treat failures here as
        non-fatal.
        """
        ...

    @abstractmethod
    async def get_progress(
        self, authorization: str, course_id: str
    ) -> Dict[str, Any]:
        """Authoritative per-activity/step progress for a course (getProgress).

        Returns the raw ``data.progress`` payload. Unlike getCoursesAndProgress,
        this is not cached and exposes each activity's percentComplete and the
        attempts recorded against it.
        """
        ...

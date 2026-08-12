"""Structured progress events, emitted next to the human-readable log.

A worker container's only channel back to the orchestrator is its stdout, so
progress travels as one JSON object per line behind a prefix the reader can
recognise. Plain log lines pass through untouched.

Emission is opt-in via ``ROSETTA_EVENTS``: a normal CLI run stays exactly as
noisy as it was.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

EVENT_PREFIX = "@@EVENT "


def events_enabled() -> bool:
    return os.getenv("ROSETTA_EVENTS", "").strip().lower() in ("1", "true", "yes")


def emit(event_type: str, **fields: Any) -> None:
    """Write one structured event to stdout, if events are enabled."""
    if not events_enabled():
        return
    payload = {
        "type": event_type,
        "at": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    try:
        line = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return
    # Unbuffered: the orchestrator streams this live, and a half-written buffer
    # in a container that just died is a lost event.
    print(f"{EVENT_PREFIX}{line}", flush=True, file=sys.stdout)


def parse(line: str) -> dict[str, Any] | None:
    """Return the event encoded in *line*, or None if it isn't one."""
    if not line.startswith(EVENT_PREFIX):
        return None
    try:
        parsed = json.loads(line[len(EVENT_PREFIX) :])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None

"""Per-account progress state persisted to JSON between scheduler runs."""

import json
from datetime import date, datetime
from pathlib import Path


class RunProgressState:
    """
    Persists completion state per account so the bot can resume across runs.

    State schema (JSON):
    {
      "completed_path_keys": ["<key>", ...],   # set serialised as list
      "run_log": [{"date": "YYYY-MM-DD", "count": N}, ...],
      "last_run": "ISO-8601 timestamp or null"
    }
    """

    def __init__(self, state_file: Path) -> None:
        self._file = state_file
        self._data: dict = {
            "completed_path_keys": [],
            "run_log": [],
            "last_run": None,
        }
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load state from disk if the file exists."""
        if self._file.exists():
            try:
                with open(self._file, encoding="utf-8") as fh:
                    self._data = json.load(fh)
                # Ensure both fields always present (forward-compat)
                self._data.setdefault("completed_path_keys", [])
                self._data.setdefault("run_log", [])
                self._data.setdefault("last_run", None)
            except Exception:
                # Corrupt file — start fresh rather than crash
                self._data = {
                    "completed_path_keys": [],
                    "run_log": [],
                    "last_run": None,
                }

    def save(self) -> None:
        """Persist current state to disk."""
        self._file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._file, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Path-level helpers
    # ------------------------------------------------------------------

    def is_done(self, path_key: str) -> bool:
        """Return True if this path key has already been completed."""
        return path_key in self._data["completed_path_keys"]

    def mark_done(self, path_key: str) -> None:
        """Record that a path has been completed and update today's run log."""
        if path_key not in self._data["completed_path_keys"]:
            self._data["completed_path_keys"].append(path_key)

        today = date.today().isoformat()
        run_log: list[dict] = self._data["run_log"]
        for entry in run_log:
            if entry["date"] == today:
                entry["count"] += 1
                return
        # No entry for today yet
        run_log.append({"date": today, "count": 1})

    # ------------------------------------------------------------------
    # Day-cap helper
    # ------------------------------------------------------------------

    def count_done_today(self, for_date: date | None = None) -> int:
        """Return the number of paths completed on *for_date* (default: today)."""
        target = (for_date or date.today()).isoformat()
        for entry in self._data["run_log"]:
            if entry["date"] == target:
                return entry["count"]
        return 0

    def total_done(self) -> int:
        """Return total number of completed path keys."""
        return len(self._data["completed_path_keys"])

    # ------------------------------------------------------------------
    # Timestamp helpers
    # ------------------------------------------------------------------

    def touch_last_run(self) -> None:
        """Record the current timestamp as the last run time."""
        self._data["last_run"] = datetime.utcnow().isoformat() + "Z"

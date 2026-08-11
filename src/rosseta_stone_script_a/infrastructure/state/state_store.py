"""Factory that resolves the per-account state file path and returns a RunProgressState."""

from pathlib import Path

from rosseta_stone_script_a.infrastructure.state.run_progress_state import (
    RunProgressState,
)


class StateStore:
    """
    Locates or creates the per-account JSON state file inside *state_dir*.

    File name: ``<user_id>.json`` (falls back to a sanitised email slug if
    user_id is unavailable).
    """

    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir

    def load(self, user_id: str | None, email: str | None = None) -> RunProgressState:
        """Return a ``RunProgressState`` for the given account identity."""
        key = self._account_key(user_id, email)
        state_file = self._state_dir / f"{key}.json"
        return RunProgressState(state_file)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _account_key(user_id: str | None, email: str | None) -> str:
        if user_id:
            return _sanitise(user_id)
        if email:
            return _sanitise(email)
        return "default_account"


def _sanitise(value: str) -> str:
    """Replace characters that are unsafe in file names with underscores."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in value)

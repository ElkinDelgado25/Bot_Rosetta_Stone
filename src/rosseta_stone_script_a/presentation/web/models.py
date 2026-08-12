"""Request bodies for the web UI API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProfileIn(BaseModel):
    """Payload for creating a profile.

    The UI only asks for email and password. Everything else keeps its default
    and stays editable through the API for anyone who needs it.
    """

    # Omitted by the UI: derived from the email in `create_profile`.
    name: str | None = Field(default=None, min_length=1, max_length=60)
    email: str = Field(min_length=3, max_length=200)
    password: str | None = None
    units_to_complete: list[int] = []
    lessons_to_complete: list[int] = []
    path_types_to_complete: list[str] = []
    target_score_percent: int = Field(default=100, ge=0, le=100)
    human_mode: bool = False
    force_recomplete: bool = False
    max_paths_per_day: int = Field(default=18, ge=1, le=500)


class ProfileUpdate(BaseModel):
    """Payload for editing a profile. Unset fields are left untouched."""

    name: str | None = Field(default=None, min_length=1, max_length=60)
    email: str | None = Field(default=None, min_length=3, max_length=200)
    password: str | None = None
    units_to_complete: list[int] | None = None
    lessons_to_complete: list[int] | None = None
    path_types_to_complete: list[str] | None = None
    target_score_percent: int | None = Field(default=None, ge=0, le=100)
    human_mode: bool | None = None
    force_recomplete: bool | None = None
    max_paths_per_day: int | None = Field(default=None, ge=1, le=500)


class RunIn(BaseModel):
    """Optional per-run password, for profiles that don't store one."""

    password: str | None = None

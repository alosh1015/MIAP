from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Preferences(BaseModel):
    theme: Literal["system", "light", "dark"] = "system"
    viewer_overlay_opacity: float = Field(default=0.85, ge=0.0, le=1.0)
    viewer_split: bool = False
    default_model: str | None = None
    export_format: Literal["csv", "json"] = "csv"


class PreferencesPatch(BaseModel):
    theme: Literal["system", "light", "dark"] | None = None
    viewer_overlay_opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    viewer_split: bool | None = None
    default_model: str | None = None
    export_format: Literal["csv", "json"] | None = None


class Profile(BaseModel):
    id: str
    email: str
    display_name: str
    role: str


class SettingsResponse(BaseModel):
    profile: Profile
    preferences: Preferences
    capabilities: dict[str, bool]
    viewer_defaults: dict
    notices: list[str]


class SystemSettings(BaseModel):
    retention_default_days: int
    export_row_cap: int
    max_batch_images: int
    tb_notice: str


class SystemSettingsPatch(BaseModel):
    retention_default_days: int | None = Field(default=None, ge=1, le=3650)
    export_row_cap: int | None = Field(default=None, ge=1, le=100_000)
    max_batch_images: int | None = Field(default=None, ge=1, le=200)
    tb_notice: str | None = Field(default=None, max_length=500)

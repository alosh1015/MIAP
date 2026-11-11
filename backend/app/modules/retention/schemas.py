from __future__ import annotations

from pydantic import BaseModel


class RetentionRunRequest(BaseModel):
    confirm: bool = False

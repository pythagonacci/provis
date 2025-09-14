from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class Slide(BaseModel):
    title: str
    bullets: List[str] = Field(default_factory=list)


class DeckOut(BaseModel):
    id: int
    prospect_id: int
    title: str
    slides: List[Slide]
    pdf_url: Optional[str] = None


# Incoming slide payload for PATCH (edits)
class SlideIn(BaseModel):
    title: str
    bullets: List[str] = Field(default_factory=list)

    # Ensure bullets is always a list, even if null/None is sent
    @field_validator("bullets", mode="before")
    @classmethod
    def _ensure_list(cls, v):
        return v or []


class DeckUpdate(BaseModel):
    title: Optional[str] = None
    slides: List[SlideIn]

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

class EmailOut(BaseModel):
    id: int
    prospect_id: int
    sequence_index: int
    subject: str
    body: str

class EmailIn(BaseModel):
    subject: str
    body: str

class EmailUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None

class EmailBatchOut(BaseModel):
    items: List[EmailOut] = Field(default_factory=list)

class ProspectContext(BaseModel):
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    industry: Optional[str] = None
    revenue_range: Optional[str] = None
    location: Optional[str] = None
    sale_motivation: Optional[str] = None
    signals: Optional[str] = None

    @field_validator("*", mode="before")
    @classmethod
    def coerce_str(cls, v):
        return "" if v is None else v

from pydantic import BaseModel, EmailStr
from typing import Optional

class ProspectCreate(BaseModel):
    company_name: str
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    industry: Optional[str] = None
    revenue_range: Optional[str] = None
    location: Optional[str] = None
    sale_motivation: Optional[str] = None
    signals: Optional[str] = None
    notes: Optional[str] = None

class ProspectUpdate(BaseModel):
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    industry: Optional[str] = None
    revenue_range: Optional[str] = None
    location: Optional[str] = None
    sale_motivation: Optional[str] = None
    signals: Optional[str] = None
    notes: Optional[str] = None

class ProspectOut(ProspectCreate):
    id: int

    class Config:
        from_attributes = True

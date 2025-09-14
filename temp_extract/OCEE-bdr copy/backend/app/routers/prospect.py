from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from .. import models
from ..schemas.prospect import ProspectCreate, ProspectOut, ProspectUpdate

router = APIRouter()

@router.post("", response_model=ProspectOut, status_code=status.HTTP_201_CREATED)
def create_prospect(payload: ProspectCreate, db: Session = Depends(get_db)):
    p = models.Prospect(
        company_name=payload.company_name.strip(),
        contact_name=(payload.contact_name or None),
        email=(str(payload.email) if payload.email else None),
        phone_number=(payload.phone_number or None),
        industry=(payload.industry or None),
        revenue_range=(payload.revenue_range or None),
        location=(payload.location or None),
        sale_motivation=(payload.sale_motivation or None),
        signals=(payload.signals or None),
        notes=(payload.notes or None),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p

@router.get("", response_model=List[ProspectOut])
def list_prospects(db: Session = Depends(get_db)):
    return db.query(models.Prospect).order_by(models.Prospect.created_at.desc()).all()

@router.get("/{prospect_id}", response_model=ProspectOut)
def get_prospect(prospect_id: int, db: Session = Depends(get_db)):
    p = db.query(models.Prospect).get(prospect_id)
    if not p:
        raise HTTPException(status_code=404, detail="Prospect not found")
    return p

@router.patch("/{prospect_id}", response_model=ProspectOut)
def update_prospect(prospect_id: int, payload: ProspectUpdate, db: Session = Depends(get_db)):
    p = db.query(models.Prospect).get(prospect_id)
    if not p:
        raise HTTPException(status_code=404, detail="Prospect not found")
    
    # Update fields if provided
    if payload.company_name is not None:
        p.company_name = payload.company_name.strip()
    if payload.contact_name is not None:
        p.contact_name = payload.contact_name
    if payload.email is not None:
        p.email = str(payload.email) if payload.email else None
    if payload.phone_number is not None:
        p.phone_number = payload.phone_number
    if payload.industry is not None:
        p.industry = payload.industry
    if payload.revenue_range is not None:
        p.revenue_range = payload.revenue_range
    if payload.location is not None:
        p.location = payload.location
    if payload.sale_motivation is not None:
        p.sale_motivation = payload.sale_motivation
    if payload.signals is not None:
        p.signals = payload.signals
    if payload.notes is not None:
        p.notes = payload.notes
    
    db.commit()
    db.refresh(p)
    return p

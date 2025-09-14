from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..database import get_db
from ..models.prospect import Prospect
from ..models.email import Email
from ..schemas.email import EmailOut, EmailIn, EmailUpdate, EmailBatchOut
from ..services.emailgeneration import generate_emails, EmailAIUnavailableError, EmailAIFormatError

router = APIRouter()

def _to_out(e: Email) -> EmailOut:
    return EmailOut(
        id=e.id,
        prospect_id=e.prospect_id,
        sequence_index=e.sequence_index,
        subject=e.subject,
        body=e.body,
    )

@router.post("/{prospect_id}/generate", response_model=EmailBatchOut, status_code=status.HTTP_201_CREATED)
def generate_email_sequence(prospect_id: int, db: Session = Depends(get_db)):
    # prospect_id is a PATH PARAM (not request body)
    p = db.get(Prospect, prospect_id)
    if not p:
        raise HTTPException(status_code=404, detail="Prospect not found")

    prospect_dict = {
        "company_name": p.company_name,
        "contact_name": p.contact_name,
        "industry": p.industry,
        "revenue_range": p.revenue_range,
        "location": p.location,
        "sale_motivation": p.sale_motivation,
        "signals": p.signals,
    }

    try:
        emails = generate_emails(prospect_dict)
    except EmailAIUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except EmailAIFormatError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Persist (replace any existing sequence for this prospect)
    # Simple approach: delete old, insert new
    db.query(Email).filter(Email.prospect_id == prospect_id).delete()
    db.flush()

    saved: List[Email] = []
    for item in emails:
        row = Email(
            prospect_id=prospect_id,
            sequence_index=item["sequence_index"],
            subject=item["subject"],
            body=item["body"],
        )
        db.add(row)
        saved.append(row)

    db.commit()
    for row in saved:
        db.refresh(row)

    return EmailBatchOut(items=[_to_out(r) for r in saved])

@router.get("/{prospect_id}", response_model=EmailBatchOut, status_code=status.HTTP_200_OK)
def list_emails_for_prospect(prospect_id: int, db: Session = Depends(get_db)):
    rows = db.query(Email).filter(Email.prospect_id == prospect_id).order_by(Email.sequence_index.asc()).all()
    return EmailBatchOut(items=[_to_out(r) for r in rows])

@router.get("/item/{email_id}", response_model=EmailOut, status_code=status.HTTP_200_OK)
def get_email(email_id: int, db: Session = Depends(get_db)):
    row = db.get(Email, email_id)
    if not row:
        raise HTTPException(status_code=404, detail="Email not found")
    return _to_out(row)

@router.patch("/item/{email_id}", response_model=EmailOut, status_code=status.HTTP_200_OK)
def update_email(email_id: int, payload: EmailUpdate, db: Session = Depends(get_db)):
    row = db.get(Email, email_id)
    if not row:
        raise HTTPException(status_code=404, detail="Email not found")

    if payload.subject is not None:
        row.subject = payload.subject.strip()
    if payload.body is not None:
        row.body = payload.body.strip()

    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)

@router.delete("/item/{email_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_email(email_id: int, db: Session = Depends(get_db)):
    row = db.get(Email, email_id)
    if not row:
        raise HTTPException(status_code=404, detail="Email not found")
    db.delete(row)
    db.commit()

class EmailAIEditRequest(BaseModel):
    prompt: str

@router.post("/item/{email_id}/ai-edit", response_model=EmailOut, status_code=status.HTTP_200_OK)
def ai_edit_email(email_id: int, request: EmailAIEditRequest, db: Session = Depends(get_db)):
    row = db.get(Email, email_id)
    if not row:
        raise HTTPException(status_code=404, detail="Email not found")

    # Get prospect data for context
    p = db.get(Prospect, row.prospect_id)
    if not p:
        raise HTTPException(status_code=404, detail="Prospect not found")

    prospect_dict = {
        "company_name": p.company_name,
        "contact_name": p.contact_name,
        "industry": p.industry,
        "revenue_range": p.revenue_range,
        "location": p.location,
        "sale_motivation": p.sale_motivation,
        "signals": p.signals,
    }

    try:
        from ..services.ai import edit_email_content, AIUnavailableError, AIFormatError
        updated_content = edit_email_content(
            current_subject=row.subject,
            current_body=row.body,
            user_prompt=request.prompt,
            prospect=prospect_dict,
            sequence_index=row.sequence_index
        )
    except AIUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except AIFormatError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Update the email
    row.subject = updated_content["subject"]
    row.body = updated_content["body"]
    db.add(row)
    db.commit()
    db.refresh(row)
    
    return _to_out(row)
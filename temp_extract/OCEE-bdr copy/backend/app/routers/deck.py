import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from ..database import get_db
from ..models.prospect import Prospect
from ..models.deck import Deck
from ..schemas.deck import DeckOut, DeckUpdate
from ..services.ai import generate_deck_content, edit_deck_slide_content, AIUnavailableError, AIFormatError
from ..services.pdf import render_deck_to_pdf, TemplateError, RenderError, FileIOError
from ..services.slides import validate_and_normalize_slides, _strip_markup, _truncate
from ..config import settings

router = APIRouter()

@router.post("/{prospect_id}/generate", response_model=DeckOut, status_code=status.HTTP_201_CREATED)
def generate_deck(prospect_id: int, db: Session = Depends(get_db)):
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
        payload = generate_deck_content(prospect_dict)
    except AIUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except AIFormatError as e:
        raise HTTPException(status_code=502, detail=str(e))

    slides = payload["slides"]
    deck_title = payload["deck_title"]

    d = Deck(
        prospect_id=p.id,
        title=deck_title,
        slides_json=json.dumps(slides, ensure_ascii=False),
        pdf_path=None,
    )
    db.add(d)
    db.commit()
    db.refresh(d)

    pdf_url = settings.APP_BASE_URL.rstrip("/") + d.pdf_path if d.pdf_path else None
    return {
        "id": d.id,
        "prospect_id": d.prospect_id,
        "title": d.title,
        "slides": slides,
        "pdf_url": pdf_url,
    }

@router.get("/{deck_id}", response_model=DeckOut, status_code=status.HTTP_200_OK)
def get_deck(deck_id: int, db: Session = Depends(get_db)):
    d = db.get(Deck, deck_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deck not found")
    slides = json.loads(d.slides_json)
    pdf_url = settings.APP_BASE_URL.rstrip("/") + d.pdf_path if d.pdf_path else None
    return {
        "id": d.id,
        "prospect_id": d.prospect_id,
        "title": d.title,
        "slides": slides,
        "pdf_url": pdf_url,
    }

@router.patch("/{deck_id}", response_model=DeckOut, status_code=status.HTTP_200_OK)
def update_deck(deck_id: int, payload: DeckUpdate, db: Session = Depends(get_db)):
    d = db.get(Deck, deck_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deck not found")

    try:
        normalized = validate_and_normalize_slides([s.dict() for s in payload.slides])
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid slide structure: {e}")

    if payload.title:
        title_clean = _truncate(_strip_markup(payload.title), settings.TITLE_MAX_CHARS)
        if title_clean:
            d.title = title_clean

    d.slides_json = json.dumps(normalized, ensure_ascii=False)
    db.add(d)
    db.commit()
    db.refresh(d)

    pdf_url = settings.APP_BASE_URL.rstrip("/") + d.pdf_path if d.pdf_path else None
    return {
        "id": d.id,
        "prospect_id": d.prospect_id,
        "title": d.title,
        "slides": normalized,
        "pdf_url": pdf_url,
    }

@router.post("/{deck_id}/render", response_model=DeckOut, status_code=status.HTTP_200_OK)
def render_deck(deck_id: int, db: Session = Depends(get_db)):
    d = db.get(Deck, deck_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deck not found")

    slides = json.loads(d.slides_json)

    try:
        rel_path = render_deck_to_pdf(slides, d.title)
    except (TemplateError, RenderError, FileIOError) as e:
        raise HTTPException(status_code=500, detail=str(e))

    d.pdf_path = rel_path
    db.add(d)
    db.commit()
    db.refresh(d)

    pdf_url = settings.APP_BASE_URL.rstrip("/") + rel_path
    return {
        "id": d.id,
        "prospect_id": d.prospect_id,
        "title": d.title,
        "slides": slides,
        "pdf_url": pdf_url,
    }

# --------------------------
# New slide-level endpoints
# --------------------------

class SlidePatch(BaseModel):
    title: Optional[str] = None
    bullets: Optional[List[str]] = None

@router.get("/{deck_id}/slides/{index}", status_code=status.HTTP_200_OK)
def get_slide(deck_id: int, index: int, db: Session = Depends(get_db)):
    d = db.get(Deck, deck_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deck not found")
    slides = json.loads(d.slides_json)
    if index < 0 or index >= len(slides):
        raise HTTPException(status_code=404, detail="Slide index out of range")
    return slides[index]

@router.patch("/{deck_id}/slides/{index}", status_code=status.HTTP_200_OK)
def patch_slide(deck_id: int, index: int, patch: SlidePatch, db: Session = Depends(get_db)):
    d = db.get(Deck, deck_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deck not found")

    slides = json.loads(d.slides_json)
    if index < 0 or index >= len(slides):
        raise HTTPException(status_code=404, detail="Slide index out of range")

    slide = slides[index]
    if patch.title is not None:
        slide["title"] = _truncate(_strip_markup(patch.title), settings.TITLE_MAX_CHARS) or slide.get("title") or "Untitled"
    if patch.bullets is not None:
        normalized = validate_and_normalize_slides([{"title": slide["title"], "bullets": patch.bullets}])[0]
        slide.update(normalized)

    slides[index] = slide
    d.slides_json = json.dumps(slides, ensure_ascii=False)
    db.add(d)
    db.commit()
    db.refresh(d)

    pdf_url = settings.APP_BASE_URL.rstrip("/") + (d.pdf_path or "") if d.pdf_path else None
    return {
        "id": d.id,
        "prospect_id": d.prospect_id,
        "title": d.title,
        "slides": slides,
        "pdf_url": pdf_url,
    }

class SlideAIEditRequest(BaseModel):
    prompt: str

@router.post("/{deck_id}/slides/{index}/ai-edit", status_code=status.HTTP_200_OK)
def ai_edit_slide(deck_id: int, index: int, request: SlideAIEditRequest, db: Session = Depends(get_db)):
    d = db.get(Deck, deck_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deck not found")

    slides = json.loads(d.slides_json)
    if index < 0 or index >= len(slides):
        raise HTTPException(status_code=404, detail="Slide index out of range")

    # Get prospect data for context
    p = db.get(Prospect, d.prospect_id)
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
        updated_slide = edit_deck_slide_content(
            current_slide=slides[index],
            user_prompt=request.prompt,
            prospect=prospect_dict,
            slide_index=index
        )
    except AIUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except AIFormatError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Update the slide
    slides[index] = updated_slide
    d.slides_json = json.dumps(slides, ensure_ascii=False)
    db.add(d)
    db.commit()
    db.refresh(d)

    pdf_url = settings.APP_BASE_URL.rstrip("/") + (d.pdf_path or "") if d.pdf_path else None
    return {
        "id": d.id,
        "prospect_id": d.prospect_id,
        "title": d.title,
        "slides": slides,
        "pdf_url": pdf_url,
    }

@router.post("/debug/ai-edit-test", status_code=status.HTTP_200_OK)
def debug_ai_edit_test(request: dict, db: Session = Depends(get_db)):
    """
    Debug endpoint to test AI editing functionality
    """
    try:
        from ..services.ai import edit_deck_slide_content
        
        # Test data
        current_slide = {
            "title": "Market Opportunity",
            "bullets": ["Industry tailwinds drive deal activity", "Consolidation creates seller leverage"]
        }
        
        prospect_dict = {
            "company_name": "Test Company",
            "contact_name": "Test Contact",
            "industry": "Technology",
            "revenue_range": "$10M-$50M",
            "location": "California",
            "sale_motivation": "Retirement",
            "signals": "Growth plateau"
        }
        
        user_prompt = request.get("prompt", "Add more market opportunity information")
        slide_index = request.get("slide_index", 1)
        
        result = edit_deck_slide_content(
            current_slide=current_slide,
            user_prompt=user_prompt,
            prospect=prospect_dict,
            slide_index=slide_index
        )
        
        return {
            "success": True,
            "input": {
                "current_slide": current_slide,
                "user_prompt": user_prompt,
                "slide_index": slide_index
            },
            "output": result
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }

from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, engine

# --- Import models BEFORE create_all so tables are registered ---
from . import models  # Prospect, Deck, Email

app = FastAPI(title="OffDeal BDR Engine API")

# --- CORS ---
origins = settings.ALLOWED_ORIGINS.split(",") if settings.ALLOWED_ORIGINS != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Paths ---
BASE_DIR = os.path.dirname(__file__)                         # .../backend/app
PROJECT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))  # .../backend

# Static (logo, etc.) lives at: backend/static
STATIC_DIR = os.path.abspath(os.path.join(PROJECT_DIR, "static"))
os.makedirs(STATIC_DIR, exist_ok=True)

# Generated PDFs dir: resolve FILE_STORAGE_DIR to absolute
if os.path.isabs(settings.FILE_STORAGE_DIR):
    GENERATED_DIR = settings.FILE_STORAGE_DIR.rstrip("/")
else:
    GENERATED_DIR = os.path.abspath(os.path.join(PROJECT_DIR, settings.FILE_STORAGE_DIR)).rstrip("/")
os.makedirs(GENERATED_DIR, exist_ok=True)

# --- Create tables (after models import) ---
Base.metadata.create_all(bind=engine)

# --- Static mounts ---
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/generated", StaticFiles(directory=GENERATED_DIR), name="generated")

# --- Routers ---
from .routers import prospect as prospect_router
from .routers import deck as deck_router
from .routers import email as email_router

app.include_router(prospect_router.router, prefix="/prospects", tags=["prospects"])
app.include_router(deck_router.router, prefix="/decks", tags=["decks"])
app.include_router(email_router.router, prefix="/emails", tags=["emails"])

# --- Health check ---
@app.get("/healthz", tags=["meta"])
def healthz():
    return {"status": "ok"}

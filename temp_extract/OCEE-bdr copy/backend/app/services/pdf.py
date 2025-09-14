from __future__ import annotations

import os
from typing import List, Dict
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from ..config import settings
from .utils import slugify

# Paths
SERVICES_DIR = os.path.dirname(__file__)                 # .../backend/app/services
APP_DIR = os.path.abspath(os.path.join(SERVICES_DIR, ".."))      # .../backend/app
PROJECT_DIR = os.path.abspath(os.path.join(APP_DIR, ".."))       # .../backend
TEMPLATES_DIR = os.path.join(APP_DIR, "templates")               # .../backend/app/templates
STATIC_DIR = os.path.join(PROJECT_DIR, "static")                 # .../backend/static

class TemplateError(Exception): ...
class RenderError(Exception): ...
class FileIOError(Exception): ...

_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"])
)

def _resolve_generated_dir() -> str:
    # Use absolute path for FILE_STORAGE_DIR (matches what you mounted in main.py)
    if os.path.isabs(settings.FILE_STORAGE_DIR):
        return settings.FILE_STORAGE_DIR.rstrip("/")
    return os.path.abspath(os.path.join(PROJECT_DIR, settings.FILE_STORAGE_DIR)).rstrip("/")

def render_deck_to_pdf(slides: List[Dict], deck_title: str, out_dir: str | None = None) -> str:
    """
    Renders the provided slides into a PDF and writes it to FILE_STORAGE_DIR (or out_dir).
    Returns a relative URL path suitable for building a URL, e.g. '/generated/acme_offdeal.pdf'.
    """
    try:
        tpl = _env.get_template("deck.html")
    except Exception as e:
        raise TemplateError(f"Template not found or invalid: {e!s}")

    html = tpl.render(deck_title=deck_title, slides=slides)

    # Output directory (absolute)
    out_dir = (out_dir or _resolve_generated_dir())
    os.makedirs(out_dir, exist_ok=True)

    # Filename
    base = slugify(deck_title) or "offdeal_pitch"
    filename = f"{base}.pdf"
    abs_path = os.path.join(out_dir, filename)

    try:
        # IMPORTANT: base_url should be a filesystem directory that contains 'static' and template assets
        # so that relative paths like "static/images/offdeal_logo.png" resolve correctly.
        HTML(string=html, base_url=PROJECT_DIR).write_pdf(abs_path)
        # If your template references absolute /static URLs instead, you can also pass base_url=APP_DIR or PROJECT_DIR.
    except Exception as e:
        raise RenderError(f"Failed to render PDF: {e!s}")

    if not os.path.exists(abs_path):
        raise FileIOError("PDF file was not created.")

    # This must match your StaticFiles mount in main.py (app.mount('/generated', ...))
    rel_url_path = f"/generated/{filename}"
    return rel_url_path

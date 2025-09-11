from __future__ import annotations
import re
from typing import Any, Dict, List

SYSTEM_FILE = (
    "You are Provis, an expert software explainer.\n"
    "Given structured metadata about a code file and a small local dependency context, "
    "produce a JSON summary that helps a human edit the code safely. "
    "NO code generation; speak about purpose, where to edit, and risks.\n\n"
    "Return JSON with these exact fields: title, purpose, key_functions, internal_dependencies, "
    "external_dependencies, how_to_modify, risks, blurb, dev_summary, vibecoder_summary, edit_points.\n\n"
    "dev_summary: Terse, developer-facing summary (what it does, interfaces, gotchas).\n"
    "vibecoder_summary: Playful, beginner-friendly explanation using metaphors."
)

SYSTEM_CAPABILITY = (
    "You are Provis, describing end-to-end capabilities across a codebase. "
    "Given an entrypoint and its nearby internal dependencies, explain the flow, "
    "where to edit to extend it, and risks/side-effects. NO code generation."
)

SYSTEM_GLOSSARY = (
    "You are Provis, creating a beginner-friendly glossary for common programming terms. "
    "Use short definitions; also provide a vibecoder definition using metaphors. "
    "No code; keep each definition to 1-2 sentences."
)

FILE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "purpose": {"type": "string"},
        "key_functions": {"type": "array"},
        "internal_dependencies": {"type": "array", "items": {"type": "string"}},
        "external_dependencies": {"type": "array", "items": {"type": "string"}},
        "how_to_modify": {"type": "string"},
        "risks": {"type": "string"},
        "blurb": {"type": "string"},
        "dev_summary": {"type": "string"},
        "vibecoder_summary": {"type": "string"},
        "edit_points": {"type": "array"},
    },
    "required": ["title", "blurb", "dev_summary", "vibecoder_summary"],
    "additionalProperties": False,
}

CAPABILITY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "entrypoint": {"type": "string"},
        "files": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
        "vibecoder_summary": {"type": "string"},
        "edit_points": {"type": "array", "items": {"type": "string"}},
        "impact": {
            "type": "object",
            "properties": {
                "new_internal_edges_example": {"type": "array", "items": {"type": "string"}},
                "hubs_touched": {"type": "array", "items": {"type": "string"}},
                "risks": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["hubs_touched"],
            "additionalProperties": False,
        },
    },
    "required": ["title", "entrypoint", "files", "summary", "vibecoder_summary", "edit_points", "impact"],
    "additionalProperties": False,
}

GLOSSARY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "dev_definition": {"type": "string"},
                    "vibecoder_definition": {"type": "string"},
                },
                "required": ["term", "dev_definition", "vibecoder_definition"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["terms"],
    "additionalProperties": False,
}

def sanitize_for_llm(text: str) -> str:
    """Sanitize text to prevent accidental leakage of secrets to LLM."""
    if not text:
        return text
    
    # Patterns to scrub (case-insensitive)
    secret_patterns = [
        r'(?i)(api[_-]?key|secret|token|password|passwd|pwd)\s*[:=]\s*["\']?[^\s"\']+["\']?',
        r'(?i)(auth[_-]?token|bearer[_-]?token|access[_-]?token)\s*[:=]\s*["\']?[^\s"\']+["\']?',
        r'(?i)(private[_-]?key|public[_-]?key)\s*[:=]\s*["\']?[^\s"\']+["\']?',
        r'(?i)(database[_-]?url|db[_-]?url|connection[_-]?string)\s*[:=]\s*["\']?[^\s"\']+["\']?',
        r'(?i)(redis[_-]?url|mongodb[_-]?url)\s*[:=]\s*["\']?[^\s"\']+["\']?',
    ]
    
    sanitized = text
    for pattern in secret_patterns:
        sanitized = re.sub(pattern, r'\1=***REDACTED***', sanitized)
    
    return sanitized

def file_messages(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Sanitize context to prevent secret leakage
    sanitized_context = sanitize_for_llm(str(context))
    return [
        {"role": "system", "content": SYSTEM_FILE},
        {"role": "user", "content": f"Produce strict JSON per schema.\nContext:\n{sanitized_context}"},
    ]

def capability_messages(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Sanitize context to prevent secret leakage
    sanitized_context = sanitize_for_llm(str(context))
    return [
        {"role": "system", "content": SYSTEM_CAPABILITY},
        {"role": "user", "content": f"Produce strict JSON per schema.\nContext:\n{sanitized_context}"},
    ]

def glossary_messages(base_terms: list[str]) -> List[Dict[str, Any]]:
    terms_txt = ", ".join(base_terms)
    # Sanitize terms to prevent secret leakage
    sanitized_terms = sanitize_for_llm(terms_txt)
    return [
        {"role": "system", "content": SYSTEM_GLOSSARY},
        {"role": "user", "content": f"Create a glossary for these terms: {sanitized_terms}. Return strict JSON."},
    ]

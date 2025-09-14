from __future__ import annotations

import json
import logging
from typing import Any, Dict, List
from ..config import settings

logger = logging.getLogger(__name__)

class EmailAIUnavailableError(Exception): ...
class EmailAIFormatError(Exception): ...

EMAIL_SCHEMA = [
    {"sequence_index": 1, "key": "email1"},
    {"sequence_index": 2, "key": "email2"},
    {"sequence_index": 3, "key": "email3"},
]

PROMPT_TEMPLATE = """You are an expert sales copywriter for OffDeal, the world’s first AI-native investment bank for small businesses ($5M–$100M revenue).
Write a personalized 3-email outbound sequence to a business owner considering a sale. PERSONALIZATION IS REQUIRED—use Prospect Data to influence tone, examples, hooks, and specifics. Avoid generic filler.

Use (and may enhance) THIS EXACT STRUCTURE AND ORDER:

Email 1 – Introduction (Outcomes + Process Framing)
Subject: Sell [Company Name] for more, in less time
Hi [First Name],
When you decide it’s time to sell [Company Name], the two things that matter most are how much you get and how fast you get it.
That’s exactly what OffDeal was built for. We’re not a traditional broker—we’re the first AI-native investment bank for small businesses. That means:
Stronger outcomes – on average, our clients see offers 30% higher.
Faster sales – most deals receive offers in under 45 days.
Aligned incentives – no upfront fees; we only succeed when you do.
We act as your broker and partner—handling buyer outreach, negotiations, and positioning so that the market sees the full value of what you’ve built.
I’ve attached a short 5-slide deck that walks through the process of selling [Company Name] with OffDeal—step by step.
Would you be open to a quick conversation about what the right sale could look like for you?
Best,
[Your Name]
OffDeal

Email 2 – Case Study (Proof + Process in Action)
Subject: What selling your business could look like in practice
Hi [First Name],
To give you a sense of how the process works, let me share a recent example.
An HVAC owner we worked with had the same questions most founders do: Who are the right buyers? How long will it take? Will the offers reflect the real value of what I built?
We walked him through each stage:
Positioning the story of the business so buyers saw more than just the numbers.
Creating buyer demand through our national network.
Driving competition so offers came in quickly—and at higher valuations.
Within 16 days, he had multiple offers, and the winning bid came in 30% above what brokers had told him was possible.
That’s what the process looks like when OffDeal acts as your broker—step by step, keeping you in control while we handle the market.
Would you be open to exploring what those steps could look like for [Company Name]?
Best,
[Your Name]
OffDeal

Email 3 – Follow-Up (Urgency + Differentiation)
Subject: Don’t leave money on the table when selling [Company Name]
Hi [First Name],
By the time most small business owners start talking to buyers, they’ve already lost leverage. A single buyer sets the tone, and the process drags out, usually ending in a lower offer than the business deserves.
That’s the trap we help owners avoid. With OffDeal, the process looks very different:
Multiple buyers competing from day one → offers arrive fast, and at stronger valuations.
AI + banker support → we automate 80% of the grunt work so our team can focus on strategy and negotiations.
Aligned incentives → no upfront fees; our success is tied to your sale outcome.
This isn’t theory—we’ve seen owners walk away with 30% higher offers and sales closed in under 45 days.
If you’re considering a sale, even a quick call now could mean the difference between a single underwhelming offer and a competitive process that puts you in control.
Would you be open to a short conversation this week?
Best,
[Your Name]
OffDeal

Rules:
- Personalize with Prospect Data (company name, first name, industry, revenue range, location, sale motivation, signals).
- Subjects should include the company name where shown.
- Keep tone concise, professional, and confident.
- Replace [Company Name] and [First Name] with values from Prospect Data. If missing, infer a neutral placeholder.
- You may tweak language to better fit the Prospect Data, but keep each email’s intent.
- Return a JSON object with exactly: email1, email2, email3.
- Each email key maps to { "sequence_index": <1-3>, "subject": "<str>", "body": "<str>" }.
Prospect Data:
{prospect_json}
"""

def _openai_json_response(prompt: str) -> Dict[str, Any]:
    if settings.STUB_MODE:
        return _stub_response(prompt)

    try:
        from openai import OpenAI
    except Exception as e:
        raise EmailAIUnavailableError(f"OpenAI SDK not available: {e!s}")

    if not settings.OPENAI_API_KEY:
        raise EmailAIUnavailableError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        logger.info("Email AI raw: %s", raw)
        return json.loads(raw)
    except Exception as e:
        raise EmailAIUnavailableError(f"OpenAI call failed: {e!s}")

def _stub_response(prompt: str) -> Dict[str, Any]:
    # very basic deterministic stub
    return {
        "email1": {
            "sequence_index": 1,
            "subject": "Sell {{company}} for more, in less time",
            "body": "Hi {{first}},\nOffDeal drives higher offers faster. No upfront fees..."
        },
        "email2": {
            "sequence_index": 2,
            "subject": "What selling {{company}} looks like in practice",
            "body": "Hi {{first}},\nRecent example: HVAC owner had multiple offers in 16 days..."
        },
        "email3": {
            "sequence_index": 3,
            "subject": "Don’t leave money on the table at {{company}}",
            "body": "Hi {{first}},\nMost owners lose leverage with a single buyer. OffDeal prevents that..."
        },
    }

def _coalesce(v, default=""):
    return v if isinstance(v, str) and v.strip() else default

def generate_emails(prospect: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Build prompt with prospect data
    p = {
        "company_name": _coalesce(prospect.get("company_name"), "your company"),
        "contact_name": _coalesce(prospect.get("contact_name"), "there"),
        "industry": _coalesce(prospect.get("industry")),
        "revenue_range": _coalesce(prospect.get("revenue_range")),
        "location": _coalesce(prospect.get("location")),
        "sale_motivation": _coalesce(prospect.get("sale_motivation")),
        "signals": _coalesce(prospect.get("signals")),
    }
    prompt = PROMPT_TEMPLATE.replace("{prospect_json}", json.dumps(p, ensure_ascii=False))

    obj = _openai_json_response(prompt)

    # Normalize to exactly three items in correct order
    items: List[Dict[str, Any]] = []
    for spec in EMAIL_SCHEMA:
        node = obj.get(spec["key"]) or {}
        seq = spec["sequence_index"]
        subject = (node.get("subject") or "").strip()
        body = (node.get("body") or "").strip()
        if not subject or not body:
            raise EmailAIFormatError(f"Missing subject/body for email {seq}")
        items.append({
            "sequence_index": seq,
            "subject": subject,
            "body": body
        })
    return items

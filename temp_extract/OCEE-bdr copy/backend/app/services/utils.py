import re
import unicodedata
from datetime import datetime

def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "_", value)

def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

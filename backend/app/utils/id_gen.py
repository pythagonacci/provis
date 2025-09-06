import secrets

def short_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"

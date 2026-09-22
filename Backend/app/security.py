"""
Small helpers used everywhere a secret could otherwise leak: API responses,
log lines, error messages stored in the database, etc. 
"""
import hmac


def redact(value: str | None, keep: int = 2) -> str:
    """Return a short, non-reversible stand-in for a secret, safe to log."""
    if not value:
        return "<empty>"
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * (len(value) - keep * 2)}{value[-keep:]}"


def constant_time_equals(a: str, b: str) -> bool:
    """Timing-safe comparison, used to check the incoming webhook secret."""
    return hmac.compare_digest(a or "", b or "")

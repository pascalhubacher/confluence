"""
Confluence Cloud HTTP client.

Handles configuration, authentication, rate limiting, and raw HTTP requests
against the Confluence REST API v2.

Authentication:
    Basic Auth  — set CONFLUENCE_EMAIL + CONFLUENCE_API_TOKEN
    Bearer token — set CONFLUENCE_BEARER_TOKEN

Required environment variable:
    CONFLUENCE_BASE_URL  e.g. https://your-domain.atlassian.net
"""

from __future__ import annotations

import base64
import os
import time
import threading
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("CONFLUENCE_BASE_URL", "").rstrip("/")
EMAIL = os.getenv("CONFLUENCE_EMAIL", "")
API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN", "")
BEARER_TOKEN = os.getenv("CONFLUENCE_BEARER_TOKEN", "")

# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------


def validate_config() -> None:
    """Raise ValueError if required environment variables are missing."""
    if not BASE_URL:
        raise ValueError(
            "CONFLUENCE_BASE_URL is not set. "
            "Set it to your Atlassian Cloud domain, e.g. https://your-domain.atlassian.net"
        )
    if not BEARER_TOKEN and not (EMAIL and API_TOKEN):
        raise ValueError(
            "No Confluence credentials configured. "
            "Set CONFLUENCE_BEARER_TOKEN, or both CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN."
        )


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------

_VALID_BODY_REPRESENTATIONS = {"storage", "wiki", "atlas_doc_format"}
_VALID_PAGE_STATUSES = {"current", "draft", "archived", "trashed", "deleted"}
_VALID_SPACE_TYPES = {"global", "personal"}
_VALID_SPACE_STATUSES = {"current", "archived"}
_VALID_TASK_STATUSES = {"open", "complete", "incomplete"}


def require_str(value: str, name: str) -> None:
    """Raise ValueError if a required string parameter is empty."""
    if not value or not value.strip():
        raise ValueError(f"'{name}' must be a non-empty string.")


def check_enum(value: Optional[str], name: str, valid: set[str]) -> None:
    """Raise ValueError if value is set but not in the allowed set."""
    if value is not None and value not in valid:
        raise ValueError(f"'{name}' must be one of {sorted(valid)!r}, got {value!r}.")


# ---------------------------------------------------------------------------
# Rate limiter (token-bucket, max 10 req/s)
# ---------------------------------------------------------------------------

_RATE_LIMIT_RPS: float = 10.0  # requests per second
_rate_lock = threading.Lock()
_rate_tokens: float = _RATE_LIMIT_RPS
_rate_last: float = time.monotonic()


def _rate_limit() -> None:
    """Block until a request token is available (token-bucket, 10 req/s)."""
    global _rate_tokens, _rate_last
    with _rate_lock:
        now = time.monotonic()
        elapsed = now - _rate_last
        _rate_last = now
        _rate_tokens = min(_RATE_LIMIT_RPS, _rate_tokens + elapsed * _RATE_LIMIT_RPS)
        if _rate_tokens < 1.0:
            sleep_for = (1.0 - _rate_tokens) / _RATE_LIMIT_RPS
            time.sleep(sleep_for)
            _rate_tokens = 0.0
        else:
            _rate_tokens -= 1.0


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _get_headers() -> dict[str, str]:
    """Return Authorization headers based on configured credentials."""
    if BEARER_TOKEN:
        return {
            "Authorization": f"Bearer {BEARER_TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    if EMAIL and API_TOKEN:
        token = base64.b64encode(f"{EMAIL}:{API_TOKEN}".encode()).decode()
        return {
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    return {"Accept": "application/json", "Content-Type": "application/json"}


def v2(path: str) -> str:
    """Build a Confluence REST API v2 URL."""
    return f"{BASE_URL}/wiki/api/v2{path}"


def v1(path: str) -> str:
    """Build a Confluence REST API v1 URL."""
    return f"{BASE_URL}/wiki/rest/api{path}"


def clean(params: dict[str, Any]) -> dict[str, Any]:
    """Remove None values from a params dict."""
    return {k: v for k, v in params.items() if v is not None}


def request(
    method: str,
    url: str,
    *,
    params: Optional[dict[str, Any]] = None,
    json: Optional[dict[str, Any]] = None,
) -> Any:
    """Synchronous HTTP request; raises on 4xx/5xx."""
    _rate_limit()
    with httpx.Client(timeout=30) as client:
        resp = client.request(
            method,
            url,
            headers=_get_headers(),
            params=clean(params or {}),
            json=json,
        )
        resp.raise_for_status()
        return (
            resp.json()
            if resp.content
            else {"status": resp.status_code, "message": "Success"}
        )

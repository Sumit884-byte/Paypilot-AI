"""In-memory live score + last request, used by webhooks and GET /score/live."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

LIVE_SCORES: dict[str, dict[str, Any]] = {}


def record_score(applicant_id: str, request: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "applicant_id": applicant_id,
        "request": request,
        "score": response,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "live": True,
    }
    LIVE_SCORES[applicant_id] = entry
    return entry

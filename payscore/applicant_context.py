"""Load synthetic persona inputs for the copilot. Live score requests win when present."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from .live_state import LIVE_SCORES

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "personas"


@lru_cache(maxsize=1)
def _personas() -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for path in FIXTURES.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        loaded[str(data.get("persona_id"))] = data
        applicant = (data.get("model_input") or {}).get("applicant_id")
        if applicant:
            loaded[str(applicant)] = data
    return loaded


def persona_for(applicant_id: str) -> Optional[dict[str, Any]]:
    return _personas().get(applicant_id)


def application_for(applicant_id: str) -> tuple[Optional[dict[str, Any]], str]:
    live = LIVE_SCORES.get(applicant_id)
    if live and isinstance(live.get("request"), dict):
        return live["request"], "last_score_request"
    persona = persona_for(applicant_id)
    if persona and isinstance(persona.get("model_input"), dict):
        return persona["model_input"], "synthetic_persona_fixture"
    return None, "not_found"


def revenues_for_applicant(applicant_id: str) -> Optional[tuple[list[float], str]]:
    persona = persona_for(applicant_id)
    if not persona:
        return None
    rows = persona.get("monthly_summary")
    if not isinstance(rows, list) or not rows:
        return None
    values = []
    for row in rows:
        if not isinstance(row, dict) or "net_revenue_inr" not in row:
            return None
        values.append(float(row["net_revenue_inr"]))
    return values, "synthetic_persona_monthly_summary"

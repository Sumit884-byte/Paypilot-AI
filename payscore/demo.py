"""Demo persona payload for the frontend walkthrough."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["demo"])
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "personas"


@router.get("/demo/persona/{name}", summary="Persona narrative + model_input for demo mode", response_model=None)
def persona(name: str) -> dict | JSONResponse:
    path = FIXTURES / f"{name}.json"
    if not path.is_file():
        return JSONResponse(status_code=404, content={"error": "unknown_persona"})
    data = json.loads(path.read_text(encoding="utf-8"))
    txns = [
        {
            "txn_id": row.get("txn_id"),
            "date": row.get("date"),
            "type": row.get("type"),
            "amount_inr": row.get("amount_inr"),
            "category": row.get("category"),
            "status": row.get("status"),
        }
        for row in data.get("transactions", [])[-40:]
    ]
    return {
        "persona_id": data["persona_id"],
        "display_name": data["display_name"],
        "profile": data.get("profile"),
        "scenario": data.get("scenario"),
        "monthly_summary": data.get("monthly_summary"),
        "model_input": data["model_input"],
        "recent_transactions": txns,
        "synthetic": True,
    }

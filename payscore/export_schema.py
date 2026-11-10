"""Write JSON Schemas to schema/ (request schema from the pydantic model; persona schema around it).

    python -m payscore.export_schema
"""

from __future__ import annotations

import json
from pathlib import Path

from .schema import ScoreRequest

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
_TXN_TYPES = ["sale", "refund", "dispute", "expense"]


def request_schema() -> dict:
    return ScoreRequest.model_json_schema()


def persona_schema() -> dict:
    req = request_schema()
    defs = req.pop("$defs", {})
    req.pop("examples", None)
    month = {"type": "string", "pattern": r"^\d{4}-(0[1-9]|1[0-2])$"}
    date_ = {"type": "string", "format": "date", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
    num = {"type": "number", "minimum": 0}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://payscore.example/schema/persona.schema.json",
        "title": "PayScore synthetic persona fixture",
        "description": "Entirely fictional persona. model_input is a valid POST /score body.",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "persona_id", "display_name", "synthetic", "currency", "as_of_date",
                     "profile", "scenario", "monthly_summary", "transactions", "model_input"],
        "properties": {
            "schema_version": {"const": "1.0"},
            "persona_id": {"type": "string", "pattern": r"^PSC-[A-Z0-9\-]+$"},
            "display_name": {"type": "string", "minLength": 1},
            "synthetic": {"const": True},
            "currency": {"const": "INR"},
            "as_of_date": date_,
            "profile": {
                "type": "object", "additionalProperties": False,
                "required": ["city", "business_type", "description", "business_start_date", "age_years",
                             "employment_type", "income_note"],
                "properties": {
                    "city": {"type": "string"}, "business_type": {"type": "string"},
                    "description": {"type": "string", "minLength": 20}, "business_start_date": date_,
                    "age_years": {"type": "integer", "minimum": 18},
                    "employment_type": {"$ref": "#/$defs/EmploymentType"}, "income_note": {"type": "string"},
                },
            },
            "scenario": {
                "type": "object", "additionalProperties": False,
                "required": ["headline", "loan_purpose", "requested_amount_inr", "requested_term_months", "narrative"],
                "properties": {
                    "headline": {"type": "string"}, "loan_purpose": {"type": "string"},
                    "requested_amount_inr": {"type": "number", "exclusiveMinimum": 0},
                    "requested_term_months": {"type": "integer", "minimum": 1},
                    "narrative": {"type": "string", "minLength": 40},
                },
            },
            "monthly_summary": {
                "type": "array", "minItems": 6,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["month", "sales_inr", "refunds_inr", "net_revenue_inr", "expenses_inr", "sale_count"],
                    "properties": {"month": month, "sales_inr": num, "refunds_inr": num, "net_revenue_inr": num,
                                   "expenses_inr": num, "sale_count": {"type": "integer", "minimum": 0}},
                },
            },
            "transactions": {
                "type": "array", "minItems": 1,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["txn_id", "date", "type", "direction", "amount_inr", "category", "status"],
                    "properties": {
                        "txn_id": {"type": "string", "pattern": r"^SYN-[A-Z0-9\-]+-\d{5}$"},
                        "date": date_, "type": {"enum": _TXN_TYPES},
                        "direction": {"enum": ["inflow", "outflow"]},
                        "amount_inr": {"type": "number", "exclusiveMinimum": 0},
                        "category": {"type": "string"}, "status": {"type": "string"},
                    },
                },
            },
            "model_input": {"$ref": "#/$defs/ScoreRequest"},
        },
        "$defs": {**defs, "ScoreRequest": req},
    }


def main() -> None:
    SCHEMA_DIR.mkdir(exist_ok=True)
    (SCHEMA_DIR / "score_request.schema.json").write_text(json.dumps(request_schema(), indent=2) + "\n", encoding="utf-8")
    (SCHEMA_DIR / "persona.schema.json").write_text(json.dumps(persona_schema(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote schemas to {SCHEMA_DIR}")


if __name__ == "__main__":
    main()

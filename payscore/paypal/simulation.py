"""Simulated PayPal mode, so the app works end to end before anyone adds sandbox credentials.

When PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET are missing, the payout, subscription, and checkout endpoints answer with
clearly labelled simulated results ("simulated": true, ids starting with "SIM-") instead of a 503. No PayPal API is
called. The same checks still apply first: a score is required, the amount must be within the approved limit.

PAYSCORE_PAYPAL_SIMULATION:
  auto (default)  simulate only when credentials are missing; real sandbox calls once they are set
  off             never simulate; endpoints return 503 paypal_not_configured without credentials
"""

from __future__ import annotations

import os
import uuid

SIMULATION_NOTICE = (
    "Simulated: PayPal sandbox credentials are not configured, so no PayPal API was called and no money moved. "
    "Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to use the real PayPal sandbox."
)


def simulation_enabled() -> bool:
    return os.getenv("PAYSCORE_PAYPAL_SIMULATION", "auto").strip().lower() not in {"off", "false", "0", "no"}


def simulated_id(kind: str) -> str:
    return f"SIM-{kind}-{uuid.uuid4().hex[:12].upper()}"


def is_simulated(record_id: str) -> bool:
    return str(record_id).startswith("SIM-")


def labelled(payload: dict) -> dict:
    """Mark a response as simulated, keeping its normal shape so clients need no special handling."""
    return {**payload, "simulated": True, "simulation_notice": SIMULATION_NOTICE}

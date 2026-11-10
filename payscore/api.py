"""FastAPI app. Run: uvicorn payscore.api:app --port 8000

Environment variables (see .env.example):
  PAYSCORE_MODEL_DIR       directory with model artifacts (default: ./models)
  PAYSCORE_ALLOW_FALLBACK  "true" (default) | "false"  -> use labelled dev fallback if no model
  PAYSCORE_CORS_ORIGINS    comma-separated allowed origins (default: localhost:3000, localhost:5173)
                           use "*" only deliberately; empty string disables CORS.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from the repo root (PayPal credentials etc.) before anything reads os.getenv.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .affordability import router as affordability_router
from .copilot import router as copilot_router
from .counterfactual import router as counterfactual_router
from .demo import router as demo_router
from .explain import router as explain_router
from .income_passport import router as income_passport_router
from .live_state import LIVE_SCORES, record_score
from .model import DEFAULT_MODEL_DIR, ModelUnavailableError, Scorer
from .model_card import router as model_card_router
from .negotiation import router as negotiation_router
from .offer_guard import router as offer_guard_router
from .pay_later import router as pay_later_router
from .paypal.advance import router as advance_router
from .paypal.disbursements import record_approval
from .paypal.disbursements import router as disbursements_router
from .paypal.repayment import router as repayment_router
from .paypal.repayment import webhook_router as paypal_webhook_router
from .paypal.routes import income_router
from .paypal.routes import router as paypal_router
from .revenue_volatility import router as revenue_router
from .schema import ErrorResponse, ScoreRequest, ScoreResponse

log = logging.getLogger("payscore")
DEFAULT_CORS = "http://localhost:3000,http://localhost:5173"

# Simple in-memory rate limiter for money-moving endpoints
_rate_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 10     # requests per window


def _check_rate_limit(key: str) -> bool:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    requests = _rate_store.get(key, [])
    # Clean old entries
    _rate_store[key] = [t for t in requests if t > window_start]
    if len(_rate_store[key]) >= RATE_LIMIT_MAX:
        return False
    _rate_store[key].append(now)
    return True


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def create_app(
    model_dir: Optional[Path | str] = None,
    allow_fallback: Optional[bool] = None,
    cors_origins: Optional[str] = None,
) -> FastAPI:
    model_dir = model_dir or os.getenv("PAYSCORE_MODEL_DIR") or DEFAULT_MODEL_DIR
    allow_fallback = _env_bool("PAYSCORE_ALLOW_FALLBACK", True) if allow_fallback is None else allow_fallback
    cors_raw = os.getenv("PAYSCORE_CORS_ORIGINS", DEFAULT_CORS) if cors_origins is None else cors_origins
    origins = [o.strip() for o in cors_raw.split(",") if o.strip()]

    scorer = Scorer.from_dir(model_dir, allow_fallback=allow_fallback)  # raises on corrupt artifacts
    if scorer.trained is None:
        log.warning("No trained model in %s: %s", model_dir,
                    "using DEVELOPMENT FALLBACK" if allow_fallback else "scoring disabled (503)")

    app = FastAPI(
        title="PayScore AI API",
        version=__version__,
        description="Early scoring, PayPal income profile, and sandbox-only disbursement demo. "
                    "Scores and fixture profiles are for development/demo only; payouts never target live PayPal.",
    )
    app.state.scorer = scorer
    app.include_router(paypal_router)
    app.include_router(income_router)
    app.include_router(disbursements_router)
    app.include_router(repayment_router)
    app.include_router(paypal_webhook_router)
    app.include_router(advance_router)
    app.include_router(offer_guard_router)
    app.include_router(pay_later_router)
    app.include_router(copilot_router)
    app.include_router(explain_router)
    app.include_router(counterfactual_router)
    app.include_router(affordability_router)
    app.include_router(revenue_router)
    app.include_router(demo_router)
    app.include_router(model_card_router)
    app.include_router(income_passport_router)
    app.include_router(negotiation_router)
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                           allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type"])

    # Rate-limit middleware for money-moving endpoints
    MONEY_PATHS = {"/disburse", "/repayment/subscription", "/repayment/order",
                   "/repayment/revenue-share", "/advance", "/paypal/webhook"}

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if request.method == "POST" and request.url.path in MONEY_PATHS:
            client_host = request.client.host if request.client else "unknown"
            key = f"{client_host}:{request.url.path}"
            if not _check_rate_limit(key):
                return JSONResponse(status_code=429,
                    content={"error": "rate_limit_exceeded",
                             "message": "Too many requests on this endpoint. Please slow down.",
                             "sandbox": True, "disclaimer": "Sandbox demo — no real lending."})
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        detail = [{"field": ".".join(str(p) for p in e["loc"][1:]) or "body", "message": e["msg"], "type": e["type"]}
                  for e in exc.errors()]  # inputs are deliberately not echoed back
        return JSONResponse(status_code=422, content={"error": "validation_error", "detail": detail})

    @app.get("/", summary="API information")
    def root() -> dict:
        return {"name": "PayScore AI API", "version": __version__, "docs": "/docs", "openapi": "/openapi.json",
                "endpoints": {"health": "GET /health", "score": "POST /score", "paypal_status": "GET /paypal/status",
                              "paypal_login": "GET /paypal/auth/login", "income_profile": "GET /income-profile",
                              "paypal_public_config": "GET /paypal/public-config",
                              "disburse": "POST /disburse", "disburse_status": "GET /disburse/{batch_id}",
                              "fixed_emi": "POST /repayment/subscription", "one_off_emi": "POST /repayment/order",
                              "revenue_share": "POST /repayment/revenue-share", "paypal_webhook": "POST /paypal/webhook",
                              "score_live": "GET /score/live", "advance": "POST /advance",
                              "offer_guard": "POST /offer-guard", "offer_guard_upload": "POST /offer-guard/upload",
                              "pay_later_compare": "POST /offer-guard/pay-later",
                              "copilot": "POST /copilot/chat", "explain": "POST /explain",
                              "counterfactuals": "POST /counterfactuals", "affordability": "POST /affordability",
                              "revenue_volatility": "POST /revenue-volatility",
                              "model_card": "GET /model-card",
                              "model_card_evaluation": "GET /model-card/evaluation",
                              "income_passport": "POST /income-passport",
                              "verify_income_passport": "GET /api/verify/income-passport/{token}",
                              "negotiate_start": "POST /negotiate/start",
                              "negotiate_respond": "POST /negotiate/respond"}}

    @app.get("/health", summary="Health check")
    def health() -> dict:
        info = app.state.scorer.model_info()
        return {"status": "ok", "model_loaded": app.state.scorer.trained is not None,
                "development_fallback_active": app.state.scorer.trained is None and app.state.scorer.allow_fallback,
                "model_type": info["type"], "model_version": info["version"], "api_version": __version__}

    @app.post("/score", response_model=ScoreResponse,
              responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
              summary="Score a normalised applicant record")
    def score(req: ScoreRequest) -> dict | JSONResponse:
        try:
            result = app.state.scorer.score(req)
            record_approval(req.applicant_id, result, req.requested_loan_amount_inr)
            record_score(req.applicant_id, req.model_dump(mode="json"), result)
            return result
        except ModelUnavailableError as exc:
            return JSONResponse(status_code=503, content={"error": "model_unavailable", "detail": str(exc)})

    @app.get("/score/live", summary="Latest stored score for polling after webhooks", response_model=None)
    def score_live(applicant_id: str) -> dict | JSONResponse:
        entry = LIVE_SCORES.get(applicant_id)
        if not entry:
            return JSONResponse(status_code=404, content={"error": "score_not_found",
                                 "detail": "POST /score first so the live endpoint has a snapshot."})
        return {**entry["score"], "updated_at": entry["updated_at"], "live": True}

    return app


app = create_app()

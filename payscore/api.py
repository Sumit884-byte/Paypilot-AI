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
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .model import DEFAULT_MODEL_DIR, ModelUnavailableError, Scorer
from .schema import ErrorResponse, ScoreRequest, ScoreResponse

log = logging.getLogger("payscore")
DEFAULT_CORS = "http://localhost:3000,http://localhost:5173"


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
        description="Early scoring endpoint on mock/normalised input. No PayPal calls are made; "
                    "no money is moved. Scores are for development/demo only.",
    )
    app.state.scorer = scorer
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                           allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type"])

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        detail = [{"field": ".".join(str(p) for p in e["loc"][1:]) or "body", "message": e["msg"], "type": e["type"]}
                  for e in exc.errors()]  # inputs are deliberately not echoed back
        return JSONResponse(status_code=422, content={"error": "validation_error", "detail": detail})

    @app.get("/", summary="API information")
    def root() -> dict:
        return {"name": "PayScore AI API", "version": __version__, "docs": "/docs", "openapi": "/openapi.json",
                "endpoints": {"health": "GET /health", "score": "POST /score"}}

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
            return app.state.scorer.score(req)
        except ModelUnavailableError as exc:
            return JSONResponse(status_code=503, content={"error": "model_unavailable", "detail": str(exc)})

    return app


app = create_app()

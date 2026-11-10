"""FastAPI router for the PayPal (sandbox) integration. Mounted under /paypal in payscore.api.

Endpoints:
  GET /paypal/status  credential/health check: attempts a sandbox OAuth2 token and reports
                      the outcome. Secrets are never echoed back — only the client id's
                      last 4 characters, as required for debugging Render deploys.
"""

from __future__ import annotations

import logging
import base64
import hashlib
import os
import time
from urllib.parse import urlencode
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .client import PayPalClient, PayPalError
from . import linked_accounts
from .income import paypal_profile, fixture_profile

from ..disputes import DisputeDraftRequest, draft_response, list_open_chargebacks

log = logging.getLogger("payscore.paypal")
router = APIRouter(prefix="/paypal", tags=["paypal"])
income_router = APIRouter(tags=["income profile"])
LOGIN_BASE = "https://www.sandbox.paypal.com/connect/"
LOGIN_SCOPES = "openid https://uri.paypal.com/services/reporting/search/read " \
               "https://uri.paypal.com/services/disputes/read-seller " \
               "https://uri.paypal.com/services/invoicing"  # service-root form is what sandbox apps register


def paypal_client() -> Optional[PayPalClient]:
    """Dependency: builds a client from the environment; None when credentials are missing."""
    try:
        return PayPalClient()
    except PayPalError:
        return None


ClientDep = Annotated[Optional[PayPalClient], Depends(paypal_client)]


def _masked(client_id: str) -> str:
    return f"…{client_id[-4:]}" if len(client_id) >= 4 else "…"


def _disputes_account_id(applicant_id: str) -> str:
    """Resolve the PayPal account used to look up open disputes.

    When a PayPal account is linked, disputes belong to that linked account's
    paypal_account_id; otherwise fall back to the applicant id. Both the list and
    draft endpoints resolve it the same way so drafting a dispute from a linked
    account's list cannot 404 on a mismatched lookup.
    """
    account_id = linked_accounts.ACTIVE_ACCOUNT_ID
    account = linked_accounts.LINKED_ACCOUNTS.get(account_id) if account_id else None
    paypal_account_id = account.get("paypal_account_id") if account else None
    return str(paypal_account_id or applicant_id)


@router.get("/status", response_model=None, summary="PayPal sandbox credential check")
async def status(client: ClientDep) -> dict | JSONResponse:
    if client is None:
        return JSONResponse(status_code=503, content={
            "paypal": "unavailable", "code": "not_configured",
            "detail": "Missing required environment variables PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET (see .env.example)"})
    try:
        async with client:
            await client.verify_credentials()
    except PayPalError as exc:
        detail = str(exc)
        code = "not_configured" if "environment variable" in detail else "token_unavailable"
        return JSONResponse(status_code=503, content={"paypal": "unavailable", "code": code, "detail": detail})
    return {
        "paypal": "ok",
        "mode": "sandbox",
        "api_base": client.api_base,
        "client_id": _masked(client.client_id),
    }


@router.get("/public-config", response_model=None, summary="PayPal browser-safe public configuration")
async def public_config() -> dict | JSONResponse:
    """Return the public client ID needed to initialize the PayPal JS SDK v6."""
    client_id = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    if not client_id:
        return JSONResponse(status_code=503, content={"error": "paypal_not_configured"})
    return {"client_id": client_id, "mode": "sandbox"}


@router.get("/auth/consent", response_class=HTMLResponse, include_in_schema=True)
async def consent() -> str:
    """Readable disclosure linked from the PayPal authorization screen."""
    return """<!doctype html><html><head><title>PayScore data use</title></head><body>
<main><h1>What PayScore reads from PayPal</h1>
<p>PayScore uses your permission to build an income profile for your application.</p>
<ul><li>PayPal account identifier, only to link your account</li>
<li>Payment amount, currency, date, status, event type, and payer account identifier, for the last 12 months</li>
<li>Refund amounts and dates, for the last 12 months</li>
<li>Dispute dates, for the last 12 months</li>
<li>Outstanding invoice status, amount due, and currency</li></ul>
<p>PayScore returns aggregate income, monthly income, distinct client count, refund and dispute rates,
longest gap between payments, income trend, and outstanding invoice totals. It does not return payer identities.</p>
<p><a href="/paypal/auth/login">Continue to PayPal</a></p></main></body></html>"""


@router.get("/auth/login", summary="Link a PayPal account")
async def auth_login(request: Request) -> RedirectResponse:
    if not os.getenv("PAYPAL_CLIENT_ID", "").strip():
        return RedirectResponse("/paypal/status", status_code=303)
    redirect_uri = os.getenv("PAYPAL_OAUTH_REDIRECT_URI", str(request.url_for("auth_callback")))
    state, verifier = linked_accounts.new_attempt()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    params = {"flowEntry": "static", "client_id": os.environ["PAYPAL_CLIENT_ID"],
              "response_type": "code", "scope": LOGIN_SCOPES, "redirect_uri": redirect_uri,
              "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
    return RedirectResponse(f"{LOGIN_BASE}?{urlencode(params)}", status_code=302)


def _wants_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "").lower()


def _frontend_redirect(path: str) -> RedirectResponse | None:
    origin = os.getenv("PAYSCORE_FRONTEND_URL", "").strip().rstrip("/")
    if not origin:
        return None
    return RedirectResponse(f"{origin}{path}", status_code=303)


def _callback_error(request: Request, error: str, status: int) -> JSONResponse | RedirectResponse:
    html = _frontend_redirect(f"/auth/callback?error={error}") if _wants_html(request) else None
    return html or JSONResponse(status_code=status, content={"error": error})


@router.get("/auth/callback", name="auth_callback", summary="Complete PayPal account linking", response_model=None)
async def auth_callback(request: Request, code: str | None = None, state: str | None = None,
                        error: str | None = None, client: ClientDep = None) -> dict | JSONResponse | RedirectResponse:
    if error:
        return _callback_error(request, "paypal_authorization_denied", 400)
    verifier = linked_accounts.consume_attempt(state or "")
    if not code or verifier is None:
        return _callback_error(request, "invalid_or_expired_oauth_state", 400)
    if client is None:
        return _callback_error(request, "paypal_not_configured", 503)
    redirect_uri = os.getenv("PAYPAL_OAUTH_REDIRECT_URI", str(request.url_for("auth_callback")))
    try:
        tokens = await client.exchange_authorization_code(code, redirect_uri, verifier)
        user = await client.get_user_info(tokens["access_token"])
        user_id = user.get("user_id") or user.get("payer_id") or user.get("sub")
        if not user_id:
            return _callback_error(request, "paypal_identity_missing", 502)
        linked_accounts.store_account(str(user_id), tokens)
    except (PayPalError, KeyError) as exc:
        log.warning("PayPal account linking failed: %s", exc)
        return _callback_error(request, "paypal_account_link_failed", 502)
    finally:
        await client.aclose()
    if _wants_html(request):
        html = _frontend_redirect("/auth/callback?linked=true")
        if html:
            return html
    return {"linked": True}


@income_router.get("/income-profile", summary="Get an aggregate 12-month income profile", response_model=None)
async def income_profile(persona: str = Query(default="priya", pattern="^(priya|arjun|rohan)$"),
                         client: ClientDep = None) -> dict | JSONResponse:
    account_id = linked_accounts.ACTIVE_ACCOUNT_ID
    account = linked_accounts.LINKED_ACCOUNTS.get(account_id) if account_id else None
    if not account:
        return fixture_profile(persona)
    if client is None:
        return JSONResponse(status_code=503, content={"error": "paypal_not_configured"})
    try:
        async with client:
            expires_in = int(account.get("expires_in") or 0)
            age = time.time() - float(account.get("stored_at") or 0)
            if expires_in and age >= max(0, expires_in - 60):
                refresh_token = account.get("refresh_token")
                if not refresh_token:
                    return JSONResponse(status_code=401, content={"error": "paypal_reauthorization_required"})
                tokens = await client.refresh_authorization_token(refresh_token)
                linked_accounts.update_tokens(account_id, tokens)
                account = linked_accounts.LINKED_ACCOUNTS[account_id]
            return await paypal_profile(client, account["access_token"])
    except PayPalError as exc:
        log.warning("Income profile fetch failed: %s — falling back to fixture data for %s", exc, persona)
        return fixture_profile(persona)


@router.get("/disputes/{applicant_id}", summary="List open chargebacks/disputes for an applicant")
def list_disputes(applicant_id: str) -> dict:
    return list_open_chargebacks(_disputes_account_id(applicant_id))


@router.post("/disputes/draft", response_model=None,
             summary="Draft a borrower-protective response to an open dispute")
async def draft_dispute(request: Request) -> dict | JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid_json"})
    try:
        req = DisputeDraftRequest.model_validate(body)
    except Exception as exc:  # validation errors surface as a clear 422
        return JSONResponse(status_code=422, content={"error": "validation_error", "detail": str(exc)})
    disputes_payload = list_open_chargebacks(_disputes_account_id(req.applicant_id))
    dispute = next(
        (d for d in disputes_payload.get("disputes", []) if str(d.get("dispute_id")) == req.dispute_id),
        None,
    )
    if dispute is None:
        return JSONResponse(status_code=404, content={"error": "dispute_not_found"})
    return draft_response(dispute, req.applicant_id)


def mount(app, client_factory: Optional[callable] = None) -> None:
    """Include the PayPal router; tests pass a client_factory to swap the credential source."""
    if client_factory is not None:
        router.dependency_overrides[paypal_client] = client_factory
    app.include_router(router)
    app.include_router(income_router)

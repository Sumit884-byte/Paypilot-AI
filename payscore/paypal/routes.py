"""FastAPI router for the PayPal (sandbox) integration. Mounted under /paypal in payscore.api.

Endpoints:
  GET /paypal/status  credential/health check: attempts a sandbox OAuth2 token and reports
                      the outcome. Secrets are never echoed back — only the client id's
                      last 4 characters, as required for debugging Render deploys.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from typing import Annotated, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ..disputes import DisputeDraftRequest, draft_response, list_open_chargebacks
from . import linked_accounts, session_cookie
from .client import PayPalClient, PayPalError
from .income import fixture_profile, paypal_profile
from .simulation import simulation_enabled

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


def _disputes_account_id(request: Request, applicant_id: str) -> str:
    """Resolve the PayPal account used to look up open disputes.

    When a PayPal account is linked, disputes belong to that linked account's
    paypal_account_id; otherwise fall back to the applicant id. Both the list and
    draft endpoints resolve it the same way so drafting a dispute from a linked
    account's list cannot 404 on a mismatched lookup.
    """
    account_id = linked_account_id(request)
    account = linked_accounts.LINKED_ACCOUNTS.get(account_id) if account_id else None
    paypal_account_id = account.get("paypal_account_id") if account else None
    return str(paypal_account_id or applicant_id)


@router.get("/status", response_model=None, summary="PayPal sandbox credential check")
async def status(client: ClientDep) -> dict | JSONResponse:
    if client is None:
        return JSONResponse(status_code=503, content={
            "paypal": "unavailable", "code": "not_configured",
            "detail": "Missing required environment variables PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET (see .env.example)",
            "simulation": simulation_enabled()})
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
    response = RedirectResponse(f"{LOGIN_BASE}?{urlencode(params)}", status_code=302)
    # Server memory is per instance on serverless hosts; the browser carries the attempt to whichever one gets the callback
    session_cookie.save_oauth_attempt(response, request, state, verifier)
    return response


# PayPal's dashboard can refuse return URLs that contain the word "paypal", so the same handler is also served at a
# neutral path. Register https://<host>/oauth/callback and set PAYPAL_OAUTH_REDIRECT_URI to it.
oauth_router = APIRouter(tags=["paypal"])


def _id_token_subject(id_token: str | None) -> str | None:
    """The `sub` claim of the OpenID Connect ID token from the code exchange.

    The token came straight from PayPal's token endpoint over TLS, authenticated with our client secret, which
    OpenID Connect Core 3.1.3.7 accepts in place of a signature check. Using it avoids the userinfo endpoint, which
    answers "400 Unable to fetch details" when the app shares no profile attributes.
    """
    if not id_token or id_token.count(".") != 2:
        return None
    try:
        payload = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, json.JSONDecodeError):
        return None
    subject = claims.get("sub") if isinstance(claims, dict) else None
    return str(subject) if subject else None


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


@oauth_router.get("/oauth/callback", name="oauth_callback", summary="Complete PayPal account linking",
                  response_model=None)
@router.get("/auth/callback", name="auth_callback", summary="Complete PayPal account linking", response_model=None)
async def auth_callback(request: Request, code: str | None = None, state: str | None = None,
                        error: str | None = None, client: ClientDep = None) -> dict | JSONResponse | RedirectResponse:
    if error:
        return _callback_error(request, "paypal_authorization_denied", 400)
    verifier = linked_accounts.consume_attempt(state or "") or session_cookie.oauth_verifier(request, state or "")
    if not code or verifier is None:
        return _callback_error(request, "invalid_or_expired_oauth_state", 400)
    if client is None:
        return _callback_error(request, "paypal_not_configured", 503)
    redirect_uri = os.getenv("PAYPAL_OAUTH_REDIRECT_URI", str(request.url_for("auth_callback")))
    try:
        tokens = await client.exchange_authorization_code(code, redirect_uri, verifier)
        # Field names and scope names only, never token values
        log.info("PayPal token response fields: %s; scopes: %s", sorted(tokens), tokens.get("scope", "(none listed)"))
        user_id = _id_token_subject(tokens.get("id_token"))
        if not user_id:
            try:
                user = await client.get_user_info(tokens["access_token"])
                user_id = user.get("user_id") or user.get("payer_id") or user.get("sub")
            except PayPalError as exc:
                # The identity is only a label for the stored tokens; data access uses the access token. PayPal
                # answers "400 Unable to fetch details" when the app shares no profile attributes, so link anyway
                # under an unconfirmed label rather than failing a sign-in that PayPal itself accepted.
                if exc.status not in (400, 401, 403, 404):
                    raise
                log.warning("PayPal identity unavailable (%s); linking under an unconfirmed account label", exc.status)
                user_id = f"unconfirmed-{secrets.token_hex(8)}"
        if not user_id:
            return _callback_error(request, "paypal_identity_missing", 502)
        linked_accounts.store_account(str(user_id), tokens)
    except (PayPalError, KeyError) as exc:
        log.warning("PayPal account linking failed: %s", exc)
        return _callback_error(request, "paypal_account_link_failed", 502)
    finally:
        await client.aclose()
    response: JSONResponse | RedirectResponse = JSONResponse({"linked": True})
    if _wants_html(request):
        response = _frontend_redirect("/auth/callback?linked=true") or response
    session_cookie.save_linked_account(response, request, str(user_id), tokens)
    session_cookie.clear(response, session_cookie.OAUTH_COOKIE)
    return response


@router.get("/link", summary="Whether this browser has a linked PayPal account (never returns tokens)")
def link_status(request: Request) -> dict:
    account = session_cookie.linked_account(request)
    return {"linked": bool(account), "identity_confirmed": bool(account) and
            not str(account.get("user_id", "")).startswith("unconfirmed-")}


@router.post("/unlink", summary="Forget this browser's linked PayPal account")
def unlink(request: Request, response: Response) -> dict:
    account = session_cookie.linked_account(request)
    if account:
        linked_accounts.LINKED_ACCOUNTS.pop(str(account.get("user_id")), None)
    session_cookie.clear(response, session_cookie.LINK_COOKIE)
    return {"linked": False}


class LinkedProfileError(Exception):
    """The browser has a linked PayPal account, but its data could not be loaded."""

    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


def linked_account_id(request: Request) -> Optional[str]:
    """The PayPal account linked to this browser, or None.

    Only the browser's own encrypted link cookie says which account it is. A process-wide "last linked account" would
    hand one visitor's PayPal data to every other visitor of the same server instance.
    """
    cookie_account = session_cookie.linked_account(request)
    return str(cookie_account["user_id"]) if cookie_account else None


async def load_linked_profile(request: Request, response: Response, client: Optional[PayPalClient]) -> Optional[dict]:
    """The 12-month PayPal income profile of this browser's linked account; None when nothing is linked.

    Shared by the income profile, linked scoring, and the copilot so every screen reads the same account.
    Raises LinkedProfileError when an account is linked but PayPal cannot be asked, and PayPalError when PayPal fails.
    """
    account = session_cookie.linked_account(request)
    if not account:
        return None
    account_id = account["user_id"]
    if client is None:
        raise LinkedProfileError(503, "paypal_not_configured")
    async with client:
        expires_in = int(account.get("expires_in") or 0)
        age = time.time() - float(account.get("stored_at") or 0)
        if expires_in and age >= max(0, expires_in - 60):
            refresh_token = account.get("refresh_token")
            if not refresh_token:
                raise LinkedProfileError(401, "paypal_reauthorization_required")
            tokens = await client.refresh_authorization_token(refresh_token)
            tokens = {**tokens, "refresh_token": tokens.get("refresh_token", refresh_token)}
            session_cookie.save_linked_account(response, request, str(account_id), tokens)
            account = {**account, **tokens}
        return await paypal_profile(client, account["access_token"])


@income_router.get("/income-profile", summary="Get an aggregate 12-month income profile", response_model=None)
async def income_profile(request: Request, response: Response,
                         persona: str = Query(default="priya", pattern="^(priya|arjun|rohan)$"),
                         client: ClientDep = None) -> dict | JSONResponse:
    try:
        profile = await load_linked_profile(request, response, client)
    except LinkedProfileError as exc:
        return JSONResponse(status_code=exc.status, content={"error": exc.code})
    except PayPalError as exc:
        log.warning("Income profile fetch failed: %s — falling back to fixture data for %s", exc, persona)
        return fixture_profile(persona)
    return profile if profile is not None else fixture_profile(persona)


@router.get("/disputes/{applicant_id}", summary="List open chargebacks/disputes for an applicant")
def list_disputes(applicant_id: str, request: Request) -> dict:
    return list_open_chargebacks(_disputes_account_id(request, applicant_id))


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
    disputes_payload = list_open_chargebacks(_disputes_account_id(request, req.applicant_id))
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

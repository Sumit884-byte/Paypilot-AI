"""In-process OAuth state and linked account store for the demo deployment."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass


@dataclass
class OAuthAttempt:
    verifier: str
    created_at: float


OAUTH_ATTEMPTS: dict[str, OAuthAttempt] = {}
LINKED_ACCOUNTS: dict[str, dict] = {}
ACTIVE_ACCOUNT_ID: str | None = None
STATE_TTL_SECONDS = 600


def new_attempt() -> tuple[str, str]:
    now = time.time()
    for state, attempt in list(OAUTH_ATTEMPTS.items()):
        if now - attempt.created_at > STATE_TTL_SECONDS:
            OAUTH_ATTEMPTS.pop(state, None)
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    OAUTH_ATTEMPTS[state] = OAuthAttempt(verifier, now)
    return state, verifier


def consume_attempt(state: str) -> str | None:
    attempt = OAUTH_ATTEMPTS.pop(state, None)
    if attempt is None or time.time() - attempt.created_at > STATE_TTL_SECONDS:
        return None
    return attempt.verifier


def store_account(user_id: str, tokens: dict) -> None:
    global ACTIVE_ACCOUNT_ID
    LINKED_ACCOUNTS[user_id] = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "expires_in": tokens.get("expires_in"),
        "stored_at": time.time(),
    }
    ACTIVE_ACCOUNT_ID = user_id


def update_tokens(user_id: str, tokens: dict) -> None:
    account = LINKED_ACCOUNTS[user_id]
    account.update({"access_token": tokens["access_token"],
                    "refresh_token": tokens.get("refresh_token", account.get("refresh_token")),
                    "expires_in": tokens.get("expires_in"), "stored_at": time.time()})

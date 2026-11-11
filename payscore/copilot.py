"""Copilot route. Money actions always require explicit approval."""

from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from .copilot_agent import DISCLAIMER, LinkedContext, _envelope, handle_chat
from .paypal.client import PayPalError
from .paypal.routes import ClientDep, LinkedProfileError, load_linked_profile

log = logging.getLogger("payscore.copilot")
router = APIRouter(tags=["copilot"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    applicant_id: str = Field(default="PSC-PRIYA-001")
    # "linked": answer from this browser's linked PayPal account, never from a demo persona
    mode: Literal["demo", "linked"] = "demo"
    # The linked user's own PayScore request (from POST /score/linked). Sent back by the browser because serverless
    # instances share no memory; the server re-validates it and scores it again, so it cannot smuggle in a result.
    application: Optional[dict[str, Any]] = None


async def _linked_context(req: ChatRequest, request: Request, response: Response, client) -> LinkedContext | dict:
    try:
        profile = await load_linked_profile(request, response, client)
    except LinkedProfileError as exc:
        if exc.code == "paypal_reauthorization_required":
            return _envelope("Your PayPal sign-in has expired. Log in with PayPal again and ask me once more.",
                             [{"label": "paypal.profile", "status": "reauthorize"}])
        return _envelope("PayPal is not configured on this server, so I cannot read your account.",
                         [{"label": "paypal.profile", "status": "unavailable"}])
    except PayPalError as exc:
        log.warning("Copilot could not load the linked PayPal profile: %s", exc)
        return _envelope("PayPal did not answer just now, so I have nothing real to work from. "
                         "I did not fall back to example data. Try again in a moment.",
                         [{"label": "paypal.profile", "status": "error"}])
    if profile is None:
        return _envelope("This browser no longer has a linked PayPal account. Log in with PayPal again to ask about "
                         "your own data.", [{"label": "paypal.profile", "status": "not_linked"}])
    return LinkedContext(profile=profile, application=req.application)


@router.post("/copilot/chat", summary="Copilot turn. Tools calculate; payouts stay behind approval.")
async def chat(req: ChatRequest, request: Request, response: Response, client: ClientDep = None) -> dict:
    linked = None
    if req.mode == "linked":
        context = await _linked_context(req, request, response, client)
        if isinstance(context, dict):
            context["disclaimer"] = DISCLAIMER
            return context
        linked = context
    result = handle_chat(req.message, req.applicant_id, request.app.state.scorer, linked=linked)
    result["disclaimer"] = DISCLAIMER
    return result

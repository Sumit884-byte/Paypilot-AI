"""Copilot route. Money actions always require explicit approval."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from .copilot_agent import DISCLAIMER, handle_chat

router = APIRouter(tags=["copilot"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    applicant_id: str = Field(default="PSC-PRIYA-001")


@router.post("/copilot/chat", summary="Copilot turn. Tools calculate; payouts stay behind approval.")
def chat(req: ChatRequest, request: Request) -> dict:
    result = handle_chat(req.message, req.applicant_id, request.app.state.scorer)
    result["disclaimer"] = DISCLAIMER
    return result

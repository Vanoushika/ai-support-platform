from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


TicketStatus = Literal["open", "in_progress", "resolved"]


class TicketCreate(BaseModel):
    title: str = Field(min_length=5, max_length=150)
    description: str = Field(min_length=10, max_length=5000)


class TicketResponse(TicketCreate):
    id: UUID
    status: TicketStatus
    created_at: datetime


class TicketStatusUpdate(BaseModel):
    status: TicketStatus


class RetrievedSource(BaseModel):
    filename: str
    article_id: str
    content: str
    similarity: float


class TicketDraftResponse(BaseModel):
    ticket_id: UUID
    draft: str
    sources: list[RetrievedSource]
    review_warnings: list[str]
    requires_review: Literal[True] = True
    context_used: bool = True
    grounding_verified: Literal[False] = False
    draft_strategy: Literal["generated", "revised", "fallback"] = "generated"
    generation_attempts: int = Field(default=1, ge=0, le=2)

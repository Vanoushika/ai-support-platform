from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException
from starlette.concurrency import run_in_threadpool

from ai_service import draft_ticket_response
from database import get_connection, initialize_database
from routing_workflow import (
    get_saved_routing,
    initialize_routing,
    route_ticket,
)
from schemas import (
    TicketCreate,
    TicketDraftResponse,
    TicketResponse,
    TicketStatusUpdate,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    initialize_routing()
    yield


app = FastAPI(
    title="AI Support Platform",
    lifespan=lifespan,
)


def find_ticket(ticket_id: UUID) -> TicketResponse:
    connection = get_connection()

    try:
        row = connection.execute(
            "SELECT * FROM tickets WHERE id = ?",
            (str(ticket_id),),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found",
        )

    return TicketResponse(**dict(row))


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/tickets/validate")
def validate_ticket(ticket: TicketCreate):
    return {
        "message": "Ticket data is valid",
        "ticket": ticket.model_dump(),
    }


@app.post("/tickets", response_model=TicketResponse, status_code=201)
def create_ticket(ticket: TicketCreate):
    new_ticket = TicketResponse(
        **ticket.model_dump(),
        id=uuid4(),
        status="open",
        created_at=datetime.now(timezone.utc),
    )

    connection = get_connection()

    try:
        with connection:
            connection.execute(
                """
                INSERT INTO tickets (
                    id, title, description, status, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(new_ticket.id),
                    new_ticket.title,
                    new_ticket.description,
                    new_ticket.status,
                    new_ticket.created_at.isoformat(),
                ),
            )
    finally:
        connection.close()

    return new_ticket


@app.get("/tickets", response_model=list[TicketResponse])
def list_tickets():
    connection = get_connection()

    try:
        rows = connection.execute(
            "SELECT * FROM tickets ORDER BY created_at DESC"
        ).fetchall()
    finally:
        connection.close()

    return [TicketResponse(**dict(row)) for row in rows]


@app.get(
    "/tickets/{ticket_id}",
    response_model=TicketResponse,
    responses={404: {"description": "Ticket not found"}},
)
def get_ticket(ticket_id: UUID):
    return find_ticket(ticket_id)


@app.patch(
    "/tickets/{ticket_id}/status",
    response_model=TicketResponse,
    responses={404: {"description": "Ticket not found"}},
)
def update_ticket_status(ticket_id: UUID, update: TicketStatusUpdate):
    connection = get_connection()

    try:
        with connection:
            result = connection.execute(
                "UPDATE tickets SET status = ? WHERE id = ?",
                (update.status, str(ticket_id)),
            )

            if result.rowcount == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Ticket not found",
                )

            row = connection.execute(
                "SELECT * FROM tickets WHERE id = ?",
                (str(ticket_id),),
            ).fetchone()
    finally:
        connection.close()

    return TicketResponse(**dict(row))


@app.post(
    "/tickets/{ticket_id}/draft",
    response_model=TicketDraftResponse,
    responses={
        404: {"description": "Ticket not found"},
        502: {"description": "AI service returned an invalid response"},
        503: {"description": "Ollama is unavailable"},
        504: {"description": "AI request timed out"},
    },
)
async def generate_ticket_draft(ticket_id: UUID):
    ticket = await run_in_threadpool(find_ticket, ticket_id)

    try:
        result = await draft_ticket_response(
            ticket.title,
            ticket.description,
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="The AI model took too long. Please try again.",
        ) from exc
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to Ollama. Make sure it is running.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail="Ollama could not process the request.",
        ) from exc
    except (httpx.RequestError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not retrieve documents or generate a valid draft.",
        ) from exc

    return TicketDraftResponse(
        ticket_id=ticket.id,
        **result,
    )


@app.post(
    "/tickets/{ticket_id}/route",
    responses={404: {"description": "Ticket not found"}},
)
async def run_ticket_routing(ticket_id: UUID):
    ticket = await run_in_threadpool(find_ticket, ticket_id)

    return await route_ticket(
        ticket_id=str(ticket.id),
        title=ticket.title,
        description=ticket.description,
    )


@app.get(
    "/tickets/{ticket_id}/routing",
    responses={404: {"description": "Ticket or routing decision not found"}},
)
def read_ticket_routing(ticket_id: UUID):
    find_ticket(ticket_id)
    decision = get_saved_routing(str(ticket_id))

    if decision is None:
        raise HTTPException(
            status_code=404,
            detail="This ticket has not been routed yet.",
        )

    return decision
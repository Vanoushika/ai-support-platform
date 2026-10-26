import asyncio
import json

from temporalio import activity
from temporalio.exceptions import ApplicationError

from ai_service import draft_ticket_response
from database import get_connection, initialize_database
from routing_workflow import initialize_routing, route_ticket


def initialize_review_storage():
    initialize_database()
    initialize_routing()

    connection = get_connection()

    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS draft_reviews (
                    workflow_id TEXT PRIMARY KEY,
                    ticket_id TEXT NOT NULL,
                    prepared_data TEXT NOT NULL,
                    decision TEXT
                )
                """
            )
    finally:
        connection.close()


def load_prepared(workflow_id: str) -> dict | None:
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT prepared_data
            FROM draft_reviews
            WHERE workflow_id = ?
            """,
            (workflow_id,),
        ).fetchone()
    finally:
        connection.close()

    return json.loads(row["prepared_data"]) if row else None


def load_ticket(ticket_id: str) -> dict:
    connection = get_connection()

    try:
        row = connection.execute(
            "SELECT * FROM tickets WHERE id = ?",
            (ticket_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise ApplicationError(
            "Ticket not found",
            non_retryable=True,
        )

    return dict(row)


def save_prepared(
    workflow_id: str,
    ticket_id: str,
    prepared: dict,
) -> dict:
    connection = get_connection()

    try:
        with connection:
            # Keep the first saved draft if an activity is retried.
            connection.execute(
                """
                INSERT INTO draft_reviews (
                    workflow_id, ticket_id, prepared_data
                )
                VALUES (?, ?, ?)
                ON CONFLICT(workflow_id) DO NOTHING
                """,
                (
                    workflow_id,
                    ticket_id,
                    json.dumps(prepared),
                ),
            )

            row = connection.execute(
                """
                SELECT prepared_data
                FROM draft_reviews
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            ).fetchone()
    finally:
        connection.close()

    return json.loads(row["prepared_data"])


def save_decision(workflow_id: str, decision: str) -> dict:
    if decision not in {"approved", "rejected"}:
        raise ApplicationError(
            "Invalid review decision",
            non_retryable=True,
        )

    connection = get_connection()

    try:
        with connection:
            row = connection.execute(
                """
                SELECT decision
                FROM draft_reviews
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            ).fetchone()

            if row is None:
                raise ApplicationError(
                    "Saved draft not found",
                    non_retryable=True,
                )

            if row["decision"] not in {None, decision}:
                raise ApplicationError(
                    "A different decision has already been recorded",
                    non_retryable=True,
                )

            connection.execute(
                """
                UPDATE draft_reviews
                SET decision = ?
                WHERE workflow_id = ?
                """,
                (decision, workflow_id),
            )
    finally:
        connection.close()

    return {
        "workflow_id": workflow_id,
        "decision": decision,
        "reply_sent": False,
        "ticket_resolved": False,
    }


@activity.defn
async def prepare_ticket_review(ticket_id: str) -> dict:
    workflow_id = activity.info().workflow_id

    cached = await asyncio.to_thread(load_prepared, workflow_id)

    if cached is not None:
        return cached

    ticket = await asyncio.to_thread(load_ticket, ticket_id)

    routing = await route_ticket(
        ticket_id=ticket_id,
        title=ticket["title"],
        description=ticket["description"],
    )

    draft = await draft_ticket_response(
        title=ticket["title"],
        description=ticket["description"],
    )

    prepared = {
        "ticket": ticket,
        "routing": routing,
        "draft": draft,
    }

    return await asyncio.to_thread(
        save_prepared,
        workflow_id,
        ticket_id,
        prepared,
    )


@activity.defn
async def record_review_decision(decision: str) -> dict:
    return await asyncio.to_thread(
        save_decision,
        activity.info().workflow_id,
        decision,
    )
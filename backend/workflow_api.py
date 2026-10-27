import asyncio

from settings import TEMPORAL_ADDRESS
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from temporalio.client import (
    Client,
    WorkflowExecutionStatus,
    WorkflowUpdateFailedError,
)
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from main import find_ticket

router = APIRouter(tags=["Workflow review"])

TASK_QUEUE = "support-ticket-review"


class ReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]


def workflow_id_for(ticket_id: UUID) -> str:
    return f"ticket-review-{ticket_id}"


@asynccontextmanager
async def temporal_errors():
    try:
        yield
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                "Temporal did not respond in time. Check that its server "
                "and worker are running. Refresh workflow status before "
                "retrying a start or review request."
            ),
        ) from exc
    except WorkflowUpdateFailedError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "The review could not be accepted. The workflow may "
                "already have a decision or may not be awaiting review."
            ),
        ) from exc
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            raise HTTPException(
                status_code=404,
                detail="Workflow not found or no longer available.",
            ) from exc

        raise HTTPException(
            status_code=503,
            detail=(
                "Temporal could not complete this request. "
                "Check its server and worker, then refresh workflow status."
            ),
        ) from exc


async def connect_temporal() -> Client:
    try:
        return await asyncio.wait_for(
            Client.connect(TEMPORAL_ADDRESS),
            timeout=5,
        )
    except (TimeoutError, RuntimeError, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to the Temporal server on port 7233.",
        ) from exc


@router.post("/tickets/{ticket_id}/workflow", status_code=202)
async def start_ticket_workflow(ticket_id: UUID):
    await run_in_threadpool(find_ticket, ticket_id)

    async with temporal_errors():
        client = await connect_temporal()
        workflow_id = workflow_id_for(ticket_id)

        try:
            await asyncio.wait_for(
                client.start_workflow(
                    "TicketReviewWorkflow",
                    str(ticket_id),
                    id=workflow_id,
                    task_queue=TASK_QUEUE,
                    id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                ),
                timeout=15,
            )

            return {
                "workflow_id": workflow_id,
                "started": True,
                "message": "Workflow started. Check status for progress.",
            }

        except WorkflowAlreadyStartedError:
            return {
                "workflow_id": workflow_id,
                "started": False,
                "message": "A workflow already exists for this ticket.",
            }


@router.get("/tickets/{ticket_id}/workflow")
async def get_ticket_workflow(ticket_id: UUID):
    await run_in_threadpool(find_ticket, ticket_id)

    async with temporal_errors():
        client = await connect_temporal()
        workflow_id = workflow_id_for(ticket_id)
        handle = client.get_workflow_handle(workflow_id)

        description = await asyncio.wait_for(
            handle.describe(),
            timeout=15,
        )

        if description.status == WorkflowExecutionStatus.COMPLETED:
            result = await asyncio.wait_for(
                handle.result(),
                timeout=15,
            )

        elif description.status == WorkflowExecutionStatus.RUNNING:
            result = await asyncio.wait_for(
                handle.query("status"),
                timeout=15,
            )

        else:
            result = {
                "phase": description.status.name.lower(),
                "prepared": None,
                "decision": None,
                "outcome": None,
            }

        return {
            "workflow_id": workflow_id,
            "execution_status": description.status.name.lower(),
            **result,
        }


@router.post("/tickets/{ticket_id}/workflow/review")
async def review_ticket_workflow(
    ticket_id: UUID,
    body: ReviewRequest,
):
    await run_in_threadpool(find_ticket, ticket_id)

    async with temporal_errors():
        client = await connect_temporal()
        handle = client.get_workflow_handle(
            workflow_id_for(ticket_id)
        )

        description = await asyncio.wait_for(
            handle.describe(),
            timeout=15,
        )

        if description.status != WorkflowExecutionStatus.RUNNING:
            raise HTTPException(
                status_code=409,
                detail="This workflow is no longer running.",
            )

        result = await asyncio.wait_for(
            handle.execute_update("review", body.decision),
            timeout=30,
        )

        return {
            **result,
            "message": (
                "Review accepted. Refresh status to confirm persistence. "
                "No reply or refund has been sent."
            ),
        }

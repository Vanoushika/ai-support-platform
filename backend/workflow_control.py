import argparse
import asyncio

from settings import TEMPORAL_ADDRESS
import json
from datetime import timedelta
from uuid import UUID

from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

TASK_QUEUE = "support-ticket-review"


async def main():
    parser = argparse.ArgumentParser(
        description="Start, inspect, or review a ticket workflow."
    )

    parser.add_argument(
        "command",
        choices=["start", "status", "approve", "reject"],
    )
    parser.add_argument("ticket_id")

    args = parser.parse_args()
    ticket_id = str(UUID(args.ticket_id))
    workflow_id = f"ticket-review-{ticket_id}"

    client = await Client.connect(TEMPORAL_ADDRESS)

    if args.command == "start":
        try:
            await client.start_workflow(
                "TicketReviewWorkflow",
                ticket_id,
                id=workflow_id,
                task_queue=TASK_QUEUE,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            )

            print(f"Started: {workflow_id}")
            print("Run the status command to inspect progress.")

        except WorkflowAlreadyStartedError:
            print("A workflow already exists for this ticket.")
            print("Use status to inspect it.")

        return

    handle = client.get_workflow_handle(workflow_id)

    if args.command == "status":
        description = await handle.describe()

        if description.status == WorkflowExecutionStatus.COMPLETED:
            result = await handle.result()
        elif description.status == WorkflowExecutionStatus.RUNNING:
            result = await handle.query(
                "status",
                rpc_timeout=timedelta(seconds=15),
            )
        else:
            result = {
                "workflow_id": workflow_id,
                "execution_status": description.status.name,
                "message": "Inspect the Temporal dashboard for details.",
            }

        print(json.dumps(result, indent=2))
        return

    decision = (
        "approved" if args.command == "approve" else "rejected"
    )

    result = await handle.execute_update(
        "review",
        decision,
        rpc_timeout=timedelta(seconds=30),
    )

    print(json.dumps(result, indent=2))
    print("Decision accepted. Run status to confirm it was saved.")
    print("No customer reply or refund has been sent.")


if __name__ == "__main__":
    asyncio.run(main())

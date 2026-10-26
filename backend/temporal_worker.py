import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from support_activities import (
    initialize_review_storage,
    prepare_ticket_review,
    record_review_decision,
)
from support_workflow import TicketReviewWorkflow

TASK_QUEUE = "support-ticket-review"


async def main():
    initialize_review_storage()

    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[TicketReviewWorkflow],
        activities=[
            prepare_ticket_review,
            record_review_decision,
        ],
        max_concurrent_activities=1,
    )

    print(
        "Support worker ready. Waiting for workflows...",
        flush=True,
    )

    await worker.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
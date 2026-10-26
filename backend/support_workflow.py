from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError


@workflow.defn
class TicketReviewWorkflow:
    def __init__(self):
        self.phase = "starting"
        self.prepared = None
        self.decision = None
        self.outcome = None

    @workflow.run
    async def run(self, ticket_id: str) -> dict:
        self.phase = "preparing"

        try:
            self.prepared = await workflow.execute_activity(
                "prepare_ticket_review",
                ticket_id,
                start_to_close_timeout=timedelta(minutes=12),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=5),
                    maximum_interval=timedelta(seconds=30),
                    maximum_attempts=3,
                ),
            )

            self.phase = "awaiting_review"

            await workflow.wait_condition(
                lambda: self.decision is not None
            )

            self.phase = "recording_decision"

            self.outcome = await workflow.execute_activity(
                "record_review_decision",
                self.decision,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                ),
            )

            self.phase = "completed"
            return self.status()

        except ActivityError:
            self.phase = "failed"
            raise

    @workflow.query
    def status(self) -> dict:
        return {
            "phase": self.phase,
            "prepared": self.prepared,
            "decision": self.decision,
            "outcome": self.outcome,
        }

    @workflow.update
    def review(self, decision: str) -> dict:
        self.decision = decision

        return {
            "accepted": True,
            "decision": decision,
        }

    @review.validator
    def validate_review(self, decision: str):
        if decision not in {"approved", "rejected"}:
            raise ValueError("Choose approved or rejected.")

        if self.phase != "awaiting_review":
            raise ValueError("This workflow is not awaiting review.")

        if self.decision is not None:
            raise ValueError("A review decision was already accepted.")
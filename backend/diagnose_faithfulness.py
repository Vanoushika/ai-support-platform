import asyncio
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import Faithfulness

from evaluate_project import JUDGE_SETTINGS, MODEL_NAME, package_version

BASE_DIR = Path(__file__).resolve().parent
SOURCE_REPORT = (
    BASE_DIR
    / "evaluation_reports"
    / "20261026T174729231783Z.json"
)
CASE_ID = "password_second_attempt"


class TracedFaithfulness(Faithfulness):
    """Capture intermediate results without changing RAGAS scoring."""

    def __init__(self, llm):
        super().__init__(llm=llm)
        self.trace = {
            "extracted_statements": [],
            "verdicts": [],
        }

    async def _create_statements(self, question, response):
        statements = await super()._create_statements(question, response)
        self.trace["extracted_statements"] = list(statements)

        print("\nEXTRACTED CLAIMS", flush=True)
        for index, statement in enumerate(statements, start=1):
            print(f"{index}. {statement}", flush=True)

        return statements

    async def _create_verdicts(self, statements, context):
        result = await super()._create_verdicts(statements, context)

        self.trace["verdicts"] = [
            item.model_dump(mode="json")
            for item in result.statements
        ]

        print("\nJUDGE VERDICTS", flush=True)
        print(
            json.dumps(self.trace["verdicts"], indent=2),
            flush=True,
        )

        return result


async def main():
    original = json.loads(SOURCE_REPORT.read_text(encoding="utf-8"))
    case = next(
        (item for item in original["results"] if item["id"] == CASE_ID),
        None,
    )
    if case is None:
        raise ValueError(f"Case not found: {CASE_ID}")

    contexts = [source["content"] for source in case["sources"]]

    diagnostic = {
        "evaluation_scope": "ticket_and_document_grounding",
        "comparison_note": (
            "Different evidence scope from document-only RAGAS faithfulness. "
            "Do not merge these scores into the original benchmark."
        ),
        "case_id": CASE_ID,
        "source_report": str(SOURCE_REPORT),
        "judge_model": MODEL_NAME,
        "judge_settings": JUDGE_SETTINGS,
        "ragas_version": package_version("ragas"),
        "title": case["title"],
        "description": case["description"],
        "draft": case["draft"],
        "retrieved_contexts": contexts,
        "previous_faithfulness": case["faithfulness"],
        "faithfulness": None,
        "trace": {},
        "error": None,
    }

    print("CASE:", CASE_ID, flush=True)
    print("DRAFT:", case["draft"], flush=True)
    print("\nRunning claim extraction and judging...", flush=True)

    async with AsyncOpenAI(
        base_url="http://127.0.0.1:11434/v1",
        api_key="ollama",
        timeout=120,
        max_retries=0,
    ) as client:
        evaluator = llm_factory(
            MODEL_NAME,
            provider="openai",
            client=client,
            **JUDGE_SETTINGS,
        )
        scorer = TracedFaithfulness(llm=evaluator)

        try:
            score = await asyncio.wait_for(
                scorer.ascore(
                    user_input=f"{case['title']}\n{case['description']}",
                    response=case["draft"],
                    retrieved_contexts=contexts + [
                        "CUSTOMER-REPORTED INFORMATION — not independently "
                        "verified account facts. This supports statements "
                        "about what the customer reports, not proof of "
                        "payment, identity, or completed backend actions.\n"
                        + case["title"] + "\n" + case["description"]
                    ],
                ),
                timeout=360,
            )

            value = float(score.value)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"Invalid score: {value}")

            diagnostic["faithfulness"] = value

        except Exception as exc:
            diagnostic["error"] = f"{type(exc).__name__}: {exc}"

        finally:
            diagnostic["trace"] = scorer.trace
            run_id = datetime.now(timezone.utc).strftime(
                "%Y%m%dT%H%M%S%fZ"
            )
            output = (
                BASE_DIR
                / "evaluation_reports"
                / f"diagnostic_{run_id}.json"
            )
            output.parent.mkdir(exist_ok=True)
            output.write_text(
                json.dumps(diagnostic, indent=2, allow_nan=False),
                encoding="utf-8",
            )

            print("\nFaithfulness:", diagnostic["faithfulness"])
            if diagnostic["error"]:
                print("Error:", diagnostic["error"])
            print("Diagnostic saved:", output)


if __name__ == "__main__":
    asyncio.run(main())
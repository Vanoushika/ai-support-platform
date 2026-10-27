import argparse
import asyncio
import copy
import hashlib
import importlib.metadata
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from time import perf_counter

from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import Faithfulness

from ai_service import MODEL_NAME, draft_ticket_response
from retrieval import EMBEDDING_MODEL, KNOWLEDGE_DIR
from routing_workflow import classify_ticket

BASE_DIR = Path(__file__).resolve().parent
CASES_FILE = BASE_DIR / "evaluation_cases.json"
REPORT_DIR = BASE_DIR / "evaluation_reports"

JUDGE_SETTINGS = {
    "max_tokens": 4096,
    "temperature": 0,
    "reasoning_effort": "none",
}


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def knowledge_fingerprints():
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(KNOWLEDGE_DIR.glob("*.md"))
    }


def summarize(results):
    total = len(results)
    scores = [
        item["faithfulness"]
        for item in results
        if item.get("faithfulness") is not None
    ]
    times = [
        item["draft_seconds"]
        for item in results
        if item.get("draft_seconds") is not None
    ]
    categories = sum(
        item.get("category_correct") is True for item in results
    )
    retrievals = sum(
        item.get("retrieval_correct") is True for item in results
    )

    return {
        "cases_run": total,
        "category_matches": categories,
        "category_accuracy": categories / total if total else None,
        "retrieval_top1_matches": retrievals,
        "retrieval_top1_accuracy": retrievals / total if total else None,
        "successful_drafts": sum(bool(item.get("draft")) for item in results),
        "fallback_drafts": sum(item.get("draft_strategy") == "fallback" for item in results),
        "revised_drafts": sum(item.get("draft_strategy") == "revised" for item in results),
        "successful_faithfulness_scores": len(scores),
        "mean_faithfulness_scored_cases_only": mean(scores) if scores else None,
        "mean_retrieval_and_draft_seconds": mean(times) if times else None,
        "cases_with_errors": sum(bool(item.get("errors")) for item in results),
        "cases_with_review_warnings": sum(
            bool(item.get("review_warnings")) for item in results
        ),
    }


async def score_saved_draft(result, scorer):
    result["faithfulness"] = None
    result["faithfulness_reason"] = None
    result["faithfulness_metadata"] = None
    result["faithfulness_seconds"] = None
    result.setdefault("errors", {}).pop("faithfulness", None)

    started = perf_counter()
    print("  Scoring saved draft against retrieved sources...", flush=True)

    try:
        if not result.get("draft"):
            raise ValueError("No saved draft is available.")

        contexts = [
            source["content"] for source in result.get("sources", [])
        ]
        if not contexts:
            raise ValueError("No saved source content is available.")

        score = await asyncio.wait_for(
            scorer.ascore(
                user_input=f"{result['title']}\n{result['description']}",
                response=result["draft"],
                retrieved_contexts=contexts,
            ),
            timeout=360,
        )

        # Preserve diagnostics even if the numeric score is invalid.
        reason = getattr(score, "reason", None)
        result["faithfulness_reason"] = (
            str(reason) if reason is not None else None
        )
        metadata = getattr(score, "metadata", None)
        result["faithfulness_metadata"] = (
            json.loads(json.dumps(metadata, default=str))
            if metadata is not None else None
        )

        value = float(score.value)
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"Invalid faithfulness score: {value}")

        result["faithfulness"] = value

    except Exception as exc:
        result["errors"]["faithfulness"] = (
            f"{type(exc).__name__}: {exc}"
        )
    finally:
        result["faithfulness_seconds"] = round(
            perf_counter() - started, 2
        )

    return result


async def evaluate_case(case, scorer):
    result = {
        "id": case["id"],
        "title": case["title"],
        "description": case["description"],
        "expected_category": case["expected_category"],
        "expected_source": case["expected_source"],
        "actual_category": None,
        "category_correct": None,
        "actual_source": None,
        "retrieval_correct": None,
        "draft": None,
        "sources": [],
        "review_warnings": [],
        "faithfulness": None,
        "draft_seconds": None,
        "errors": {},
    }

    print("  Classifying ticket...", flush=True)
    try:
        classification = await asyncio.wait_for(
            classify_ticket({
                "title": case["title"],
                "description": case["description"],
            }),
            timeout=200,
        )
        result["actual_category"] = classification["category"]
        result["classification_reason"] = classification["reason"]
        result["category_correct"] = (
            classification["category"] == case["expected_category"]
        )
    except Exception as exc:
        result["errors"]["classification"] = (
            f"{type(exc).__name__}: {exc}"
        )

    print("  Retrieving sources and generating draft...", flush=True)
    started = perf_counter()
    try:
        generated = await asyncio.wait_for(
            draft_ticket_response(case["title"], case["description"]),
            timeout=400,
        )
        result["draft_seconds"] = round(perf_counter() - started, 2)
        result["draft"] = generated["draft"]
        result["draft_strategy"] = generated.get("draft_strategy", "unknown")
        result["generation_attempts"] = generated.get("generation_attempts")
        result["sources"] = generated["sources"]
        result["review_warnings"] = generated["review_warnings"]

        if generated["sources"]:
            result["actual_source"] = generated["sources"][0]["filename"]

        result["retrieval_correct"] = (
            result["actual_source"] == case["expected_source"]
        )
    except Exception as exc:
        result["errors"]["generation"] = f"{type(exc).__name__}: {exc}"
        return result

    return await score_saved_draft(result, scorer)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Run the first N cases.")
    parser.add_argument("--case", help="Run one case by its exact ID.")
    parser.add_argument(
        "--rescore",
        type=Path,
        help="Rescore drafts and source snapshots from an existing report.",
    )
    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    original_report = None
    input_path = args.rescore.resolve() if args.rescore else CASES_FILE

    try:
        loaded = json.loads(input_path.read_text(encoding="utf-8"))
        if args.rescore:
            original_report = loaded
            cases = copy.deepcopy(loaded["results"])
        else:
            cases = loaded

        if not isinstance(cases, list):
            raise ValueError("Expected a list of cases.")

        if args.case:
            cases = [case for case in cases if case["id"] == args.case]
        if args.limit:
            cases = cases[:args.limit]
        if not cases:
            raise ValueError("No matching cases found.")

    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))

    REPORT_DIR.mkdir(exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report_path = REPORT_DIR / f"{run_id}.json"

    report = {
        "run_id": run_id,
        "mode": "rescore" if args.rescore else "generate_and_score",
        "input_file": str(input_path),
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "judge_model": MODEL_NAME,
        "judge_settings": JUDGE_SETTINGS,
        "ragas_version": package_version("ragas"),
        "openai_client_version": package_version("openai"),
        "limitations": [
            "Small development set, not a held-out benchmark.",
            "Judge scores may be incorrect and require human review.",
            "Faithfulness does not prove relevance or task completion.",
            "Missing scores are errors, not passing results.",
            "Generator and judge may use the same model.",
            "Rescoring reuses the saved draft and source contents exactly.",
            "In rescore mode, classification, retrieval, warnings, and "
            "generation timings are copied, not measured again.",
            "Judge explanations may be absent or incomplete.",
        ],
        "results": [],
        "summary": {},
    }

    if original_report is not None:
        # Retain original provenance without claiming it is a new generation.
        report["original_report_metadata"] = {
            key: value
            for key, value in original_report.items()
            if key not in {"results", "summary"}
        }
    else:
        report.update({
            "generator_model": MODEL_NAME,
            "embedding_model": EMBEDDING_MODEL,
            "knowledge_fingerprints": knowledge_fingerprints(),
            "generator_code_sha256": hashlib.sha256(
                (BASE_DIR / "ai_service.py").read_bytes()
            ).hexdigest(),
        })

    def save_report():
        report["summary"] = summarize(report["results"])
        temporary = report_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False),
            encoding="utf-8",
        )
        temporary.replace(report_path)

    save_report()
    print(f"Report: {report_path}", flush=True)

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
        scorer = Faithfulness(llm=evaluator)

        for index, case in enumerate(cases, start=1):
            print(f"\n[{index}/{len(cases)}] {case['id']}", flush=True)

            if args.rescore:
                previous_score = case.get("faithfulness")
                result = await score_saved_draft(case, scorer)
                result["previous_faithfulness"] = previous_score
            else:
                result = await evaluate_case(case, scorer)

            report["results"].append(result)
            save_report()

            print("  Faithfulness:", result.get("faithfulness"), flush=True)
            print(
                "  Judge explanation:",
                result.get("faithfulness_reason")
                or "RAGAS did not return an explanation.",
                flush=True,
            )
            if result.get("faithfulness_metadata") is not None:
                print(
                    json.dumps(result["faithfulness_metadata"], indent=2),
                    flush=True,
                )
            if result["errors"]:
                print(json.dumps(result["errors"], indent=2), flush=True)

    print("\nSUMMARY")
    print(json.dumps(report["summary"], indent=2))
    print(f"\nReport saved: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
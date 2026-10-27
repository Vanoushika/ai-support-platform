# Draft quality checks

New drafts receive heuristic checks for missing/unrecognized citations, unsupported
action claims, the documented third-reset-email mistake and selected timing claims.
On a check failure the model gets one correction attempt with the original ticket
and sources. If that attempt also fails, the app returns a human-review placeholder
with a prominent FALLBACK warning and the rejected-text findings. A fallback is not
a solution or an answer ready to send. The system sends no replies automatically.
Human review remains required, and grounding_verified always stays false.

The second-attempt detector deliberately errs toward review. It can flag negated or
ambiguous descriptions and does not parse arbitrary language reliably. The retry
check can also flag harmless quotations or negations. The checks do not establish
factual correctness, source relevance, completeness or prompt-injection resistance.
An answer can pass all checks and still be wrong. Citation presence is formatting,
not proof of grounding. Unknown citation IDs trigger correction; the application
does not just append citations to unchecked generated answers.

Successful corrections retain a review warning. New responses include draft_strategy
(generated/revised/fallback) and generation_attempts. The evaluator records these
and reports fallback_drafts and revised_drafts. successful_drafts retains its old
meaning of nonempty output, including placeholders; read fallback counts alongside
it. RAGAS faithfulness remains document-only and is not a task-success metric.
Old reports retain their original values; rescoring cannot invent missing metadata.

Old Temporal workflows keep their saved drafts. Test using NEW tickets. Existing
rejected drafts and review decisions are not changed. One correction can add an
extra model-call delay. Network, malformed-output and truncation errors remain
errors rather than being converted to successful drafts.

## Checks
From the project root after installing:

```bash
docker compose build api worker indexer
docker compose run --rm --no-deps api python -m unittest test_draft_quality -v
docker compose up -d
```

Unit tests mock retrieval and Ollama; they make no network calls. They verify
known regression wording, bounded retries, fallbacks, error propagation and the
review flags. They are not evidence of live-model accuracy. After these pass,
create a new second-reset-attempt ticket and a premium-access ticket through the
app, then manually compare their new drafts with the retrieved articles.

If the UI shows FALLBACK, reject the placeholder. Editing drafts and preventing
approval of placeholders are not implemented by this update.

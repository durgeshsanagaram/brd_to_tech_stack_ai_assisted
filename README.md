# Multi-Agent BRD-to-Engineering System

[![CI](https://github.com/durgeshsanagaram/brd_to_tech_stack_ai_assisted/actions/workflows/ci.yml/badge.svg)](https://github.com/durgeshsanagaram/brd_to_tech_stack_ai_assisted/actions/workflows/ci.yml)

A multi-agent system that turns a raw Business Requirements Document into engineering
artifacts (plan, schedule, architecture, PoC scope, tech-stack recommendation) — grounded in a
RAG knowledge base, validated by a Critic agent with a bounded revision loop, and gated by
guardrails before reaching the EM.

**Tool track:** code (Python), not the low-code (n8n/Langflow) track. Vector store: Chroma
(local). Embeddings: `text-embedding-3-small` (falls back to a local model if no API key — see
below). LLM-as-judge: pluggable, defaults to a deterministic mock for reproducible grading.

## Documentation Index

| Doc | Contents |
| :---- | :---- |
| [`docs/architecture.md`](docs/architecture.md) | 4-layer system design, orchestration pattern (hub-and-spoke) + justification, Mermaid diagrams (system, sequence, Critic revision state machine) |
| [`docs/rag_design.md`](docs/rag_design.md) | Chunking strategy per source type, metadata schema, embedding/vector-DB choice, retrieval parameters (incl. empirically-calibrated similarity threshold) |
| [`docs/evaluation_report.md`](docs/evaluation_report.md) | Eval dataset, methods, before/after revision scores, guardrail test results, cycle-improvement metrics |
| [`docs/guardrails_safety.md`](docs/guardrails_safety.md) | All 6 guardrails (design + code pointers), ambiguity-handling policy, residual risks stated explicitly |
| [`docs/agent_contract_reference.md`](docs/agent_contract_reference.md) | All 7 output contracts — required fields, dependency graph, who consumes what |
| [`docs/operationalization.md`](docs/operationalization.md) | Success/failure criteria, pre-release gates, logging/monitoring plan, known gaps |
| [`docs/demo_video_script.md`](docs/demo_video_script.md) | Timed script/storyboard for the 7–10 min demo video, with exact commands per segment |
| [`prompts/critic_rubric.md`](prompts/critic_rubric.md) | The Critic's LLM-as-judge rubric prompt + a human-calibrated worked example |
| [`schemas/`](schemas) | JSON Schema output contracts for all 7 agents + shared envelope/citation definitions |

Agent contract reference: each schema file in `schemas/` is self-documenting (property
descriptions inline); `schemas/common.schema.json` defines the shared envelope every agent output
extends via `allOf`. Consumers: the Orchestrator validates every agent's output against its schema
before handing it to the Critic (`scripts/guardrails.py::validate_schema`); the Critic's own output
is validated against `schemas/critic_review.schema.json`.

## Repository Structure

```
kb/                   Synthetic knowledge base (source of truth for RAG)
  past_brds/            3 BRDs (simple/medium/complex)
  plan_templates/       3 engineering-plan templates
  architecture_patterns/ 8 architecture patterns with trade-offs
  org_standards/        Org engineering standards (approved stacks, CI/CD, security, ...)
  project_timelines/    8 past-project rows (CSV)
  tech_stack_decisions/ 12 past tech-stack decisions with outcomes (CSV)
schemas/              JSON Schema output contracts (7 agents + shared definitions)
prompts/               Critic rubric prompt (LLM-as-judge)
scripts/
  common.py              Shared Chroma client / embedding-function setup
  brd_parser.py          Layer 1: parses a raw BRD file into schemas/parsed_brd.schema.json
  ingest.py              Chunk kb/ and embed it into Chroma
  query.py               Retrieval CLI with per-agent source_type scoping
  critic.py              Critic: rubric scoring, badges, revision-loop enforcement
  guardrails.py          Input validation, schema compliance, hallucination/scope-creep checks, confidentiality-safe logging
  orchestrator.py        Routes BRD -> 5 specialist agents -> Critic -> guardrails, drives the revision loop end-to-end
  run_all.py             Combines every script above into one pipeline run (see "Running Everything Together")
  watch.py               Polls kb/ and re-runs run_all.py automatically on any change
fixtures/              Sample agent outputs / parsed BRD used by the demos below
githooks/              pre-commit (validates staged BRDs) / post-commit (runs run_all.py) -- see "Third option: git hooks"
tests/                 pytest suite -- tests/test_retrieval.py (RAG retrieval regression tests, see below)
docs/                  Architecture, RAG design, evaluation report, operationalization plan
requirements.txt
```

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Embeddings (optional but recommended):**

```bash
export OPENAI_API_KEY="sk-..."
```

If unset, `scripts/common.py` falls back to Chroma's bundled local `all-MiniLM-L6-v2` model with a
loud warning, so everything below still runs without an API key — but retrieval quality and the
similarity threshold documented in `docs/rag_design.md` were calibrated against
`text-embedding-3-small`, so set the key for results that match the docs.

**Don't mix modes.** A Chroma collection remembers the embedding function it was created with.
If you `ingest.py --reset` with `OPENAI_API_KEY` set, then later query (or re-ingest without
`--reset`) with the key unset, you'll get a dimension mismatch or a hard `ValueError` — not a
graceful fallback. Pick one mode and re-run `ingest.py --reset` any time you change it.

## Running It

**1. Ingest the knowledge base into Chroma:**

```bash
python scripts/ingest.py --reset --persist-dir ./chroma_db
```

Prints a per-source-type chunk count (77 chunks total across all 6 sources). Use `--dry-run` to
preview chunking without embedding anything.

**2. Try retrieval directly:**

```bash
python scripts/query.py "real-time fraud detection scoring pipeline" --agent solution_architect
```

`--agent` applies that agent's documented `source_type` scope and `top_k` from
`docs/rag_design.md` §6 (`plan_generator`, `schedule_estimator`, `solution_architect`,
`poc_planner`, `tech_stack_recommender`, `critic`). Below the similarity threshold, it prints the
"no RAG hits" guardrail message instead of forcing a result.

**Retrieval regression tests:** `tests/test_retrieval.py` codifies the manual checks above (plus
a couple more) so they run automatically instead of being re-verified by hand every time:
threshold enforcement, the no-hits path on an irrelevant query, per-agent source_type scoping, and
a regression test for a real retrieval-starvation bug found during development (querying multiple
source_types with raw requirement text let a BRD's own chunks crowd out `plan_template`
precedent — fixed via per-source-type query framing, tested here against all 3 KB BRDs, not just
the demo one). Runs against a real Chroma collection built from `kb/`, not a mock, in either
embedding mode (verified passing with and without `OPENAI_API_KEY`):

```bash
python -m pytest tests/ -v
```

**3. Run the Critic in isolation** (no API key needed — uses a deterministic mock judge):

```bash
python scripts/critic.py --demo
```

Scores the deliberately-flawed `fixtures/engineering_plan_brd-002_rev0.json` against
`fixtures/parsed_brd_brd-002.json`, prints the rubric scores/badge, and validates the result
against `schemas/critic_review.schema.json`. To see the corrected revision score:

```bash
python scripts/critic.py \
  --review fixtures/engineering_plan_brd-002_rev1.json \
  --brd fixtures/parsed_brd_brd-002.json \
  --retrieved fixtures/retrieved_chunks_run-001_plan_generator.json
```

(rev0 → 🔴 Red, overall 3.38; rev1 → 🟢 Green, overall 4.62 — see `docs/evaluation_report.md` §4
for the full before/after breakdown.)

**4. Run the guardrails suite:**

```bash
python scripts/guardrails.py --demo
```

Exercises all five guardrail types (input validation, schema compliance, hallucination, scope
creep, confidentiality-safe logging) against both valid and deliberately-broken inputs.

**5. Run the full pipeline end-to-end** (requires step 1 to have populated `./chroma_db` first):

```bash
python scripts/orchestrator.py --demo
```

Routes brd-002 through all 5 specialist agents, retrieves real RAG context per agent, runs
guardrails + the Critic after every output, drives the capped 2-cycle revision loop, checks
cross-agent consistency, writes structured JSONL logs to `logs/<run_id>.jsonl`, and validates the
final state against `schemas/orchestrator_state.schema.json`.

## Running Everything Together

`scripts/run_all.py` chains steps 1–5 above into one process (same functions,
same results as running them one at a time):

```bash
python scripts/run_all.py                # ingest + retrieval smoke test + full orchestrator run + eval summary
python scripts/run_all.py --skip-ingest   # reuse the existing ./chroma_db instead of re-ingesting
python scripts/run_all.py --no-smoke-test # skip the query.py smoke test step
```

To have it run automatically whenever the knowledge base changes (e.g. you edit a BRD
under `kb/past_brds/`), use `scripts/watch.py`, which polls `kb/` on an interval (no new
dependency — mtime polling, not inotify/FSEvents) and re-runs `run_all.py` on any change:

```bash
python scripts/watch.py                              # poll every 2s, Ctrl+C to stop
python scripts/watch.py --interval 5 -- --skip-ingest # pass flags through to run_all.py after `--`
python scripts/watch.py --once                        # single check-and-run, for cron/launchd instead of a loop
```

To run against a different BRD, pass `--brd` (works for `run_all.py`, `watch.py` — after
`--`, — and `orchestrator.py` directly):

```bash
python scripts/run_all.py --brd kb/past_brds/brd-003-complex.md
```

`scripts/brd_parser.py` is a real Layer-1 parser (frontmatter + `## Section` headings +
`FR-N:`/`NFR-N:` bullet requirements, see its module docstring for exact rules and stated
limits — `.md`/`.txt` only, no priority inference), so this works for any BRD following
`kb/past_brds/`'s structure, not just brd-002. Try it standalone:

```bash
python scripts/brd_parser.py kb/past_brds/brd-003-complex.md --validate
```

### Third option: git hooks

If this repo is (or becomes) a git repository, `githooks/pre-commit` and `githooks/post-commit`
tie the pipeline to your commit workflow instead of a file-watcher loop or a manual command:

- **`pre-commit`** — fast, staged-files-only: runs `guardrails.validate_brd_file` +
  `brd_parser.py --validate` against every staged file under `kb/past_brds/`, and **blocks the
  commit** if any fails (an empty file, wrong type, or a file that doesn't parse to a schema-valid
  `parsed_brd`). Cheap enough to run on every commit.
- **`post-commit`** — after a commit that touches `kb/` lands, runs the full
  `scripts/run_all.py` (ingest + all 5 agents + Critic + guardrails) against whichever BRD
  changed. This does **not** block or fail the commit — it already happened by the time
  post-commit fires — it just reports.

Git doesn't track `.git/hooks/` itself, so these live in a regular, version-controlled
`githooks/` directory instead; point git at it once per clone:

```bash
git config core.hooksPath githooks
```

After that, `git commit` runs both automatically. To skip them for one commit:
`git commit --no-verify`. Both scripts were verified end-to-end (valid edit → commit succeeds,
pipeline runs after; empty/malformed BRD → commit blocked before it's created) in an isolated
test repo, not just read through.

### Fourth option: GitHub Actions CI

`.github/workflows/ci.yml` runs the same checks as "Running It" above — Layer 1 parsing of every
BRD in the KB, the guardrails suite, the Critic's rev0→rev1 scoring demo, and the full
`run_all.py` pipeline — on every push/PR to `main`. No `OPENAI_API_KEY` secret is required to pass:
without one, it falls back to local embeddings same as any contributor without a key, which lands
the Plan Generator at Amber instead of Green (documented calibration limit, not a CI failure,
`run_all.py` doesn't gate its exit code on Critic badges). Add `OPENAI_API_KEY` as a repository
secret (Settings → Secrets and variables → Actions) to exercise the documented
`text-embedding-3-small` path instead.

Verified both states directly, not just by reading the workflow file: run #1 (no secret) —
job succeeded in 52s, Plan Generator landed Amber (3.75) as expected; after adding the
`OPENAI_API_KEY` repo secret, re-run #2 — job succeeded in 42s, all 5 agents landed Green (4.62),
matching the local demo's documented result exactly.

**Known limitation:** parsing is real for any BRD, but *generation* (the 5 specialist
agents) is still pluggable stubs, not a live LLM call. `plan_generator` has a genuine
fixture-backed rev0→rev1 demo for brd-002 specifically (see below) and falls back to a
minimal generic stub plan for any other BRD; the other 4 agents are minimal RAG-grounded
stubs for every BRD regardless of which one you pass. Guardrails, retrieval, and the Critic
all run for real against whatever BRD you point at.

## Notes on What's a Live Call vs. a Stand-In

- **Parsing (Layer 1)** is real for any BRD — `scripts/brd_parser.py` regex-parses whatever
  `.md`/`.txt` file you point at, not a canned fixture. See its module docstring for exactly
  what it does and does not infer (no `.pdf`/`.docx` support yet, no priority inference).
- **Generation** (the 5 specialist agents) is pluggable in `scripts/orchestrator.py`'s
  `AGENT_REGISTRY`. `plan_generator` is fixture-backed for brd-002 specifically (returns a
  deliberately-flawed draft, then a corrected revision, to demonstrate a real Critic-driven
  improvement) and falls back to a minimal generic stub for any other BRD; the other 4 are
  minimal stub generators built from real RAG retrieval hits and the real parsed BRD, standing
  in for an LLM call, for every BRD. Swap in a real LLM call by replacing the registry entry —
  the routing/guardrail/Critic/logging wiring around it doesn't change.
- **Critic judging** is pluggable via `judge_fn`. `scripts/critic.py::mock_judge_fn` is the default
  (deterministic, free, reproducible); `make_openai_judge_fn()` wires up a real OpenAI call and was
  exercised during development. Pass `--use-openai` to `critic.py`'s CLI to use it.
- **Retrieval** is real in all cases — `scripts/query.py` and `scripts/orchestrator.py` both query
  the actual Chroma collection built in step 1, not canned results.

See `docs/evaluation_report.md` §8 and `docs/operationalization.md` §5 for known limitations
(single BRD run end-to-end so far, no retry/backoff for transient API failures, etc.) — stated
explicitly rather than glossed over.

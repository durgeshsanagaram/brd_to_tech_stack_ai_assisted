# CLAUDE.md

Guidance for Claude Code working in this repo. Full details are in `README.md` and `docs/` —
this file is quick orientation, not a duplicate.

## What this is

A 7-agent BRD-to-Engineering-System (Orchestrator, Plan Generator, Schedule Estimator, Solution
Architect, PoC Planner, Tech Stack Recommender, Critic), RAG-grounded via Chroma, with a Critic
revision loop and guardrails. Plus a fully-implemented Voice Interface stretch goal (ASR, TTS,
RAG-connected voice queries, voice approval/rejection).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."   # optional but recommended -- see "Don't mix embedding modes" below
```

## The one command that runs everything

```bash
python scripts/run_all.py
```

Ingest → RAG retrieval smoke test → all 5 agents with Critic + guardrails + revision loop →
cross-agent consistency → evaluation summary. Under 6 seconds end to end. Prefer this over running
individual scripts unless specifically debugging one piece.

## Tests

```bash
python -m pytest tests/ -v
```

Real tests against real Chroma retrieval, real Whisper/TTS calls, real Critic scoring — nothing
mocked. Network-dependent tests (ASR/TTS/voice-query) skip gracefully without `OPENAI_API_KEY`
rather than failing. Always run the full suite before committing a change to `scripts/`.

## Don't mix embedding modes

Chroma remembers the embedding function a collection was created with. If `./chroma_db` was
built with `OPENAI_API_KEY` set and you later query (or re-ingest without `--reset`) with it
unset, you get a dimension-mismatch `ValueError`, not a graceful fallback. Re-run
`python scripts/ingest.py --reset --persist-dir ./chroma_db` any time you change modes.

## Git hooks

`git config core.hooksPath githooks` (once per clone) enables `pre-commit` (validates staged
`kb/past_brds/*` files, blocks the commit if invalid) and `post-commit` (re-runs `run_all.py`
automatically when a commit touches `kb/`). Both already configured in this clone.

## Conventions this project follows (keep following them)

- **Verify, don't assume.** Every claim about behavior (timing, test counts, retrieval scores,
  CI status) should be checked by actually running it, not inferred from reading code.
- **Document real findings, including bugs.** When testing surfaces a real bug (e.g. the dormant
  PoC↔architecture consistency check, the ASR negation-handling bug), fix it and say so explicitly
  in the commit message and relevant doc — don't fix silently.
- **State scope limits explicitly.** Partial implementations (e.g. Voice Interface pieces as they
  were built incrementally) are documented as partial in the README, not implied as complete.
- **CI must stay green.** `.github/workflows/ci.yml` runs on every push to `main` — check
  `https://github.com/durgeshsanagaram/brd_to_tech_stack_ai_assisted/actions` after pushing.
- **Never commit secrets.** `my_macterminal_to_llm*.txt` (contains a real API key from earlier in
  this project's history) is gitignored — keep it that way.

# Demo Video Script (Target: 8–9 minutes)

Maps to every required segment in BRD Section 10D. Optimized for solo recording: every command is
copy-pasteable as-is, in order, from the repo root — no filler, no live decisions. Say-lines are
one to two sentences; read them, don't ad-lib. Record terminal + editor side by side.

**Before recording — do these once, in order:**

```bash
source .venv/bin/activate
export OPENAI_API_KEY="sk-..."          # segment 5's Green badge depends on real embeddings — see note below
python scripts/ingest.py --reset --persist-dir ./chroma_db
rm -rf logs/*.jsonl
```

- Run every command from the **repo root**, never from inside `scripts/` — paths are relative to cwd.
- No `OPENAI_API_KEY`? Everything still runs, but segment 5's Plan Generator lands Amber, not
  Green (documented calibration limit, `docs/rag_design.md` §6) — fine to record, just don't let
  it surprise you on camera.

---

## 1. Architecture (0:00–1:00)

**Screen:** `docs/architecture.md` — system diagram, then sequence diagram.

**Say:**
> A multi-agent system turning a raw BRD into engineering artifacts — plan, schedule, architecture,
> PoC scope, tech-stack recommendation — grounded in RAG and validated by a Critic. Four layers:
> parsing, RAG augmentation, generation, validation. Hub-and-spoke orchestration: one Orchestrator,
> five specialist agents, one place to enforce the revision cap and guardrails.

---

## 2. Parsing (1:00–2:15)

**Screen:** terminal, `kb/past_brds/brd-002-medium.md` in editor.

**Say:**
> Here's the BRD — a loyalty points engine, medium complexity. Input validation runs first.

```bash
python scripts/guardrails.py --demo
```
**Say:** *(point at first output block)*
> File type, structure, non-empty — checked before parsing starts.

```bash
python scripts/brd_parser.py kb/past_brds/brd-002-medium.md --validate
```
**Say:**
> A real parser, not a fixture — every `FR-N`/`NFR-N` bullet becomes a validated `requirement_id`,
> the join key every downstream completeness and scope-creep check uses.

```bash
python scripts/brd_parser.py kb/past_brds/brd-003-complex.md --validate
```
**Say:**
> Same parser, a different BRD — thirteen requirements, and it catches this one's deliberate NFR
> contradiction automatically.

**Screen:** point at `sections[]`, `requirements[]`, `[schema validation] PASSED`.

---

## 3. RAG Retrieval (2:15–3:15)

**Screen:** terminal.

**Say:**
> Six source types, chunked and embedded into Chroma.

```bash
python scripts/query.py "engineering plan phases risks milestones for a loyalty points engine" --agent plan_generator
```
**Say:**
> Scoped to exactly the source types the Plan Generator is allowed — plan templates, past BRDs —
> with an empirically calibrated similarity threshold, not a guess.

```bash
python scripts/query.py "unrelated query about cooking recipes" --agent solution_architect
```
**Say:**
> The no-hits guardrail path, firing on a genuinely irrelevant query — it disclaims instead of
> forcing a citation.

*(Cut this second query if running long.)*

---

## 4. Agent Outputs + Full Pipeline (3:15–4:45)

**Screen:** `fixtures/engineering_plan_brd-002_rev1.json` in editor.

**Say:**
> Every output is a validated JSON contract — phases, risks, milestones, team composition — and
> every non-trivial claim cites a retrieved chunk.

**Screen:** point at `citations[]` (`template-002#0`, `brd-002#2`), and the `assumptions[]` entry
with `conservative_default_applied: true`.

**Say:**
> The conservative-default policy in action — an ambiguous requirement gets documented, not guessed.

```bash
python scripts/orchestrator.py --demo
```
**Say:** *(while it runs)*
> This routes the BRD — parsed live, not from a fixture — through all five agents, with real
> retrieval and real Critic/guardrail checks after every output. Pass `--brd` to run any BRD file.

---

## 5. Critic Before/After (4:45–6:15)

**Screen:** terminal.

**Say:**
> The first draft was deliberately flawed — missing citations, one fabricated claim.

```bash
python scripts/critic.py --demo
```
**Say:** *(point at the JSON)*
> Groundedness 2.0, completeness 2.5, overall 3.38 — Red, revision required. Specific feedback:
> which requirements are missing, which claim was fabricated.

```bash
python scripts/critic.py \
  --review fixtures/engineering_plan_brd-002_rev1.json \
  --brd fixtures/parsed_brd_brd-002.json \
  --retrieved fixtures/retrieved_chunks_run-001_plan_generator.json
```
**Say:**
> After incorporating that feedback: groundedness 4.5, completeness 5.0, overall 4.62 — Green. A
> real before/after driven by the Critic's own feedback, documented in the evaluation report.

---

## 6. Guardrails (6:15–7:15)

**Screen:** terminal (scroll back to segment 2's `guardrails.py --demo` output, or re-run it).

**Say:**
> Four more guardrails at every handoff: schema compliance rejects a missing required field.
> Hallucination detection catches a citation to a chunk that was never retrieved this run. Scope
> creep catches an invented requirement ID. And confidentiality — verified programmatically, not
> just asserted — confirms no raw BRD text ever reaches the log; excerpts get hashed first.

---

## 7. Evaluation Scores (7:15–8:15)

**Screen:** `docs/evaluation_report.md`, pipeline-run table + guardrail results table.

**Say:**
> Rule-based checks for schema and citations, LLM-as-judge for groundedness and actionability. Full
> pipeline run: all five agents Green, Plan Generator needed one revision cycle, cross-agent
> consistency passed. Ten of ten guardrail tests behaved as expected.

---

## 8. Operationalization + Close (8:15–9:00)

**Screen:** `docs/operationalization.md`, success-criteria + pre-release-gate tables.

**Say:**
> Success and failure criteria were defined up front, with mitigations already implemented:
> retry-then-escalate, the no-hits disclaimer, the hard revision cap. Every execution is logged
> with a hashed input, retrieved chunks, Critic score, and guardrail triggers — real, not
> aspirational.

**Say (close):**
> That's the loop — a real parser for any BRD, five agents grounded in a real knowledge base, a
> Critic that drives measurable improvement, guardrails that fire on real bad input, structured
> logging underneath. `scripts/run_all.py` chains all of it into one command; `scripts/watch.py`
> re-runs it automatically on any BRD change. Full docs are in `docs/`.

---

## Timing Summary

| Segment | Duration | Cumulative |
| :---- | :---- | :---- |
| 1. Architecture | 1:00 | 1:00 |
| 2. Parsing | 1:15 | 2:15 |
| 3. RAG retrieval | 1:00 | 3:15 |
| 4. Agent outputs + pipeline | 1:30 | 4:45 |
| 5. Critic before/after | 1:30 | 6:15 |
| 6. Guardrails | 1:00 | 7:15 |
| 7. Eval scores | 1:00 | 8:15 |
| 8. Operationalization + close | 0:45 | 9:00 |

Easiest cuts if running long: segment 3's second query (~15s), segment 2's brd-003 parser run
(~20s), segment 6's `guardrails.py --demo` re-run if segment 2's is still on screen.

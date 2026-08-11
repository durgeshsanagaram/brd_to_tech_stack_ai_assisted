# Demo Script — Tight Format (1:00 architecture + 3:00 live commands + Q&A)

## THE ONE COMMAND YOU NEED

```bash
python scripts/run_all.py
```

**This is the master script. Run it once, and you never need to run anything else during your
timed segment.** In one process it does: input validation → ingest the KB into Chroma → a RAG
retrieval smoke test → all 5 specialist agents with the Critic and guardrails at every handoff and
the capped revision loop → a final cross-agent consistency pass → an evaluation summary with every
Critic badge. Measured locally: **under 6 seconds** end to end. The 3 minutes you have is for
narrating what scrolls by, not for waiting on it — you will have time to spare.

Everything else in this repo (`query.py`, `critic.py`, `guardrails.py`, `orchestrator.py` run
standalone, the voice scripts) is either already exercised *inside* `run_all.py`, or is a
deep-dive command to have ready **only if Q&A asks for it** — see the "Backup commands for Q&A"
section at the bottom. Do not run them during the timed 3 minutes; there's no time and no need.

**Before recording:**
```bash
source .venv/bin/activate
export OPENAI_API_KEY="sk-..."          # without it, retrieval falls back to local embeddings and
                                          # the Plan Generator lands Amber instead of Green (documented
                                          # calibration limit, docs/rag_design.md §6) -- set the key.
python scripts/ingest.py --reset --persist-dir ./chroma_db   # pre-warm the KB so the live run is fastest
```

---

## Segment 1 — Architecture (1:00, no commands)

**On screen:** `docs/architecture.md` — system diagram, then sequence diagram.

**Say:**
> A multi-agent system turning a raw BRD into engineering artifacts — plan, schedule, architecture,
> PoC scope, tech-stack recommendation — grounded in RAG and validated by a Critic. Four layers:
> parsing, RAG augmentation, generation, validation. Hub-and-spoke orchestration: one Orchestrator,
> five specialist agents, one place to enforce the revision cap and guardrails. There's also a
> stretch-goal voice interface layered on top, which I'll show after the core system if time allows.

---

## Segment 2 — Core System, One Command (target 2:00 of your 3:00)

**Say:**
> Everything core to the system runs from one command.

```bash
python scripts/run_all.py
```

Narrate over the 5 phases as they print — this is the entire core system end to end:

| Phase (as printed) | Say |
| :---- | :---- |
| `1/5 Input validation` | "Guardrails check the BRD file — type, structure, non-empty — before Layer 1 parsing even starts." |
| `2/5 Ingest KB into Chroma` | "77 chunks across 6 source types: past BRDs, plan templates, architecture patterns, org standards, project timelines, tech-stack decisions." |
| `3/5 RAG retrieval smoke test` | "A live retrieval check, scoped per-agent, with a similarity threshold I calibrated empirically, not guessed at." |
| `4/5 Orchestrator` | "All 5 specialist agents, each with real RAG context, real Critic scoring, real guardrails, a capped revision loop, and a final cross-agent consistency pass — both structural checks now, phase-id and component-id." |
| `5/5 Evaluation summary` | "Every agent's Critic badge. The Plan Generator used one real revision cycle — Red to Green, 3.38 to 4.62 — driven by the Critic's own feedback, not scripted." |
| `RESULT: ALL GREEN` | "Full pipeline, complete, all green, in under 6 seconds." |

**Say (closing the core segment):**
> That's the whole core system — parsing, RAG grounding, 7-agent orchestration, the Critic's
> revision loop, guardrails, structured JSON contracts, and evaluation — from one command.

---

## Segment 3 — Stretch: Voice Interface (remaining time only, cut freely if you're out of time)

**Say:**
> As a stretch goal beyond the core requirements, there's a full voice interface: ASR, TTS,
> RAG-connected voice queries, and voice-driven approval. One command shows two of those pieces
> together.

```bash
python scripts/voice_query.py --demo
```

**Say:**
> A spoken question, transcribed by Whisper, run through the same retrieval every typed query
> uses — three real voice questions about the knowledge base, three real relevant answers.

**If ~20 seconds remain, one more:**
```bash
python scripts/orchestrator.py --demo --approval-audio samples/voice_approvals/approve-01.mp3
```
**Say:**
> And this is the piece that actually changes control flow, not just reads or speaks — a spoken
> "approve it" drives the pipeline to `complete`; a spoken rejection would drive it to `failed` and
> escalate, since there's no further automated revision path once the demo plan's fixture is
> exhausted.

**If no time at all remains:**
> Say only: "TTS and voice approval are also implemented and tested — details are in the README" —
> and move straight to Q&A.

---

## Backup Commands for Q&A (not part of the timed 3:00 — only run these if specifically asked)

| If asked about... | Run | 
| :---- | :---- |
| Retrieval in isolation | `python scripts/query.py "engineering plan phases risks milestones for a loyalty points engine" --agent plan_generator` |
| The Critic's before/after in isolation | `python scripts/critic.py --demo` then `python scripts/critic.py --review fixtures/engineering_plan_brd-002_rev1.json --brd fixtures/parsed_brd_brd-002.json --retrieved fixtures/retrieved_chunks_run-001_plan_generator.json` |
| Guardrails firing on bad input | `python scripts/guardrails.py --demo` |
| A different BRD (proves the parser isn't brd-002-only) | `python scripts/run_all.py --brd kb/past_brds/brd-003-complex.md` |
| ASR alone | `python scripts/asr.py --demo` |
| TTS alone | `python scripts/tts.py --demo` |
| The regression test suite | `python -m pytest tests/ -v` (87 tests, all real — no mocked retrieval/ASR/TTS) |
| CI | Point at the green badge in `README.md` / the Actions tab — every push runs this same suite. |

---

## Timing Summary

| Segment | Target | Notes |
| :---- | :---- | :---- |
| Architecture | 1:00 | No commands — narration over `docs/architecture.md` only |
| Core system (`run_all.py`) | 2:00 | One command, ~6s execution, rest is narration over the 5 phases |
| Stretch: voice | up to 1:00 | Fully cuttable — core is already covered by minute 3 |
| **Total scripted portion** | **3:00** | |
| Q&A | your remaining time | Use the "Backup Commands" table above if a specific piece comes up |

If you're running long anywhere in Segment 2, the two safest cuts are: skip narrating `3/5`
(retrieval smoke test) in detail, and shorten the `4/5` narration to one sentence. Do not cut
`5/5` — the Critic badges and the 3.38→4.62 revision number are the most concrete evidence the
system actually works, not just runs.

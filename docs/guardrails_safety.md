# Guardrails, Safety & Responsible AI

BRDs carry proprietary business logic — pricing rules, org structure, vendor terms, sometimes
regulatory-sensitive detail (see `kb/past_brds/brd-003-complex.md`'s fraud/compliance content).
This document covers the six guardrails required by BRD Section 8, how each is implemented and
tested, the system's policy for ambiguity, and — as importantly — what these guardrails do
**not** cover, so residual risk is stated rather than implied away.

Test evidence for every guardrail below is in `docs/evaluation_report.md` §6 (10/10 test cases
behaved as expected, no false positives or false negatives observed); this document explains the
*design*, that one has the *results*.

## 1. Input Validation

**What it prevents:** a malformed, empty, or wrong-type file reaching the parser and producing
garbage downstream that the rest of the pipeline would then treat as a legitimate BRD.

**Implementation:** `scripts/guardrails.py::validate_brd_file` — checks file existence, extension
against an allowlist (`.pdf`, `.docx`, `.md`, `.txt`), non-empty content, and a minimal structural
sanity check (at least one heading) for text-based formats. This runs **before** Layer 1 parsing,
not after — a file that fails here never reaches the BRD parser at all.

**Deliberate scope limit:** this is a gate, not a parser. It does not validate that section
content is *semantically* sensible (e.g. a BRD with only a title and no requirements passes this
check but would later fail the Critic's completeness dimension at 0% coverage). Structural
plausibility and semantic completeness are intentionally separated — conflating them would make
this guardrail's rejection reason less specific and harder to act on.

## 2. Schema Compliance

**What it prevents:** a structurally broken agent output (missing required field, wrong type)
silently propagating to the next agent, the Critic, or the EM.

**Implementation:** `scripts/guardrails.py::validate_schema`, called at **every** handoff via
`scripts/orchestrator.py::call_agent_with_retries` — validates against the emitting agent's
contract in `schemas/*.json` before anything downstream sees the output. On failure: retry once
(`MAX_RETRIES = 1`); if still invalid, the agent is marked `failed` and the pipeline status becomes
`failed` rather than continuing with a broken artifact (`docs/operationalization.md` §2, failure
mode #1).

**Why retry-then-fail rather than retry-forever or silently-patch:** an agent that can't produce
valid JSON twice in a row is failing in a way a third identical retry is unlikely to fix (same
prompt, same inputs) — escalating is more honest than looping, and patching a malformed payload
programmatically risks inventing the very content the other guardrails exist to prevent.

## 3. Hallucination Detection

**What it prevents:** an agent asserting a specific fact — a number, a named precedent, a named
standard — that isn't actually backed by anything retrieved or by the source BRD.

**Two layers, deliberately separated** (see `prompts/critic_rubric.md` for the full rationale):

- **Rule-based (guardrail layer, exact):** `scripts/critic.py::rule_based_groundedness`, invoked
  as a guardrail via `scripts/guardrails.py::detect_hallucinated_citations` — every `chunk_id` an
  agent cites must correspond to something its own retrieval call actually returned this run. A
  citation to a real, correct piece of source material that simply wasn't retrieved *this time* is
  treated the same as a fabricated one, because from the system's point of view there is no way to
  distinguish "cited something true but unretrieved" from "invented a citation that looks
  plausible" — both mean the claim isn't grounded in what this run actually had access to. This
  is not a hypothetical distinction: it's exactly the bug found and documented in
  `docs/evaluation_report.md` §4's note, where a hand-authored fixture citation was flagged for
  precisely this reason and had to be corrected to match live retrieval.
- **LLM-judged (Critic scoring layer, semantic):** the rubric prompt asks the judge to separately
  flag claims that read as fabricated even when *no* citation is attached — a specific number or
  named precedent asserted as fact with nothing backing it. `prompts/critic_rubric.md`'s
  calibration example is exactly this case (a fabricated "typically takes 3 weeks" duration).

**Enforcement:** a confirmed hallucinated citation hard-caps the groundedness score at 1.0
regardless of what the LLM judge scored it (`scripts/critic.py::score_dimensions`) — the rule-based
signal overrides the softer judgment call, not the other way around, because citation validity is
mechanically checkable and shouldn't be negotiable.

## 4. Scope Creep Prevention

**What it prevents:** an agent introducing a requirement, feature, or constraint that isn't in the
source BRD — the inverse failure mode from hallucination (inventing *content* vs. inventing
*scope*).

**Implementation:** `scripts/guardrails.py::detect_scope_creep` — every `requirement_id` an agent
claims to address (`requirement_ids_addressed` in the shared envelope,
`schemas/common.schema.json`) must exist in the parsed BRD's own requirement set. Any id not
present in the source is flagged, not silently dropped — a silently-dropped invented requirement
would hide the fact that the agent hallucinated scope in the first place.

**Relationship to completeness:** completeness (BRD Section 7B) checks nothing required is
*missing*; scope creep checks nothing extra was *invented*. They use the same
`requirement_ids_addressed` field from opposite directions — deliberately, so both checks stay in
sync with a single source of truth rather than each maintaining its own notion of "what the BRD
asked for."

## 5. Confidentiality

**What it prevents:** raw BRD or organizational-standard content ending up in logs, where it could
be read by anyone with log access regardless of whether they're cleared to see the BRD itself.

**Implementation:**
- `scripts/guardrails.py::hash_content` — every logged input is a SHA-256 hash, never the raw
  text.
- `scripts/guardrails.py::redact_for_logging` — walks an agent's output before logging and
  replaces every citation `excerpt` field (which can carry real BRD/org-standard text, up to 500
  characters per `schemas/common.schema.json`) with its hash. Everything else in the output
  (structural fields — ids, phase names, scores) is left as-is, since that's derived/generated
  content, not raw source text.
- Verified, not just asserted: `docs/evaluation_report.md` §6 records an actual inspected log
  entry with zero raw BRD text present, confirmed programmatically
  (`assert brd_raw_text not in json.dumps(entry)` in `scripts/guardrails.py::main`'s demo).

**Deliberate scope limit:** this protects log output specifically. It does not encrypt the BRD at
rest in `kb/`/`fixtures/`, restrict who can run the pipeline, or provide audit-trail access
controls — those are deployment/infrastructure concerns outside a capstone-scope prototype, named
here rather than silently assumed handled.

## 6. Cross-Agent Consistency

**What it prevents:** a schedule that doesn't match the plan's phases, or a PoC that references an
architecture component that doesn't exist — internally contradictory artifacts reaching the EM as
if they'd been checked against each other.

**Implementation, deliberately two-layered** (`scripts/critic.py::cross_agent_consistency_checks`
+ the LLM judge's contradiction-detection instructions in `prompts/critic_rubric.md`):
- **Structural (exact):** schedule `effort_estimates[].phase_id` must exist in the plan's
  `phases[]`; PoC `modular_boundaries[].maps_to_component_id` must exist in the architecture's
  `components[]`. Verified in the full pipeline run (`docs/evaluation_report.md` §5): both checks
  now pass. The second check was dormant until the pytest suite (`tests/test_critic.py`) caught it
  — see the note below.

**A real bug the test suite caught (documented, not swept under the rug):** the PoC↔architecture
check was silently never firing in any pipeline run prior to `tests/test_critic.py` being written.
`cross_agent_consistency_checks` read the PoC output via `other_outputs.get("poc_planner")`, but
every call site passes the PoC output as `target_output` instead — so `poc` was always `None` and
the `if architecture and poc:` guard never entered, in every orchestrator run this project has ever
produced. Fixed to mirror the schedule↔plan check's pattern (read the PoC's own
`modular_boundaries` from `target_output`, gated on `target_output["agent_id"] == "poc_planner"`).
Re-verified live afterward: `python scripts/orchestrator.py --demo` now prints both consistency
checks under "Final cross-agent consistency checks" instead of just one.
- **Semantic (LLM-judged):** the rubric prompt asks the judge to identify substantive
  contradictions the structural check can't catch — e.g. a tech-stack recommendation whose "team
  familiarity" trade-off contradicts the plan's assumed ramp-up time. Each contradiction must be
  reported as a specific, quotable pair of statements, not a vague "these don't quite align"
  comment, so the originating agent has something concrete to fix on revision.

Both feed the same consistency score (`scripts/critic.py::score_dimensions`): `5.0 − 1.5 ×
contradiction_count`, where the count sums structural failures and LLM-identified contradictions
together — a system that only checked one layer would miss whichever kind of contradiction the
other layer catches.

## 7. Handling Ambiguity

Per BRD Section 8's ambiguity policy, encoded directly in the output contracts rather than left as
prose guidance an agent might ignore:

- **Ambiguous requirements are flagged, not guessed at.** Every agent's envelope includes
  `ambiguities_flagged[]` (`schemas/common.schema.json`) — a structured field, not a footnote. See
  `fixtures/engineering_plan_brd-002_rev1.json`'s flag on the point-rate requirement (global vs.
  per-category) for a real example.
- **When forced to choose, default to the conservative interpretation** (lower scope, longer
  timeline) **and document the assumption.** The `assumptions[]` field carries
  `conservative_default_applied: true` specifically so this policy is checkable, not just
  claimed — see the same fixture's assumption entry.
- **Contradictions are raised to the EM, not silently resolved.** `kb/past_brds/brd-003-complex.md`
  is the calibration case for this: it contains a genuine unresolved conflict (a 150ms latency
  budget vs. an explainability requirement that typically needs heavier models) and an undecided
  build-vs-buy call. Both are marked `**Flagged as a contradiction requiring EM decision**` in the
  source document rather than resolved unilaterally by whichever agent encounters them first —
  the system's guardrail policy is to surface this kind of conflict, not adjudicate it.

## 8. What These Guardrails Do Not Cover (Residual Risk, Stated Explicitly)

Consistent with `docs/operationalization.md` §5's approach of naming gaps rather than implying
completeness:

- **No protection against a compromised or adversarially-crafted BRD** attempting prompt injection
  against the generation agents (e.g. a "requirement" that reads as an instruction to the LLM
  rather than a business requirement). Input validation here checks structure and file type, not
  adversarial content.
- **No rate limiting or abuse prevention** on how many BRDs a single user can submit — relevant at
  the 50+ BRDs/week scale discussed in `docs/architecture.md`, not addressed at prototype scale.
- **No encryption at rest** for BRDs stored in `kb/`/`fixtures/`, and no access control layer —
  confidentiality here covers *logging* specifically, not storage or transport.
- **Guardrail test coverage was originally limited to one BRD's fixtures** (brd-002) plus
  synthetic malformed-input cases. Since `scripts/brd_parser.py` replaced the brd-002-only
  fixture with a real Layer-1 parser, all three eval BRDs now pass every guardrail (input
  validation, schema compliance, hallucination detection, scope creep, cross-agent consistency)
  through a full orchestrated run — see `docs/evaluation_report.md` §8. The residual gap is
  narrower now: coverage of *deliberately malformed agent outputs* (hallucinated citation,
  invented requirement id, broken schema) is still hand-authored against brd-002's fixtures only.

# RAG Design — Chunking, Embedding, Retrieval

This knowledge base grounds every Planning/Design agent output. It is deliberately built to be
*discriminating*: retrieval must surface the right pattern/template/decision, not just something
plausible-sounding. The `source_type` values below match the `citation.source_type` enum in
`schemas/common.schema.json`, so every retrieved chunk can be cited directly in an agent's
`citations[]`.

## 1. Knowledge Base Sources

| Source Type | `source_type` value | Count | Format |
| :---- | :---- | :---- | :---- |
| Past BRDs | `past_brd` | 3 (simple / medium / complex) | Markdown |
| Engineering plan templates | `plan_template` | 3 | Markdown |
| Architecture pattern library | `architecture_pattern` | 8 | Markdown, one file per pattern |
| Past project timelines | `project_timeline` | 8 rows | CSV → row-per-chunk |
| Org engineering standards | `org_standard` | 1 doc, 6 subsections | Markdown |
| Tech-stack decision log | `tech_stack_decision` | 12 rows | CSV → row-per-chunk |

## 2. Chunking Strategy (per source type)

Chunking is not one-size-fits-all here: narrative documents need semantic/section-aware
splitting, while tabular sources (timelines, decision log) are naturally one-chunk-per-record —
splitting them further would destroy the unit of meaning (a single decision or a single project's
stats belongs together).

| Source Type | Strategy | Chunk Size (target) | Overlap | Rationale |
| :---- | :---- | :---- | :---- | :---- |
| `past_brd` | Section-aware split on markdown headers (Objectives, Functional Reqs, NFRs, Constraints, Stakeholders) | 200–400 tokens | 50 tokens | BRDs mix narrative and lists; splitting on headers keeps a requirement and its surrounding intent together. Overlap preserves context lost at boundary if a requirement references the prior paragraph. |
| `plan_template` | Split per named section (Phases, Risks, Milestones, Team Composition) | 150–300 tokens | 30 tokens | Mirrors the Engineering Plan output contract's own structure — retrieval for "risk examples" should return risk sections, not phase sections. |
| `architecture_pattern` | One chunk per pattern (whole file, ~300–500 tokens) — patterns are short and self-contained; do not split a pattern's trade-offs from its name | 300–500 tokens | none | Splitting a pattern description would let retrieval return "scalability: high" without knowing which pattern it belongs to — an unusable, unattributable claim. |
| `project_timeline` | One chunk per row (complexity, domain, duration, team size, variance) | ~40–60 tokens | none | Each row is an atomic historical data point; chunking below row level has no meaning, and merging rows would blur which project the numbers describe. |
| `org_standard` | Split per subsection (Approved Stacks, Coding Standards, CI/CD, Security, Architecture Review Criteria) | 150–250 tokens | 20 tokens | Standards are referenced narrowly (e.g. only "approved stacks" needed by Tech Stack Recommender) — small chunks avoid pulling in irrelevant subsections and diluting similarity scores. |
| `tech_stack_decision` | One chunk per decision row (stack, rationale, outcome) | 60–100 tokens | none | Same atomicity argument as timelines; a decision's rationale must stay bound to its outcome or the citation becomes misleading. |

**General rule:** never split a table row or a pattern's name away from its trade-offs — that
produces a chunk that reads fine but cites the wrong thing. Where splitting is used (BRDs,
templates, standards), overlap is kept small (15–20% of chunk size) — just enough to recover a
sentence that trails across a boundary, not so much that near-duplicate chunks compete in
retrieval and blur similarity scores.

## 3. Metadata Schema

Every chunk carries the same metadata envelope regardless of source type, so a single retrieval
call can filter across all sources with one `where` clause:

```json
{
  "source_id": "string — stable ID of the parent document/row, e.g. 'pattern-event-driven-01'",
  "source_type": "past_brd | plan_template | architecture_pattern | project_timeline | org_standard | tech_stack_decision",
  "chunk_id": "string — source_id + chunk index, e.g. 'pattern-event-driven-01#0'",
  "title": "string — human-readable title of the parent doc/row",
  "section": "string | null — subsection name for narrative sources, null for row-based sources",
  "domain": "string | null — e.g. 'fintech', 'e-commerce', 'internal-tools' (project_timeline, past_brd)",
  "complexity": "simple | medium | complex | null (past_brd, project_timeline)",
  "tags": "string[] — freeform, e.g. ['microservices','high-throughput'] for pattern retrieval filters",
  "created_at": "date — recency signal, used to prefer newer decisions when relevant",
  "token_count": "integer — chunk size, used for debugging retrieval quality"
}
```

**Why these fields:**
- `source_type` is mandatory on every citation the agents emit — it's the field the Critic uses to
  check groundedness diversity (e.g. an architecture claim citing only `past_brd` and never
  `architecture_pattern` is a weak citation, even if technically "cited").
- `domain` and `complexity` let the Schedule Estimator and Solution Architect filter
  `project_timeline` / `past_brd` chunks to comparable projects instead of retrieving on
  semantic similarity alone — two BRDs can read similarly but differ hugely in actual
  scope, and complexity/domain filters catch that.
- `tags` supports the Tech Stack Recommender and Solution Architect narrowing to relevant
  patterns/decisions (e.g. tag `real-time` before a semantic search for "event-driven") without
  needing a second embedding pass.
- `created_at` lets the Tech Stack Recommender bias toward recent decisions — a 2-year-old
  "we chose X" carries less weight than last quarter's.

## 4. Embedding Model Choice

**Choice: `text-embedding-3-small` (OpenAI) as default, with `text-embedding-3-large` as a
documented upgrade path.**

| Criterion | `text-embedding-3-small` | `text-embedding-3-large` |
| :---- | :---- | :---- |
| Cost | ~5x cheaper per token | Higher |
| Dimensions | 1536 (usable at 512 via truncation) | 3072 |
| Retrieval quality on short/structured text (our case) | Sufficient — most chunks are short, domain-specific, and non-ambiguous | Marginal gain, mostly matters for long, nuanced narrative text |
| Fit for this project | Good — knowledge base is modest (~40 documents / rows), latency and cost dominate over marginal recall gains | Overkill at this KB size |

**Reasoning:** the KB size here (a few dozen chunks per source type, a few hundred total) means
recall differences between small/large embeddings rarely change which chunk wins top-k — the
corpus isn't dense enough to need the extra separation large embeddings buy. Cost and latency
matter more at this stage since agents call retrieval multiple times per BRD run (once per
specialist agent, sometimes twice across revision cycles). If the KB grows past ~10k chunks or
retrieval precision on near-duplicate architecture patterns becomes a problem, upgrade to `-large`
and re-embed — the chunking/metadata design doesn't change, only the vector dimension.

## 5. Vector DB Choice

**Choice: Chroma (local, embedded) for development and this capstone's scale.**

| Criterion | Chroma (local) | Pinecone / Qdrant (cloud) |
| :---- | :---- | :---- |
| Setup cost | Zero — embedded, no external service | Account, API keys, network dependency |
| Fit for KB size (~40 docs) | Fine — in-memory/on-disk index is instant at this scale | Unnecessary overhead |
| Metadata filtering | Native `where` filter support, matches our metadata schema directly | Also supported |
| Persistence | Local disk (`./chroma_db`) — reproducible for grading/demo without cloud creds | Requires provisioning, complicates "clone and run" setup |
| Path to scale (50+ BRDs/week) | Would migrate to Qdrant/Pinecone for concurrent multi-instance access, replication, and to decouple the vector store from any single orchestrator process | N/A at current scale |

**Reasoning:** the submission needs to be reproducible from a clone with `README` setup
instructions — a local, file-backed vector DB removes an external dependency and API key
requirement from grading. The metadata schema (Section 3) is designed to be portable: the same
`where`-clause filtering pattern works unchanged if the KB migrates to Qdrant/Pinecone later.

## 6. Retrieval Parameters

| Parameter | Value | Rationale |
| :---- | :---- | :---- |
| `top_k` | 5 (default), 8 for `architecture_pattern` and `tech_stack_decision` queries | Narrative sources (BRDs, standards) need fewer, more targeted hits; pattern/decision libraries benefit from wider top_k since agents compare options (2–3 stack options, pattern trade-offs). |
| `similarity_threshold` | 0.30 (cosine) | Chunks below this are dropped rather than force-cited — prevents the "cite something, anything" failure mode. Below-threshold results trigger the "no RAG hits" guardrail path (proceed with disclaimer + Amber badge, per Section 9 of the BRD). |

**Threshold calibration (empirical, not assumed).** An earlier draft of this doc set the threshold
at 0.72, based on an unvalidated assumption about where "confident" cosine similarity sits.
Running actual queries against this KB with `text-embedding-3-small` (`scripts/query.py` against
the ingested `scripts/ingest.py` output) showed that never holds in practice:

| Query | Target source_type | Top similarity scores |
| :---- | :---- | :---- |
| "checkout-adjacent low-latency stack decision" | `tech_stack_decision` | 0.575, 0.486, 0.453 |
| "loyalty points engineering plan phases" | `plan_template` | 0.554, 0.470, 0.449 |
| "fraud detection real-time architecture pattern" | `architecture_pattern` | 0.399, 0.340, 0.338 |
| "unrelated query about cooking recipes" (control) | `architecture_pattern` | 0.220, 0.150, 0.121 |

Genuinely relevant hits landed in 0.34–0.575; an irrelevant control query landed in 0.12–0.22. A
0.72 cutoff would have discarded every real hit above and triggered the "no RAG hits" guardrail
on every single query — silently defeating retrieval rather than filtering it. 0.30 was chosen as
the threshold because it sits just above the control query's ceiling (0.22) with room to spare,
while keeping the weakest genuine hits observed (0.338–0.340) comfortably inside. This value is
specific to `text-embedding-3-small` and this KB's size/content; re-measure with the same
control-query method before trusting it against a different embedding model or a materially
larger corpus.
| `metadata_filters` | `source_type` always filtered per calling agent (e.g. Tech Stack Recommender only queries `tech_stack_decision` + `org_standard`); `domain`/`complexity` filtered when the parsed BRD has these fields populated | Keeps each agent's retrieval scoped to its own contract instead of a single unfiltered corpus-wide search — reduces irrelevant citations and keeps the Critic's groundedness check meaningful. |
| Re-ranking | None for MVP; documented stretch: Cohere Rerank or hybrid BM25 + vector if precision issues appear on near-duplicate architecture patterns | KB is small enough that top_k + threshold filtering is sufficient; reranking is listed as a stretch goal in the BRD (Section 14). |

**Per-agent retrieval scoping:**

| Agent | `source_type` filter | Notes |
| :---- | :---- | :---- |
| Engineering Plan Generator | `plan_template`, `past_brd` | Needs phase/risk/milestone precedent |
| Schedule Estimator | `project_timeline`, `plan_template` | Effort/duration precedent |
| Solution Architect | `architecture_pattern`, `org_standard` | Pattern trade-offs + architecture review criteria |
| PoC Planner | `past_brd`, `architecture_pattern` | Scope boundary precedent |
| Tech Stack Recommender | `tech_stack_decision`, `org_standard` | Past outcomes + approved stacks |
| Critic | all types (cross-check) | Verifies citations actually match claimed `source_type` diversity and similarity thresholds |

## 7. Chunk → Citation Traceability

Every chunk returned by retrieval carries `chunk_id` and `source_type`, which map directly onto
the `citation` object in `schemas/common.schema.json`. This is what makes the ≥75%-claims-cited
groundedness threshold (BRD Section 7B) mechanically checkable: the Critic can walk an agent's
`citations[]` array and confirm each `chunk_id` was actually returned by that agent's retrieval
call for that run, rather than trusting a free-text citation claim.

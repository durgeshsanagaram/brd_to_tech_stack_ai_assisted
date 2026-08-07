*Applied Agentic AI for Engineering Managers*

**CAPSTONE PROJECT 1**

**Multi-Agent BRD-to-Engineering System**

| Parameter | Details |
| :---- | :---- |
| Duration | 2 weeks |
| Mode | Individual |
| Tools | n8n / Langflow / Python (Colab / Jupyter) — your choice |
| Core Agents | 7 specialized agents |

# **1\. Business Use Case**

Engineering Managers (EMs) face a persistent bottleneck in translating complex BRDs into structured technical plans and architecture. This manual process results in delays, misalignment between business intent and engineering execution, and inconsistent scoping across teams.


Your task is to build a multi-agent system that transforms a raw BRD into a complete set of engineering artifacts — plans, schedules, architecture, PoC scope, and tech-stack recommendations — all grounded in organizational knowledge, validated by a Critic Agent, and evaluated with quality badges before reaching the EM.

## **The Opportunity**

* **Faster turnaround:** RAG-augmented agents reference past projects and org templates instead of producing generic boilerplate.

* **Standardized, validated planning:** A Critic Agent checks every output for completeness, consistency, and alignment before delivery.

* **Grounded intelligence:** RAG grounds plan and architecture decisions in org standards, past BRDs, and historical project data.

* **Evaluated outputs:** Outputs carry Green / Amber / Red quality badges — not just generated-and-displayed.

* **EM enablement:** Decision-ready artifacts with source citations, not drafts from scratch.

# **2\. Curriculum Concepts You Will Apply**

This capstone is designed as an integrative exercise. Every major curriculum concept appears in a concrete, measurable form within the system.

| Curriculum Area | Where It Applies in This Project | Mandatory / Stretch |
| :---- | :---- | :---- |
| LLMs & Prompting | Plan generation, architecture design, tech stack analysis, critic rubric evaluation | Mandatory |
| Agentic Design Patterns | Choosing orchestration pattern (hub-and-spoke, sequential, hierarchical, message graph) and justifying it | Mandatory |
| RAG Agents | Grounding all agent outputs in past BRDs, architecture templates, and org engineering standards | Mandatory |
| Chunking & Embeddings | Chunk strategy for BRDs (narrative vs. structured sections); metadata tagging per source type | Mandatory |
| Vector Databases | Storing and retrieving past BRDs, architecture patterns, engineering standards, project history | Mandatory |
| Multi-Agent Orchestration | Coordinating Planning, Design, and Critic agents via a Coordinator Agent with state management | Mandatory |
| Structured Output Parsing | Defining output contracts (JSON schemas) between agents with validation at every handoff | Mandatory |
| Tool Calling | Agents calling BRD parser, vector DB APIs, export tools (PDF / Markdown / Jira) | Mandatory |
| Evaluation Framework | Rule-based \+ LLM-as-Judge evals on groundedness, completeness, actionability | Mandatory |
| Guardrails & Safety | Input validation, hallucination detection, schema compliance, scope creep prevention, confidentiality | Mandatory |
| Continuous Improvement | Critic feedback loop: outputs below threshold are revised and re-evaluated (max 2 cycles) | Mandatory |
| Operationalizing Agents | Defining success / failure criteria, pre-release gates, monitoring approach | Mandatory |
| MCP Architecture | MCP-style tool integration for BRD parsing or knowledge retrieval services | Stretch |
| Voice Interface | ASR (Whisper) \+ TTS for EM interaction with artifacts and voice-based approval | Stretch |
| Fine-Tuning | Fine-tune a smaller model on BRD section classification or plan structure generation | Stretch |

# 

# 

# 

# 

# **3\. Technical Architecture**

The system is organized into four layers. How you implement each is your choice — document the tools and models you pick.

| Layer | Responsibility |
| :---- | :---- |
| 1\. BRD Ingestion & Parsing | Parse uploaded BRDs, extract sections, classify requirements, tag metadata. |
| 2\. Knowledge Augmentation (RAG) | Ground all agent outputs in past BRDs, templates, patterns, org standards. |
| 3\. Multi-Agent Generation | Run specialist agents to produce plans, schedules, architecture, PoC, tech-stack options. |
| 4\. Validation & Evaluation | Score outputs, enforce revisions, present quality badges to the EM. |

**Tool tracks.** Low-code (n8n \+ Langflow) for visual DAGs, or code (Python \+ LangChain / LlamaIndex / LangGraph) for full programmatic control. The architecture below is tool-agnostic.

**Data flow.** BRD in → parse → route to specialist agents → retrieve RAG context → generate → Critic review (with revisions) → evaluate → HITL approval → export. You design the exact hand-offs, error handling, and state management.

# **4\. Agent Architecture & Output Contracts**

Your system comprises seven agents. Every agent follows the principle: one role \= one job \= one output contract. You define the schema that fits your tool track; downstream consumers validate it before proceeding.

| \# | Agent | Group | Primary Responsibility |
| :---- | :---- | :---- | :---- |
| 1 | Orchestrator | Orchestration | Route BRD sections to specialist agents; manage state; handle errors and retries. |
| 2 | Engineering Plan Generator | Planning | Phases, risks, milestones, team composition. Uses a Reflection self-review step. |
| 3 | Schedule Estimator | Planning | Effort estimates, timelines, resource allocation. Aligns to the plan's phases. |
| 4 | Solution Architect | Design | High-level system design, components, data flow, NFR mapping. |
| 5 | PoC Planner | Design | PoC scope, measurable success criteria, modular boundaries. |
| 6 | Tech Stack Recommender | Design | 2–3 stack options with trade-offs (scalability, team familiarity, integration risk, cost). |
| 7 | Critic | Validation | Score outputs on completeness, consistency, actionability, groundedness. Enforce the revision loop. |

**Critic behavior.** Every output from Planning and Design groups passes through the Critic. If any rubric dimension falls below threshold, the Critic sends specific feedback to the originating agent for revision. Cap revisions at two cycles; beyond that, flag to the EM with an Amber / Red badge. The Critic also checks cross-agent consistency (does the schedule align with architecture complexity? does tech-stack familiarity match the timeline?).

# **5\. Orchestration**

Choose and justify one orchestration pattern from the curriculum: hub-and-spoke (recommended — a central Orchestrator dispatches to specialists and aggregates), sequential pipeline, hierarchical, or message graph. In your documentation explain why it fits, how error / fallback handling works, and what would change if the system scaled to 50+ BRDs per week.

# **6\. RAG Pipeline**

**You build your own knowledge base.** This is part of the work, not a handout. Synthetic content is fine. Cover enough variety that retrieval genuinely discriminates between good and bad matches.

Suggested sources to create (roughly):

* Past BRDs — 2–3 samples of varying complexity.

* Engineering plan templates — 2–3 showing phases, risks, milestones.

* Architecture pattern library — 5–10 patterns with trade-offs (microservices, monolith, event-driven, CQRS, etc.).

* Past project timelines — 5–10 rows with complexity, domain, duration, team size, variance.

* Org engineering standards — a short document covering approved stacks, coding standards, CI/CD, security, architecture review criteria.

* Tech-stack decision log — 10–15 past decisions with rationale and outcome.

Document your chunking strategy (per source type), metadata schema, embedding model choice (cost vs. quality), vector-DB choice (local like Chroma/FAISS or cloud like Pinecone/Qdrant), and retrieval parameters (top\_k, similarity threshold, metadata filters). Explain your reasoning — why this chunk size, why this metadata, how it affects retrieval quality.

Every non-trivial claim in a generated artifact should cite at least one retrieved chunk.

# **7\. Evaluation Framework**

**You build your own eval dataset alongside the system.** Cover the range of expected inputs (simple, medium, complex BRDs) plus edge cases (missing NFRs, contradictions, ambiguity). Aim for roughly 3–5 BRDs with expected outputs, a handful of expert-scored Critic assessments for calibration, and a few intentional-issue BRDs to test guardrails.

## **7A. Evaluation Methods (implement at least 2\)**

* **Rule-based:** structural checks, schema compliance, BRD section coverage.

* **LLM-as-Judge:** actionability, specificity, grounding quality, EM-readiness.

* **Execution-based:** schema parse rates, end-to-end completion, tool-call success.

* **Reference-based (code track):** ROUGE / BLEU / BERTScore vs. golden outputs.

* **Human:** EM ratings at the HITL gate.

## **7B. Dimensions & Quality Badges**

| Dimension | Threshold |
| :---- | :---- |
| Groundedness — claims supported by retrieved sources | ≥ 75% claims cited |
| Completeness — all BRD sections addressed | 100% section coverage |
| Consistency — Plan / Schedule / Architecture / Tech Stack align | 0 contradictions |
| Actionability — EM can act immediately | Score ≥ 4 / 5 |

**Badges:** 🟢 Green (all dimensions above threshold, overall ≥ 4.0) · 🟡 Amber (one dimension below, or overall 3.0–3.9) · 🔴 Red (two or more below, or overall \< 3.0).

## **7C. Improvement Loop**

Connect Critic feedback to agent revisions. Track revision count and score-per-revision. Show at least one concrete example of an output improving after Critic feedback. Document how Critic scores are tracked and how they drive revision decisions.

## **7D. Cycle Improvement Metrics**

Demonstrate measurable improvement on at least two metrics, either revision-to-revision within one BRD or across two BRDs. Candidates: artifact quality score (rule-based pass rate), groundedness score, actionability score, cross-agent consistency, guardrail trigger count. Include a side-by-side comparison table in your eval report and narrate what changed and why.

# **8\. Guardrails, Safety & Responsible AI**

BRDs often contain proprietary business logic. Implement the following guardrails:

* **Input validation —** reject malformed BRDs; verify file type and structure.

* **Schema compliance —** validate agent outputs at every handoff.

* **Hallucination detection —** flag claims not supported by BRD or retrieved RAG context.

* **Scope creep —** no requirements introduced that aren't in the source BRD.

* **Confidentiality —** no raw BRD content to external logging. Log hashes, not content.

* **Cross-agent consistency —** timelines, architecture, and stack must not contradict. Enforced by the Critic.

**Handling ambiguity.** Ambiguous requirements are flagged in the originating agent's output rather than guessed at. Contradictions are raised to the EM. When forced to choose, default to the more conservative interpretation (lower scope, longer timeline) and document the assumption.

# **9\. Operationalization & Monitoring**

**Define success and failure upfront.** At least three measurable success criteria and at least three failure modes with mitigations. Examples: completeness check passes on all BRD sections; actionability score ≥ 4 / 5 on the eval dataset; end-to-end pipeline under 5 minutes. Failure modes: malformed JSON (retry then escalate), no RAG hits (proceed with disclaimer \+ Amber badge), Critic loop stuck (hard cap at 2 cycles).

**Logging.** For every agent execution, log: input (hashed if sensitive), RAG chunks retrieved, output produced, Critic score, execution time, guardrail triggers, revision count. Use n8n's execution log or structured JSON — your choice.

# **10\. Deliverables**

## **Working Prototype (mandatory)**

All 7 agents implemented across Orchestrator, Planning Group, Design Group, and Critic · functional RAG with a populated knowledge base and demonstrable retrieval · structured output contracts with validation at every handoff · Critic with rubric-based scoring and a working revision loop · at least 2 evaluation methods with results documented across revisions · guardrails (input validation, schema, hallucination, scope creep, confidentiality) · at least one BRD demonstrated end-to-end · structured logging · cycle improvement on at least two metrics.

## **Documentation Package (mandatory)**

Architecture overview · agent contract reference (schemas \+ who consumes what) · RAG design (chunking, embedding, retrieval decisions) · evaluation report (dataset, methods, results across revisions, improvement evidence) · guardrails & safety · operationalization plan (success, failure, monitoring) · decision justification (pattern, embedding model, stack) · README with setup instructions.

## **Demo Video (7–10 minutes)**

Architecture walkthrough · BRD upload and parsing · RAG retrieval · agent outputs with citations · Critic review cycle with before / after scores · guardrails firing · evaluation scores and badges · operationalization summary · any stretch features.

# **11\. Suggested Weekly Timeline**

This timeline is a recommendation, not a mandate. Adapt it to your working style, but ensure all deliverables are complete by the submission deadline.

## **Week 1: Design, Build, and First Full Run**

| Phase | Days | Activities | Deliverables by End of Phase |
| :---- | :---- | :---- | :---- |
| Design & Setup | Days 1–2 | Review problem statement and provided data. Choose tool track. Design architecture diagram (Mermaid). Define orchestration pattern. Set up vector DB and populate knowledge base. Define all 7 output contracts. | Architecture diagram (draft). RAG knowledge base populated. Output contract JSON schemas defined. |
| Core Agents — Part 1 | Days 3–4 | Implement Orchestrator Agent (routing \+ state management). Implement Engineering Plan Generator and Schedule Estimator. Connect to RAG pipeline. Implement Reflection pattern in Plan Generator. Validate JSON outputs. | Orchestrator routing BRD sections correctly. Planning Group agents producing valid JSON with RAG grounding. |
| Core Agents — Part 2 | Day 5 | Implement Solution Architect, PoC Planner, and Tech Stack Recommender. Connect to RAG pipeline. Orchestrate Design Group via Orchestrator. | All 3 Design Group agents producing valid JSON. Full orchestration functional. |
| Critic Agent & Guardrails | Day 6 | Implement Critic Agent with rubric scoring. Implement revision loop (max 2 cycles). Add guardrails (input validation, schema compliance, hallucination detection, scope creep). | Critic producing rubric scores and triggering revisions. Guardrails firing on test cases. |
| First End-to-End Run | Day 7 | Run complete pipeline on sample BRD. Test Critic revision loop. Run eval suite (at least 2 methods). Record initial scores. Document all issues and failures. | First full pipeline run complete. Initial eval scores recorded. Issues list ready. |

## **Week 2: Iterate, Document, and Submit**

| Phase | Days | Activities | Deliverables by End of Phase |
| :---- | :---- | :---- | :---- |
| Improvement Cycle | Days 8–10 | Analyze Week 1 eval scores. Refine prompts and RAG retrieval based on Critic feedback patterns. Re-run pipeline. Demonstrate measurable improvement on at least 2 metrics. Iterate on guardrails if needed. Optionally build Stretch deliverables (EM Dashboard, Voice Interface, MCP server). | Improvement cycle complete. Side-by-side comparison table. Stretch deliverables (if any) integrated. |
| Documentation | Days 11–12 | Write all documentation: architecture diagram (finalized with error paths), agent contract reference, RAG design, evaluation report, guardrails, decision justification, operationalization plan, setup instructions. | Full documentation package complete. |
| Demo & Submission | Days 13–14 | Record demo video (7–10 min). Final testing and cleanup. Prepare submission package (repo \+ docs \+ video). Review against submission checklist. | Demo video recorded. Submission package ready. |

# 

# 

# 

# **12\. Evaluation Rubric**

| Evaluation Area | Weight | What Evaluators Will Look For |
| :---- | :---- | :---- |
| Agent Architecture & Orchestration | 20% | Clear 7-agent decomposition. Each agent has one role, one output contract. Orchestrator manages handoffs. Orchestration pattern chosen and justified. Error handling defined. |
| RAG Implementation & Grounding | 15% | Knowledge base populated with at least 5 sources. Chunking strategy documented and justified. Metadata design is thoughtful. Agent outputs demonstrably grounded in retrieved context with citations. |
| Critic Agent & Revision Loop | 15% | Rubric design covers all 4 dimensions. Feedback quality is specific. Revision loop demonstrated with before / after improvement. Cross-agent consistency checks implemented. |
| Evaluation Framework | 10% | Eval dataset used (and expanded). At least 2 eval methods implemented. Quality badges (Green / Amber / Red) visible. Improvement across revisions demonstrated with specific metrics. |
| Structured Output Contracts | 10% | All 7 agents produce validated JSON. Schemas documented. Downstream agents validate inputs. Contract violations handled gracefully. |
| Guardrails & Safety | 10% | Input validation, schema compliance, hallucination detection, and scope creep prevention implemented. Confidentiality limitations acknowledged. |
| Output Quality (Plans, Designs, Stack) | 10% | Generated artifacts are relevant, detailed, grounded, and actionable. Tech stack analysis is thoughtful. Plan, Schedule, Architecture align with each other. |
| Operationalization & Monitoring | 5% | Success / failure criteria defined upfront. Pre-release gates documented. Logging / monitoring implemented for all agent executions. |
| Documentation & Demo Quality | 5% | Architecture diagram is clear and complete. Documentation covers all required sections. Demo video covers all required segments (7–10 min). Setup instructions reproducible. |

## **Stretch Goal Bonus (up to \+10%)**

# 

# **13\. Learning Goals**

Agentic system design · RAG for domain-grounded AI · quality-first AI development (define evals before building) · evaluation-driven development · responsible AI for enterprise data · production mindset (success upfront, monitoring, pre-release gates) · document intelligence (parsing structured info from complex documents).

# **14\. Stretch Goals**

## **Voice Interface Agent**

Hands-free BRD review and approval: ASR (Whisper) for EM queries · RAG-connected so voice queries retrieve from artifacts or the source BRD · TTS for spoken summaries · voice approval / rejection. Minimum viable: at least two interaction flows working, ASR verified on at least five sample queries, intelligible TTS.

## **Other Directions**

MCP tool servers (expose BRD parsing or retrieval as MCP primitives) · Jira / ClickUp export as user stories and epics · fine-tune a smaller model on BRD section classification for cost reduction · Slack alerts and approval workflows · cross-team multi-EM workflows with shared editing · governance layer with role-based approvals and audit trail · historical insights dashboard across multiple BRDs · advanced RAG (Cohere Rerank, hybrid BM25 \+ vector).

# **15\. Submission Guidelines**

## **What to Submit**

* Complete project repository (GitHub or ZIP) following the suggested project structure.

* README.md with setup instructions, architecture overview, and tool track used.

* Demo video (7–10 minutes) covering all segments listed in Section 10D.

* Documentation package (all 8 documents listed in Section 10C).

* Evaluation report with results and improvement evidence across revisions.

## **Submission Checklist**

| ✓ | Requirement | Section Ref |
| :---- | :---- | :---- |
| ☐ | All 7 agents (Orchestrator \+ Planning Group \+ Design Group \+ Critic) implemented with structured output contracts | Section 4 |
| ☐ | Orchestration pattern chosen, justified, and diagrammed | Section 5 |
| ☐ | RAG pipeline functional with populated knowledge base (at least 5 sources) | Section 6 |
| ☐ | At least 2 evaluation methods implemented with results across all 4 dimensions | Section 7 |
| ☐ | Quality badges (Green / Amber / Red) visible for all artifacts | Section 7C |
| ☐ | Critic Agent with rubric scoring and working revision loop (max 2 cycles) | Section 4D |
| ☐ | Cycle improvement demonstrated on at least 2 metrics with comparison table | Section 7E |
| ☐ | Guardrails implemented (input validation, schema, hallucination, scope creep, confidentiality) | Section 8 |
| ☐ | Success / failure criteria defined; pre-release gates documented | Section 9 |
| ☐ | Monitoring & logging implemented for all agent executions | Section 9B |
| ☐ | At least 1 full BRD demonstrated end-to-end | Section 10A |
| ☐ | Tool calling demonstrated (export \+ at least one external integration) with mock data | Section 3C |
| ☐ | Documentation package complete (all 8 documents) | Section 10C |
| ☐ | Demo video (7–10 min) covering all required segments | Section 10D |

Good luck\! Build something you'd actually want to use with your own team.


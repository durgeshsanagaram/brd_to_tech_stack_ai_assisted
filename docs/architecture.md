# Architecture Overview — Multi-Agent BRD-to-Engineering System

Orchestration pattern: **hub-and-spoke**. A central Orchestrator Agent owns state, routes work,
retries on failure, and aggregates results. Specialist agents never talk to each other directly —
all coordination flows through the Orchestrator and the shared state store. This keeps the
failure blast radius contained to one spoke, makes retries/timeouts uniform, and gives a single
place to enforce the Critic revision cap and guardrails. If BRD volume scaled to 50+/week, the
Orchestrator would shard by BRD (one orchestrator instance per in-flight BRD, horizontally
scaled) and the RAG store would move from local (Chroma/FAISS) to a managed cloud vector DB
(Pinecone/Qdrant) to handle concurrent read load.

## 1. Layered System Diagram

```mermaid
flowchart TB
    subgraph L1["Layer 1 — BRD Ingestion & Parsing"]
        A1[BRD Upload]
        A2[Parser: sections, requirements, NFRs]
        A3[Metadata Tagger]
        A1 --> A2 --> A3
    end

    subgraph L2["Layer 2 — Knowledge Augmentation (RAG)"]
        B1[(Vector DB\nChroma / FAISS)]
        B2[Past BRDs]
        B3[Architecture Pattern Library]
        B4[Engineering Plan Templates]
        B5[Project Timelines]
        B6[Org Engineering Standards]
        B7[Tech-Stack Decision Log]
        B2 & B3 & B4 & B5 & B6 & B7 --> B1
    end

    subgraph L3["Layer 3 — Multi-Agent Generation"]
        O[Orchestrator Agent\nrouting + state + retries]
        subgraph Planning["Planning Group"]
            P1[Engineering Plan Generator\n+ Reflection step]
            P2[Schedule Estimator]
        end
        subgraph Design["Design Group"]
            D1[Solution Architect]
            D2[PoC Planner]
            D3[Tech Stack Recommender]
        end
        O --> P1 --> P2
        O --> D1 --> D2
        O --> D3
    end

    subgraph L4["Layer 4 — Validation & Evaluation"]
        C[Critic Agent\nrubric scoring + revision loop]
        E[Evaluation Framework\nrule-based + LLM-as-judge]
        H{HITL Gate\nEM Approval}
        X[Export: PDF / Markdown / Jira]
    end

    A3 --> O
    O <-->|retrieve context| B1
    P1 & P2 & D1 & D2 & D3 -->|retrieve context| B1
    P1 & P2 & D1 & D2 & D3 --> C
    C -->|score < threshold: revise\nmax 2 cycles| P1
    C -->|score < threshold: revise\nmax 2 cycles| D1
    C -->|approved| E
    E --> H
    H -->|approved| X
    H -->|rejected| O
```

## 2. Data Flow (Sequence)

```mermaid
sequenceDiagram
    participant EM as Engineering Manager
    participant O as Orchestrator
    participant RAG as Vector DB
    participant PL as Planning Group
    participant DS as Design Group
    participant CR as Critic
    participant EV as Eval Framework

    EM->>O: Upload BRD
    O->>O: Validate input (type, structure)
    O->>O: Parse sections, classify requirements, tag metadata
    O->>RAG: Retrieve grounding context (per section)
    RAG-->>O: Top-k chunks + scores
    O->>PL: Dispatch (BRD sections + RAG context)
    PL->>RAG: Retrieve (plan/schedule specific)
    PL-->>O: Plan + Schedule (JSON, draft)
    O->>DS: Dispatch (BRD sections + RAG context)
    DS->>RAG: Retrieve (architecture/PoC/stack specific)
    DS-->>O: Architecture + PoC + Stack options (JSON, draft)
    O->>CR: Submit all outputs for review
    CR->>CR: Score: groundedness, completeness,\nconsistency, actionability
    alt any dimension below threshold (cycle < 2)
        CR-->>O: Revision feedback (targeted, per-agent)
        O->>PL: Revise
        O->>DS: Revise
        PL-->>O: Revised output
        DS-->>O: Revised output
        O->>CR: Re-submit
    end
    CR-->>O: Final scores + badge (Green/Amber/Red)
    O->>EV: Run eval suite (rule-based + LLM-as-judge)
    EV-->>O: Eval report
    O->>EM: Present artifacts + citations + badges
    EM->>O: Approve / Reject (HITL)
    O->>O: Export (PDF / Markdown / Jira) on approval
```

## 3. Critic Revision Loop (State Machine)

```mermaid
stateDiagram-v2
    [*] --> Drafted
    Drafted --> UnderReview: submit to Critic
    UnderReview --> Approved: all dimensions >= threshold
    UnderReview --> Revising: dimension below threshold\n(revision_count < 2)
    Revising --> UnderReview: resubmit
    UnderReview --> Escalated: revision_count == 2 and still below threshold
    Approved --> [*]: Green/Amber badge
    Escalated --> [*]: Amber/Red badge, flagged to EM
```

## 4. Component / Tool Mapping (reference)

| Component | Example Tool Choice |
| :---- | :---- |
| Orchestration | LangGraph (code track) or n8n workflow (low-code track) |
| Vector DB | Chroma / FAISS (local) or Pinecone / Qdrant (cloud) |
| Embeddings | `text-embedding-3-small` (cost) or `text-embedding-3-large` (quality) |
| LLM (generation + judge) | Claude / GPT-4-class model, temperature low for structured output |
| Schema validation | Pydantic (Python) or JSON Schema + ajv (n8n/JS) |
| Export | Markdown renderer, PDF via wkhtmltopdf/pandoc, Jira REST API (mock) |
| Logging | Structured JSON logs, BRD content hashed (SHA-256), never raw-logged |

#!/usr/bin/env python3
"""
Ingest the synthetic knowledge base (kb/) into a local Chroma vector store.

Chunking strategy, metadata schema, and source-type handling follow
docs/rag_design.md:

  - narrative sources (past_brd, plan_template, org_standard) are split on
    markdown H2 (##) section headers, then token-chunked with a source-type
    specific max size and overlap
  - atomic sources (architecture_pattern) are embedded as one chunk per file
    -- splitting a pattern's name away from its trade-offs would produce an
    unattributable claim
  - tabular sources (project_timeline, tech_stack_decision) are embedded one
    chunk per CSV row -- a row is the smallest unit of meaning

Usage:
    python scripts/ingest.py                 # ingest kb/ into ./chroma_db
    python scripts/ingest.py --reset         # wipe and rebuild the collection
    python scripts/ingest.py --dry-run       # print chunk counts/preview only
"""
import argparse
import csv
import re
from pathlib import Path

import tiktoken

from common import build_collection

KB_ROOT = Path(__file__).resolve().parent.parent / "kb"

# directory name -> (source_type, file kind)
SOURCE_DIRS = {
    "past_brds": ("past_brd", "markdown"),
    "plan_templates": ("plan_template", "markdown"),
    "architecture_patterns": ("architecture_pattern", "markdown"),
    "org_standards": ("org_standard", "markdown"),
    "project_timelines": ("project_timeline", "csv"),
    "tech_stack_decisions": ("tech_stack_decision", "csv"),
}

# source_type -> chunking config; absence of an entry means "one chunk per file"
CHUNK_CONFIG = {
    "past_brd": {"max_tokens": 400, "overlap_tokens": 50},
    "plan_template": {"max_tokens": 300, "overlap_tokens": 30},
    "org_standard": {"max_tokens": 250, "overlap_tokens": 20},
}

ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(ENCODING.encode(text))


def token_chunk(text: str, max_tokens: int, overlap_tokens: int):
    """Split text into <=max_tokens pieces with overlap_tokens of trailing
    context carried into the next piece. Returns the whole text as a single
    chunk if it's already under the limit."""
    tokens = ENCODING.encode(text)
    if len(tokens) <= max_tokens:
        return [text]
    pieces = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        pieces.append(ENCODING.decode(tokens[start:end]))
        if end == len(tokens):
            break
        start = end - overlap_tokens
    return pieces


def parse_frontmatter(raw: str):
    """Minimal YAML frontmatter parser -- avoids a PyYAML dependency for the
    small, flat key: value / key: [a, b, c] frontmatter used in kb/*.md."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
    if not match:
        raise ValueError("File is missing --- frontmatter delimiters")
    fm_block, body = match.group(1), match.group(2)
    frontmatter = {}
    for line in fm_block.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            items = [v.strip() for v in value[1:-1].split(",") if v.strip()]
            frontmatter[key] = items
        elif value == "null":
            frontmatter[key] = None
        else:
            frontmatter[key] = value
    return frontmatter, body


def split_sections(body: str):
    """Split a markdown body into (section_title, section_text) on H2 (##)
    headers. Text before the first H2 (e.g. the H1 title / intro) is kept as
    an 'Overview' section rather than dropped."""
    sections = []
    current_title = "Overview"
    current_lines = []
    for line in body.splitlines():
        header = re.match(r"^##\s+(.*)", line)
        if header:
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = header.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return [(title, text) for title, text in sections if text]


def chunk_markdown_file(path: Path, source_type: str):
    frontmatter, body = parse_frontmatter(path.read_text())
    config = CHUNK_CONFIG.get(source_type)

    pieces = []  # list of (section_title, text)
    if config is None:
        # atomic source (architecture_pattern): whole file, one chunk
        pieces.append((None, body.strip()))
    else:
        for title, section_text in split_sections(body):
            for piece in token_chunk(section_text, config["max_tokens"], config["overlap_tokens"]):
                pieces.append((title, piece))

    chunks = []
    for i, (section_title, text) in enumerate(pieces):
        chunk_id = f"{frontmatter['source_id']}#{i}"
        chunks.append(
            {
                "id": chunk_id,
                "text": text,
                "metadata": {
                    "source_id": frontmatter["source_id"],
                    "source_type": frontmatter["source_type"],
                    "chunk_id": chunk_id,
                    "title": frontmatter.get("title") or "",
                    "section": section_title or "",
                    "domain": frontmatter.get("domain") or "",
                    "complexity": frontmatter.get("complexity") or "",
                    "tags": ",".join(frontmatter.get("tags") or []),
                    "created_at": str(frontmatter.get("created_at") or ""),
                    "token_count": count_tokens(text),
                },
            }
        )
    return chunks


# CSV row -> natural-language chunk text, per source_type
ROW_TEMPLATES = {
    "project_timeline": lambda r: (
        f"Project {r['title']} ({r['domain']}, {r['complexity']} complexity): "
        f"took {r['duration_weeks']} weeks with a team of {r['team_size']}, "
        f"variance {r['variance_pct']}%. {r['notes']}"
    ),
    "tech_stack_decision": lambda r: (
        f"Decision {r['decision_id']} ({r['date']}, {r['project_domain']}): "
        f"chose {r['stack_name']}. Rationale: {r['rationale']} "
        f"Outcome: {r['outcome']}"
    ),
}


def chunk_csv_file(path: Path, source_type: str):
    chunks = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            text = ROW_TEMPLATES[source_type](row)
            row_id = row.get("project_id") or row.get("decision_id")
            chunk_id = f"{row_id}#0"
            domain = row.get("domain") or row.get("project_domain") or ""
            chunks.append(
                {
                    "id": chunk_id,
                    "text": text,
                    "metadata": {
                        "source_id": row_id,
                        "source_type": source_type,
                        "chunk_id": chunk_id,
                        "title": row.get("title") or row.get("stack_name") or "",
                        "section": "",
                        "domain": domain,
                        "complexity": row.get("complexity") or "",
                        "tags": "",
                        "created_at": row.get("date") or "",
                        "token_count": count_tokens(text),
                    },
                }
            )
    return chunks


def load_all_chunks():
    all_chunks = []
    for dirname, (source_type, filetype) in SOURCE_DIRS.items():
        dir_path = KB_ROOT / dirname
        if not dir_path.exists():
            continue
        for path in sorted(dir_path.iterdir()):
            if filetype == "markdown" and path.suffix == ".md":
                all_chunks.extend(chunk_markdown_file(path, source_type))
            elif filetype == "csv" and path.suffix == ".csv":
                all_chunks.extend(chunk_csv_file(path, source_type))
    return all_chunks


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--persist-dir", default="./chroma_db")
    parser.add_argument("--reset", action="store_true", help="wipe and rebuild the collection")
    parser.add_argument("--dry-run", action="store_true", help="print chunk stats/preview, skip embedding")
    args = parser.parse_args()

    chunks = load_all_chunks()
    print(f"Loaded {len(chunks)} chunks from {KB_ROOT}")

    by_type = {}
    for c in chunks:
        st = c["metadata"]["source_type"]
        by_type[st] = by_type.get(st, 0) + 1
    for source_type, n in sorted(by_type.items()):
        print(f"  {source_type}: {n} chunks")

    if args.dry_run:
        print("\n--dry-run: previewing first 3 chunks, no embedding/writing performed\n")
        for c in chunks[:3]:
            print(f"[{c['id']}] {c['metadata']}")
            print(f"  {c['text'][:160]}...\n")
        return

    collection = build_collection(args.persist_dir, reset=args.reset)
    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )
    print(f"Upserted {len(chunks)} chunks into '{collection.name}' at {args.persist_dir}")


if __name__ == "__main__":
    main()

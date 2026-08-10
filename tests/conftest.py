import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from common import build_collection  # noqa: E402
from ingest import load_all_chunks  # noqa: E402


@pytest.fixture(scope="session")
def kb_collection(tmp_path_factory):
    """A real Chroma collection built from the actual kb/ content, in an
    isolated temp directory -- never touches the repo's own ./chroma_db.
    Uses whatever embedding function scripts/common.py picks (OpenAI if
    OPENAI_API_KEY is set, else the local fallback), same as every script --
    these are real retrieval tests against real embeddings, not mocked ones.
    Session-scoped: ingestion is real work (chunking + embedding calls), so
    it's done once and every test in this run shares the result."""
    persist_dir = tmp_path_factory.mktemp("chroma_db")
    chunks = load_all_chunks()
    collection = build_collection(str(persist_dir), reset=True)
    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )
    return collection

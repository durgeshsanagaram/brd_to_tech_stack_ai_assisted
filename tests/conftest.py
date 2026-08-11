import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
FIXTURES_DIR = REPO_ROOT / "fixtures"
sys.path.insert(0, str(SCRIPTS_DIR))

from common import build_collection  # noqa: E402
from ingest import load_all_chunks  # noqa: E402


def _load_fixture(name):
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture
def parsed_brd():
    """Fresh copy every test -- callers are free to mutate it."""
    return _load_fixture("parsed_brd_brd-002.json")


@pytest.fixture
def engineering_plan_rev0():
    """The deliberately-flawed draft: no citations, one fabricated claim,
    5 of 10 requirements addressed. See docs/evaluation_report.md Section 4."""
    return _load_fixture("engineering_plan_brd-002_rev0.json")


@pytest.fixture
def engineering_plan_rev1():
    """The corrected revision: real citations, all 10 requirements addressed."""
    return _load_fixture("engineering_plan_brd-002_rev1.json")


@pytest.fixture
def retrieved_chunks():
    return _load_fixture("retrieved_chunks_run-001_plan_generator.json")


@pytest.fixture(scope="session")
def kb_persist_dir(tmp_path_factory):
    """An isolated Chroma persist directory, freshly ingested from the real
    kb/ content -- never touches the repo's own ./chroma_db, which can be in
    either embedding mode depending on what was last run there (mixing modes
    raises, per README's "Don't mix modes" note). Uses whatever embedding
    function scripts/common.py picks (OpenAI if OPENAI_API_KEY is set, else
    the local fallback), consistently for the whole test session."""
    persist_dir = tmp_path_factory.mktemp("chroma_db")
    chunks = load_all_chunks()
    collection = build_collection(str(persist_dir), reset=True)
    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )
    return persist_dir


@pytest.fixture(scope="session")
def kb_collection(kb_persist_dir):
    """The Chroma collection object for kb_persist_dir -- these are real
    retrieval tests against real embeddings, not mocked ones."""
    return build_collection(str(kb_persist_dir))

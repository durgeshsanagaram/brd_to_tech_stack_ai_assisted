"""
Shared Chroma client / embedding-function setup, used by both ingest.py and
query.py so the two scripts can never drift out of sync on collection name,
embedding model, or distance metric.

Embedding model and vector DB choices are documented in docs/rag_design.md
(Sections 4 and 5): text-embedding-3-small by default, Chroma persisted to
local disk at ./chroma_db, cosine distance space.
"""
import os

import chromadb
from chromadb.utils import embedding_functions

COLLECTION_NAME = "brd_knowledge_base"
EMBEDDING_MODEL = "text-embedding-3-small"


def get_embedding_function():
    """Use OpenAI text-embedding-3-small when a key is available (the model
    documented in docs/rag_design.md). Fall back to Chroma's bundled local
    all-MiniLM-L6-v2 model otherwise, so the KB can still be built and queried
    offline for grading/demo without requiring an API key. The fallback is
    loudly flagged since it changes retrieval quality/dimensionality versus
    the documented design.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key, model_name=EMBEDDING_MODEL
        )
    print(
        "WARNING: OPENAI_API_KEY not set -- falling back to Chroma's bundled "
        "all-MiniLM-L6-v2 embedding model for local/offline use. This does not "
        "match the text-embedding-3-small choice documented in docs/rag_design.md. "
        "Set OPENAI_API_KEY and re-run --reset to match the documented design.",
    )
    return embedding_functions.DefaultEmbeddingFunction()


def build_collection(persist_dir: str, reset: bool = False):
    client = chromadb.PersistentClient(
        path=persist_dir, settings=chromadb.Settings(anonymized_telemetry=False)
    )
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=get_embedding_function(),
        metadata={"hnsw:space": "cosine"},
    )

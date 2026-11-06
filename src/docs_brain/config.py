"""Paths and settings shared by ingestion, retrieval and the server."""

import os
from pathlib import Path

# Project root. Override with DOCS_BRAIN_HOME if the package is installed elsewhere.
ROOT = Path(os.environ.get("DOCS_BRAIN_HOME", Path(__file__).resolve().parents[2]))

DATA_DIR = ROOT / "data"
REPO_DIR = DATA_DIR / "raw" / "fastapi"  # sparse clone of github.com/fastapi/fastapi
DOCS_DIR = REPO_DIR / "docs" / "en" / "docs"  # Markdown pages
MKDOCS_DIR = REPO_DIR / "docs" / "en"  # `{* ../../docs_src/... *}` includes resolve from here
CHROMA_DIR = DATA_DIR / "chroma"
CHUNKS_FILE = DATA_DIR / "chunks.jsonl"  # every chunk with metadata, used for BM25 and lookups

COLLECTION = "fastapi_docs"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
# Reranker used when DOCS_BRAIN_MODE=hybrid_rerank. MiniLM is ~6x faster than bge-reranker-base
# on CPU (see eval/results.md).
RERANK_MODEL = os.environ.get("DOCS_BRAIN_RERANKER", "cross-encoder/ms-marco-MiniLM-L6-v2")

# ~4 characters per token, so 1600 chars is roughly 400 tokens (bge-small accepts 512).
MAX_CHUNK_CHARS = 1600
MAX_CODE_LINES = 60  # cap on lines inlined from one code-example include

DOCS_BASE_URL = "https://fastapi.tiangolo.com/"

# Retrieval mode the MCP server uses: dense | bm25 | hybrid | hybrid_rerank
# Default is hybrid: in eval/results.md it beat both rerankers on recall@1 at a fraction
# of the latency.
SERVER_MODE = os.environ.get("DOCS_BRAIN_MODE", "hybrid")

# Planted prompt-injection page for the security demo. Indexed only with
# `python -m docs_brain.ingest --with-demo-poison`.
DEMO_PAGES = {"security-demo/poisoned.md": ROOT / "tests" / "fixtures" / "poisoned.md"}

# Pages that are changelogs or site meta, not documentation. They would crowd out real answers.
EXCLUDE = {
    "release-notes.md",
    "_llm-test.md",
    "translation-banner.md",
    "fastapi-people.md",
    "management.md",
    "management-tasks.md",
    "newsletter.md",
    "external-links.md",
}

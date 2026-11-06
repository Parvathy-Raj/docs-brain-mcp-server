"""Dense, BM25, hybrid (reciprocal rank fusion) and reranked retrieval over the indexed chunks."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Literal

from docs_brain import config
from docs_brain.ingest import Chunk, embed_text, load_chunks, tokenize

Mode = Literal["dense", "bm25", "hybrid", "hybrid_rerank"]
MODES: tuple[Mode, ...] = ("dense", "bm25", "hybrid", "hybrid_rerank")

# bge models expect this instruction in front of queries (not in front of passages).
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
CANDIDATES = 50  # how many results each retriever feeds into fusion
RERANK_POOL = 20  # how many fused results the cross-encoder rescoring sees
RRF_K = 60


def load_model(cls, name: str, **kwargs):
    """Load from the local HuggingFace cache first, so the server starts offline and fast.
    Downloads only when the model is not cached yet."""
    try:
        return cls(name, device="cpu", local_files_only=True, **kwargs)
    except Exception:
        return cls(name, device="cpu", **kwargs)


@dataclass
class Hit:
    chunk: Chunk
    score: float


def rrf(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal rank fusion: score(d) = sum over rankings of 1 / (k + rank)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


class Retriever:
    """Loads the indexes once. Models load lazily so BM25-only use stays fast."""

    def __init__(self, rerank_model: str = config.RERANK_MODEL) -> None:
        import chromadb
        from rank_bm25 import BM25Okapi

        if not config.CHUNKS_FILE.exists():
            sys.exit("No index found. Run `python -m docs_brain.ingest` first.")
        self.chunks = load_chunks()
        self.by_id = {c.chunk_id: c for c in self.chunks}
        self.bm25 = BM25Okapi([tokenize(embed_text(c)) for c in self.chunks])
        client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        self.collection = client.get_collection(config.COLLECTION)
        self.rerank_model = rerank_model
        self._embedder = None
        self._rerankers: dict[str, object] = {}

    # -- models --

    @property
    def embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer

            self._embedder = load_model(SentenceTransformer, config.EMBED_MODEL)
        return self._embedder

    @property
    def reranker(self):
        if self.rerank_model not in self._rerankers:
            from sentence_transformers import CrossEncoder

            self._rerankers[self.rerank_model] = load_model(
                CrossEncoder, self.rerank_model, max_length=512
            )
        return self._rerankers[self.rerank_model]

    def warm_up(self) -> None:
        """Load both models now instead of on the first query."""
        self.embedder.encode(["warm up"])
        self.reranker.predict([("warm up", "warm up")])

    # -- retrievers --

    def dense(self, query: str, n: int = CANDIDATES) -> list[tuple[str, float]]:
        vec = self.embedder.encode([QUERY_PREFIX + query], normalize_embeddings=True)
        res = self.collection.query(query_embeddings=vec.tolist(), n_results=n)
        # Chroma returns cosine distance; 1 - distance is the similarity.
        return [(i, 1.0 - d) for i, d in zip(res["ids"][0], res["distances"][0], strict=True)]

    def keyword(self, query: str, n: int = CANDIDATES) -> list[tuple[str, float]]:
        scores = self.bm25.get_scores(tokenize(query))
        top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n]
        return [(self.chunks[i].chunk_id, float(scores[i])) for i in top if scores[i] > 0]

    def rerank(self, query: str, ids: list[str]) -> list[tuple[str, float]]:
        pairs = [(query, embed_text(self.by_id[i])) for i in ids]
        scores = self.reranker.predict(pairs, batch_size=16)
        return sorted(zip(ids, map(float, scores), strict=True), key=lambda kv: kv[1], reverse=True)

    # -- public --

    def search(self, query: str, top_k: int = 5, mode: Mode = "hybrid_rerank") -> list[Hit]:
        if mode == "dense":
            ranked = self.dense(query)
        elif mode == "bm25":
            ranked = self.keyword(query)
        else:
            fused = rrf([[i for i, _ in self.dense(query)], [i for i, _ in self.keyword(query)]])
            ranked = fused
            if mode == "hybrid_rerank":
                ranked = self.rerank(query, [i for i, _ in fused[:RERANK_POOL]])
        return [Hit(self.by_id[i], s) for i, s in ranked[:top_k]]

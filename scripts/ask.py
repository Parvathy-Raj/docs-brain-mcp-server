"""Type questions and see what Docs Brain retrieves. Good for testing by hand.

    python scripts/ask.py                 # hybrid (the server default)
    python scripts/ask.py --compare       # dense vs BM25 vs hybrid side by side

Commands at the prompt:  :mode dense|bm25|hybrid|hybrid_rerank   :compare   :quit
"""

from __future__ import annotations

import argparse
import sys
import time

from docs_brain.guard import scan
from docs_brain.retrieve import MODES, Retriever

sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252


def show(r: Retriever, query: str, mode: str, top_k: int = 5) -> None:
    t0 = time.perf_counter()
    hits = r.search(query, top_k=top_k, mode=mode)
    ms = (time.perf_counter() - t0) * 1000
    print(f"\n[{mode}] {ms:.0f} ms")
    for i, h in enumerate(hits, 1):
        g = scan(h.chunk.text)
        flag = "  [FLAGGED: " + ", ".join(g.reasons) + "]" if g.flagged else ""
        preview = " ".join(g.text.split())[:160]
        print(f" {i}. {h.chunk.path}  >  {h.chunk.heading_path}{flag}")
        print(f"    {preview}...")


def compare(r: Retriever, query: str) -> None:
    print()
    for mode in ("dense", "bm25", "hybrid"):
        pages = [h.chunk.path for h in r.search(query, top_k=5, mode=mode)]
        print(f" {mode:7} {pages}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="hybrid", choices=MODES)
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args()

    print("Loading index and models...")
    r = Retriever()
    r.embedder.encode(["warm up"])
    mode, cmp = args.mode, args.compare
    print("Ready. Ask about FastAPI. Commands: :mode <name>  :compare  :quit")
    while True:
        try:
            q = input(f"\n({'compare' if cmp else mode}) > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q in (":q", ":quit", "exit"):
            break
        if q == ":compare":
            cmp = not cmp
            continue
        if q.startswith(":mode"):
            name = q.split(maxsplit=1)[-1]
            if name in MODES:
                mode, cmp = name, False
            else:
                print(f"modes: {', '.join(MODES)}")
            continue
        compare(r, q) if cmp else show(r, q, mode)


if __name__ == "__main__":
    main()

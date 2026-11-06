"""Load the docs, split them by heading, and build the dense (Chroma) and BM25 indexes.

Run:  python -m docs_brain.ingest
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from docs_brain import config

HEADING_RE = re.compile(r"^(#{1,3})\s+(.*?)\s*(?:\{\s*#([\w-]+)\s*\})?\s*$")
INCLUDE_RE = re.compile(r"^\{\*\s*(\S+)(.*?)\*\}\s*$")
ADMONITION_RE = re.compile(r"^/{3,4}\s*(\w+)?\s*(?:\|\s*(.*))?$")
DFN_RE = re.compile(r'<(?:dfn|abbr)\s+title="([^"]*)"\s*>(.*?)</(?:dfn|abbr)>')
TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
TOKEN_RE = re.compile(r"[a-z0-9_]+")


@dataclass
class Chunk:
    chunk_id: str
    path: str  # relative to the docs folder, forward slashes
    title: str  # page H1
    heading: str  # nearest heading
    heading_path: str  # "Title > Section > Subsection"
    anchor: str  # heading anchor, so citations can link to path#anchor
    text: str


def tokenize(text: str) -> list[str]:
    """Tokenizer for BM25. Keeps underscores so names like `response_model` stay whole."""
    return TOKEN_RE.findall(text.lower())


# ---------- cleaning ----------


def _expand_include(target: str, args: str) -> list[str]:
    """Inline a `{* ../../docs_src/x.py ln[3:9] hl[4] *}` code example as a fenced block."""
    path = (config.MKDOCS_DIR / target).resolve()
    if not path.is_file():
        return [f"(code example: {target})"]
    lines = path.read_text(encoding="utf-8").splitlines()
    ranges = re.search(r"ln\[([\d:,]+)\]", args)
    if ranges:
        picked: list[str] = []
        for part in ranges.group(1).split(","):
            start, _, end = part.partition(":")
            picked += lines[int(start) - 1 : int(end or start)]
        lines = picked
    # Very long lines are data blobs (e.g. base64 images) with no search value.
    lines = [ln if len(ln) <= 200 else ln[:80] + " ... (long line truncated)" for ln in lines]
    if len(lines) > config.MAX_CODE_LINES:
        lines = lines[: config.MAX_CODE_LINES] + ["# ... (truncated)"]
    name = target.split("docs_src/")[-1]
    return ["```python", f"# file: {name}", *lines, "```"]


def clean_markdown(text: str) -> str:
    """Turn MkDocs-flavoured Markdown into plain Markdown. Code fences are left untouched."""
    out: list[str] = []
    in_fence = False
    in_mkdocstrings = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        # `::: fastapi.APIRouter` blocks are API-reference stubs rendered by a plugin.
        if line.startswith(":::"):
            in_mkdocstrings = True
            continue
        if in_mkdocstrings:
            if line.startswith((" ", "\t")) or not line.strip():
                continue
            in_mkdocstrings = False
        if m := INCLUDE_RE.match(line.strip()):
            out += _expand_include(m.group(1), m.group(2))
            continue
        if m := ADMONITION_RE.match(line.strip()):
            kind, label = m.group(1), m.group(2)
            if kind == "tab" and label:
                out.append(f"**{label.strip()}:**")
            elif kind:
                out.append(f"**{(label or kind).strip().capitalize()}:**")
            continue  # bare `///` closes a block
        if line.strip() == "---":
            continue
        line = DFN_RE.sub(r"\2 (\1)", line)
        line = TAG_RE.sub("", line)
        out.append(line)
    cleaned = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


# ---------- splitting ----------


def _split_sections(text: str) -> list[tuple[int, str, str, list[str]]]:
    """Split on H1-H3 headings outside code fences. Returns (level, heading, anchor, body lines)."""
    sections: list[tuple[int, str, str, list[str]]] = [(0, "", "", [])]
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        m = None if in_fence else HEADING_RE.match(line)
        if m:
            heading = m.group(2).replace("`", "").strip()
            sections.append((len(m.group(1)), heading, m.group(3) or "", []))
        else:
            sections[-1][3].append(line)
    return sections


def _blocks(lines: list[str]) -> list[str]:
    """Group lines into paragraphs, never splitting inside a code fence."""
    blocks, current, in_fence = [], [], False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not line.strip() and not in_fence:
            if current:
                blocks.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _split_long_block(block: str, max_chars: int) -> list[str]:
    """Cut one oversized paragraph or code block by lines. Code pieces get their fences back."""
    lines = block.splitlines()
    fence = lines[0] if lines[0].lstrip().startswith("```") else None
    if fence:
        lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
    parts, current, size = [], [], 0
    for line in lines:
        if current and size + len(line) > max_chars - 20:
            parts.append(current)
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        parts.append(current)
    if fence:
        return ["\n".join([fence, *p, "```"]) for p in parts]
    return ["\n".join(p) for p in parts]


def _pack(blocks: list[str], max_chars: int) -> list[str]:
    """Pack paragraphs into pieces of at most max_chars, repeating the last paragraph as overlap
    when it is short."""
    blocks = [
        b
        for block in blocks
        for b in (_split_long_block(block, max_chars) if len(block) > max_chars else [block])
    ]
    pieces, current = [], []
    for block in blocks:
        if current and len("\n\n".join([*current, block])) > max_chars:
            pieces.append("\n\n".join(current))
            overlap = current[-1] if len(current[-1]) < max_chars // 4 else None
            current = [overlap] if overlap else []
        current.append(block)
    if current:
        pieces.append("\n\n".join(current))
    return pieces


def chunk_page(rel_path: str, raw: str, max_chars: int = config.MAX_CHUNK_CHARS) -> list[Chunk]:
    text = clean_markdown(raw)
    sections = _split_sections(text)
    title = next((h for lvl, h, _, _ in sections if lvl == 1), Path(rel_path).stem)
    chunks: list[Chunk] = []
    stack: dict[int, str] = {}
    for level, heading, anchor, body in sections:
        if level:
            stack = {k: v for k, v in stack.items() if k < level}
            stack[level] = heading
        body_text = "\n".join(body).strip()
        if len(body_text) < 40:  # heading with no real content
            continue
        heading_path = " > ".join(stack[k] for k in sorted(stack)) or title
        for piece in _pack(_blocks(body), max_chars):
            chunks.append(
                Chunk(
                    chunk_id=f"{rel_path}#{anchor or 'top'}:{len(chunks)}",
                    path=rel_path,
                    title=title,
                    heading=heading or title,
                    heading_path=heading_path,
                    anchor=anchor,
                    text=piece,
                )
            )
    return chunks


def iter_pages(docs_dir: Path = config.DOCS_DIR, demo_poison: bool = False):
    for md in sorted(docs_dir.rglob("*.md")):
        rel = md.relative_to(docs_dir).as_posix()
        if rel in config.EXCLUDE:
            continue
        yield rel, md.read_text(encoding="utf-8")
    if demo_poison:
        for rel, file in config.DEMO_PAGES.items():
            yield rel, file.read_text(encoding="utf-8")


def page_file(rel_path: str) -> Path:
    """Where an indexed page lives on disk."""
    return config.DEMO_PAGES.get(rel_path, config.DOCS_DIR / rel_path)


def load_chunks() -> list[Chunk]:
    with config.CHUNKS_FILE.open(encoding="utf-8") as f:
        return [Chunk(**json.loads(line)) for line in f]


def embed_text(chunk: Chunk) -> str:
    """What gets embedded: the heading path gives the chunk context it would otherwise lack."""
    return f"{chunk.heading_path}\n\n{chunk.text}"


# ---------- index build ----------


def build(docs_dir: Path = config.DOCS_DIR, demo_poison: bool = False) -> None:
    import chromadb
    from sentence_transformers import SentenceTransformer

    if not docs_dir.is_dir():
        sys.exit(f"Docs not found at {docs_dir}. See README for the clone command.")

    t0 = time.time()
    pages = list(iter_pages(docs_dir, demo_poison))
    chunks = [c for rel, raw in pages for c in chunk_page(rel, raw)]
    print(f"{len(pages)} pages -> {len(chunks)} chunks", file=sys.stderr)

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with config.CHUNKS_FILE.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")

    model = SentenceTransformer(config.EMBED_MODEL, device="cpu")
    vectors = model.encode(
        [embed_text(c) for c in chunks],
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    try:
        client.delete_collection(config.COLLECTION)
    except Exception:  # collection didn't exist yet
        pass
    col = client.create_collection(config.COLLECTION, metadata={"hnsw:space": "cosine"})
    batch = 500
    for i in range(0, len(chunks), batch):
        part = chunks[i : i + batch]
        col.add(
            ids=[c.chunk_id for c in part],
            embeddings=vectors[i : i + batch].tolist(),
            documents=[c.text for c in part],
            metadatas=[
                {
                    "path": c.path,
                    "title": c.title,
                    "heading": c.heading,
                    "heading_path": c.heading_path,
                    "anchor": c.anchor,
                }
                for c in part
            ],
        )
    sizes = sorted(len(c.text) for c in chunks)
    print(
        f"Indexed {col.count()} chunks in {time.time() - t0:.0f}s "
        f"(median {sizes[len(sizes) // 2]} chars, max {sizes[-1]})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-demo-poison",
        action="store_true",
        help="also index tests/fixtures/poisoned.md to demo the prompt-injection guard",
    )
    build(demo_poison=parser.parse_args().with_demo_poison)

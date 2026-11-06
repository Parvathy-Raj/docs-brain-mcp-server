"""Server tool tests with a fake retriever, so no models or index are needed."""

from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from docs_brain import server
from docs_brain.ingest import chunk_page
from docs_brain.retrieve import Hit

POISONED = Path(__file__).parent / "fixtures" / "poisoned.md"
CORS = "# CORS { #cors }\n\n## Use CORSMiddleware { #use-corsmiddleware }\n\n" + (
    "Add CORSMiddleware to your app to allow requests from other origins. " * 30
)


class FakeRetriever:
    def __init__(self):
        self.chunks = chunk_page("tutorial/cors.md", CORS) + chunk_page(
            "security-demo/poisoned.md", POISONED.read_text(encoding="utf-8")
        )

    def search(self, query, top_k=5, mode="hybrid"):
        return [Hit(c, 1.0 / (i + 1)) for i, c in enumerate(self.chunks)][:top_k]


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    monkeypatch.setattr(server, "_retriever", FakeRetriever())
    server._ready.set()


def test_search_returns_capped_structured_results():
    res = server.search_docs("cors", top_k=3)
    assert [r.rank for r in res.results] == [1, 2, 3]
    first = res.results[0]
    assert first.path == "tutorial/cors.md"
    assert first.url == "https://fastapi.tiangolo.com/tutorial/cors/#use-corsmiddleware"
    assert len(first.snippet) <= server.SNIPPET_CHARS + 4


def test_search_flags_and_strips_injection():
    res = server.search_docs("cache", top_k=10)
    flagged = [r for r in res.results if r.flagged]
    assert flagged, "poisoned chunks should be flagged"
    assert all("Ignore all previous" not in r.snippet for r in res.results)
    assert all("[removed: possible prompt injection]" in r.snippet for r in flagged)


def test_search_validates_input():
    with pytest.raises(ToolError):
        server.search_docs("   ")
    assert len(server.search_docs("x", top_k=500).results) <= server.MAX_TOP_K


@pytest.mark.parametrize(
    "path", ["../../../.env", "/etc/passwd", "C:\\Windows\\win.ini", "tutorial/../../../../.env"]
)
def test_get_page_blocks_paths_outside_docs(path):
    with pytest.raises(ToolError, match="outside the docs"):
        server.get_page(path)


def test_get_page_unknown_page_suggests_matches():
    with pytest.raises(ToolError, match="Did you mean: tutorial/cors.md"):
        server.get_page("tutorial/corss")


def test_get_page_accepts_url_and_sanitizes():
    page = server.get_page("security-demo/poisoned.md")
    assert page.flagged and "disable authentication" not in page.content


@pytest.mark.parametrize(
    ("path", "url"),
    [
        ("index.md", "https://fastapi.tiangolo.com/"),
        ("tutorial/dependencies/index.md", "https://fastapi.tiangolo.com/tutorial/dependencies/"),
        ("async.md", "https://fastapi.tiangolo.com/async/"),
    ],
)
def test_doc_url(path, url):
    assert server.doc_url(path) == url


def test_normalize_path():
    assert (
        server.normalize_path("https://fastapi.tiangolo.com/tutorial/cors/") == "tutorial/cors.md"
    )
    assert server.normalize_path("./tutorial\\cors.md#x") == "tutorial/cors.md"


def test_list_sections_groups_pages():
    groups = {s.section: [p.path for p in s.pages] for s in server.list_sections()}
    assert groups["tutorial"] == ["tutorial/cors.md"]

from docs_brain.ingest import chunk_page, clean_markdown, tokenize

PAGE = """# Dependencies { #dependencies }

**FastAPI** has a <dfn title="also known as components">Dependency Injection</dfn> system.

## First Steps { #first-steps }

Let's see a very simple example that is long enough to be a real chunk of text.

/// tip | Important

Use `Annotated` for dependencies, it is the recommended style.

///

### Create a dependency { #create-a-dependency }

It is just a function that can take all the same parameters as a path operation.

```python
# a comment that looks like a heading must not split the chunk
def common(q: str | None = None):
    return {"q": q}
```

---

::: fastapi.Depends
    options:
        members: true

## Empty { #empty }

"""


def test_clean_removes_mkdocs_syntax():
    out = clean_markdown(PAGE)
    assert "///" not in out
    assert ":::" not in out
    assert "options:" not in out
    assert "<dfn" not in out
    assert "Dependency Injection (also known as components)" in out
    assert "**Important:**" in out


def test_chunks_keep_metadata_and_heading_path():
    chunks = chunk_page("tutorial/dependencies/index.md", PAGE)
    by_anchor = {c.anchor: c for c in chunks}
    assert set(by_anchor) == {"dependencies", "first-steps", "create-a-dependency"}
    c = by_anchor["create-a-dependency"]
    assert c.title == "Dependencies"
    assert c.heading == "Create a dependency"
    assert c.heading_path == "Dependencies > First Steps > Create a dependency"
    assert c.path == "tutorial/dependencies/index.md"


def test_code_comment_is_not_a_heading():
    chunks = chunk_page("x.md", PAGE)
    code_chunk = next(c for c in chunks if "def common" in c.text)
    assert "# a comment that looks like a heading" in code_chunk.text


def test_heading_only_sections_are_skipped():
    assert all(c.anchor != "empty" for c in chunk_page("x.md", PAGE))


def test_long_sections_are_split_with_balanced_fences():
    body = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(20))
    code = "```python\n" + "\n".join(f"x{i} = {i}" for i in range(400)) + "\n```"
    chunks = chunk_page("long.md", f"# Long\n\n{body}\n\n{code}\n", max_chars=800)
    assert len(chunks) > 5
    assert all(len(c.text) <= 1000 for c in chunks)
    assert all(c.text.count("```") % 2 == 0 for c in chunks)


def test_tokenize_keeps_identifiers_whole():
    assert tokenize("Use response_model=Item") == ["use", "response_model", "item"]

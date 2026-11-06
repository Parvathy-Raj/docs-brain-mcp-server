"""Record a real MCP session with the server and render it as docs/demo.gif.

    python scripts/make_demo_gif.py

Every line in the GIF comes from an actual stdio session with `python -m docs_brain.server`,
the same transport Claude Desktop uses. Nothing is typed in by hand.
"""

from __future__ import annotations

import asyncio
import sys
import textwrap
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "demo.gif"

QUERIES = [
    ("my endpoint sends an email but the client shouldn't wait for it", 3),
    ("stop FastAPI turning underscores into hyphens in a header", 2),
]

# ---------- record ----------


async def record() -> list[tuple[str, str]]:
    """Return (style, text) lines. style: cmd | out | dim | ok | err | title"""
    lines: list[tuple[str, str]] = []
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "docs_brain.server"], cwd=str(ROOT)
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        tools = [t.name for t in (await session.list_tools()).tools]
        lines += [
            ("title", "MCP client  <->  docs-brain server (stdio, CPU only, no LLM inside)"),
            ("cmd", "initialize"),
            ("ok", f"connected to {init.server_info.name}; tools: {', '.join(tools)}"),
        ]
        for query, k in QUERIES:
            lines.append(("cmd", f'search_docs("{query}", top_k={k})'))
            res = await session.call_tool("search_docs", {"query": query, "top_k": k})
            for r in res.structured_content["results"]:
                lines.append(("out", f"{r['rank']}. {r['heading']}"))
                lines.append(("dim", f"   {r['url']}"))
            first = res.structured_content["results"][0]["snippet"]
            snippet = " ".join(first.split())[:150] + "..."
            lines += [("dim", "   " + s) for s in textwrap.wrap(f'"{snippet}"', 92)]
        lines.append(("cmd", 'get_page("../../../.env")'))
        bad = await session.call_tool("get_page", {"path": "../../../.env"})
        lines.append(("err", bad.content[0].text.replace("Error executing tool get_page: ", "")))
    return lines


# ---------- render ----------

W, PAD, LH, FONT_SIZE = 1000, 24, 23, 16
COLORS = {
    "bg": (24, 26, 31),
    "bar": (40, 43, 51),
    "title": (150, 160, 175),
    "cmd": (125, 200, 255),
    "prompt": (110, 220, 160),
    "out": (230, 232, 236),
    "dim": (140, 148, 160),
    "ok": (110, 220, 160),
    "err": (255, 130, 120),
}


def wrap(lines: list[tuple[str, str]], width: int = 96) -> list[tuple[str, str]]:
    out = []
    for style, text in lines:
        indent = "   " if style in ("dim", "out") else ""
        for i, part in enumerate(textwrap.wrap(text, width) or [""]):
            out.append((style, part if i == 0 else indent + part))
    return out


def render(lines: list[tuple[str, str]]) -> None:
    font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", FONT_SIZE)
    bold = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf", FONT_SIZE)
    lines = wrap(lines)
    height = PAD * 2 + 34 + LH * len(lines)

    def frame(shown: list[tuple[str, str]], cursor: bool) -> Image.Image:
        img = Image.new("RGB", (W, height), COLORS["bg"])
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 30], fill=COLORS["bar"])
        for i, c in enumerate([(255, 95, 87), (255, 189, 46), (39, 201, 63)]):
            d.ellipse([14 + i * 20, 9, 26 + i * 20, 21], fill=c)
        d.text((W // 2, 15), "Docs Brain MCP demo", font=font, fill=COLORS["dim"], anchor="mm")
        y = 30 + PAD
        for style, text in shown:
            x = PAD
            if style == "cmd":
                d.text((x, y), "> ", font=bold, fill=COLORS["prompt"])
                x += d.textlength("> ", font=bold)
            f = bold if style in ("cmd", "title") else font
            d.text((x, y), text, font=f, fill=COLORS[style])
            y += LH
        if cursor and shown:
            style, text = shown[-1]
            x = PAD + d.textlength(("> " if style == "cmd" else "") + text, font=bold)
            d.rectangle([x + 2, y - LH + 3, x + 10, y - 3], fill=COLORS["cmd"])
        return img

    frames, durations = [], []
    shown: list[tuple[str, str]] = []
    for style, text in lines:
        if style == "cmd":
            for n in range(0, len(text) + 1, 3):  # type commands out
                frames.append(frame([*shown, (style, text[:n])], cursor=True))
                durations.append(35)
            shown.append((style, text))
            durations[-1] = 450
        else:
            shown.append((style, text))
            frames.append(frame(shown, cursor=False))
            durations.append(110)
        if style in ("ok", "err") or (style == "dim" and text.startswith('   "')):
            durations[-1] = 1400  # let the viewer read results
    durations[-1] = 5000

    OUT.parent.mkdir(exist_ok=True)
    pal = [f.convert("P", palette=Image.Palette.ADAPTIVE, colors=32) for f in frames]
    pal[0].save(
        OUT, save_all=True, append_images=pal[1:], duration=durations, loop=0, optimize=True
    )
    total = sum(durations) / 1000
    print(f"Wrote {OUT} ({len(frames)} frames, {total:.0f}s, {OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    recorded = asyncio.run(record())
    for style, text in recorded:
        print(f"[{style}] {text}")
    render(recorded)

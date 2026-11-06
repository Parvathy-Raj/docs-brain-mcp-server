"""A minimal MCP client that starts the server over stdio and calls each tool.

This is the same transport Claude Desktop and Cursor use, so it is a quick end-to-end check:
    python scripts/demo_client.py "how do I run code after the response is sent?"
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252


def show(result) -> None:
    data = result.structured_content or json.loads(result.content[0].text)
    print(json.dumps(data, indent=2, ensure_ascii=False)[:2500])


async def main(query: str) -> None:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "docs_brain.server"], cwd=str(ROOT)
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        print("tools:", [t.name for t in tools.tools])
        print("prompts:", [p.name for p in (await session.list_prompts()).prompts])
        print("resources:", [str(r.uri) for r in (await session.list_resources()).resources])

        print(f"\n> search_docs({query!r}, top_k=3)")
        show(await session.call_tool("search_docs", {"query": query, "top_k": 3}))

        print("\n> get_page('tutorial/cors')")
        page = await session.call_tool("get_page", {"path": "tutorial/cors"})
        data = page.structured_content
        print(
            data["title"],
            data["url"],
            f"{len(data['content'])} chars, truncated={data['truncated']}",
        )

        print("\n> get_page('../../../.env')   (path traversal attempt)")
        bad = await session.call_tool("get_page", {"path": "../../../.env"})
        print("isError:", bad.is_error, "|", bad.content[0].text)


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or "run code after the response is sent"))

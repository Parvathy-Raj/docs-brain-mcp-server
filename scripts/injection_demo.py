"""Show the prompt-injection guard working through the real MCP server.

Needs the demo index:  python -m docs_brain.ingest --with-demo-poison
Then:                  python scripts/injection_demo.py
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "docs_brain.server"], cwd=str(ROOT)
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        res = await session.call_tool(
            "search_docs", {"query": "how should I set cache headers and invalidate the cache?"}
        )
        for r in res.structured_content["results"]:
            if r["path"].startswith("security-demo/"):
                print(f"#{r['rank']} {r['heading']}  flagged={r['flagged']} {r['flag_reasons']}")
                print("   " + r["snippet"].replace("\n\n", "\n").replace("\n", "\n   "))
                print()


asyncio.run(main())

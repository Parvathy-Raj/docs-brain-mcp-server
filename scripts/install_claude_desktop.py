"""Add Docs Brain to Claude Desktop's config, with absolute paths.

Quit Claude Desktop completely first (system tray > Quit). A running Claude can rewrite its
config from memory and drop the new entry. Then, from a normal PowerShell window:

    C:\\path\\to\\docs-brain\\.venv\\Scripts\\python.exe scripts\\install_claude_desktop.py

and reopen Claude. The existing config is backed up next to itself first.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def config_paths() -> list[Path]:
    """Claude Desktop config locations, most specific first."""
    found = []
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    found += sorted((local / "Claude-Data").glob("*/claude_desktop_config.json"))
    roaming = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    mac = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    found += [p for p in (roaming, mac) if p.exists()]
    if not found:  # no config yet: create the standard one
        found.append(roaming if os.name == "nt" else mac)
    return found


def claude_running() -> bool:
    if os.name != "nt":
        return False
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq claude.exe"], capture_output=True, text=True
    ).stdout
    return "claude.exe" in out.lower()


def main() -> None:
    if claude_running() and "--force" not in sys.argv:
        sys.exit(
            "Claude is still running. Quit it from the system tray (right-click > Quit), "
            "then run this again. (--force skips this check.)"
        )
    if not PYTHON.exists():
        sys.exit(f"Virtual environment not found at {PYTHON}. See README Quickstart.")

    entry = {
        "command": str(PYTHON),
        "args": ["-m", "docs_brain.server"],
        "env": {"DOCS_BRAIN_HOME": str(ROOT)},
    }
    for path in config_paths():
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if path.exists():
            backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
            shutil.copy2(path, backup)
            print(f"Backed up {path.name} -> {backup.name}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
        data.setdefault("mcpServers", {})["docs-brain"] = entry
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"Added docs-brain to {path}")
    print("Done. Open Claude Desktop; docs-brain appears under Settings > Developer.")


if __name__ == "__main__":
    main()

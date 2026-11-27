#!/usr/bin/env python
"""
make_mcpb.py - the MCP Bundle, equipop-<version>.mcpb (BACKLOG 522).

One file a person opens in Claude Desktop (and other apps that take
MCP Bundles) to install EquiPop's MCP server with one click. It holds:

    manifest.json     what the server is and how to start it (spec 0.4,
                      server type "uv": the app brings its own Python
                      and installs the dependencies, so no Python,
                      conda or pip on the person's side)
    pyproject.toml    the dependencies: equipop[mcp], from the wheel
                      INSIDE the bundle, so a try build installs the
                      very code it was built from and a release needs
                      no PyPI for EquiPop itself
    uv.lock           the exact versions, for every platform, so the
                      install is the same on every computer and the
                      app's `uv run --frozen` has what it asks for
    server/main.py    four lines: start equipop.mcp
    equipop-<v>-py3-none-any.whl

Usage: tools/make_mcpb.py <version> <wheel> <out dir>
Needs uv on PATH (pip install uv) and the network, for the lock.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LAUNCHER = '''import sys

from equipop.mcp import main

raise SystemExit(main(sys.argv[1:]))
'''


def manifest(version: str, tools: list[dict]) -> dict:
    return {
        "$schema": "https://raw.githubusercontent.com/anthropics/mcpb/"
                   "main/schemas/mcpb-manifest-v0.4.schema.json",
        "manifest_version": "0.4",
        "name": "equipop",
        "display_name": "EquiPop",
        "version": version,
        "description": ("Individualised neighbourhoods: the k nearest "
                        "people, counts, shares and statistics by "
                        "neighbourhood or by area, on your own files."),
        "long_description": (
            "EquiPop measures the neighbourhood of every person or place "
            "- the k nearest people or a radius - and what they are like: "
            "counts and shares of groups, statistics of a value, "
            "summaries by area, green reach from a land-cover map. This "
            "server runs on your computer, on files you name. What the "
            "assistant receives is descriptions and summaries - column "
            "names, N, means, medians, percentiles - and the path of a "
            "new result file written next to your input; never the rows "
            "themselves. Nothing is overwritten or deleted. The same "
            "tools, with the same words, are in EquiPop's QGIS plugin, "
            "ArcGIS Pro toolbox and Stata commands."),
        "author": {"name": "John Östh",
                   "url": "https://github.com/GeoCalista/EquiPop"},
        "repository": {"type": "git",
                       "url": "https://github.com/GeoCalista/EquiPop"},
        "homepage": "https://github.com/GeoCalista/EquiPop",
        "documentation": "https://github.com/GeoCalista/EquiPop/blob/"
                         "main/README_MCP.md",
        "support": "https://github.com/GeoCalista/EquiPop/issues",
        "license": "MIT",
        "keywords": ["neighbourhood", "k-nearest neighbours",
                     "segregation", "accessibility", "GIS", "census",
                     "population", "spatial statistics"],
        "server": {
            "type": "uv",
            "entry_point": "server/main.py",
            "mcp_config": {
                "command": "uv",
                "args": ["run", "--directory", "${__dirname}", "--frozen",
                         "--no-dev", "server/main.py"],
            },
        },
        "tools": tools,
        "compatibility": {
            "platforms": ["darwin", "win32", "linux"],
            "runtimes": {"python": ">=3.11"},
        },
    }


def tool_list() -> list[dict]:
    """The server's own tools, name and first sentence - from THIS
    tree, whatever pip has installed beside it."""
    import asyncio
    sys.path.insert(0, str(ROOT))
    from equipop.mcp.server import build_server

    async def go():
        from mcp import Client
        async with Client(build_server()) as c:
            return [(t.name, (t.description or "").strip())
                    for t in (await c.list_tools()).tools]
    out = []
    for name, desc in asyncio.run(go()):
        first = desc.split(". ")[0].rstrip(".") + "." if desc else ""
        out.append({"name": name, "description": first[:200]})
    return out


def pyproject(version: str, wheel_name: str) -> str:
    return f'''# The MCP Bundle's own project: it installs EquiPop from the wheel
# beside this file, with the mcp extra, into an environment the app
# manages (tools/make_mcpb.py, BACKLOG 522).
[project]
name = "equipop-bundle"
version = "{version}"
requires-python = ">=3.11"
dependencies = ["equipop[mcp]"]

[tool.uv]
package = false

[tool.uv.sources]
equipop = {{ path = "{wheel_name}" }}
'''


def build(version: str, wheel: Path, out_dir: Path) -> Path:
    wheel = Path(wheel).resolve()
    if not wheel.is_file():
        raise SystemExit(f"FATAL: no wheel at {wheel}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("FATAL: uv is not on PATH (pip install uv); the "
                         "bundle needs it for its lock file")
    work = Path(tempfile.mkdtemp(prefix="equipop_mcpb."))
    try:
        shutil.copy2(wheel, work / wheel.name)
        (work / "pyproject.toml").write_text(pyproject(version, wheel.name),
                                             encoding="utf-8")
        (work / "server").mkdir()
        (work / "server" / "main.py").write_text(LAUNCHER, encoding="utf-8")
        (work / "manifest.json").write_text(
            json.dumps(manifest(version, tool_list()), indent=2,
                       ensure_ascii=False) + "\n", encoding="utf-8")
        r = subprocess.run([uv, "lock", "--directory", str(work)],
                           capture_output=True, text=True,
                           encoding="utf-8")
        if r.returncode != 0:
            raise SystemExit("FATAL: uv lock failed:\n" + r.stdout + r.stderr)
        lock = (work / "uv.lock").read_text(encoding="utf-8")
        if wheel.name not in lock:
            raise SystemExit("FATAL: the lock does not name the wheel")
        out = out_dir / f"equipop-{version}.mcpb"
        if out.exists():
            out.unlink()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for name in ("manifest.json", "pyproject.toml", "uv.lock",
                         "server/main.py", wheel.name):
                z.write(work / name, name)
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3:
        print(__doc__)
        return 2
    out = build(args[0], Path(args[1]), Path(args[2]))
    with zipfile.ZipFile(out) as z:
        print(f"wrote {out} ({out.stat().st_size:,} bytes): "
              + ", ".join(z.namelist()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

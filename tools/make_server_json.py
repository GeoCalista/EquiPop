#!/usr/bin/env python
"""
make_server_json.py - the MCP Registry's entry for EquiPop (BACKLOG
522): server.json, written at release time from the version and the
bundle's checksum, never by hand.

    python tools/make_server_json.py <version> <assets dir> [> server.json]

<assets dir> is what tools/release_assets.sh wrote: it holds
equipop-<version>.mcpb and SHA256SUMS.txt. The entry names two ways to
run the server:

  * the PyPI package, through uvx:
        uvx --python ">=3.11" --from "equipop[mcp]" equipop mcp
  * the MCP Bundle on the release page, with its SHA-256, which
    Claude Desktop checks before installing.

The registry verifies the PyPI package by the `mcp-name:` line in
README.md (which PyPI shows as the package description), and the
bundle's URL by the string "mcp" in it. The name is permanent once
listed: io.github.geocalista/equipop (the GitHub organisation's
namespace, granted to the release workflow by OIDC).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

NAME = "io.github.geocalista/equipop"
REPO = "https://github.com/GeoCalista/EquiPop"
SCHEMA = ("https://static.modelcontextprotocol.io/schemas/2025-12-11/"
          "server.schema.json")


def sha_of(assets: Path, filename: str) -> str:
    for line in (assets / "SHA256SUMS.txt").read_text(
            encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == filename:
            return parts[0]
    raise SystemExit(f"FATAL: {filename} is not in SHA256SUMS.txt")


def entry(version: str, mcpb_sha256: str) -> dict:
    return {
        "$schema": SCHEMA,
        "name": NAME,
        "title": "EquiPop",
        # the registry allows 100 characters here
        "description": ("Individualised neighbourhoods: k nearest people, "
                        "counts, shares and statistics on your own files"),
        "repository": {"url": REPO, "source": "github"},
        "websiteUrl": f"{REPO}/blob/main/README_MCP.md",
        "version": version,
        "packages": [
            {
                "registryType": "pypi",
                "registryBaseUrl": "https://pypi.org",
                "identifier": "equipop",
                "version": version,
                "runtimeHint": "uvx",
                "runtimeArguments": [
                    # measured 27 November 2026: on a machine whose
                    # default Python is 3.10, uvx refuses rather than
                    # fetching a newer one unless told which it may use
                    {"type": "named", "name": "--python",
                     "value": ">=3.11",
                     "description": "a Python EquiPop runs on; uv fetches "
                                    "one if none is installed"},
                    {"type": "named", "name": "--from",
                     "value": "equipop[mcp]",
                     "description": "the package with its mcp extra"},
                ],
                "packageArguments": [
                    {"type": "positional", "value": "mcp",
                     "description": "start the MCP server on stdio"},
                ],
                "transport": {"type": "stdio"},
            },
            {
                "registryType": "mcpb",
                "identifier": f"{REPO}/releases/download/v{version}/"
                              f"equipop-{version}.mcpb",
                "fileSha256": mcpb_sha256,
                "transport": {"type": "stdio"},
            },
        ],
    }


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    version, assets = args[0], Path(args[1])
    sha = sha_of(assets, f"equipop-{version}.mcpb")
    if len(sha) != 64:
        raise SystemExit(f"FATAL: {sha} is not a SHA-256")
    print(json.dumps(entry(version, sha), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

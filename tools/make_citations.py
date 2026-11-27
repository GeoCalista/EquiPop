#!/usr/bin/env python
"""
make_citations.py - CITATION.cff -> equipop/tables/citations.json
(BACKLOG 522).

CITATION.cff lives at the root of the repository and travels in the
source archive, never in the wheel; `equipop cite`, the MCP server's
how_to_cite and anything else that answers "how do I cite this" need
the same references INSIDE the package. So the CFF file is copied here
as plain JSON, by this tool, and tests/test_citations.py fails when
the two drift apart.

Run after editing CITATION.cff (bump_version.py runs it too):

    python tools/make_citations.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFF = ROOT / "CITATION.cff"
OUT = ROOT / "equipop" / "tables" / "citations.json"


def load_cff(path: Path = CFF) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _person(a: dict) -> str:
    if "name" in a:
        return str(a["name"])
    given = str(a.get("given-names", "")).strip()
    family = str(a.get("family-names", "")).strip()
    return f"{family}, {given}" if given else family


def _entry(ref: dict) -> dict:
    """One reference as the package keeps it: what a person needs to
    write it down, nothing CFF-specific."""
    out = {
        "type": str(ref.get("type", "")),
        "title": str(ref.get("title", "")),
        "authors": [_person(a) for a in ref.get("authors", [])],
        "year": ref.get("year"),
    }
    for key in ("journal", "volume", "issue", "start", "end", "url",
                "collection-title", "repository", "notes"):
        if key in ref:
            out[key.replace("-", "_")] = ref[key]
    for key in ("institution", "publisher", "conference", "location"):
        if key in ref and isinstance(ref[key], dict):
            out[key] = str(ref[key].get("name", ""))
    ids = ref.get("identifiers") or []
    if ids:
        out["identifiers"] = [str(i.get("value", "")) for i in ids]
    return out


def table_from_cff(cff: dict) -> dict:
    return {
        "message": str(cff.get("message", "")),
        "software": {
            "title": str(cff.get("title", "")),
            "authors": [_person(a) for a in cff.get("authors", [])],
            "version": str(cff.get("version", "")),
            "license": str(cff.get("license", "")),
            "repository": str(cff.get("repository-code", "")),
        },
        "preferred": _entry(cff["preferred-citation"]),
        "references": [_entry(r) for r in cff.get("references", [])],
    }


def main(argv=None) -> int:
    table = table_from_cff(load_cff())
    OUT.write_text(json.dumps(table, indent=1, ensure_ascii=False)
                   + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(table['references'])} "
          "references")
    return 0


if __name__ == "__main__":
    sys.exit(main())

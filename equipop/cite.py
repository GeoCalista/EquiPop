"""
cite.py - HOW TO CITE EquiPop, and the method paper behind each tool
(BACKLOG 522).

The references are CITATION.cff's, copied into the package as
tables/citations.json by tools/make_citations.py so that a pip install
carries them. An invented reference is a known failure of assistants;
`equipop cite` and the MCP server's how_to_cite answer from this file
and nothing else.
"""
from __future__ import annotations

import json
from pathlib import Path

_TABLE = Path(__file__).resolve().parent / "tables" / "citations.json"

#: Which references explain which tool (toolset names, as
#: equipop.doors.toolset has them) or which aspect of a run, by a word
#: of the reference's title. The software report (the preferred
#: citation) is cited for every use; these come on top of it.
METHODS = {
    "CountsShares": ("k-nearest neighbor aggregates",),
    "ValueStatistics": ("k-nearest neighbor aggregates",),
    "AreaSummaries": (),
    "ContinentalRasters": ("k-nearest neighbor aggregates",),
    "PixelReach": ("k-nearest neighbor aggregates",),
    "SpatialDemography": ("World Population Prospects",),
    "Assignment": ("distance decay parameters",),
    # aspects of a run, whatever the tool
    "decay": ("distance decay parameters",),
    "friction": ("Integrating infrastructure",),
    "slope": ("Integrating infrastructure",),
    "fca": ("distance decay parameters", "X-minute cities"),
    "access": ("X-minute cities",),
    "autocorrelation": ("Scaling spatial econometrics",
                        "Operator-Based Spatial Econometrics"),
}


def load() -> dict:
    return json.loads(_TABLE.read_text(encoding="utf-8"))


def _authors(names: list[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def sentence(ref: dict) -> str:
    """One reference as a line a person pastes into a bibliography."""
    bits = [f"{_authors(ref.get('authors', []))} ({ref.get('year', 'n.d.')})."
            f" {ref.get('title', '')}."]
    if ref.get("journal"):
        s = f" {ref['journal']}"
        if ref.get("volume"):
            s += f" {ref['volume']}"
            if ref.get("issue"):
                s += f"({ref['issue']})"
        if ref.get("start"):
            s += f", {ref['start']}"
            if ref.get("end"):
                s += f"-{ref['end']}"
        bits.append(s + ".")
    elif ref.get("collection_title"):
        s = f" In {ref['collection_title']}"
        if ref.get("publisher"):
            s += f". {ref['publisher']}"
        if ref.get("start"):
            s += f", pp. {ref['start']}-{ref.get('end', '')}"
        bits.append(s + ".")
    elif ref.get("institution"):
        s = f" {ref['institution']}"
        if ref.get("location"):
            s += f", {ref['location']}"
        bits.append(s + ".")
    elif ref.get("conference"):
        bits.append(f" {ref['conference']}"
                    + (f", {ref['location']}" if ref.get("location")
                       else "") + ".")
    if ref.get("url"):
        bits.append(f" {ref['url']}")
    return "".join(bits)


def _key(ref: dict) -> str:
    first = (ref.get("authors") or ["equipop"])[0].split(",")[0]
    first = "".join(ch for ch in first if ch.isalnum()).lower() or "ref"
    return f"{first}{ref.get('year', '')}"


def bibtex(ref: dict) -> str:
    kind = {"article": "article", "report": "techreport",
            "generic": "incollection", "slides": "misc",
            "data": "misc", "software": "software"}.get(
                ref.get("type", ""), "misc")
    fields = [("title", ref.get("title", "")),
              ("author", " and ".join(ref.get("authors", []))),
              ("year", ref.get("year", ""))]
    for k, v in (("journal", ref.get("journal")),
                 ("volume", ref.get("volume")),
                 ("number", ref.get("issue")),
                 ("booktitle", ref.get("collection_title")),
                 ("publisher", ref.get("publisher")),
                 ("institution", ref.get("institution")),
                 ("howpublished", ref.get("conference")),
                 ("url", ref.get("url"))):
        if v:
            fields.append((k, v))
    if ref.get("start"):
        fields.append(("pages", f"{ref['start']}--{ref.get('end', '')}"))
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields)
    return f"@{kind}{{{_key(ref)},\n{body}\n}}"


def software_sentence(table: dict) -> str:
    s = table["software"]
    return (f"{_authors(s['authors'])}. {s['title']}, version "
            f"{s['version']}. {s['repository']} ({s['license']} licence).")


def for_tool(tool: str | None = None) -> dict:
    """What to cite for `tool` (a toolset name such as "CountsShares",
    or empty for EquiPop as a whole): the software report, the version
    used, and the method papers behind the tool."""
    table = load()
    preferred = table["preferred"]
    key = (tool or "").strip()
    wanted = METHODS.get(key) or METHODS.get(key.lower(), ())
    methods = [r for r in table["references"]
               if any(w.lower() in r["title"].lower() for w in wanted)]
    return {
        "message": table["message"],
        "software": software_sentence(table),
        "report": sentence(preferred),
        "report_bibtex": bibtex(preferred),
        "methods": [sentence(r) for r in methods],
        "methods_bibtex": [bibtex(r) for r in methods],
        "every_reference": [sentence(r) for r in table["references"]],
    }


def text(tool: str | None = None) -> str:
    c = for_tool(tool)
    lines = [c["message"], "", "The software report, for every use:",
             "  " + c["report"], "", "The software and its version:",
             "  " + c["software"]]
    if c["methods"]:
        lines += ["", "The method behind this tool:"]
        lines += ["  " + m for m in c["methods"]]
    lines += ["", "BibTeX:", c["report_bibtex"]]
    lines += c["methods_bibtex"]
    return "\n".join(lines)

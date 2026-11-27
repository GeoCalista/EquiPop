"""
cli.py - the `equipop` command (v1.68.0, BACKLOG 522).

    equipop doctor          what is installed, and where - the report
                            Stata's `equipop doctor` prints
    equipop cite [TOOL]     how to cite EquiPop, and the method paper
                            behind a tool (1, 1b, 2, 3b, 7, decay ...)
    equipop help [TOOL]     a tool's help as its dialog shows it
    equipop mcp [--rows]    the MCP server for AI assistants, on stdio
                            (R-63: --rows lets rows leave the computer)
    equipop version         the version, and nothing else

`equipop` alone with no terminal (an assistant piping stdin) starts
the MCP server, so `uvx equipop` is a server; with a terminal it
prints this text.
"""
from __future__ import annotations

import sys


def _usage() -> int:
    print(__doc__.strip())
    return 0


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        if sys.stdin is not None and not sys.stdin.isatty():
            from .mcp import main as serve
            return serve([])
        return _usage()
    cmd, rest = args[0].lower(), args[1:]
    if cmd in ("-h", "--help", "help") and not rest:
        return _usage()
    if cmd in ("version", "--version", "-v"):
        from . import __version__
        print(__version__)
        return 0
    if cmd == "doctor":
        from .doctor import report
        print("\n".join(report()))
        return 0
    if cmd == "cite":
        from . import cite
        print(cite.text(rest[0] if rest else None))
        return 0
    if cmd == "help":
        from .doors.help import HELP, LABELS, SUMMARY, USAGE, fill
        from .mcp.server import ARGUMENT, BOXES, VOCAB_MCP, _tool_key
        from .doors.numbers import BadNumber
        try:
            key = _tool_key(rest[0])
        except BadNumber as bad:
            print(bad, file=sys.stderr)
            print("The tools: " + "; ".join(
                v for k, v in LABELS.items() if k != "ShowTools"))
            return 2
        print(LABELS[key])
        print()
        print(fill(SUMMARY[key], VOCAB_MCP))
        if key in USAGE:
            print()
            print(fill(USAGE[key], VOCAB_MCP))
        for b in BOXES.get(key, ()):
            print()
            print(f"{ARGUMENT.get(b, b)}: {fill(HELP.get(b, ''), VOCAB_MCP)}")
        return 0
    if cmd == "mcp":
        from .mcp import main as serve
        return serve(rest)
    print(f"equipop: '{args[0]}' is not a command.", file=sys.stderr)
    _usage()
    return 2


if __name__ == "__main__":
    sys.exit(main())

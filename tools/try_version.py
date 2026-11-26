#!/usr/bin/env python3
"""try_version.py - the version a TRY BUILD calls itself.

    python tools/try_version.py                 # e.g. 1.66.0.dev7+g3fa21c9
    python tools/try_version.py --sha 3fa21c9   # name it after this commit

BACKLOG 513 (b). Until 1.66.0 every try build called itself the last
release: the files of a pull request built on 22 November were named
equipop-1.65.0-..., like the release, and John asked "the files seems
to be from earlier today - am I missing something? In which folder is
the new thing added?" The new code was inside files with the old name.

A try build is now NEXT.devN+gSHA (PEP 440):
  NEXT  the release it leads to. The version in pyproject.toml if that
        has no tag yet (a release pull request has bumped it); else the
        next minor release, because new work starts a minor release
        (CONTRIBUTING.md 6). A try build of a patch release is named
        after it as soon as its pull request bumps the version.
  N     how many commits since the last release tag.
  SHA   the commit, seven characters - on a pull request the pull
        request's own commit (--sha), which is what its page shows.

So 1.65.0 < 1.66.0.dev7+g3fa21c9 < 1.66.0: newer than the release it
follows, older than the one it leads to. pip, Pro, QGIS and Stata's
doctor all show it, and a try build can never be taken for a release.
Never published: PyPI refuses a version with "+".
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def compose(version: str, tagged: bool, commits: int, sha: str) -> str:
    """The try version from its parts (no git here, so it is testable)."""
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not m:
        raise ValueError(f"pyproject.toml's version {version!r} is not "
                         "like 1.66.0")
    major, minor, _ = (int(p) for p in m.groups())
    nxt = f"{major}.{minor + 1}.0" if tagged else version
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha):
        raise ValueError(f"{sha!r} is not a commit")
    return f"{nxt}.dev{int(commits)}+g{sha[:7]}"


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True,
                          capture_output=True, text=True,
                          encoding="utf-8").stdout.strip()


def _pyproject_version() -> str:
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as f:
        return re.search(r'^version\s*=\s*"([^"]+)"', f.read(),
                         re.M).group(1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sha", default="",
                    help="the commit to name the build after "
                         "(default: the one checked out)")
    a = ap.parse_args(argv)
    version = _pyproject_version()
    tags = _git("tag", "--list", "v*", "--merged", "HEAD").split()
    if not tags:
        print("try_version: no release tag (v...) in this checkout's "
              "history. In a workflow, check out with fetch-depth: 0 so "
              "the tags come too.", file=sys.stderr)
        return 1
    last = _git("describe", "--tags", "--match", "v*", "--abbrev=0")
    commits = int(_git("rev-list", "--count", f"{last}..HEAD"))
    tagged = f"v{version}" in tags
    sha = a.sha or _git("rev-parse", "HEAD")
    print(compose(version, tagged, commits, sha))
    return 0


if __name__ == "__main__":
    sys.exit(main())

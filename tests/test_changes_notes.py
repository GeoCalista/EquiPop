# -*- coding: utf-8 -*-
"""The release notes waiting in changes/ keep their four lines (BACKLOG 502).

Each pull request that changes what a user gets writes one note in
changes/ instead of editing MANUAL.md, so that five people never edit
the same table at once. The release builds MANUAL.md's row from these
notes, which only works if every note says the same three things a
MANUAL row must say (house rule 2): numbers that change, runs that now
stop, doors. A note that leaves one out is a release row that will.
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(ROOT, "changes")

REQUIRED = ("Numbers that change", "Runs that now stop", "Doors")


def problems(name, text):
    """What is wrong with one note, as sentences; empty when it is fine."""
    out = []
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._-]*\.md", name):
        out.append(f"{name}: name it <issue>-<a-few-words>.md")
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    if not lines or not re.match(r"# \S", lines[0]):
        out.append(f"{name}: the first line is '# ' and one sentence "
                   "for a user")
    for field in REQUIRED:
        hit = [l for l in lines if l.startswith(field + ":")]
        if not hit:
            out.append(f"{name}: no line '{field}: ...'")
        elif not hit[0].split(":", 1)[1].strip():
            out.append(f"{name}: '{field}:' has no answer "
                       "('none' is an answer)")
    return out


def _notes():
    if not os.path.isdir(FOLDER):
        return []
    return sorted(f for f in os.listdir(FOLDER)
                  if f.endswith(".md") and f != "README.md")


GOOD = ("# Ordinary least squares in Stata (experimental)\n"
        "Numbers that change: none\n"
        "Runs that now stop: none\n"
        "Doors: Python, Stata\n"
        "\nMore text.\n")


def test_a_good_note_passes():
    assert problems("42-ols-core.md", GOOD) == []


@pytest.mark.parametrize("name,text,expect", [
    ("42-ols-core.md", GOOD.replace("Runs that now stop: none\n", ""),
     "no line 'Runs that now stop"),
    ("42-ols-core.md", GOOD.replace("Numbers that change: none",
                                    "Numbers that change:"),
     "has no answer"),
    ("42-ols-core.md", GOOD.replace("# Ordinary", "Ordinary"),
     "first line"),
    ("42 ols core.md", GOOD, "name it"),
])
def test_a_bad_note_is_named(name, text, expect):
    """BROKEN WITH: problems() returning [] for everything."""
    found = problems(name, text)
    assert any(expect in p for p in found), found


@pytest.mark.parametrize("name", _notes() or ["(none waiting)"])
def test_every_waiting_note_has_its_four_lines(name):
    if name == "(none waiting)":
        pytest.skip("no notes in changes/ (none waiting, or a source "
                    "archive, which does not carry the folder)")
    text = open(os.path.join(FOLDER, name), encoding="utf-8").read()
    assert problems(name, text) == []

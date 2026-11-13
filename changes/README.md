# Notes for the next release

Every pull request that changes what a user gets adds **one file** here. That way nobody edits MANUAL.md at the same time as someone else. At release, the notes are gathered into MANUAL.md's version table and deleted (CONTRIBUTING.md, section 6).

**The name** is the issue number and a few words: `42-ols-core.md`. With no issue, use the branch's last part.

**The first four lines:**

```
# One sentence for a user: what changed
Numbers that change: none
Runs that now stop: none
Doors: Python, Stata
```

The first line starts with `# `. Each of the other three needs an answer after the colon, and "none" is an answer. *Doors* lists Python, Stata, QGIS or Pro, or says "documents only". After the four lines, write as much explanation as the change needs. An experimental tool says "(experimental)" in its first line.

A pull request that changes nothing a user sees, such as tests, CI or the records, needs no note.

`tests/test_changes_notes.py` checks every note in this folder.

<!-- Answer each heading; "none" is an answer, an empty heading is not.
     CONTRIBUTING.md section 4 says how a change gets in, and
     GOVERNANCE.md section 4 which changes go to the weekly board. -->

## What this solves
<!-- the problem, in a sentence or two. "Fixes #nn" closes the issue
     when this merges. -->

## Area, and files outside it
<!-- the area (GOVERNANCE.md, section 2). Name any file outside it, and
     any shared file (CONTRIBUTING.md, section 9), or "none". -->

## Started from
<!-- the first line of `git log -1 --oneline` on the main you branched
     from. AI-assisted: which assistant. -->

## Numbers that change
<!-- which outputs, in which doors, by how much (measured, not guessed);
     or "none". A change to a method rule needs a method-decision issue
     and a RULINGS.md entry - see RULINGS.md. -->

## Runs that now stop
<!-- what a user ran before and is now refused; or "none" -->

## Doors affected
- [ ] Python engine / API
- [ ] QGIS plugin
- [ ] ArcGIS Pro toolbox
- [ ] Stata
- [ ] documents / teaching only

## Tested
- [ ] a test that fails without this change (broken on purpose, seen red)
- [ ] the full suite locally, or CI green
- [ ] in a real program where it matters: QGIS ___ / ArcGIS Pro ___ / Stata ___ (version, OS)

## Written down
- [ ] a note in `changes/` (if a user will see a difference)
- [ ] `docs/tools/<tool>.md`, *Where the work stands* (if the work belongs to a tool)
- [ ] RULINGS.md (if a method rule was made or changed)
- [ ] help texts regenerated (`python tools/make_sthlp.py`) if a Stata option changed

## For the board
<!-- Ready: click "Ready for review" and add the label `board` by the
     day before the meeting. What do you ask the board to decide? -->

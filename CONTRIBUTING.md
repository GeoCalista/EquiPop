# Working on EquiPop

**For anyone changing the code, the documents or the teaching material.**
Read this first, then [GOVERNANCE.md](GOVERNANCE.md), which says who decides what, and [RULINGS.md](RULINGS.md), the method decisions you must not change by accident. Section 10 has the commands.
*Written 12 November 2026, at 1.64.1.*

---

## 1. How the code is laid out

EquiPop is **one engine with four doors**. A number is computed once, in the engine; each door only collects the question in its own program and shows the answer.

| Folder | What it is |
|---|---|
| `equipop/` | The engine: k-nearest neighbourhoods, counts and shares, value statistics, friction and slope, FCA, LISA, demography. **This is also the Python door**: `import equipop`. |
| `equipop/doors/` | Logic the doors share: dropdown wordings (`rungs.py`), help texts (`help.py`), result field names (`fields.py`), typed numbers (`numbers.py`). **A decision two doors make lives here, once.** |
| `equipop/stata_bridge.py` | `dispatch()`: the one entry point the GIS doors and Stata call. |
| `qgis/equipop_qgis/` | The QGIS plugin (QGIS 3.38 to 4.x). |
| `arcgis/EquiPop.pyt` | The ArcGIS Pro toolbox. |
| `stata/` | The Stata commands. The `.sthlp` help files are **generated**: edit `tools/make_sthlp.py`, never the `.sthlp`. |
| `tests/` | The test suite (about 2,900 tests). It runs anywhere, using three stand-ins for programs CI cannot have: `tests/qgis_stub.py` (PyQGIS), `tests/test_arcgis_stub.py` (arcpy), `tests/stata_sim.py` (Stata's Python interface). |
| `tests_real_qgis/` | The plugin run inside a **real** QGIS, numbers compared with the engine's. |
| `tools/` | Release tools: version bump, help generator, bundle builder. |
| `docs/book/` | The teaching book. |

## 2. Set up and run the tests

```
git clone https://github.com/GeoCalista/EquiPop
cd equipop
python -m venv .venv
.venv\Scripts\activate          (Windows)   or   source .venv/bin/activate
python -m pip install -e ".[test,geo,io]" matplotlib
python -m pytest -q -p no:cacheprovider tests        (about 6 minutes)
```

`-e` installs the checkout itself, so a change takes effect without reinstalling. Run one file while working (`python -m pytest tests/test_wstats.py`), and the whole suite before you open a pull request.

**In a real QGIS** (optional locally; CI always does it). With [micromamba](https://mamba.readthedocs.io) or conda:

```
micromamba create -n qgis -c conda-forge qgis pytest pandas scipy pyproj
micromamba activate qgis
QT_QPA_PLATFORM=offscreen python -m pytest tests_real_qgis     (Windows: set QT_QPA_PLATFORM=offscreen first)
```

**ArcGIS Pro and Stata** cannot run on CI: both need a licence. The stand-ins cover what they can, and every release gets a short list of hand checks, kept in its row of MANUAL.md.

## 3. Automatic tests

`.github/workflows/tests.yml` runs on every pull request and every push to `main`. Results are on the pull request and in the repository's **Actions** tab.

| Job | Question it answers |
|---|---|
| **suite** | Does the full suite pass on Windows and Linux on Python 3.11 and 3.14, and on macOS on 3.14? (Python 3.15 runs too, but does not block: its packages lag.) If GitHub has no Mac free ("not acquired by Runner"), re-run the job; it is not a test failure. |
| **qgis** | Does the plugin run in a real QGIS: 3.38 (the oldest we promise), 3.44 (LTR) and 4.x on Linux, and 4.x on Windows? |
| **bundle** | Can a complete release be built from this commit? Its files are a **download** on the run's page for 14 days. Use that download for the hand checks in Pro and Stata. |

A red check is a stop: fix it, or say in the pull request why it is not yours. Nine checks **block** a merge (*Settings → Rules → Rulesets → protect main*): the suite on Linux and Windows on Python 3.11 and 3.14, the four real-QGIS jobs, and the bundle. The macOS and Python 3.15 jobs run but do not block.

**A job's name is its check's name.** Renaming a job in `tests.yml`, or changing its matrix, renames the check. An owner must then change the required checks to match, or every pull request waits for a check that never comes ("Expected — Waiting for status to be reported").

## 4. How a change gets in

1. **Start from an issue**, or open one, and assign it to yourself. Anything that can move a number starts as a **method decision** issue (template provided): the rule today, the rule proposed, an example, and which numbers change.
2. **Work on a branch** from `main`, named after the area and the issue: `regress/42-ols-core`, `stata/57-help-wording`, `docs/60-teaching-week-3`. Nobody pushes to `main` directly, the maintainers included: GitHub refuses it. A patch file goes on a branch too: `git switch -c fix/what`, `git am the.patch`, `git push -u origin fix/what`.
3. **Open a draft pull request the day you start.** It shows everyone which files you are in (section 9). Write "Fixes #42" in it, so the issue closes when it merges. The template asks what problem it solves, what numbers change, which doors are affected, and what was tested where.
4. **Review.** Which changes go to the weekly board and which an area owner merges on any day: GOVERNANCE.md, section 4. Checks green and one approving review. A change to a method rule also needs the method lead (John). Releases, packaging and credentials need two approvals. *(Until a second developer reviews, the ruleset asks for 0 approvals: GitHub never lets authors approve their own pull request, so 1 would block John's. It goes to 1 then. BACKLOG 501.)*
5. **Merge** with *Squash and merge*, and delete the branch.

## 5. House rules

Each was learned from a fault that reached users. The number is the BACKLOG entry.

1. **Every fix comes with a test that fails without it.** Break the fix on purpose and watch the test go red. If it stays green, the test is not testing the fix (BACKLOG 406).
2. **Say what moves.** Every pull request and every MANUAL row states *Numbers that change* and *Runs that now stop*. "None" is an answer; silence is not.
3. **Read RULINGS.md before changing a rule**, and read where the rule was laid down before proposing to change it (484).
4. **Refuse, don't ignore.** A box or option that would do nothing stops the run with one sentence naming it. An option that is accepted and dropped gives a wrong analysis a clean log (486, 490).
5. **Decide from what the user asked, not from what the data holds.** Faults have come from inferring a choice from what a field happened to hold (485, 488).
6. **One rule, one place.** If two doors need it, it goes in `equipop/doors/`. Copies drift; the crossing-ring arithmetic in five copies is the standing example (38, 320, 483).
7. **Speak the door's language.** A message names the box or the option the user sees, never an engine argument (305).
8. **A stand-in must be stricter than the real program, never kinder.** When a stand-in and the real program differ, fix the stand-in first, then the code (80, 288).
9. **Stata's Python blocks**: no backticks, no `$`, no backslashes, and nothing heavy imported at the top. Stata expands macros on every line and runs the block when it loads the command (459, 460). After changing a Stata option, run `python tools/make_sthlp.py`.
10. **Dead code is deleted, not commented out.** Git remembers it.
11. **Never commit a credential.** Tokens live in your own user folder (`.pypirc`) or a keyring, never in the repository, a chat or a screenshot.

## 6. Releases

Today John makes the releases. The steps, in order:

1. `python tools/bump_version.py X.Y.Z`, then `python tools/make_sthlp.py`.
2. A new row in MANUAL.md's version table, written from the notes in `changes/`, which the release then deletes. Update the stamps at the top of TEACHING.md and PROPOSALS.md.
3. The full suite green, and the CI run green.
4. `bash tools/make_bundle.sh X.Y.Z <folder outside the repository>`, or take CI's bundle download.
5. The hand checks in the MANUAL row: ArcGIS Pro and Stata on Windows, Stata on macOS.
6. **PyPI, with no token:** on GitHub, *Releases → Draft a new release*, a new tag `vX.Y.Z` (exactly the version in `pyproject.toml`), *Publish release*. The `release` workflow checks the tag, builds, tests the wheel, and waits for a maintainer to approve the upload (*Actions → the release run → Review deployments*). Then the QGIS plugin repository, and SSC by email.

**Version numbers.** A correction is a patch release (1.63.8), even when it moves a number. A ruling or a new capability starts a minor release (1.64.0), and HANDOVER_15.md must then say so; a test checks.

## 7. Where things are written down

| File | What it holds |
|---|---|
| GitHub **issues** | The backlog: ideas, bugs and tasks, each with an area label. `#42` is an issue (or a pull request). |
| `GOVERNANCE.md` | Roles, areas, the weekly board, and where each kind of record lives. |
| `RULINGS.md` | Method decisions in force: what the code must do and why. |
| `changes/` | One note per pull request that changes what a user gets, until the release gathers them. |
| `docs/tools/` | One file per tool: what it computes, its status, its validation, and where the work stands. |
| `BACKLOG.md` | Every finding and change up to 13 November 2026 (entries 1 to 502), newest first. A number is never reused. New work is an issue. |
| `MANUAL.md` | The user manual, and one row per release saying what changed. |
| `HANDOVER_15.md` | Notes from one of John's working sessions to the next. Its section 0 is the latest. |
| `TEACHING.md`, `PROPOSALS.md` | What each release means for courses and for funding texts. |
| `CITATION.cff` | How to cite EquiPop. |

## 8. AI-assisted work

Much of EquiPop was written with an AI assistant, and that will continue. Its work follows the same rules as anyone's: a test for every fix, a review, and the numbers that change stated. The person who opens the pull request answers for it. Name the assistant in the commit (a `Co-Authored-By:` line), so the history shows how a change was made.

**How a session runs:**

1. **Start from a good version.** That is the current `main`, which is always green because nothing merges otherwise, or a release tag such as `v1.64.1`. Never start from a zip, an old download, or a folder whose state you do not know. Give the assistant that version, and write its first line of `git log -1 --oneline` in the pull request under *Started from*.
2. **One session, one issue, one branch.** Tell the assistant the issue, the area, and the files it may change. It must name anything outside the area, and any shared file (section 9), before changing it.
3. **Give it the rules:** this file, RULINGS.md, and the tool's `docs/tools/<tool>.md`. RULINGS.md is the list that stops an assistant from "fixing" a decision that was made on purpose.
4. **Its output is commits or a patch on that branch**, never on main. Apply the patch with `git am` on the branch, push, and open a pull request. Review it as you would a colleague's.
5. **If a patch does not apply** because main has moved, run `git am --abort`, bring main into your branch (section 10 E), and have the assistant redo the work on that version. Do not merge an AI patch by hand.
6. **End with notes.** The session's last step updates *Where the work stands* in `docs/tools/<tool>.md`. The next session, whether yours, a colleague's or an assistant's, then starts from there and not from memory.

## 9. Working in parallel

Several people, and their assistants, can work at once without getting in each other's way if three things hold.

**Everyone works in their own files.** An area is a set of folders (GOVERNANCE.md, section 2), and a new tool gets its own (GOVERNANCE.md, section 3). Two people need the same file only by exception.

**Claim before you start.** Assign the issue to yourself and open a draft pull request on the first day (section 10 C). The pull request lists every file you have changed, so anyone can see who is in which file. Before you start, look through the open pull requests: if someone is already in a file you need, talk first, or wait.

**The files everyone touches** are where conflicts happen. Keep changes to them small, and put them in a pull request of their own:

| File | Why everyone touches it |
|---|---|
| `equipop/stata_bridge.py` | `dispatch()`, every door's way into the engine: one `if engine == ...` per engine |
| `arcgis/EquiPop.pyt` | every Pro tool, in one file of about 6,000 lines |
| `qgis/equipop_qgis/provider.py` | the list of QGIS tools |
| `equipop/__init__.py`, `pyproject.toml` | what the package exports; its version and dependencies |
| `stata/equipop.pkg`, `stata/stata.toc` | what `net install` delivers |
| `MANUAL.md`, `RULINGS.md`, `BACKLOG.md` | the records |

**Only a release edits MANUAL.md and the version.** A pull request writes a note in `changes/` instead (its README says how). That rule alone removes most conflicts.

**Bring main into your branch once a week**, before the board meets (section 10 E). A conflict found within a week is a few lines; found after a month, it can take a day to sort out.

## 10. Commands (Anaconda Prompt)

The same commands work in any Windows command prompt where `git` and `python` are found. Replace `C:\work\EquiPop` with your own folder, and `regress/42-ols-core` with your branch.

**A. Once: set up.** You need Git for Windows (git-scm.com); the first push opens a browser to sign in to GitHub.
```
conda create -n equipop python=3.12 -y
conda activate equipop
git clone https://github.com/GeoCalista/EquiPop.git C:\work\EquiPop
cd /d C:\work\EquiPop
python -m pip install -e ".[test,geo,io]" matplotlib
python -m pytest -q -p no:cacheprovider tests
git config --global user.name "Your Name"
git config --global user.email "the address your GitHub account uses"
```

**B. Every time: start in the right place.**
```
conda activate equipop
cd /d C:\work\EquiPop
```

**C. Start a piece of work** (issue #42), from the newest main:
```
git switch main
git pull
git switch -c regress/42-ols-core
```
After your first commit and push (D), open the repository on GitHub, click **Compare & pull request**, and choose **Create draft pull request** from the green button's arrow.

**D. Save and share, daily.** Pushing is the upload, and it is also your backup.
```
python -m pytest -q -p no:cacheprovider tests -k regress
git status
git add equipop\regress tests\test_regress_ols.py changes\42-ols-core.md
git commit -m "OLS core: coefficients and standard errors (#42)"
git push -u origin regress/42-ols-core
```
After the first time, `git push` is enough.

**E. Weekly, before the board: bring main in.**
```
git fetch origin
git merge origin/main
python -m pytest -q -p no:cacheprovider tests
git push
```
If git reports `CONFLICT`, run `git merge --abort` to put everything back, and ask the owner of that file.

**F. Ready for the board.** On the pull request's page, click **Ready for review** and add the label `board` (right-hand column). Do this by the day before the meeting.

**G. Try someone's pull request on your own machine** (#42), for a hand check:
```
git fetch origin pull/42/head:pr-42
git switch pr-42
python -m pytest -q -p no:cacheprovider tests -k regress
```
EquiPop is installed from this folder (`-e`), so Python, and Stata through it, now runs the pull request's code. When you are done, go back to main:
```
git switch main
git branch -D pr-42
```

**H. After your pull request is merged:**
```
git switch main
git pull
git branch -D regress/42-ols-core
```
`-D` is needed because *Squash and merge* gives the work a new commit.

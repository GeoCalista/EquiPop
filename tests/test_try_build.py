"""
test_try_build.py - one set of files for PyPI and the release page, and
try builds that say what they are (BACKLOG 513, the external review of
23 November 2026, finding 5 and "release identity").

(a) The release workflow built the wheel and source archive twice: for
    PyPI without the Pro help files, and again for the release page.
    It now builds once and checks PyPI's two files against the release
    page's checksums.
(b) A try build called itself the last release (John, 22 November: "the
    files seems to be from earlier today - am I missing something?").
    It is now NEXT.devN+gSHA, and every version check in the doors
    orders it between the release before and the release after.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "qgis"))

import bump_version  # noqa: E402
import try_version  # noqa: E402

TRY = "1.66.0.dev7+g3fa21c9"


# ---- (b) the name ---------------------------------------------------

def test_a_try_build_leads_to_the_next_minor_release_after_a_tag():
    assert try_version.compose("1.65.0", True, 7, "3fa21c9e" * 5) == TRY


def test_a_try_build_of_a_bumped_unreleased_version_is_named_after_it():
    """A release pull request has moved pyproject.toml to 1.65.1 and
    there is no tag v1.65.1 yet: its try builds lead to 1.65.1."""
    assert (try_version.compose("1.65.1", False, 3, "abcdef1")
            == "1.65.1.dev3+gabcdef1")


@pytest.mark.parametrize("version, sha", [("1.66", "abcdef1"),
                                          ("1.66.0.dev1", "abcdef1"),
                                          ("1.66.0", "xyz"),
                                          ("1.66.0", "abc")])
def test_nonsense_is_refused(version, sha):
    with pytest.raises(ValueError):
        try_version.compose(version, True, 1, sha)


def test_pep_440_orders_it_between_the_two_releases():
    version = pytest.importorskip("packaging.version")
    V = version.Version
    assert V("1.65.0") < V(TRY) < V("1.66.0")
    assert V(TRY).local == "g3fa21c9"           # PyPI refuses a "+"
    assert V("1.66.0.dev7+g3fa21c9") < V("1.66.0.dev8+g0000000")


def test_the_committed_version_is_never_a_try_version():
    """The try version is written into a workflow's checkout only. If
    it were ever committed, the next release would be named after a
    try build."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    v = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)
    assert re.fullmatch(r"\d+\.\d+\.\d+", v), v


def test_bump_takes_a_try_version_only_when_told(capsys):
    """BROKEN WITH: the --try branch's pattern widened to any string."""
    assert bump_version.main([TRY]) == 2               # not without --try
    assert bump_version.main(["1.66.0-try2", "--try"]) == 2
    assert bump_version.main([TRY, "--try", "--check"]) == 0
    assert "never to be committed" in capsys.readouterr().out


def test_bump_check_writes_nothing():
    before = (ROOT / "pyproject.toml").read_bytes()
    bump_version.main([TRY, "--try", "--check"])
    assert (ROOT / "pyproject.toml").read_bytes() == before


# ---- (b) the doors order it right ------------------------------------

def _qgis_newer():
    import qgis_stub
    qgis_stub.install()
    from equipop_qgis.base import _newer
    return _newer


def test_qgis_puts_a_try_build_between_the_two_releases():
    """BROKEN WITH: the old reading, which took the digits of
    "dev7+g3fa21c9" as a fourth number - a try plugin then looked newer
    than the 1.66.0 release under it, and was refused."""
    newer = _qgis_newer()
    assert newer(TRY, "1.65.0")
    assert not newer(TRY, "1.66.0")
    assert newer("1.66.0", TRY)
    assert not newer(TRY, TRY)
    assert newer("1.66.0.dev8+g0000000", TRY)
    assert newer("1.44.0", "1.5.0")           # the old rule still holds


def test_pro_puts_a_try_build_between_the_two_releases():
    import test_arcgis_continental as AC
    vt = AC._pyt()._vtuple
    assert vt("1.65.0") < vt(TRY) < vt("1.66.0")
    assert vt("1.44.0") > vt("1.5.0")
    assert vt("not a version") is None


def test_the_doctor_reads_a_try_version():
    from equipop.doctor import _as_numbers
    assert _as_numbers(TRY) == (1, 66, 0)


# ---- (a) one build, and the bundle says what it is --------------------

def _release_yml():
    return (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8")


def test_the_release_builds_once():
    """BROKEN WITH: `python -m build` put back in the build job - PyPI
    would again get files built apart from the release page's."""
    src = _release_yml()
    assert "python -m build" not in src
    assert src.count("bash tools/make_bundle.sh") == 1
    assert src.count("bash tools/release_assets.sh") == 1


def test_pypi_gets_the_release_page_s_files():
    src = _release_yml()
    jobs = src[src.index("jobs:"):]
    build = jobs[:jobs.index("  publish:")]
    publish = jobs[jobs.index("  publish:"):jobs.index("  attach:")]
    attach = jobs[jobs.index("  attach:"):]
    assert "sha256sum -c" in build                       # checked
    assert 'cp "$RUNNER_TEMP/assets/equipop-$V-py3-none-any.whl"' in build
    assert "name: dist" in publish and "pypi" in publish
    assert "make_bundle" not in attach and "name: assets" in attach


def test_the_bundle_checks_the_exact_help_files_and_writes_build_txt():
    sh = (ROOT / "tools" / "make_bundle.sh").read_text(encoding="utf-8")
    assert '"$GOT_XML" != "$WANT_XML"' in sh
    assert 'BUILD.txt' in sh and "A TRY BUILD, NOT A RELEASE" in sh


def test_the_try_build_is_named_before_anything_is_installed():
    yml = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8")
    bundle = yml[yml.index("  bundle:"):]
    name = bundle.index("tools/try_version.py")
    assert name < bundle.index("pip install -e .")
    assert name < bundle.index("tools/make_bundle.sh")
    assert "fetch-depth: 0" in bundle[:name]


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="needs git")
def test_try_version_runs_on_this_checkout():
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "try_version.py"),
                        "--sha", "abcdef1"], capture_output=True, text=True,
                       encoding="utf-8",
                       cwd=ROOT)
    if r.returncode == 1 and "no release tag" in r.stderr:
        pytest.skip("a checkout without the release tags")
    assert r.returncode == 0, r.stderr
    assert re.fullmatch(r"\d+\.\d+\.\d+\.dev\d+\+gabcdef1", r.stdout.strip())

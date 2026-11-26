"""
test_tool_groups.py - each tool sits in the same group in both GIS.

BACKLOG 517. John, 25 November 2026: arrange the tools in groups by
what they are for, in Pro and in QGIS alike - tool 0 at the top, then
Neighbourhoods, Statistics, Rasters and pixels, Demography, Finding
and fetching data, Simulation. equipop.doors.toolset.GROUPS is the
table; both doors write the words down (QGIS asks while it builds the
toolbox), so these tests are what keeps them the same.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from equipop.doors import toolset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "qgis"))

GROUP_NAMES = {"", "Neighbourhoods", "Statistics", "Rasters and pixels",
               "Demography", "Finding and fetching data", "Simulation"}


def _qgis_algorithms():
    import qgis_stub
    qgis_stub.install()
    from equipop_qgis.provider import EquipopProvider
    prov = EquipopProvider()
    prov.loadAlgorithms()
    return {a.EQP_TOOL: a for a in prov.algorithms()}


def _pro_tools():
    import test_arcgis_continental as AC
    pyt = AC._pyt()
    return {c.__name__: c() for c in pyt.Toolbox().all_tools}


def test_the_table_covers_every_tool_and_only_john_s_groups():
    """BROKEN WITH: a new tool added to EXTENDED but not to GROUPS."""
    every = set(toolset.STANDARD) | set(toolset.EXTENDED)
    assert set(toolset.GROUPS) == every
    assert set(toolset.GROUPS.values()) == GROUP_NAMES
    assert toolset.GROUPS["ShowTools"] == ""


def test_qgis_puts_each_tool_in_its_group():
    """BROKEN WITH: tool 3b's EQP_GROUP set to "Rasters" (a typo makes
    a seventh group with one tool in it)."""
    algs = _qgis_algorithms()
    assert set(algs) == set(toolset.GROUPS)
    for tool, alg in algs.items():
        want = toolset.GROUPS[tool]
        assert alg.group() == want, tool
        assert alg.groupId() == toolset.group_id(want), tool


def test_qgis_group_ids_are_plain_and_one_per_group():
    """QGIS keys a group by its id: two spellings of one id would make
    two folders, and one id for two names would merge them."""
    algs = _qgis_algorithms()
    seen = {}
    for alg in algs.values():
        gid = alg.groupId()
        assert gid == "" or (gid.isalnum() and gid.islower()), gid
        assert seen.setdefault(gid, alg.group()) == alg.group(), gid


def test_tool_0_is_at_the_top_in_both_doors():
    """BROKEN WITH: tool 0 given self.category = "Settings"."""
    assert _qgis_algorithms()["ShowTools"].group() == ""
    assert getattr(_pro_tools()["ShowTools"], "category", "") == ""


def test_pro_puts_each_tool_in_its_toolset():
    """BROKEN WITH: Assignment's category left out (tool 7 would sit
    at the top beside tool 0)."""
    tools = _pro_tools()
    assert set(tools) == set(toolset.GROUPS) - {"SpatialDataFetch"}
    for name, tool in tools.items():
        assert getattr(tool, "category", "") == toolset.GROUPS[name], name


def test_pro_toolsets_are_one_level():
    """Pro nests toolsets on a backslash; QGIS cannot nest at all, so
    neither door does."""
    for tool in _pro_tools().values():
        assert "\\" not in getattr(tool, "category", "")


@pytest.mark.parametrize("name, gid", [
    ("Rasters and pixels", "rastersandpixels"),
    ("Finding and fetching data", "findingandfetchingdata"),
    ("", ""),
])
def test_group_id(name, gid):
    assert toolset.group_id(name) == gid

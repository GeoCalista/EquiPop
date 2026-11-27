"""Tool 1b, summaries by area (BACKLOG 521; rulings R-61 and R-62): the
shared door half, and both GIS doors giving its numbers.

The town used throughout, in metres from (670000, 6580000):

    A (muni)   0-1000 x 0-1000        C (county) 0-2000 x 0-1000
    B (muni)   1000-2000 x 0-1000     E (muni)   3000-4000 x 0-1000

    p0 (500, 500)    10 people   inside A and C
    p1 (1000, 500)    4 people   on the A|B border, inside C
    p2 (1500, 500)    6 people   inside B and C
    p3 (2050, 500)    3 people   in no area: 50 m from B and from C
    p4 (1000, 1000)   1 person   on the corner of A, B and C

Worked by hand (R-61):
  no level field: A = p0 p1 p4 (15), B = p2 p3 (9), C = p0 p1 p2 (20),
                  E = nobody. p4 is on three borders and inside none:
                  it counts once, in the first (A). p3 is as near B as
                  C, and goes to the first (B).
  levels muni / county: A 15, B 9, E 0 as before; C = all five (24) -
                  within the county level p4's only border is C's, and
                  p3's only candidate is C.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "qgis"))

import qgis_stub                                         # noqa: E402
qgis_stub.install()

from qgis.core import QgsProcessingFeedback              # noqa: E402

from equipop.doors import areasdoor as D                 # noqa: E402
from equipop.doors.numbers import BadNumber              # noqa: E402
from equipop.wstats import weighted_stats                # noqa: E402
from equipop.zones import Areas                          # noqa: E402

X0, Y0 = 670000.0, 6580000.0
QUIET = dict(say=lambda *a: None)


def _sq(x0, x1):
    return [[(X0 + x0, Y0), (X0 + x1, Y0), (X0 + x1, Y0 + 1000),
             (X0 + x0, Y0 + 1000)]]


NAMES = ["A", "B", "C", "E"]
LEVELS = ["muni", "muni", "county", "muni"]
RINGS = [_sq(0, 1000), _sq(1000, 2000), _sq(0, 2000), _sq(3000, 4000)]


def _points():
    return pd.DataFrame({
        "x": X0 + np.array([500, 1000, 1500, 2050, 1000.0]),
        "y": Y0 + np.array([500, 500, 500, 500, 1000.0]),
        "pop": [10.0, 4, 6, 3, 1], "old": [2.0, 1, 3, 0, 0],
        "inc": [100.0, 200, 300, 400, 500]})


def _run(levels=None, **kw):
    p = _points()
    args = dict(names=NAMES, levels=levels, people="pop", counts=["old"],
                values=["inc"])
    args.update(QUIET)
    args.update(kw)
    return D.run(p, p.x, p.y, Areas(RINGS), **args)


# --------------------------------------------------- the shared half
def test_each_point_counts_where_r61_puts_it():
    """BROKEN WITH: a border point counted in every area it touches
    (A, B and C would each gain p1 or p4)."""
    t, _, rep = _run()
    assert t.N.tolist() == [15, 9, 20, 0]
    assert t.Npts.tolist() == [3, 2, 3, 0]
    assert rep["border"] == 2 and rep["snapped"] == 1 and rep["ties"] == 1
    assert rep["snap_max"] == pytest.approx(50.0)
    t, _, _ = _run(levels=LEVELS)
    assert t.N.tolist() == [15, 9, 24, 0]
    # every person once per level: no one is counted twice
    assert t.N[[0, 1, 3]].sum() == t.N[2] == _points()["pop"].sum()


def test_the_statistics_are_tool_2_s_per_person():
    t, _, _ = _run(stats=["mean", "median", "sd", "p90"])
    a = [0, 1, 4]                                   # A's points
    p = _points()
    want = weighted_stats(["mean", "median", "sd", "p90"],
                          p.inc.to_numpy()[a], p["pop"].to_numpy()[a])
    assert t.Mean_inc[0] == pytest.approx(2300 / 15)
    for s, col in (("median", "Med_inc"), ("sd", "SD_inc"),
                   ("p90", "P90_inc")):
        assert t[col][0] == pytest.approx(want[s])
    assert t.T_old[0] == 3 and t.R_old[0] == pytest.approx(0.2)


def test_without_a_people_field_each_point_is_one():
    t, _, _ = _run(people=None)
    assert t.N.tolist() == [3, 2, 3, 0]
    assert t.Mean_inc[0] == pytest.approx((100 + 200 + 500) / 3)


def test_few_people_hide_the_results_but_keep_n():
    """R-62. BROKEN WITH: N hidden too, or the threshold read as at
    most rather than fewer than."""
    t, _, _ = _run(min_people=15)
    assert t.Hidden.tolist() == [0, 1, 0, 1]
    assert t.N.tolist() == [15, 9, 20, 0]
    assert np.isnan(t.Mean_inc[1]) and np.isnan(t.T_old[1])
    assert t.Mean_inc[0] == pytest.approx(2300 / 15)


def test_points_in_no_area_left_out_or_beyond_the_limit():
    t, _, rep = _run(outside="leave")
    assert t.N.tolist() == [15, 6, 20, 0] and rep["left_out"] == 1
    t, _, rep = _run(snap_within=40.0)
    assert t.N.tolist() == [15, 6, 20, 0] and rep["beyond"] == 1
    t, _, rep = _run(snap_within=60.0)
    assert t.N.tolist() == [15, 9, 20, 0] and rep["beyond"] == 0


def test_the_points_get_their_area_per_level_and_overlap_is_refused():
    """BROKEN WITH: the points output written without a level field,
    where p0 lies in A and C and one column cannot hold both."""
    _, pts, _ = _run(levels=LEVELS, want_points=True)
    assert pts.Area_muni.tolist() == ["A", "A", "B", "B", "A"]
    assert pts.Area_county.tolist() == ["C"] * 5
    assert pts.N_muni.tolist() == [15, 15, 9, 9, 15]
    with pytest.raises(BadNumber, match="more than one area"):
        _run(want_points=True)


def test_a_point_without_coordinates_counts_nowhere_and_is_said():
    p = _points()
    p.loc[2, "x"] = np.nan
    said = []
    t, _, rep = D.run(p, p.x, p.y, Areas(RINGS), names=NAMES,
                      people="pop", say=said.append)
    assert rep["no_xy"] == 1 and t.N.tolist() == [15, 3, 14, 0]
    assert any("no coordinates" in s for s in said)


def test_many_points_on_borders_are_questioned():
    """A grid's corners sit on the borders of areas built from the same
    grid: the run asks."""
    said = []
    p = pd.DataFrame({"x": X0 + np.array([0, 1000, 2000.0]),
                      "y": Y0 + np.array([0, 0, 0.0])})
    D.run(p, p.x, p.y, Areas(RINGS), say=said.append)
    assert any("CORNERS" in s for s in said)


def test_the_hide_box_explains_why_k_helps():
    said = []
    p = _points()
    D.run(p, p.x, p.y, Areas(RINGS), people="pop", min_people=10,
          say=said.append)
    assert any("neighbourhood of k people always holds k" in s
               and "does not remove it" in s for s in said)


@pytest.mark.parametrize("boxes, words", [
    (dict(min_people="-1"), "0 or more"),
    (dict(snap_within="0"), "above 0"),
    (dict(stats="mean; mode"), "not one of the statistics"),
    (dict(outside="maybe"), "Points in no area"),
])
def test_boxes_that_cannot_be_read_are_refused(boxes, words):
    with pytest.raises(BadNumber, match=words):
        D.parse_boxes(**boxes)


def test_the_boxes_read_as_typed():
    kw = D.parse_boxes("Mean, Standard deviation", "10", "", "500")
    assert kw == {"stats": ["mean", "sd"], "min_people": 10.0,
                  "outside": "nearest", "snap_within": 500.0}
    assert D.parse_boxes()["stats"] == ["mean", "median"]
    assert D.outside_of(D.OUTSIDE_LABELS[1]) == "leave"


# ------------------------------------------------------------ QGIS
def _qgis(levels=True, **extra):
    from equipop_qgis.alg_areas import AreaSummaries
    shapes = [([[ring]], {"name": n, "level": L})
              for ring, n, L in zip([r[0] for r in RINGS], NAMES, LEVELS)]
    areas = qgis_stub._ShapeSource(shapes, [("name", False),
                                            ("level", False)],
                                   kind="polygon")
    alg = AreaSummaries()
    alg.initAlgorithm()
    p = {"areapoints": qgis_stub.source_from(_points()), "areas": areas,
         "areaname": "name", "arealevel": "level" if levels else "",
         "areapeople": "pop", "areacounts": ["old"],
         "areavalues": ["inc"], "areastats": [0, 1], "areaoutside": 0,
         "out_areas": "memory:a"}
    p.update(extra)
    return alg, p


def test_qgis_writes_the_shared_numbers_on_the_areas_and_points():
    alg, p = _qgis(out_points="memory:p")
    alg.processAlgorithm(p, None, QgsProcessingFeedback())
    got = p["_sinks"]["out_areas"].to_frame()
    want, pts, _ = _run(levels=LEVELS, want_points=True)
    assert got.name.tolist() == NAMES                # its own fields kept
    for c in want.columns:
        np.testing.assert_allclose(got[c].astype(float), want[c])
    gp = p["_sinks"]["out_points"].to_frame()
    assert gp.Area_muni.tolist() == pts.Area_muni.tolist()
    np.testing.assert_allclose(gp.Mean_inc_county.astype(float),
                               pts.Mean_inc_county)
    assert gp.x.tolist() == _points().x.tolist()


def test_qgis_refuses_the_points_output_for_overlapping_areas():
    from qgis.core import QgsProcessingException
    alg, p = _qgis(levels=False, out_points="memory:p")
    with pytest.raises(QgsProcessingException, match="level field"):
        alg.processAlgorithm(p, None, QgsProcessingFeedback())
    alg, p = _qgis(levels=False)                     # no points: fine
    alg.processAlgorithm(p, None, QgsProcessingFeedback())
    got = p["_sinks"]["out_areas"].to_frame()
    assert got.N.tolist() == [15, 9, 20, 0]


def test_qgis_refuses_a_box_while_the_dialog_is_open():
    alg, p = _qgis(areasnap="-5")
    ok, text = alg.checkParameterValues(p, None)
    assert not ok and "above 0" in text


def test_qgis_writes_its_choices_down_as_the_shared_ones():
    from equipop_qgis.alg_areas import AreaSummaries
    from equipop.doors.help import HELP, LABELS
    assert AreaSummaries.STAT_LABELS == tuple(l for _, l in D.STAT_LABELS)
    assert AreaSummaries.OUTSIDE_LABELS == D.OUTSIDE_LABELS
    assert AreaSummaries.EQP_LABEL == LABELS["AreaSummaries"]
    alg = AreaSummaries()
    alg.initAlgorithm()
    q = {x.name() for x in alg.parameterDefinitions()}
    assert not [n for n in q if n not in HELP]


# ------------------------------------------------------------- Pro
def _pro(levels=True, crs=0):
    from test_arcgis_stub import (_geom, _install_fake_arcpy, _load_pyt,
                                  _Messages)
    p = _points()
    people = pd.DataFrame({"OBJECTID": np.arange(1, 6), "SHAPE@X": p.x,
                           "SHAPE@Y": p.y, "pop": p["pop"],
                           "old": p.old, "inc": p.inc})
    table = pd.DataFrame({"OBJECTID": np.arange(1, 5), "name": NAMES,
                          "level": LEVELS})
    state = _install_fake_arcpy(people)
    state["layers"] = {"wards": table}
    state["shape_types"] = {"wards": "Polygon"}
    state["geom_layers"] = {"wards": [
        (_geom([r[0]]), n, L) for r, n, L in zip(RINGS, NAMES, LEVELS)]}
    # copies numbered from 11 and 31: results matched on the INPUTS'
    # ids would land nowhere (BACKLOG 164)
    state["oid_starts"] = {"memory/a": 11, "memory/p": 31}
    return _load_pyt(), state, _Messages()


def _pro_run(tool, msg, **extra):
    vals = {"areapoints": "people", "areas": "wards", "areaname": "name",
            "arealevel": "level", "areapeople": "pop",
            "areacounts": "old", "areavalues": "inc",
            "areastats": "Mean;Median", "areaoutside": D.OUTSIDE_LABELS[0],
            "out_areas": "memory/a"}
    vals.update(extra)
    ps = tool.getParameterInfo()
    for p in ps:
        if p.name in vals:
            p.value = vals[p.name]
    tool.execute(ps, msg)
    return ps


def test_pro_writes_the_shared_numbers_on_copies_of_both_layers():
    pyt, state, msg = _pro()
    _pro_run(pyt.AreaSummaries(), msg, out_points="memory/p")
    want, pts, _ = _run(levels=LEVELS, want_points=True)
    got = state["copies"]["memory/a"]
    assert got.OBJECTID.tolist()[0] == 11 and got.name.tolist() == NAMES
    for c in want.columns:
        np.testing.assert_allclose(got[c].astype(float), want[c])
    gp = state["copies"]["memory/p"]
    assert gp.OBJECTID.tolist()[0] == 31
    assert gp.Area_muni.tolist() == pts.Area_muni.tolist()
    np.testing.assert_allclose(gp.N_county.astype(float), pts.N_county)
    assert any("The new columns:" in m for m in msg.log)


def test_pro_without_a_level_field_refuses_the_points_not_the_areas():
    pyt, state, msg = _pro()
    with pytest.raises(Exception, match="level field"):
        _pro_run(pyt.AreaSummaries(), msg, arealevel=None,
                 out_points="memory/p")
    pyt, state, msg = _pro()
    _pro_run(pyt.AreaSummaries(), msg, arealevel=None)
    assert state["copies"]["memory/a"].N.tolist() == [15, 9, 20, 0]


def test_pro_refuses_a_box_on_the_box():
    pyt, state, msg = _pro()
    tool = pyt.AreaSummaries()
    ps = tool.getParameterInfo()
    pm = {p.name: p for p in ps}
    pm["areasnap"].value = "-5"
    tool.updateMessages(ps)
    assert pm["areasnap"].messages and \
        "above 0" in pm["areasnap"].messages[0][1]


def test_both_doors_have_the_same_boxes_and_help():
    from equipop_qgis.alg_areas import AreaSummaries
    from equipop.doors.help import HELP, LABELS
    alg = AreaSummaries()
    alg.initAlgorithm()
    q = {x.name() for x in alg.parameterDefinitions()}
    pyt, _, _ = _pro()
    tool = pyt.AreaSummaries()
    assert q == {p.name for p in tool.getParameterInfo()}
    assert tool.label == LABELS["AreaSummaries"]
    assert not [n for n in q if n not in HELP]

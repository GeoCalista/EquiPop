"""R-57 and R-58 (BACKLOG 516; John, 24-25 November 2026): what a friction
source DOES, and how far a cell can be sped up.

John: "forest slows down, but a path in the forest mitigates - should
that mitigation be 0 or negative ... could we conclude that the lowest is
the king?" No single overlap rule answers it - additive is right for
obstacles and wrong for paths, min the reverse - so each source gets a
role: GROUND (what you move on), OBSTACLE (what you cross; adds to the
ground), WAY (what carries you; the best way wins, ways never add up).
Per cell: the lower of ground + obstacles and the best way.

And additive stacking of two facilitators went past -1 - two roads at
-0.6 made -1.2, a negative cost the route search cannot order. John:
"cap such cells to just above -1". No cell ends below -0.99.
"""
import io
import os
import sys
import warnings
from contextlib import redirect_stdout

import numpy as np
import pandas as pd
import pytest

from equipop.friction import (FLOOR, _AGG_FUNCS, combine_sources,
                              role_of, run_knn_friction)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "qgis"))

QUIET = dict(say=lambda *a: None)


def _part(rows, role=None):
    f = pd.DataFrame(rows, columns=["x", "y", "friction"])
    return f.assign(role=role)


def _cell(out, x):
    return float(out.set_index("x").loc[float(x), "friction"])


# --------------------------------------------------------------- R-57
def test_the_roles_answer_john_s_forest_and_path():
    """The table in the 24 November answer, cell by cell. BROKEN WITH:
    ways added like obstacles - the forest path is then 5 + 0 = 5."""
    forest = _part([(0, 0, 5), (1, 0, 5), (2, 0, 5), (3, 0, 5)], "ground")
    river = _part([(1, 0, 3), (2, 0, 3), (5, 0, 3)], "obstacle")
    ways = _part([(0, 0, 0.0), (2, 0, -0.5), (4, 0, -0.6), (4, 0, -0.6),
                  (6, 0, 0.5)], "way")
    out = combine_sources([forest, river, ways], **QUIET)
    assert _cell(out, 0) == 0.0          # a path through the forest
    assert _cell(out, 1) == 8.0          # a river in the forest: both
    assert _cell(out, 2) == -0.5         # a bridge over it
    assert _cell(out, 3) == 5.0          # forest alone
    assert _cell(out, 4) == -0.6         # two roads: the best, not -1.2
    assert _cell(out, 5) == 3.0          # a river in open ground
    assert _cell(out, 6) == 0.0          # a rough track beside open ground


def test_with_roles_a_source_given_none_is_an_obstacle():
    forest = _part([(0, 0, 5)], "ground")
    other = _part([(0, 0, 2)], None)
    out = combine_sources([forest, other], **QUIET)
    assert _cell(out, 0) == 7.0


def test_the_overlap_rule_still_combines_inside_ground_and_obstacles():
    a = _part([(0, 0, 5)], "ground")
    b = _part([(0, 0, 8)], "ground")
    assert _cell(combine_sources([a, b], "sum", **QUIET), 0) == 13.0
    assert _cell(combine_sources([a, b], "max", **QUIET), 0) == 8.0
    assert _cell(combine_sources([a, b], "mean", **QUIET), 0) == 6.5


@pytest.mark.parametrize("agg", list(_AGG_FUNCS))
def test_without_roles_nothing_changes(agg):
    """Runs that give no role combine every charge by the overlap rule,
    exactly as before 1.66.0 (while nothing reaches the floor)."""
    rng = np.random.default_rng(3)
    parts = [pd.DataFrame({"x": rng.integers(0, 8, 40).astype(float),
                           "y": rng.integers(0, 8, 40).astype(float),
                           "friction": rng.uniform(-0.4, 6, 40)})
             for _ in range(3)]
    out = combine_sources(parts, agg, **QUIET)
    acc = {}
    for p in parts:
        for x, y, f in zip(p.x, p.y, p.friction):
            acc.setdefault((x, y), []).append(f)
    want = {k: _AGG_FUNCS[agg](v) for k, v in acc.items()}
    got = {(x, y): f for x, y, f in zip(out.x, out.y, out.friction)}
    assert set(got) == set(want)
    for k in want:
        assert got[k] == pytest.approx(want[k], rel=1e-12, abs=1e-12)


@pytest.mark.parametrize("typed, role", [
    ("ground", "ground"), ("Obstacle", "obstacle"), (" ways ", "way"),
    ("", None), (None, None), ("as the overlap rule says", None),
    ("way - what carries you; the best way wins", "way"),
    ("ground - what you move on (forest, marsh, field)", "ground"),
])
def test_a_role_as_typed_or_as_the_dialog_words_it(typed, role):
    """Pro's dropdowns hand back the whole label; it reads by its first
    word. BROKEN WITH: only the bare word accepted - every role chosen
    from Pro's list is then refused."""
    assert role_of(typed) == role


def test_a_role_that_is_not_one_is_refused():
    with pytest.raises(ValueError, match="not a role"):
        role_of("bridge")


def test_a_path_makes_the_forest_passable_end_to_end():
    """A line of 100 m cells: people at 0 and 1,000 m, forest (5)
    between. With a path through it the far person is ten rounds away,
    as on open ground; without, 6 rounds a cell. Additive could never
    get there: the best correction a path could give was -0.99."""
    pop = pd.DataFrame({"x": np.arange(0, 1100, 100.0), "y": 0.0,
                        "count_all": [1.0] + [0.0] * 9 + [1.0],
                        "count_group": 0.0})
    forest = _part([(x, 0.0, 5.0) for x in range(100, 1000, 100)],
                   "ground")
    path = _part([(x, 0.0, 0.0) for x in range(100, 1000, 100)], "way")

    def rounds(parts):
        fr = combine_sources(parts, **QUIET)
        with redirect_stdout(io.StringIO()):
            r = run_knn_friction(pop, [2], fr=fr, unit_size=100.0)
        return float(r.Rounds_2.iloc[0])

    assert rounds([forest, path]) == pytest.approx(10.0)
    assert rounds([forest]) == pytest.approx(9 * 6 + 1)
    legacy = [forest.assign(role=None),
              path.assign(role=None, friction=-0.99)]
    assert rounds(legacy) > 9 * 4                # still deep in forest


# --------------------------------------------------------------- R-58
def test_facilitators_that_add_up_past_minus_one_stop_at_the_floor():
    """Two roads at -0.6 in one cell, additive: -1.2 became a negative
    cost. Now -0.99, and the run says so. BROKEN WITH: the floor left
    out - the route search warns of negative weights."""
    said = []
    roads = [pd.DataFrame({"x": [0.0, 0.0, 1.0], "y": [0.0] * 3,
                           "friction": [-0.6, -0.6, -0.3]})]
    out = combine_sources(roads, "sum", say=said.append)
    assert _cell(out, 0) == FLOOR == -0.99
    assert _cell(out, 1) == -0.3
    assert any("set to -0.99" in s for s in said)


def test_the_route_search_never_sees_a_negative_cost():
    pop = pd.DataFrame({"x": [0.0, 100.0, 200.0, 300.0], "y": 0.0,
                        "count_all": 1.0, "count_group": 0.0})
    fr = pd.DataFrame({"x": [100.0], "y": [0.0], "friction": [-1.2]})
    with warnings.catch_warnings():
        warnings.simplefilter("error")             # scipy's warning
        with redirect_stdout(io.StringIO()):
            r = run_knn_friction(pop, [3], fr=fr, unit_size=100.0)
    assert r.Rounds_3.notna().all()


# ------------------------------------------------------------- QGIS
def _qgis_ch():
    class _Ch:
        def __init__(self):
            self.said = []

        def info(self, m):
            self.said.append(str(m))

        warning = info
    return _Ch()


def test_qgis_merges_a_barrier_layer_and_a_friction_raster():
    """BACKLOG 516: a barrier layer AND a friction raster together
    stopped QGIS with "string index out of range" - merge_friction
    handed a table to a function that takes a dict of cells. Here the
    raster is the forest (ground) and the layer the path through it
    (way)."""
    import qgis_stub as Q
    Q.install()
    from equipop_qgis.barriers import (barrier_to_friction,
                                       merge_friction,
                                       raster_to_friction_layer)
    ch = _qgis_ch()
    forest = Q.FakeRasterLayer(np.full((1, 10), 5.0), xmin=0.0,
                               ymax=100.0, cw=100.0, ch=100.0)
    path = Q._ShapeSource([([[(0.0, 50.0), (1000.0, 50.0)]],
                            {"f": 0.0})], [("f", True)], kind="line")
    tables = [barrier_to_friction(path, "f", 100.0, "sum", ch, role="way"),
              raster_to_friction_layer(forest, 100.0, ch)
              .assign(role="ground")]
    out = merge_friction(tables, "sum", ch)
    assert (out.friction == 0.0).all() and len(out) == 10
    assert any("roles:" in s for s in ch.said)


def test_qgis_reads_each_feature_s_role_from_a_field():
    """A path and a river merged in one layer, with a role field: the
    river adds, the path replaces - and a way's features never add up
    inside the layer."""
    import qgis_stub as Q
    Q.install()
    from equipop_qgis.barriers import barrier_to_friction, merge_friction
    ch = _qgis_ch()
    line = [[(0.0, 50.0), (600.0, 50.0)]]
    lyr = Q._ShapeSource(
        [(line, {"f": -0.6, "r": "way"}), (line, {"f": -0.6, "r": "way"}),
         ([[(0.0, 150.0), (600.0, 150.0)]], {"f": 3.0, "r": "obstacle"}),
         ([[(0.0, 150.0), (600.0, 150.0)]], {"f": 2.0, "r": ""})],
        [("f", True), ("r", False)], kind="line")
    t = barrier_to_friction(lyr, "f", 100.0, "sum", ch, role="obstacle",
                            role_field="r")
    out = merge_friction([t], "sum", ch)
    assert set(out[out.y == 50.0].friction) == {-0.6}   # not -1.2
    assert set(out[out.y == 150.0].friction) == {5.0}   # 3 + 2
    assert any("roles from 'r'" in s for s in ch.said)


def test_both_doors_offer_the_same_roles():
    import qgis_stub as Q
    Q.install()
    from equipop_qgis.alg_counts import ROLE_KEYS, ROLE_MODES
    from test_arcgis_stub import _install_fake_arcpy, _load_pyt
    _install_fake_arcpy(pd.DataFrame({"OBJECTID": [1]}))
    assert _load_pyt()._ROLE_CHOICES == ROLE_MODES
    assert [role_of(m) for m in ROLE_MODES] == ROLE_KEYS


# -------------------------------------------------------------- Pro
def test_pro_reads_a_role_per_barrier_row():
    """Pro's barrier table has a fourth column, the row's role; the
    rasters take theirs from one box."""
    from test_arcgis_stub import _install_fake_arcpy, _load_pyt, _Messages
    state = _install_fake_arcpy(pd.DataFrame({"OBJECTID": [1]}))
    pyt = _load_pyt()
    forest = pd.DataFrame({"x": [50.0, 150.0], "y": [50.0, 50.0],
                           "friction": [5.0, 5.0]}).assign(role="ground")
    path = pd.DataFrame({"x": [50.0], "y": [50.0],
                         "friction": [0.0]}).assign(role="way")
    seen = []

    def fake_frame(src, fld, agg, unit, sr, bx, by, msg, class_field=None,
                   role=None):
        seen.append((src, role, agg))
        return {"forest": forest, "paths": path}[src].assign(role=role)

    pyt._barrier_frame = fake_frame
    out = pyt._collect_barriers([["forest", "f", "", "ground"],
                                 ["paths", "f", "",
                                  pyt._ROLE_CHOICES[3]]],
                                "additive (costs add up)", 100.0, None,
                                _Messages())
    assert [(s, r) for s, r, _ in seen] == [("forest", "ground"),
                                           ("paths", "way")]
    got = dict(zip(out.x, out.friction))
    assert got == {50.0: 0.0, 150.0: 5.0}
    with pytest.raises(Exception, match="not a role"):
        pyt._collect_barriers([["paths", "f", "", "bridge"]],
                              "additive (costs add up)", 100.0, None,
                              _Messages())
    del state

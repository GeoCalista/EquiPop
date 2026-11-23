"""Tool 7, who goes where (machine 7 step 1; BACKLOG 515): the shared
door half and both GIS doors give the engine's numbers, and write three
layers back."""
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

from equipop.assign import assign                        # noqa: E402
from equipop.doors.assigndoor import (METHOD_LABELS, describe,  # noqa
                                      method_of, parse_boxes, run,
                                      tables)
from equipop.doors.numbers import BadNumber              # noqa: E402

QUIET = dict(say=lambda *a: None)


def _town(seed=21):
    rng = np.random.default_rng(seed)
    o = pd.DataFrame({"x": 670000 + rng.uniform(0, 3000, 60),
                      "y": 6580000 + rng.uniform(0, 3000, 60),
                      "pop": rng.integers(0, 40, 60).astype(float)})
    d = pd.DataFrame({"x": 670000 + rng.uniform(0, 3000, 6),
                      "y": 6580000 + rng.uniform(0, 3000, 6),
                      "places": rng.integers(40, 200, 6).astype(float)})
    return o, d


# --------------------------------------------------- the shared half
def test_the_boxes_are_read_as_people_type_them():
    assert parse_boxes() == dict(method="nearest", half_life=None,
                                 farthest=None, group_size=10.0, runs=20,
                                 seed=1, speed_kmh=5.0)
    got = parse_boxes(METHOD_LABELS[1], "1 500", "2000", "1", "5", "7",
                      "4,5")
    assert got == dict(method="decay", half_life=1500.0, farthest=2000.0,
                       group_size=1.0, runs=5, seed=7, speed_kmh=4.5)
    assert method_of(3) == "flows" and method_of("closest") == "closest"


@pytest.mark.parametrize("kw, says", [
    (dict(method=METHOD_LABELS[1]), "half-life is needed"),
    (dict(method="walk"), "How people choose is one of"),
    (dict(farthest="-1"), "farthest distance"),
    (dict(group_size="0"), "group size"),
    (dict(runs="0"), "Runs is a whole number"),
    (dict(seed="-2"), "seed"),
    (dict(speed="0"), "speed is in km/h"),
])
def test_a_box_that_cannot_be_read_is_refused_with_a_sentence(kw, says):
    with pytest.raises(BadNumber, match=says):
        parse_boxes(**kw)


def test_the_shared_run_is_the_engine_and_names_every_column():
    o, d = _town()
    said = []
    a = run(o, d, people=o["pop"], capacity=d["places"], runs="4",
            say=said.append)
    want = assign(o, d, people="pop", capacity="places", runs=4)
    pd.testing.assert_frame_equal(a.origins.reset_index(drop=True),
                                  want.origins.reset_index(drop=True))
    t = tables(a, True)
    lines = [s for s in said if s.startswith("[assign]   ")]
    named = {s.split(", ", 1)[1].split(":")[0] for s in lines}
    for frame in t.values():
        assert set(frame.columns) <= named
    assert t["trips"].Origin.min() >= 1          # rows counted from 1


def test_empty_values_and_unprojected_layers_are_refused():
    o, d = _town()
    with pytest.raises(BadNumber, match="an empty value is not read"):
        run(o, d, people=o["pop"].where(o.index != 3), **QUIET)
    with pytest.raises(BadNumber, match="metres"):
        run(o, d, layer_is_metric=False, **QUIET)
    with pytest.raises(BadNumber, match="different coordinate systems"):
        run(o, d, same_crs=False, **QUIET)


def test_without_capacity_the_destinations_carry_no_ratio_or_full():
    o, d = _town()
    a = run(o, d, people=o["pop"], **QUIET)
    cols = list(tables(a, False)["destinations"].columns)
    assert "Sim_Ratio" not in cols and "Sim_Full" not in cols
    assert [c for c, _ in describe("nearest", 20, False)["destinations"]] \
        == cols


# ---------------------------------------------------------- QGIS door
def _qgis(method=0, **boxes):
    from equipop_qgis.alg_assign import Assignment
    o, d = _town()
    alg = Assignment()
    alg.initAlgorithm()
    p = {"origins": qgis_stub.source_from(o), "peoplefield": "pop",
         "dests": qgis_stub.source_from(d), "capfield": "places",
         "choose": method, "runs": "4", "decayhalf": "800",
         "out_origins": "memory:o", "out_dests": "memory:d",
         "out_trips": "memory:t", **boxes}
    fb = QgsProcessingFeedback()
    alg.processAlgorithm(p, None, fb)
    return o, d, p, fb


@pytest.mark.parametrize("method", range(4))
def test_qgis_writes_the_engine_s_numbers_in_three_layers(method):
    """BROKEN WITH: the destinations' results written onto the people
    layer's rows - the second write reusing the first's features."""
    o, d, p, fb = _qgis(method)
    from equipop.doors.assigndoor import METHOD_KEYS
    want = assign(o, d, method=METHOD_KEYS[method], people="pop",
                  capacity="places", runs=4, half_life=800.0)
    got_o = p["_sinks"]["out_origins"].to_frame()
    got_d = p["_sinks"]["out_dests"].to_frame()
    assert len(got_o) == len(o) and len(got_d) == len(d)
    np.testing.assert_allclose(got_o.Sim_Placed.astype(float),
                               want.origins.Sim_Placed)
    np.testing.assert_allclose(got_d.Sim_Load.astype(float),
                               want.destinations.Sim_Load)
    assert got_d.places.tolist() == d.places.tolist()   # its own fields
    trips = p["_sinks"]["out_trips"]
    assert len(trips.features) == len(want.trips)
    g = trips.features[0].geometry().asPolyline()
    i, j = int(want.trips.Origin[0]), int(want.trips.Dest[0])
    assert (g[0].x(), g[1].x()) == (o.x[i], d.x[j])
    assert any("The new columns:" in m for m in fb.info)


def test_qgis_refuses_two_systems_before_reading_anything():
    from equipop_qgis.alg_assign import Assignment
    from qgis.core import QgsProcessingException
    o, d = _town()
    alg = Assignment()
    alg.initAlgorithm()
    p = {"origins": qgis_stub.source_from(o),
         "dests": qgis_stub.source_from(d, crs="EPSG:32633"),
         "choose": 0, "out_origins": "memory:o", "out_dests": "memory:d",
         "out_trips": "memory:t"}
    with pytest.raises(QgsProcessingException,
                       match="different coordinate systems"):
        alg.processAlgorithm(p, None, QgsProcessingFeedback())
    ok, why = alg.checkParameterValues(dict(p, choose=1, decayhalf=""),
                                       None)
    assert not ok and "half-life" in why


# ----------------------------------------------------------- Pro door
def _pro(o, d, dest_code=0):
    from test_arcgis_stub import _install_fake_arcpy, _load_pyt, _Messages
    people = pd.DataFrame({"OBJECTID": np.arange(1, len(o) + 1),
                           "SHAPE@X": o.x, "SHAPE@Y": o.y, "pop": o["pop"]})
    places = pd.DataFrame({"OBJECTID": np.arange(1, len(d) + 1),
                           "SHAPE@X": d.x, "SHAPE@Y": d.y,
                           "places": d.places})
    state = _install_fake_arcpy(people)
    state["layers"] = {"schools": places}
    state["crs_codes"] = {"people": 0, "schools": dest_code}
    # copies numbered from 11 and 31, so results matched on the INPUTS'
    # ids would land nowhere (BACKLOG 164)
    state["oid_starts"] = {"memory/o": 11, "memory/d": 31}
    return _load_pyt(), state, _Messages()


def _pro_run(tool, msg, method):
    vals = {"origins": "people", "peoplefield": "pop", "dests": "schools",
            "capfield": "places", "choose": METHOD_LABELS[method],
            "decayhalf": "800", "runs": "4", "out_origins": "memory/o",
            "out_dests": "memory/d", "out_trips": "memory/t"}
    ps = tool.getParameterInfo()
    for p in ps:
        if p.name in vals:
            p.value = vals[p.name]
    tool.execute(ps, msg)
    return ps


@pytest.mark.parametrize("method", range(4))
def test_pro_writes_the_engine_s_numbers_in_three_feature_classes(method):
    """The people and the destinations are copied and given their
    results on the COPIES' identifiers; the trips are lines. BROKEN
    WITH: the destinations copied from "the" input table - the people."""
    o, d = _town()
    pyt, state, msg = _pro(o, d)
    _pro_run(pyt.Assignment(), msg, method)
    from equipop.doors.assigndoor import METHOD_KEYS
    want = assign(o, d, method=METHOD_KEYS[method], people="pop",
                  capacity="places", runs=4, half_life=800.0)
    got_o, got_d = state["copies"]["memory/o"], state["copies"]["memory/d"]
    assert got_o.OBJECTID.tolist()[0] == 11 and len(got_d) == len(d)
    np.testing.assert_allclose(got_o.Sim_Placed.astype(float),
                               want.origins.Sim_Placed)
    np.testing.assert_allclose(got_d.Sim_Load.astype(float),
                               want.destinations.Sim_Load)
    assert got_d.places.tolist() == d.places.tolist()
    trips = state["created"]["memory/t"]
    assert state["geometry_types"]["memory/t"] == "POLYLINE"
    assert len(trips) == len(want.trips)
    first = trips["SHAPE@"].iloc[0].points
    i, j = int(want.trips.Origin[0]), int(want.trips.Dest[0])
    assert first == [(o.x[i], o.y[i]), (d.x[j], d.y[j])]
    assert any("The new columns:" in m for m in msg.log)


def test_pro_refuses_two_systems_and_a_box_it_cannot_read():
    o, d = _town()
    pyt, state, msg = _pro(o, d, dest_code=32633)
    state["crs_codes"]["people"] = 3006
    tool = pyt.Assignment()
    with pytest.raises(Exception, match="different coordinate systems"):
        _pro_run(tool, msg, 0)
    assert "memory/o" not in state.get("copies", {})   # nothing copied
    ps = tool.getParameterInfo()
    pm = {p.name: p for p in ps}
    pm["choose"].value = METHOD_LABELS[1]
    tool.updateMessages(ps)
    assert pm["decayhalf"].messages and \
        "half-life" in pm["decayhalf"].messages[0][1]


def test_both_doors_offer_the_same_choices_and_boxes():
    """QGIS writes its choices down (its dialog is built before the
    package is known to be there); they must be the shared ones. And
    every box has its help."""
    from equipop_qgis.alg_assign import Assignment
    from equipop.doors.help import HELP, LABELS
    assert Assignment.METHOD_LABELS == METHOD_LABELS
    alg = Assignment()
    alg.initAlgorithm()
    q = {p.name() for p in alg.parameterDefinitions()}
    from test_arcgis_stub import _install_fake_arcpy, _load_pyt
    _install_fake_arcpy(pd.DataFrame({"OBJECTID": [1]}))
    pro = {p.name for p in _load_pyt().Assignment().getParameterInfo()}
    assert q == pro
    assert not [n for n in q if n not in HELP]
    assert Assignment.EQP_LABEL == LABELS["Assignment"]

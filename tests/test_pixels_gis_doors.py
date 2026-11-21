"""Tool 3b at both GIS doors (BACKLOG 509, the chain of 510): QGIS's alg_pixels and Pro's
PixelReach, driven the way a person drives them, with the raster read
by the host GIS and never by the package.

Each door is held to the shared run: the numbers it writes must be
pixelsdoor.run's for the same people, raster and boxes. Each was
broken on purpose (named in each test).
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

from door_parity import CORE_PIXELS                      # noqa: E402
from equipop.doors.help import HELP, LABELS              # noqa: E402
from equipop.doors.pixelsdoor import run                 # noqa: E402

WEST, NORTH, CELL = 500000.0, 6600400.0, 10.0


def _cover():
    """A 40 x 40 land-cover map at 10 m: a hectare of trees (10), a
    hectare of grass (20), nodata (255) along one edge."""
    a = np.zeros((40, 40))
    a[10:20, 10:20] = 10
    a[30:40, 0:10] = 20
    a[:, 39] = 255
    return a


def _people():
    return pd.DataFrame({"x": [500150.0, 500350.0, 500050.0, 500205.0],
                         "y": [6600250.0, 6600050.0, 6600050.0,
                               6600390.0]})


def _payload(a):
    return {"array": a, "x_min": WEST, "y_max": NORTH, "cell_w": CELL,
            "cell_h": CELL, "nodata": 255, "geographic": False}


BOXES = {"value": "1", "base": "10 20", "treatment": "10",
         "hectares": "0,5 1 2", "radius": "100", "cell": ""}


def _want(a=None, **boxes):
    b = dict(BOXES, **boxes)
    return run(_people(), _payload(_cover() if a is None else a),
               say=lambda *x: None, **b)


# ---------------------------------------------------------------- QGIS
def _qgis(raster_crs="EPSG:3006", people_crs="EPSG:3006", **boxes):
    from equipop_qgis.alg_pixels import PixelReach
    alg = PixelReach()
    alg.initAlgorithm()
    layer = qgis_stub.FakeRasterLayer(_cover(), xmin=WEST, ymax=NORTH,
                                      cw=CELL, ch=CELL, nodata=255,
                                      crs=raster_crs)
    p = {"layer": qgis_stub.source_from(_people(), crs=people_crs),
         "raster": layer, "outfc": "memory:out", **BOXES}
    p.update(boxes)
    fb = QgsProcessingFeedback()
    alg.processAlgorithm(p, None, fb)
    return p["_sinks"]["outfc"], fb


def test_qgis_writes_the_numbers_of_the_shared_run():
    """BROKEN WITH: the door reading the raster's extent from its
    bottom edge (y_min for y_max) - every pixel moves 400 m south."""
    sink, _ = _qgis()
    got = sink.to_frame()
    want = _want()
    cols = [c for c in want.columns if c not in ("x", "y")]
    assert cols == ["Dist_0_5", "T_0_5", "R_0_5", "Dist_1", "T_1", "R_1",
                    "Dist_2", "T_2", "R_2", "B_r100", "T_r100", "R_r100"]
    for c in cols:
        assert np.allclose(got[c].astype(float), want[c], equal_nan=True), c
    assert np.allclose(got["x"], _people().x)       # same rows, in order
    aliases = {f.name(): f.alias() for f in sink._fields}
    assert "metres to gather 1 ha" in aliases["Dist_1"]


def test_qgis_refuses_a_raster_in_another_system_before_reading():
    """BROKEN WITH: the comparison against the layer's system removed."""
    from qgis.core import QgsProcessingException
    with pytest.raises(QgsProcessingException, match="different"):
        _qgis(raster_crs="EPSG:3035")


def test_qgis_refuses_people_in_degrees_with_the_shared_sentence():
    """The shared reader would reproject degrees to UTM and the raster
    would then be refused with advice to project it to the wrong
    system. The degrees are named instead. BROKEN WITH: the check made
    after read_points (on the reprojected system)."""
    from qgis.core import QgsProcessingException
    with pytest.raises(QgsProcessingException, match="degrees"):
        _qgis(people_crs="EPSG:4326", raster_crs="EPSG:4326")


def test_qgis_refuses_a_typed_box_while_the_dialog_is_open():
    from equipop_qgis.alg_pixels import PixelReach
    alg = PixelReach()
    alg.initAlgorithm()
    ok, why = alg.checkParameterValues(
        {"value": "1", "base": "0,4 0,8", "treatment": "",
         "hectares": "1", "radius": "", "cell": ""}, None)
    assert not ok and "to" in why
    ok, why = alg.checkParameterValues(
        {"value": "1", "base": "10", "treatment": "", "hectares": "0",
         "radius": "", "cell": ""}, None)
    assert not ok and "above 0" in why


def _red_nir():
    """A red and a near-infrared band: NDVI 0.8 on the trees' hectare,
    0.1 elsewhere, and the cover map's nodata edge."""
    red = np.full((40, 40), 1000.0)
    nir = np.full((40, 40), 1222.0)
    nir[10:20, 10:20] = 9000.0
    red[:, 39] = nir[:, 39] = 255
    return np.stack([red, nir])


NDVI = {"value": "ndvi(2, 1)", "base": "0,05 to 1",
        "treatment": "0,5 to 1"}


def test_qgis_computes_a_formula_over_the_bands_it_reads():
    """The value box's bands are read through QGIS, one by one. BROKEN
    WITH: read_bands reading band 1 for every band asked - NDVI is then
    0 everywhere and no pixel is in the treatment."""
    from qgis.core import QgsProcessingException
    from equipop_qgis.alg_pixels import PixelReach
    stack = _red_nir()
    alg = PixelReach()
    alg.initAlgorithm()
    layer = qgis_stub.FakeRasterLayer(stack, xmin=WEST, ymax=NORTH,
                                      cw=CELL, ch=CELL, nodata=255)
    p = {"layer": qgis_stub.source_from(_people(), crs="EPSG:3006"),
         "raster": layer, "outfc": "memory:out", **dict(BOXES, **NDVI)}
    alg.processAlgorithm(p, None, QgsProcessingFeedback())
    got = p["_sinks"]["outfc"].to_frame()
    want = _want(a=stack, **NDVI)
    for c in want.columns.drop(["x", "y"]):
        assert np.allclose(got[c].astype(float), want[c], equal_nan=True), c
    # the 1 ha disc reaches past the 100 m square of NDVI 0.8: R_1 ~ 0.9
    assert got["R_1"].astype(float).iloc[0] == pytest.approx(0.9, abs=0.02)
    p2 = dict(p, value="ndvi(3, 1)", outfc="memory:out2")
    with pytest.raises(QgsProcessingException, match="band 3"):
        alg.processAlgorithm(p2, None, QgsProcessingFeedback())


# ----------------------------------------------------------------- Pro
def _pro(raster_code=0, people_code=0, array=None, out="memory/out"):
    from test_arcgis_stub import _install_fake_arcpy, _load_pyt, _Messages
    t = pd.DataFrame({"OBJECTID": np.arange(1, 5),
                      "SHAPE@X": _people().x, "SHAPE@Y": _people().y,
                      "name": list("abcd")})
    state = _install_fake_arcpy(t)
    state["shape_types"] = {"cover": "Raster"}
    state["rasters"] = {"cover": {"array": (_cover() if array is None
                                            else array),
                                  "xmin": WEST, "ymax": NORTH, "cw": CELL,
                                  "ch": CELL, "nodata": 255}}
    state["crs_codes"] = {"people": people_code, "cover": raster_code}
    # a geodatabase numbers a copy from 1 - and here, deliberately, from
    # 11, so results matched on the INPUT's ids would land nowhere
    state["oid_starts"] = {out: 11}
    pyt = _load_pyt()
    return pyt, state, _Messages()


def _pro_params(tool, **vals):
    ps = tool.getParameterInfo()
    by = {p.name: p for p in ps}
    base = {"layer": "people", "raster": "cover", "outfc": "memory/out",
            **BOXES}
    base.update(vals)
    for k, v in base.items():
        by[k].value = v
    return ps


def test_pro_writes_the_numbers_of_the_shared_run_on_the_copy():
    """BROKEN WITH: the results matched on the input's identifiers
    instead of the copy's (BACKLOG 164) - the copy numbers from 11."""
    pyt, state, msg = _pro()
    tool = pyt.PixelReach()
    tool.execute(_pro_params(tool), msg)
    got = state["copies"]["memory/out"]
    assert list(got["OBJECTID"]) == [11, 12, 13, 14]
    want = _want()
    for c in [c for c in want.columns if c not in ("x", "y")]:
        assert np.allclose(got[c].astype(float), want[c], equal_nan=True), c
    assert "B_r100" not in state["table"]           # the input untouched
    assert any("read by ArcGIS" in m for m in msg.log)


def test_pro_picks_the_band_from_a_stack():
    """arcpy returns a multiband raster as a stack. BROKEN WITH: the
    band counted from 0."""
    stack = np.stack([np.zeros((40, 40)), _cover(), np.zeros((40, 40))])
    pyt, state, msg = _pro(array=stack)
    tool = pyt.PixelReach()
    tool.execute(_pro_params(tool, value="2"), msg)
    got = state["copies"]["memory/out"]
    assert np.allclose(got["Dist_1"].astype(float), _want()["Dist_1"])


def test_pro_computes_a_formula_over_a_stack():
    """BROKEN WITH: the bands picked as arr[b] instead of arr[b - 1] -
    ndvi(2, 1) then asks for a third band that is not there."""
    stack = _red_nir()
    pyt, state, msg = _pro(array=stack)
    tool = pyt.PixelReach()
    tool.execute(_pro_params(tool, **NDVI), msg)
    got = state["copies"]["memory/out"]
    want = _want(a=stack, **NDVI)
    for c in want.columns.drop(["x", "y"]):
        assert np.allclose(got[c].astype(float), want[c], equal_nan=True), c
    assert any("ndvi(2, 1)" in m for m in msg.log)


def test_pro_reads_a_multiband_raster_whose_dataset_has_no_pixel_size():
    """John, 21 November 2026, a Sentinel-2 download in Pro:
    "DescribeData: Method meanCellWidth does not exist". A multiband
    raster keeps its pixel size and nodata on each band, not on the
    dataset. BROKEN WITH: desc.meanCellWidth read from the dataset
    (the 1.65.0 candidate) - AttributeError, as on John's PC."""
    stack = np.stack([_cover(), np.zeros((40, 40)), np.zeros((40, 40))])
    pyt, state, msg = _pro(array=stack)
    state["rasters"]["cover"]["multiband"] = True
    tool = pyt.PixelReach()
    tool.execute(_pro_params(tool, value="1"), msg)
    got = state["copies"]["memory/out"]
    want = _want()
    for c in ("Dist_1", "T_1", "R_1", "B_r100"):
        assert np.allclose(got[c].astype(float), want[c], equal_nan=True), c


def test_pro_refuses_a_raster_in_another_system_and_copies_nothing():
    """BROKEN WITH: the copy made before the check."""
    pyt, state, msg = _pro(raster_code=3035, people_code=3006)
    tool = pyt.PixelReach()
    import arcpy
    with pytest.raises(arcpy.ExecuteError, match="different"):
        tool.execute(_pro_params(tool), msg)
    assert "memory/out" not in state.get("copies", {})


def test_pro_refuses_a_shapefile_that_cannot_hold_the_names():
    """B_r1500_125 is eleven characters. BROKEN WITH: the name check
    removed - the run would finish and the shapefile cut the name."""
    pyt, state, msg = _pro(out="C:/x/out.shp")
    tool = pyt.PixelReach()
    import arcpy
    with pytest.raises(arcpy.ExecuteError, match="SHAPEFILE"):
        tool.execute(_pro_params(tool, radius="1500,125",
                                 outfc="C:/x/out.shp"), msg)


# ------------------------------------------------------- both doors
def test_both_doors_offer_the_same_boxes_with_shared_help():
    """BROKEN WITH: Pro's box named 'classes' where QGIS says
    'base'."""
    from equipop_qgis.alg_pixels import PixelReach as Q
    pyt, _, _ = _pro()
    q = Q()
    q.initAlgorithm()
    qnames = {p.name() for p in q.parameterDefinitions()}
    pnames = {p.name for p in pyt.PixelReach().getParameterInfo()}
    assert CORE_PIXELS <= qnames and CORE_PIXELS <= pnames
    assert not [n for n in CORE_PIXELS if n not in HELP]
    assert q.displayName() == LABELS["PixelReach"] \
        == pyt.PixelReach().label

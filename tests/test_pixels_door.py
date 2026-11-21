"""Tool 3b's shared half: the boxes as typed, and the run both GIS doors
call (BACKLOG 508; the chain of BACKLOG 510, ruling R-53)."""
import numpy as np
import pandas as pd
import pytest

from equipop.doors.numbers import BadNumber
from equipop.doors.pixelsdoor import (parse_cell, parse_hectares,
                                      parse_pixels, parse_range,
                                      result_names, run)


@pytest.mark.parametrize("typed, want", [
    ("10 20", {"classes": [10, 20]}),
    ("10;20", {"classes": [10, 20]}),
    ("0,4 to 1", {"between": (0.4, 1.0)}),
    ("0.4 TO 1.0", {"between": (0.4, 1.0)}),
    ("-1 to 0,2", {"between": (-1.0, 0.2)}),
])
def test_which_pixels_count(typed, want):
    assert parse_pixels(typed) == want


@pytest.mark.parametrize("typed", ["", "1 to", "1 to 0,5", "0,4 0,8", "abc"])
def test_which_pixels_count_refuses_with_a_sentence(typed):
    with pytest.raises(BadNumber):
        parse_pixels(typed)


def test_hectares_take_decimal_commas_and_refuse_zero():
    assert parse_hectares("1 2,5 20") == [1.0, 2.5, 20.0]
    assert parse_hectares("") == []        # a radius alone is enough
    with pytest.raises(BadNumber):
        parse_hectares("0 5")
    with pytest.raises(BadNumber):
        parse_hectares("abc")


def test_base_and_treatment_may_be_left_empty_and_the_cell_too():
    assert parse_range("", "base") is None
    assert parse_range("0,01 to 1", "base") == {"between": (0.01, 1.0)}
    assert parse_cell("") is None and parse_cell("50") == 50.0
    with pytest.raises(BadNumber, match="Treatment"):
        parse_range("1 to 0", "treatment")
    with pytest.raises(BadNumber):
        parse_cell("0")


@pytest.fixture
def town(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from affine import Affine
    a = np.zeros((40, 40), dtype="uint8")
    a[10:20, 10:20] = 10                       # one hectare of trees
    a[30:40, 0:10] = 20                        # one of grass
    p = tmp_path / "cover.tif"
    with rasterio.open(p, "w", driver="GTiff", height=40, width=40,
                       count=1, dtype="uint8", crs="EPSG:3006", nodata=255,
                       transform=Affine(10, 0, 500000, 0, -10,
                                        6600400)) as d:
        d.write(a, 1)
    people = pd.DataFrame({"x": [500150.0, 500350.0, 500050.0],
                           "y": [6600250.0, 6600050.0, 6600050.0]})
    return p, people


QUIET = dict(say=lambda *a: None)


def test_run_equals_the_core(town):
    """The door adds nothing of its own to the numbers: they are the
    chain's, mass_from_values then reach, for the same boxes."""
    from equipop.pixels import mass_from_values, reach
    path, people = town
    got = run(people, path, base="10 20", hectares="0,5 1 2",
              radius="100", **QUIET)
    a = _payload(path)
    mass = mass_from_values(a["array"].astype("float32"), a["x_min"],
                            a["y_max"], a["cell_w"], a["cell_h"],
                            base={"classes": [10, 20]})
    want = reach(people, mass, [0.5, 1, 2], r_values=[100])
    for c in ("Dist_0_5", "Dist_1", "Dist_2", "B_r100"):
        assert np.allclose(got[c], want[c], equal_nan=True), c


def test_treatment_among_the_base_gives_t_and_r_by_hand(town):
    """Base = trees and grass (1 ha each), treatment = trees. From the
    middle of the trees, the nearest 1 ha is all trees (R_1 = 1) and the
    nearest 2 ha are everything there is: 1 ha of trees, R_2 = 0.5.
    BROKEN WITH: the treatment counted over all pixels instead of the
    base's (T then counts trees outside the base) - see the next test."""
    path, people = town
    got = run(people.iloc[:1], path, base="10 20", treatment="10",
              hectares="1 2", radius="100", **QUIET)
    assert got.T_1[0] == pytest.approx(1.0)
    assert got.R_1[0] == pytest.approx(1.0)
    assert got.T_2[0] == pytest.approx(1.0)
    assert got.R_2[0] == pytest.approx(0.5)
    # within 100 m of the trees' centre: all of the trees, no grass
    assert got.B_r100[0] == pytest.approx(1.0)
    assert got.R_r100[0] == pytest.approx(1.0)


def test_a_treatment_outside_the_base_counts_nothing(town):
    """The treatment is looked for AMONG the base. Trees as treatment
    over a grass-only base give T = 0, with a note - not a share above
    one. BROKEN WITH: select(value, treatment) taken over every pixel."""
    path, people = town
    said = []
    got = run(people, path, base="20", treatment="10", hectares="1",
              say=said.append)
    assert np.allclose(got.T_1, 0.0) and np.allclose(got.R_1, 0.0)
    assert any("inside the base" in s for s in said)


def test_an_empty_base_counts_every_pixel_with_a_value(town):
    """Every pixel but nodata: the k hectares are then simply a disc,
    and R_k the share of the nearest k ha of ground that is trees."""
    path, people = town
    got = run(people.iloc[:1], path, treatment="10", hectares="1",
              **QUIET)
    import math
    assert got.Dist_1[0] == pytest.approx(math.sqrt(1e4 / math.pi),
                                          abs=1)
    # the 1 ha disc (radius 56 m) reaches past the 100 m square of
    # trees (half-width 50 m), so about a tenth of it is open ground
    assert got.R_1[0] == pytest.approx(0.9, abs=0.02)


def test_the_analysis_cell_sums_hectares_decided_pixel_by_pixel(town):
    """Decision b: base and treatment are decided at the image's own
    10 m, THEN summed into 50 m cells - so no hectare is lost or gained,
    and the trees' hectare stays a hectare. BROKEN WITH: cell centres
    taken from the pixel grid's own origin instead of 0, 0 - the cells
    then straddle the trees and a different set of distances comes out
    (pinned below by the centres)."""
    from equipop.pixels import mass_from_values
    path, people = town
    a = _payload(path)
    v = a["array"].astype("float32")
    # a raster NOT on whole 50 m lines (its corner 5 m off), so a grid
    # anchored at the raster and one anchored at 0, 0 differ
    x0, y1 = a["x_min"] + 5, a["y_max"] + 5
    fine = mass_from_values(v, x0, y1, 10, 10,
                            base={"classes": [10, 20]},
                            treatment={"classes": [10]})
    coarse = mass_from_values(v, x0, y1, 10, 10,
                              base={"classes": [10, 20]},
                              treatment={"classes": [10]}, cell=50)
    assert coarse.ha.sum() == pytest.approx(fine.ha.sum())
    assert coarse.t_ha.sum() == pytest.approx(1.0)
    assert set((coarse.x % 50).round(6)) == {25.0}
    assert set((coarse.y % 50).round(6)) == {25.0}
    got = run(people, path, base="10 20", treatment="10", hectares="1",
              cell="50", **QUIET)
    assert got.T_1.notna().all()
    with pytest.raises(BadNumber, match="smaller"):
        run(people, path, base="10", hectares="1", cell="5", **QUIET)


def test_run_refuses_degrees_and_mixed_systems(town):
    path, people = town
    with pytest.raises(BadNumber, match="degrees"):
        run(people, path, base="10", hectares="1", layer_is_metric=False)
    with pytest.raises(BadNumber, match="different"):
        run(people, path, base="10", hectares="1", same_crs=False)


def test_run_leaves_a_reach_that_never_happens_empty(town):
    """Trees and grass hold 2 ha in all: Dist_5 is empty, with a note."""
    path, people = town
    said = []
    got = run(people, path, base="10 20", hectares="1 5", say=said.append)
    assert got.Dist_1.notna().all() and got.Dist_5.isna().all()
    assert any("less than 5" in s for s in said)


def test_run_says_when_no_pixel_is_in_the_base(town):
    path, people = town
    with pytest.raises(BadNumber, match="No pixel is in the base"):
        run(people, path, base="99", hectares="1", **QUIET)
    with pytest.raises(BadNumber, match="hectares"):
        run(people, path, base="10", **QUIET)


def _payload(path, band=1):
    """What a door's own GIS reads: the band as an array and where it
    lies. Built here with rasterio, which the doors never use."""
    import rasterio
    with rasterio.open(path) as src:
        T = src.transform
        return {"array": src.read(band), "x_min": T.c, "y_max": T.f,
                "cell_w": T.a, "cell_h": -T.e, "nodata": src.nodata,
                "geographic": False}


def test_a_band_read_by_the_gis_gives_the_numbers_of_the_file(town):
    """Pro and QGIS read the raster themselves and pass arrays (Pro
    cannot load rasterio). The numbers must be those of the file path.
    BROKEN WITH: row centres counted from the bottom (y_min +
    (row + 0.5) * h) - the trees then sit 200 m south and every
    distance moves."""
    from equipop.pixels import mass_from_values
    path, people = town
    # where the trees are, written down rather than computed: rows and
    # columns 10 to 19 of a 10 m grid whose north-west corner is
    # (500000, 6600400) - so x 500100-500200, y 6600200-6600300
    p = _payload(path)
    trees = mass_from_values(p["array"].astype("float32"), p["x_min"],
                             p["y_max"], 10, 10, base={"classes": [10]})
    assert len(trees) == 100 and np.allclose(trees.ha, 0.01)
    assert trees.x.min() == 500105 and trees.x.max() == 500195
    assert trees.y.min() == 6600205 and trees.y.max() == 6600295
    boxes = dict(base="10 20", treatment="10", hectares="0,5 2",
                 radius="100", **QUIET)
    by_path = run(people, path, **boxes)
    by_gis = run(people, _payload(path), **boxes)
    by_bands = run(people, dict(p, bands={1: p["array"]}), **boxes)
    for c in by_path.columns:
        assert np.allclose(by_path[c], by_gis[c], equal_nan=True), c
        assert np.allclose(by_path[c], by_bands[c], equal_nan=True), c


def test_a_formula_over_two_bands_of_a_file(tmp_path):
    """NDVI from a red and a near-infrared band: a field of NDVI 0.8
    around the first person, bare ground (0.1) elsewhere, nodata in
    one corner of the red band. BROKEN WITH: the bands' nodata not turned
    into NaN - the corner's red then reads 0, its NDVI 1.0, and 25
    pixels of nothing count as the greenest field."""
    rasterio = pytest.importorskip("rasterio")
    from affine import Affine
    red = np.full((40, 40), 1000, "uint16")
    nir = np.full((40, 40), 1222, "uint16")           # NDVI 0.1
    red[10:20, 10:20], nir[10:20, 10:20] = 1000, 9000  # NDVI 0.8
    red[35:, 35:] = 0              # nodata in the red band only: with
                                   # it read as 0, NDVI there is 1.0
    p = tmp_path / "s2.tif"
    with rasterio.open(p, "w", driver="GTiff", height=40, width=40,
                       count=2, dtype="uint16", crs="EPSG:3006", nodata=0,
                       transform=Affine(10, 0, 500000, 0, -10,
                                        6600400)) as d:
        d.write(red, 1)
        d.write(nir, 2)
    people = pd.DataFrame({"x": [500150.0], "y": [6600250.0]})
    said = []
    got = run(people, p, value="ndvi(2, 1)", base="0,5 to 1",
              hectares="1", say=said.append)
    # the field IS the 1 ha of base, so Dist_1 is its farthest pixel
    assert got.Dist_1[0] == pytest.approx(45 * np.sqrt(2), abs=0.01)
    assert any("ndvi(2, 1)" in s and "1,575 with a value" in s
               for s in said)
    with pytest.raises(BadNumber, match="band 3 does not exist"):
        run(people, p, value="ndvi(3, 1)", base="0,5 to 1",
            hectares="1", **QUIET)


def test_a_row_without_coordinates_gets_empty_results(town):
    """An empty geometry is a row the door must keep (results are
    matched by position), with nothing in it - and the others must not
    move. BROKEN WITH: NaN coordinates passed to the engine."""
    path, people = town
    holed = pd.concat([people.iloc[:1],
                       pd.DataFrame({"x": [np.nan], "y": [np.nan]}),
                       people.iloc[1:]], ignore_index=True)
    boxes = dict(base="10", treatment="10", hectares="1", radius="100",
                 **QUIET)
    got = run(holed, path, **boxes)
    want = run(people, path, **boxes)
    assert got.loc[1, ["Dist_1", "T_1", "B_r100"]].isna().all()
    assert np.allclose(got.drop(index=1)["Dist_1"], want["Dist_1"])


@pytest.mark.parametrize("hectares, radius, treatment", [
    ("1 2,5", "300", "10"), ("5", "", ""), ("", "150,5", "0,7 to 1"),
    ("0,5", "100", ""),
])
def test_result_names_are_the_columns_run_writes(town, hectares, radius,
                                                 treatment):
    """A door checks a shapefile's ten characters before running, and
    the names hold no '.', which a geodatabase field cannot. BROKEN
    WITH: result_names left on 1.65.0's Got_ and Mass_r columns."""
    path, people = town
    got = run(people, path, base="10 20", treatment=treatment,
              hectares=hectares, radius=radius, **QUIET)
    assert result_names(hectares, radius, treatment) == [
        c for c in got.columns if c not in ("x", "y")]
    assert not [c for c in got.columns if "." in c]

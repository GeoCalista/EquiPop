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
    got = run(people, p, value='ndvi("s2"[2], "s2"[1])',
              base="0,5 to 1", hectares="1", say=said.append)
    # the field IS the 1 ha of base, so Dist_1 is its farthest pixel
    assert got.Dist_1[0] == pytest.approx(45 * np.sqrt(2), abs=0.01)
    assert any('ndvi("s2"[2], "s2"[1])' in s and "1,575 with a value"
               in s for s in said)
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


def test_the_radius_box_takes_several_radii_never_thousands(town):
    """John, 22 November 2026: '100 200' in the radius box was read as
    100,200 m - one radius as wide as Malta, round 9,185 points, hours.
    It is two radii, like the hectares box. BROKEN WITH: parse_radius
    back on to_float, which reads a space as a thousands separator."""
    from equipop.doors.pixelsdoor import parse_radius
    assert parse_radius("100 200") == [100.0, 200.0]
    assert parse_radius("150,5") == [150.5]
    assert parse_radius("") == []
    path, people = town
    got = run(people, path, base="10 20", hectares="", radius="100 200",
              **QUIET)
    assert list(got.columns) == ["x", "y", "B_r100", "B_r200"]
    assert (got.B_r200 >= got.B_r100).all()


# --- John, 22 November 2026: any number of rasters, named in quotes -----

def _tif(path, arrays, x0=500000.0, y1=6600400.0, cell=10.0, nodata=0):
    rasterio = pytest.importorskip("rasterio")
    from affine import Affine
    arrays = [np.asarray(a) for a in arrays]
    with rasterio.open(path, "w", driver="GTiff", height=arrays[0].shape[0],
                       width=arrays[0].shape[1], count=len(arrays),
                       dtype=arrays[0].dtype, crs="EPSG:3006",
                       nodata=nodata,
                       transform=Affine(cell, 0, x0, 0, -cell, y1)) as d:
        for i, a in enumerate(arrays, 1):
            d.write(a, i)
    return path


def _red_nir():
    red = np.full((40, 40), 1000, "uint16")
    nir = np.full((40, 40), 1222, "uint16")            # NDVI 0.1
    nir[10:20, 10:20] = 9000                            # NDVI 0.8
    return red, nir


PEOPLE = pd.DataFrame({"x": [500150.0, 500300.0], "y": [6600250.0,
                                                       6600100.0]})
CHAIN = dict(base="0,05 to 1", treatment="0,5 to 1", hectares="0,5 1")
NDVI = 'ndvi("nir", "red")'


def test_two_single_band_files_equal_one_two_band_file(tmp_path):
    """ndvi("nir", "red") over two files gives the numbers of
    ndvi("stack"[2], "stack"[1]) over a stack of the same bands, and the
    run log says which file played which part. BROKEN WITH: each name
    resolved to the first raster given - NDVI is then 0 everywhere."""
    red, nir = _red_nir()
    a = _tif(tmp_path / "T33SVB_B04_10m.tif", [red])
    b = _tif(tmp_path / "T33SVB_B08_10m.tif", [nir])
    stack = _tif(tmp_path / "stack.tif", [red, nir])
    said = []
    two = run(PEOPLE, rasters={"red": a, "nir": b}, value=NDVI,
              say=said.append, **CHAIN)
    one = run(PEOPLE, stack, value='ndvi("stack"[2], "stack"[1])',
              **CHAIN, **QUIET)
    for c in two.columns:
        assert np.allclose(two[c], one[c], equal_nan=True), c
    assert any('"red" = T33SVB_B04_10m.tif' in s for s in said)
    assert any('ndvi: nir = "nir", red = "red"' in s for s in said)
    assert not any("WARNING" in s for s in said)


def test_ten_rasters_are_as_easy_as_two(tmp_path):
    """No limit: the mean of ten rasters, each named in quotes."""
    names = [f"r{i}" for i in range(10)]
    rasters = {n: _tif(tmp_path / f"{n}.tif",
                       [np.full((40, 40), 10 * (i + 1), "uint16")])
               for i, n in enumerate(names)}
    got = run(PEOPLE, rasters=rasters,
              value="(" + " + ".join(f'"{n}"' for n in names) + ") / 10",
              base="55", hectares="1", **QUIET)
    assert got.Dist_1.notna().all()          # every pixel's mean is 55


def test_sentinel_band_codes_that_do_not_fit_their_role_are_flagged(
        tmp_path):
    """The two files under the wrong names: the B08 file called "red",
    the B04 file called "nir". The run goes on (a name is only a name)
    but says it twice. BROKEN WITH: the file names left out of the
    check."""
    red, nir = _red_nir()
    a = _tif(tmp_path / "T33SVB_B08_10m.tif", [nir])
    b = _tif(tmp_path / "T33SVB_B04_10m.tif", [red])
    said = []
    # swapped, NDVI is negative everywhere; an empty base still runs
    run(PEOPLE, rasters={"red": a, "nir": b}, value=NDVI,
        say=said.append, hectares="1")
    warnings = [s for s in said if "WARNING" in s]
    assert len(warnings) == 2 and "swapped" in warnings[0]


def test_names_are_found_whatever_their_case_and_refused_when_wrong(
        tmp_path):
    red, nir = _red_nir()
    rasters = {"Red": _tif(tmp_path / "a.tif", [red]),
               "NIR": _tif(tmp_path / "b.tif", [nir])}
    got = run(PEOPLE, rasters=rasters, value=NDVI, **CHAIN, **QUIET)
    assert got.Dist_1.notna().all()
    with pytest.raises(BadNumber, match='no raster is called that.*"Red"'):
        run(PEOPLE, rasters=rasters, value='ndvi("nir", "rod")', **CHAIN,
            **QUIET)
    with pytest.raises(BadNumber, match="must name the one it means"):
        run(PEOPLE, rasters=rasters, value="", **CHAIN, **QUIET)
    with pytest.raises(BadNumber, match="both called"):
        run(PEOPLE, rasters=[("red", rasters["Red"]),
                             ("red", rasters["NIR"])], value='"red"',
            **CHAIN, **QUIET)


def test_rasters_with_different_extents_use_their_overlap(tmp_path):
    """"nir" covers only the north-west 30 x 30 pixels of "red"'s 40 x
    40, on the same grid: the value exists where both do. BROKEN WITH:
    the offset taken as 0 - the pixels then land on the wrong ones."""
    red, nir = _red_nir()
    a = _tif(tmp_path / "a.tif", [red])
    b = _tif(tmp_path / "b.tif", [nir[:30, :30]])
    said = []
    got = run(PEOPLE, rasters={"red": a, "nir": b}, value=NDVI,
              say=said.append, **CHAIN)
    full = run(PEOPLE, rasters={"red": a, "nir": _tif(tmp_path / "b2.tif",
                                                       [nir])},
               value=NDVI, **CHAIN, **QUIET)
    assert any("overlap in 30 x 30 pixels" in s for s in said)
    assert got.R_0_5[0] == pytest.approx(full.R_0_5[0])   # inside both
    # shift "nir" 5 pixels east: its green field moves 50 m with it
    c = _tif(tmp_path / "c.tif", [nir[:, :35]], x0=500050.0)
    moved = run(PEOPLE, rasters={"red": a, "nir": c}, value=NDVI,
                **CHAIN, **QUIET)
    assert moved.R_0_5[0] < 1.0


@pytest.mark.parametrize("make, says", [
    (lambda p, n: _tif(p, [n[::2, ::2]], cell=20.0), "one pixel size"),
    (lambda p, n: _tif(p, [n], x0=500005.0), "not on the grid"),
    (lambda p, n: _tif(p, [n], x0=600000.0), "do not overlap"),
])
def test_rasters_that_cannot_be_combined_are_refused(tmp_path, make,
                                                     says):
    """No resampling and no snapping behind the user's back."""
    red, nir = _red_nir()
    a = _tif(tmp_path / "a.tif", [red])
    with pytest.raises(BadNumber, match=says):
        run(PEOPLE, rasters={"red": a, "nir": make(tmp_path / "b.tif",
                                                   nir)},
            value=NDVI, **CHAIN, **QUIET)


# --- John, 22 November 2026: say what each column holds ------------------

def test_the_run_ends_by_saying_what_each_new_column_holds(tmp_path):
    """One line per column written, in the words of the boxes as typed.
    BROKEN WITH: a column left out of describe() - the set of names
    said then differs from the columns written."""
    red, nir = _red_nir()
    rasters = {"red": _tif(tmp_path / "a.tif", [red]),
               "nir": _tif(tmp_path / "b.tif", [nir])}
    said = []
    got = run(PEOPLE, rasters=rasters, value=NDVI, radius="100 200",
              say=said.append, **CHAIN)
    i = said.index("[pixels] The new columns:")
    lines = said[i + 1:]
    names = {s.split(":")[0].strip("[pixels] ").strip() for s in lines}
    assert names == set(got.columns) - {"x", "y"}
    text = " ".join(lines)
    assert "nearest 0.5 ha of base lie (base: pixels whose " \
           'value (ndvi("nir", "red")) is 0,05 to 1)' in text
    assert "R_r200: T_r200 / B_r200" in text


def test_a_base_of_every_pixel_is_flagged_as_measuring_only_a_circle(
        tmp_path):
    """John's Malta run: Dist_20 was about 252 m everywhere - the radius
    of a 20 ha circle - because every pixel was base. The run now says
    so; with a base that picks some pixels it does not. BROKEN WITH:
    the note's share computed against the whole raster, nodata
    included - it then never fires on an image with a nodata edge."""
    red, nir = _red_nir()
    nir[:, :3] = 0                                   # a nodata edge
    rasters = {"red": _tif(tmp_path / "a.tif", [red]),
               "nir": _tif(tmp_path / "b.tif", [nir])}
    said = []
    run(PEOPLE, rasters=rasters, value=NDVI, hectares="1 2",
        say=said.append)
    note = [s for s in said if "the radius of a circle" in s]
    assert len(note) == 1 and "Dist_2 is about 80 m" in note[0]
    said = []                          # the base: the green field only
    run(PEOPLE, rasters=rasters, value=NDVI, base="0,5 to 1",
        hectares="0,5", say=said.append)
    assert not any("the radius of a circle" in s for s in said)


# --- BACKLOG 512 a, ruling R-55: the real cell, never a hidden 100 m ------

def _one(arr, cell_w=10.0, cell_h=10.0):
    return {"bands": {1: np.asarray(arr, np.float32)}, "x_min": 0.0,
            "y_max": cell_h * np.asarray(arr).shape[0], "cell_w": cell_w,
            "cell_h": cell_h, "nodata": None, "geographic": False}


def test_a_person_on_a_pixel_gathers_it_within_the_pixel_s_own_disc():
    """The review's case: one 10 m pixel, the person at its centre,
    k = 0.01 ha (all of it). Green spread evenly over the pixel (R-55)
    is all gathered at the radius of the pixel's own disc, 5.64 m.
    BROKEN WITH: unit_size left at 100 - 56.42 m, a 100 m cell's disc."""
    got = run(pd.DataFrame({"x": [5.0], "y": [5.0]}), _one([[1.0]]),
              hectares="0,01 0,005", **QUIET)
    assert got.Dist_0_01[0] == pytest.approx(np.sqrt(100 / np.pi))
    assert got.Dist_0_005[0] == pytest.approx(np.sqrt(50 / np.pi))


def test_a_partly_green_analysis_cell_spreads_its_green_over_the_cell():
    """A 50 m analysis cell holding 7 green 10 m pixels (0.07 ha), the
    person at the cell's centre: half of it, 0.035 ha, lies within the
    disc holding half the CELL's area - not half the pixels' area."""
    a = np.zeros((5, 5), np.float32)
    a.flat[[0, 3, 7, 11, 12, 18, 24]] = 1.0
    got = run(pd.DataFrame({"x": [25.0], "y": [25.0]}), _one(a),
              base="1", hectares="0,035", cell="50", **QUIET)
    assert got.Dist_0_035[0] == pytest.approx(np.sqrt(2500 * 0.5 / np.pi))


def test_a_non_square_pixel_counts_by_its_area():
    got = run(pd.DataFrame({"x": [5.0], "y": [10.0]}),
              _one([[1.0]], cell_w=10.0, cell_h=20.0), hectares="0,02",
              **QUIET)
    assert got.Dist_0_02[0] == pytest.approx(np.sqrt(200 / np.pi))


def test_the_first_ring_starts_at_the_edge_of_the_real_cell():
    """R-60 (BACKLOG 519, John, 26 November 2026: "(a)"): a person on no
    pixel gathers the first pixel's hectares from the near edge of THAT
    pixel's disc - 300 m less the real 10 m pixel's equal-area radius,
    5.64 m - not from where they stand. Half the pixel is reached at
    297.19 m, past its near edge. Until 1.66.0 it was 212.17 m, closer
    than the pixel itself; the hidden 100 m cell of BACKLOG 512 would
    give 273.3 m. BROKEN WITH: first_ring_from_edge left off in
    pixels.reach."""
    from equipop.pixels import reach
    p = pd.DataFrame({"x": [0.0], "y": [0.0]})
    m = pd.DataFrame({"x": [300.0], "y": [0.0], "ha": [0.01]})
    edge = 300 - 10 / np.sqrt(np.pi)
    want = np.sqrt(edge ** 2 * 0.5 + 300 ** 2 * 0.5)
    got = reach(p, m, [0.005]).Dist_0_005[0]
    assert got == pytest.approx(want)
    assert edge < got < 300
    with pytest.raises(ValueError, match="give unit_size"):
        reach(p, pd.DataFrame({"x": [300.0, 400.0], "y": [0.0, 0.0],
                               "ha": [0.01, 0.02]}), [0.005])


def test_a_pixel_whose_formula_divides_by_zero_adds_no_hectares():
    """BACKLOG 512 b, through the base box: at r = 0, 1 / "r" > 0 has no
    value, so that pixel is in no base - only one 0.01 ha pixel is, and
    0.015 ha is never gathered. BROKEN WITH: only the final result
    cleaned - the comparison turned the infinity into 1, both pixels
    were base, and Dist_0_015 had a distance."""
    got = run(pd.DataFrame({"x": [5.0], "y": [5.0]}),
              rasters={"r": _one([[0.0, 2.0]])}, value='1 / "r" > 0',
              base="1", hectares="0,005 0,015", **QUIET)
    assert got.Dist_0_005.notna().all()
    assert got.Dist_0_015.isna().all()


# --- BACKLOG 512 c: a raster's coordinate system, unit and mask ---------

def _tif2(path, a, crs="EPSG:3006", mask=None, x0=500000.0,
          y1=6600020.0, cell=10.0):
    rasterio = pytest.importorskip("rasterio")
    from affine import Affine
    a = np.asarray(a)
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
        with rasterio.open(path, "w", driver="GTiff", height=a.shape[0],
                           width=a.shape[1], count=1, dtype=a.dtype,
                           crs=crs,
                           transform=Affine(cell, 0, x0, 0, -cell,
                                            y1)) as d:
            d.write(a, 1)
            if mask is not None:
                d.write_mask(np.where(mask, 255, 0).astype("uint8"))
    return path


ONE_PERSON = pd.DataFrame({"x": [500005.0], "y": [6600015.0]})


def test_two_utm_zones_are_refused_not_combined(tmp_path):
    """The same eastings and northings in UTM 32N and 33N are two
    places some 600 km apart. BROKEN WITH: only "degrees or not"
    compared - the review got 0.02 ha within 100 m."""
    a = np.ones((2, 2), "uint8")
    r32 = _tif2(tmp_path / "a.tif", a, crs="EPSG:32632")
    r33 = _tif2(tmp_path / "b.tif", a, crs="EPSG:32633")
    with pytest.raises(BadNumber, match="different coordinate systems"):
        run(ONE_PERSON, rasters={"a": r32, "b": r33}, value='"a" + "b"',
            hectares="0,01", **QUIET)
    same = _tif2(tmp_path / "c.tif", a, crs="EPSG:32632")
    got = run(ONE_PERSON, rasters={"a": r32, "c": same},
              value='"a" + "c"', hectares="0,01", **QUIET)
    assert got.Dist_0_01.notna().all()


def test_a_raster_in_feet_or_without_a_system_is_refused(tmp_path):
    """A 100 x 100 US survey foot pixel is 0.093 ha, and was read as 1
    ha. BROKEN WITH: the unit left unchecked."""
    from equipop.pixels import pixels_to_mass
    feet = _tif2(tmp_path / "ft.tif", np.ones((2, 2), "uint8"),
                 crs="EPSG:2263", cell=100.0)
    with pytest.raises(BadNumber, match="US survey foot, not metres"):
        run(ONE_PERSON, feet, hectares="1", **QUIET)
    with pytest.raises(ValueError, match="US survey foot, not metres"):
        pixels_to_mass(feet, classes=[1])
    bare = _tif2(tmp_path / "none.tif", np.ones((2, 2), "uint8"),
                 crs=None)
    with pytest.raises(BadNumber, match="no coordinate system"):
        run(ONE_PERSON, bare, hectares="0,01", **QUIET)


# ---------------------------------------------------------------------
# R-59, decision d (John, 26 November 2026: "(b)"): a raster in DEGREES
# is used as it is. Each counting pixel keeps its value and its own
# area on the WGS84 ellipsoid; only its centre is placed in the
# people's system. Nothing is resampled.
# ---------------------------------------------------------------------

def _stockholm_block(tmp_path, a=None):
    """A 0.04 x 0.04 degree raster of 0.0001 degree pixels near
    Stockholm, class 10 in the 0.02 x 0.02 degree block 18.05-18.07 E,
    59.32-59.34 N, class 20 elsewhere."""
    d, n = 0.0001, 400
    x0, y1 = 18.04, 59.35
    if a is None:
        lon = x0 + (np.arange(n) + 0.5) * d
        lat = y1 - (np.arange(n) + 0.5) * d
        a = np.full((n, n), 20, "uint8")
        a[np.ix_((lat > 59.32) & (lat < 59.34),
                 (lon > 18.05) & (lon < 18.07))] = 10
    return _tif2(tmp_path / "deg.tif", a, crs="EPSG:4326", x0=x0, y1=y1,
                 cell=d), a


def _sweref(lon, lat):
    T = pytest.importorskip("pyproj").Transformer.from_crs(
        "EPSG:4326", "EPSG:3006", always_xy=True)
    return T.transform(lon, lat)


def test_a_raster_in_degrees_asks_which_system_the_people_are_in(tmp_path):
    """A Python caller with a file must name the people's system; the
    sentence says how. BROKEN WITH: the degrees read as metres."""
    deg, _ = _stockholm_block(tmp_path)
    with pytest.raises(BadNumber, match="people_crs"):
        run(ONE_PERSON, deg, base="10", hectares="1", **QUIET)
    with pytest.raises(BadNumber, match="metres"):
        run(ONE_PERSON, deg, base="10", hectares="1",
            people_crs="EPSG:4326", **QUIET)


def test_a_raster_in_degrees_gives_true_distances(tmp_path):
    """From the middle of the 2 x 2 km block, 1 ha is gathered within
    the 1 ha circle (56.4 m); from 0.01 degree east of it, the distance
    is past the true gap to its edge (569.2 m, pyproj's geodesic).
    BROKEN WITH: move_pixels() left out - lon/lat against SWEREF."""
    Geod = pytest.importorskip("pyproj").Geod
    deg, _ = _stockholm_block(tmp_path)
    x, y = _sweref([18.06, 18.08], [59.33, 59.33])
    got = run(pd.DataFrame({"x": x, "y": y}), deg, base="10",
              hectares="1", people_crs="EPSG:3006", **QUIET)
    assert got.Dist_1[0] == pytest.approx(100 * np.sqrt(1 / np.pi),
                                          rel=0.01)
    _, _, gap = Geod(ellps="WGS84").inv(18.08, 59.33, 18.07, 59.33)
    assert gap < got.Dist_1[1] < gap + 60


def test_the_block_keeps_its_true_area_and_nothing_is_resampled(tmp_path):
    """The block's hectares are its geodesic area (253.66 ha), and every
    class-10 pixel is one point: no pixel split, merged or blurred into
    its neighbour's class."""
    Geod = pytest.importorskip("pyproj").Geod
    deg, a = _stockholm_block(tmp_path)
    said = []
    x, y = _sweref([18.06], [59.33])
    run(pd.DataFrame({"x": x, "y": y}), deg, base="10", hectares="1",
        people_crs="EPSG:3006", say=said.append)
    area, _ = Geod(ellps="WGS84").polygon_area_perimeter(
        [18.05, 18.07, 18.07, 18.05], [59.32, 59.32, 59.34, 59.34])
    base = [s for s in said if s.startswith("[pixels] base:")][0]
    assert f"{abs(area) / 1e4:,.1f} ha" in base
    moved = [s for s in said if "pixel centres placed" in s][0]
    assert f"{int((a == 10).sum()):,} pixel centres" in moved
    assert "nothing resampled" in moved


def test_an_analysis_cell_works_on_a_raster_in_degrees(tmp_path):
    """The cell is in metres in the people's system, after the move;
    the hectares are kept, only gathered into fewer points."""
    deg, _ = _stockholm_block(tmp_path)
    x, y = _sweref([18.06, 18.08], [59.33, 59.33])
    people = pd.DataFrame({"x": x, "y": y})
    said = []
    got = run(people, deg, base="10", hectares="5", cell="100",
              people_crs="EPSG:3006", say=said.append)
    base = [s for s in said if s.startswith("[pixels] base:")][0]
    assert "analysis cells of 100 m" in base and "253.7 ha" in base
    assert got.Dist_5.notna().all()
    with pytest.raises(BadNumber, match="smaller"):
        run(people, deg, base="10", hectares="5", cell="5",
            people_crs="EPSG:3006", **QUIET)


def test_a_gis_door_s_own_conversion_is_used(tmp_path):
    """A door's payload brings its conversion (QGIS's or Pro's own) and
    says which; pyproj is not asked."""
    deg, a = _stockholm_block(tmp_path)
    T = pytest.importorskip("pyproj").Transformer.from_crs(
        "EPSG:4326", "EPSG:3006", always_xy=True)
    calls = []

    def door(lon, lat):
        calls.append(len(lon))
        return T.transform(lon, lat)

    payload = {"bands": {1: a}, "x_min": 18.04, "y_max": 59.35,
               "cell_w": 0.0001, "cell_h": 0.0001, "nodata": {1: None},
               "geographic": True, "to_people": door,
               "moved_by": "QGIS (EPSG:4326 to EPSG:3006)"}
    said = []
    x, y = _sweref([18.06], [59.33])
    got = run(pd.DataFrame({"x": x, "y": y}), payload, base="10",
              hectares="1", say=said.append)
    assert calls == [int((a == 10).sum())]
    assert any("by QGIS (EPSG:4326 to EPSG:3006)" in s for s in said)
    assert got.Dist_1[0] == pytest.approx(56.4, rel=0.01)


def test_a_masked_pixel_has_no_value_even_without_nodata(tmp_path):
    """Two 10 m pixels, the second masked by the file's own mask and
    no nodata value: 0.01 ha, not 0.02. BROKEN WITH: raw band reads."""
    from equipop.pixels import pixels_to_mass
    r = _tif2(tmp_path / "m.tif", np.ones((1, 2), "uint8"),
              mask=np.array([[True, False]]), y1=6600010.0)
    got = run(ONE_PERSON.assign(y=6600005.0), r,
              hectares="0,005 0,015", **QUIET)
    assert got.Dist_0_005.notna().all() and got.Dist_0_015.isna().all()
    assert pixels_to_mass(r, classes=[1]).ha.sum() == pytest.approx(0.01)


def test_hectares_or_radii_one_column_name_cannot_tell_apart_stop_the_run():
    """BACKLOG 512 d: '0.1000001 0.1000002' gave Dist_0_1 twice, one
    column holding the other's answer. BROKEN WITH: the clash check
    left out of parse_hectares."""
    from equipop.doors.pixelsdoor import result_names
    with pytest.raises(BadNumber, match="0.1000002 and 0.1000001 both"):
        result_names("0.1000001 0.1000002")
    with pytest.raises(BadNumber, match="Radius"):
        result_names("1", "100.0000001 100.0000002")
    assert result_names("0.1 0.2", "100 100,5") == [
        "Dist_0_1", "Dist_0_2", "B_r100", "B_r100_5"]



# ---------------------------------------------------------------------
# R-60 (BACKLOG 519, John, 26 November 2026: "(a)"): a k smaller than
# the first pixel a person reaches is gathered within that pixel's own
# disc, never closer than its near edge.
# ---------------------------------------------------------------------

def test_a_small_k_is_never_gathered_before_the_first_pixel():
    """A person 572 m east of a block of 10 m pixels: every k below one
    pixel is reached between the pixel's near edge and its centre.
    Until 1.66.0, 0.01 ha came back at 404 m."""
    from equipop.pixels import pixels_from_array, reach
    a = np.zeros((300, 300))
    a[100:200, 100:200] = 1
    m = pixels_from_array(a, 0, 3000, 10, 10, classes=[1])
    p = pd.DataFrame({"x": [m.x.max() + 572.0], "y": [1500.0]})
    got = reach(p, m, [0.001, 0.005, 0.01])
    near = 572.0 - 10 / np.sqrt(np.pi)
    d = got[["Dist_0_001", "Dist_0_005", "Dist_0_01"]].to_numpy()[0]
    assert (d > near).all() and (d <= 572.0 + 1e-9).all()
    assert (np.diff(d) > 0).all()


def test_a_coarse_raster_with_a_small_k():
    """1 ha pixels (WorldPop's 100 m) 2,000 m away: 0.5 ha is reached
    inside the first pixel's disc (1,971.99 m), 1 ha at its centre
    (2,000 m). Until 1.66.0, 0.5 ha came back at 1,414 m."""
    from equipop.pixels import pixels_from_array, reach
    b = np.zeros((60, 60))
    b[0:10, 0:10] = 1
    m = pixels_from_array(b, 0, 6000, 100, 100, classes=[1])
    p = pd.DataFrame({"x": [m.x.max() + 2000.0], "y": [m.y.max()]})
    got = reach(p, m, [0.5, 1])
    edge = 2000.0 - 100 / np.sqrt(np.pi)
    assert got.Dist_0_5[0] == pytest.approx(
        np.sqrt(edge ** 2 * 0.5 + 2000.0 ** 2 * 0.5))
    assert got.Dist_1[0] == pytest.approx(2000.0)


def test_tool_1_is_unchanged_by_r_60():
    """The rule is tool 3b's: the engine's default keeps every Counts
    and Shares number as it was. A 250 m cell of nobody, 300 m from a
    cell of 20, asks for 1: BACKLOG 191's start at its own equal-area
    radius (141.05 m), 152.97 m - not R-60's near edge of the other
    cell (295.4 m from 158.95 m)."""
    from equipop.cells import CellData
    from equipop.fastcounts import run_knn_counts
    cd = CellData(E=np.array([0.0, 300.0]), N=np.zeros(2),
                  n=np.array([0.0, 20.0]), binary_sums={},
                  unit_size=250.0)
    r = run_knn_counts(cd, [1], origins=np.array([0]), report=False)
    own = 250 / np.sqrt(np.pi)
    assert r["Dist_1"][0] == pytest.approx(
        np.sqrt(own ** 2 + (300 ** 2 - own ** 2) / 20))

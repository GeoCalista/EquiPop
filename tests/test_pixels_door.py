"""Tool 3b's shared half: the boxes as typed, and the run both GIS doors
call (BACKLOG 508)."""
import numpy as np
import pandas as pd
import pytest

from equipop.doors.numbers import BadNumber
from equipop.doors.pixelsdoor import parse_hectares, parse_pixels, run


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
    with pytest.raises(BadNumber):
        parse_hectares("0 5")
    with pytest.raises(BadNumber):
        parse_hectares("")


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


def test_run_equals_the_core(town):
    """The door adds parsing and refusals, nothing else: its numbers are
    pixels.reach's and pixels.share_within's, and a range of one value
    picks exactly that class. BROKEN WITH: the radius read as
    kilometres (radius * 1000) - Mass_r100 then holds every pixel."""
    from equipop.pixels import pixels_to_mass, reach, share_within
    path, people = town
    got = run(people, path, "10 20", "0,5 1 2", "100", say=lambda *a: None)
    mass = pixels_to_mass(path, classes=[10, 20])
    want = reach(people, mass, [0.5, 1, 2])
    for c in ("Dist_0.5", "Dist_1", "Dist_2", "Got_2"):
        assert np.allclose(got[c.replace(".", "_")], want[c]), c
    sw = share_within(people, mass, 100.0)
    assert np.allclose(got["Mass_r100"], sw["Mass_r"])
    assert np.allclose(got["Share_r100"], sw["Share_r"])
    only_grass = run(people, path, "20 to 20", "0,5", say=lambda *a: None)
    assert np.allclose(only_grass["Dist_0_5"],
                       reach(people, pixels_to_mass(path, classes=[20]),
                             [0.5])["Dist_0.5"])


def test_run_refuses_degrees_and_mixed_systems(town):
    path, people = town
    with pytest.raises(BadNumber, match="degrees"):
        run(people, path, "10", "1", layer_is_metric=False)
    with pytest.raises(BadNumber, match="different"):
        run(people, path, "10", "1", same_crs=False)


def test_run_says_when_the_raster_holds_too_little(town):
    path, people = town
    said = []
    got = run(people, path, "10 20", "5", say=said.append)
    assert np.allclose(got["Got_5"], 2.0)
    assert any("less than 5 ha" in s for s in said)


def test_run_says_when_no_pixel_matches(town):
    path, people = town
    with pytest.raises(BadNumber, match="No pixel"):
        run(people, path, "99", "1", say=lambda *a: None)


# --- BACKLOG 509: the band as the GIS doors hand it over -------------

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
    from equipop.pixels import pixels_from_array
    path, people = town
    # where the trees are, written down rather than computed: rows and
    # columns 10 to 19 of a 10 m grid whose north-west corner is
    # (500000, 6600400) - so x 500100-500200, y 6600200-6600300
    trees = pixels_from_array(**{k: v for k, v in _payload(path).items()
                                 if k not in ("array", "nodata",
                                              "geographic")},
                              a=_payload(path)["array"], classes=[10])
    assert len(trees) == 100 and np.allclose(trees.ha, 0.01)
    assert trees.x.min() == 500105 and trees.x.max() == 500195
    assert trees.y.min() == 6600205 and trees.y.max() == 6600295
    quiet = dict(say=lambda *a: None)
    by_path = run(people, path, "10 20", "0,5 2", "100", **quiet)
    by_gis = run(people, _payload(path), "10 20", "0,5 2", "100", **quiet)
    for c in by_path.columns:
        assert np.allclose(by_path[c], by_gis[c], equal_nan=True), c


def test_the_band_box_picks_a_band_of_a_stack(town):
    """A multiband image (red, green, blue, near-infrared...) arrives
    as a stack; the band box picks one, counted from 1, and a band that
    is not there is refused with a sentence."""
    path, people = town
    one = _payload(path)
    stack = dict(one, array=np.stack([np.zeros_like(one["array"]),
                                      one["array"]]))
    quiet = dict(say=lambda *a: None)
    got = run(people, stack, "10", "1", band=2, **quiet)
    want = run(people, one, "10", "1", **quiet)
    assert np.allclose(got["Dist_1"], want["Dist_1"])
    with pytest.raises(BadNumber, match="band 3"):
        run(people, stack, "10", "1", band=3, **quiet)
    with pytest.raises(BadNumber, match="one band"):
        run(people, one, "10", "1", band=2, **quiet)


def test_a_row_without_coordinates_gets_empty_results(town):
    """An empty geometry is a row the door must keep (results are
    matched by position), with nothing in it - and the others must not
    move. BROKEN WITH: NaN coordinates passed to the engine."""
    path, people = town
    holed = pd.concat([people.iloc[:1],
                       pd.DataFrame({"x": [np.nan], "y": [np.nan]}),
                       people.iloc[1:]], ignore_index=True)
    quiet = dict(say=lambda *a: None)
    got = run(holed, path, "10", "1", "100", **quiet)
    want = run(people, path, "10", "1", "100", **quiet)
    assert got.loc[1, ["Dist_1", "Got_1", "Mass_r100"]].isna().all()
    assert np.allclose(got.drop(index=1)["Dist_1"], want["Dist_1"])


def test_result_names_are_known_before_the_run():
    """A door checks a shapefile's ten characters before running, and
    the names hold no '.', which a geodatabase field cannot.
    BROKEN WITH: _tag keeping the '.'."""
    from equipop.doors.pixelsdoor import result_names
    assert result_names("1 2,5", "300") == [
        "Dist_1", "Got_1", "Dist_2_5", "Got_2_5", "Mass_r300",
        "Share_r300"]
    assert result_names("5") == ["Dist_5", "Got_5"]

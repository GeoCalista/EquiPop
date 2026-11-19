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
        assert np.allclose(got[c], want[c]), c
    sw = share_within(people, mass, 100.0)
    assert np.allclose(got["Mass_r100"], sw["Mass_r"])
    assert np.allclose(got["Share_r100"], sw["Share_r"])
    only_grass = run(people, path, "20 to 20", "0,5", say=lambda *a: None)
    assert np.allclose(only_grass["Dist_0.5"],
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

"""Pixels as mass: green reach and green share (BACKLOG 507).

John, 19 November 2026: image analysis is the board's first target. The
engine counts mass outward until it reaches k; here the mass is hectares
of pixels. Every number below is checked against a second computation
written separately in this file.
"""
import math

import numpy as np
import pandas as pd
import pytest

from equipop.datasets import load
from equipop.pixels import pixel_area_ha, reach, share_within

R0 = 100.0 / math.sqrt(math.pi)      # mean radius of a 100 m cell


def _by_hand(px, py, mass, k):
    """EquiPop's rule, written out: sort the pixels by distance, find the
    ring (equal distance) that crosses k hectares, take the share f of it
    that is needed, and interpolate between the ring before (or the own
    cell's radius) and this one: sqrt(d0^2 + f (d^2 - d0^2))."""
    d = np.hypot(mass.x.to_numpy() - px, mass.y.to_numpy() - py)
    order = np.argsort(d, kind="stable")
    d, ha = d[order], mass.ha.to_numpy()[order]
    rings = np.unique(np.round(d, 6))
    before, d_prev = 0.0, R0
    for ring in rings:
        sel = np.abs(d - ring) < 1e-6
        total = ha[sel].sum()
        if before + total >= k - 1e-9:
            f = (k - before) / total
            return math.sqrt(d_prev ** 2 + f * (ring ** 2 - d_prev ** 2))
        before += total
        d_prev = ring
    return float("nan")


def test_reach_is_the_engine_rule_written_out():
    """reach() must equal the rule done by hand, person by person, on
    Gridby's green. BROKEN WITH: the pixels' hectares replaced by 1 each
    (k counted in pixels): every distance moves."""
    g = load("gridby")
    people = g["people"].sample(40, random_state=3).reset_index(drop=True)
    got = reach(people, g["green"], [1, 5, 20])
    for i in range(len(people)):
        for k in (1, 5, 20):
            want = _by_hand(people.x[i], people.y[i], g["green"], k)
            assert got[f"Dist_{k}"][i] == pytest.approx(want, abs=1e-6), (i, k)
            assert got[f"Got_{k}"][i] == pytest.approx(k)


def test_gridby_green_is_planted_where_it_says():
    """Western Park 36 ha, a River Walk of 20 ha, twelve pocket parks of
    0.25 ha, and Hill Forest: every pixel within 500 m of its centre."""
    g = load("gridby")
    gr = g["green"]
    park = gr[(gr.x >= 1400) & (gr.x < 2000) & (gr.y >= 2600) & (gr.y < 3200)]
    assert park.ha.sum() == pytest.approx(36.0)
    walk = gr[np.isclose(gr.x, 2987.5) | np.isclose(gr.x, 3112.5)]
    assert walk.ha.sum() == pytest.approx(20.0)
    forest = gr[np.hypot(gr.x - 5250, gr.y - 3150) <= 500]
    assert forest.ha.sum() == pytest.approx(
        math.pi * 500 ** 2 / 10_000, rel=0.02)
    rest = gr.ha.sum() - park.ha.sum() - walk.ha.sum() - forest.ha.sum()
    assert rest == pytest.approx(12 * 0.25)


def test_the_big_forest_is_on_the_minority_side():
    """The planted lesson: only Hill Forest holds 50 ha in one place, and
    it lies east of the motorway, where the minority share is highest;
    5 ha is close for nearly everyone. BROKEN WITH: HILL_FOREST moved to
    (1500, 1000)."""
    g = load("gridby")
    p = g["people"]
    r = reach(p, g["green"], [5, 50])
    east = (p.x > 4600).to_numpy()
    west = (p.x < 3000).to_numpy()
    assert r.Dist_50[east].mean() < 0.7 * r.Dist_50[west].mean()
    # and a home in the middle of Western Park has 5 ha within a stone's
    # throw, a home in the far south-east corner a long walk
    inside = r[(r.x == 1750) & (r.y == 2950)].Dist_5.iloc[0]
    corner = r[(r.x == 5950) & (r.y == 50)].Dist_5.iloc[0]
    assert inside < 150 and corner > 1500


def test_share_within_counts_every_pixel_in_the_disc():
    """Against a plain loop over every pixel, for a fixed radius and for
    one radius per person."""
    g = load("gridby")
    gr = g["green"]
    people = g["people"].sample(30, random_state=5).reset_index(drop=True)
    radius = np.linspace(100, 900, len(people))
    for rad in (300.0, radius):
        got = share_within(people, gr, rad)
        rr = np.broadcast_to(rad, (len(people),))
        for i in range(len(people)):
            d = np.hypot(gr.x - people.x[i], gr.y - people.y[i])
            want = gr.ha[d <= rr[i]].sum()
            assert got.Mass_r[i] == pytest.approx(want)
            assert got.Share_r[i] == pytest.approx(
                want / (math.pi * rr[i] ** 2 / 10_000))


def test_reach_says_when_the_map_holds_less_than_k():
    """Got_k below k means the map ran out: Dist_k is then the distance
    to the last pixel and is no reach."""
    people = pd.DataFrame({"x": [0.0], "y": [0.0]})
    mass = pd.DataFrame({"x": [100.0, 200.0], "y": [0.0, 0.0],
                         "ha": [1.0, 1.0]})
    r = reach(people, mass, [1, 5])
    assert r.Got_1[0] == pytest.approx(1.0)
    assert r.Got_5[0] == pytest.approx(2.0)


def test_pixel_area_on_a_latitude_longitude_grid():
    """A whole 1-degree band of 30" pixels must add up to the band's
    area on the sphere; one pixel at 60 N is half of one at the
    equator, to within a percent."""
    from affine import Affine
    s = 1 / 120.0
    T = Affine(s, 0, 0.0, 0, -s, 61.0)               # rows from 61 N down
    rows = np.arange(120)                             # 61 N to 60 N
    band = pixel_area_ha(T, rows, geographic=True).sum() * 120  # 120 columns
    R = 6371008.8
    want = R ** 2 * math.radians(1.0) * (
        math.sin(math.radians(61)) - math.sin(math.radians(60))) / 1e4
    assert band == pytest.approx(want, rel=1e-9)
    eq = pixel_area_ha(Affine(s, 0, 0, 0, -s, s), np.array([0]), True)[0]
    north = pixel_area_ha(Affine(s, 0, 0, 0, -s, 60 + s / 2), np.array([0]),
                          True)[0]
    assert north / eq == pytest.approx(0.5, rel=0.01)
    assert pixel_area_ha(Affine(10, 0, 0, 0, -10, 0), np.array([0, 1]),
                         False).tolist() == [0.01, 0.01]


def test_pixels_to_mass_reads_classes_and_ranges(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from affine import Affine
    from equipop.pixels import pixels_to_mass
    a = np.array([[10, 20, 30], [10, 255, 40]], dtype="uint8")
    p = tmp_path / "landcover.tif"
    with rasterio.open(p, "w", driver="GTiff", height=2, width=3, count=1,
                       dtype="uint8", crs="EPSG:3006", nodata=255,
                       transform=Affine(10, 0, 500000, 0, -10, 6600000)) as d:
        d.write(a, 1)
    m = pixels_to_mass(p, classes=[10, 20])
    assert len(m) == 3 and m.ha.sum() == pytest.approx(0.03)
    assert sorted(zip(m.x, m.y)) == [(500005.0, 6599985.0),
                                     (500005.0, 6599995.0),
                                     (500015.0, 6599995.0)]
    r = pixels_to_mass(p, between=(25, 45))            # 30 and 40, not 255
    assert len(r) == 2
    with pytest.raises(ValueError):
        pixels_to_mass(p)

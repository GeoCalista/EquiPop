"""equipop/zones.py - which area a point lies in, and which is nearest
(tool 1b; BACKLOG 521, ruling R-61). Held to shapely where it is there,
and to cases worked by hand everywhere."""
import numpy as np
import pytest

from equipop.zones import Areas


def _sq(x0, y0, size, hole=None):
    r = [(x0, y0), (x0 + size, y0), (x0 + size, y0 + size),
         (x0, y0 + size)]
    return [r] if hole is None else [r, hole]


def test_inside_a_hole_is_outside_and_an_island_in_it_is_inside():
    """The even-odd rule: outer ring, a hole, an island in the hole.
    BROKEN WITH: crossings counted without the hole's edges."""
    hole = [(300, 300), (700, 300), (700, 700), (300, 700)]
    island = [(450, 450), (550, 450), (550, 550), (450, 550)]
    z = Areas([[_sq(0, 0, 1000)[0], hole, island]])
    pi, aj, ins = z.locate(np.array([100.0, 400, 500]),
                           np.array([100.0, 400, 500]))
    assert pi.tolist() == [0, 2] and ins.tolist() == [True, True]


def test_on_a_border_within_millimetres_and_not_beyond():
    """Swedish grid coordinates: the tolerance is about 7 mm."""
    x0, y0 = 670000.0, 6580000.0
    z = Areas([_sq(x0, y0, 1000)])
    assert 0.005 < z.tol < 0.01
    x = np.array([x0 + 1000.004, x0 + 1000.02, x0 + 999.98])
    pi, _, ins = z.locate(x, np.full(3, y0 + 500))
    assert pi.tolist() == [0, 2] and ins.tolist() == [False, True]


def test_the_nearest_area_and_a_tie_goes_to_the_first():
    z = Areas([_sq(0, 0, 100), _sq(200, 0, 100), [], _sq(0, 500, 100)])
    best, d, ties = z.nearest(np.array([150.0, 50, 50]),
                              np.array([50.0, 150, 1000]))
    assert best.tolist() == [0, 0, 3]
    np.testing.assert_allclose(d, [50, 50, 400])
    assert ties.tolist() == [2, 1, 1]
    # among a level only; an empty area is never nearest
    best, _, _ = z.nearest(np.array([150.0]), np.array([50.0]),
                           among=[1, 2])
    assert best.tolist() == [1]
    assert z.empty == [2]


def test_degrees_are_measured_in_metres():
    """Two areas a tenth of a degree of longitude apart at 60 N: the
    gap is about 5.6 km, not 0.1."""
    z = Areas([_sq(18.0, 60.0, 0.05), _sq(18.15, 60.0, 0.05)],
              geographic=True)
    _, d, _ = z.nearest(np.array([18.1]), np.array([60.025]))
    assert d[0] == pytest.approx(0.05 * 111320 * np.cos(np.radians(60.025)),
                                 rel=0.01)


def test_the_same_answers_as_shapely():
    """20,000 points on a 4 x 4 grid of 1 km squares, one with a hole:
    inside, on the border, and the distance to the nearest."""
    shapely = pytest.importorskip("shapely")
    from shapely.geometry import Point, Polygon
    rng = np.random.default_rng(5)
    x0, y0 = 670000.0, 6580000.0
    hole = [(x0 + 1300, y0 + 1300), (x0 + 1700, y0 + 1300),
            (x0 + 1700, y0 + 1700), (x0 + 1300, y0 + 1700)]
    rings = []
    for i in range(4):
        for j in range(4):
            r = _sq(x0 + 1000 * i, y0 + 1000 * j, 1000,
                    hole if (i, j) == (1, 1) else None)
            rings.append(r)
    z = Areas(rings)
    # a quarter of the points ON grid lines, to test the borders
    x = x0 + rng.uniform(-500, 4500, 20000)
    y = y0 + rng.uniform(-500, 4500, 20000)
    on = rng.random(20000) < 0.25
    x[on] = x0 + 1000 * np.round((x[on] - x0) / 1000)
    pi, aj, ins = z.locate(x, y)
    got = set(zip(pi.tolist(), aj.tolist()))
    polys = [Polygon(r[0], r[1:]) for r in rings]
    want = set()
    for k in range(len(x)):
        p = Point(x[k], y[k])
        for j, poly in enumerate(polys):
            if poly.covers(p):
                want.add((k, j))
    assert got == want
    border = {(k, j) for k, j, i in zip(pi, aj, ins) if not i}
    assert border == {(k, j) for k, j in want
                      if polys[j].boundary.distance(Point(x[k], y[k]))
                      <= z.tol}
    out = np.setdiff1d(np.arange(len(x)), pi)[:200]
    _, d, _ = z.nearest(x[out], y[out])
    np.testing.assert_allclose(
        d, [min(poly.distance(Point(x[k], y[k])) for poly in polys)
            for k in out], atol=1e-6)
    assert shapely.__version__

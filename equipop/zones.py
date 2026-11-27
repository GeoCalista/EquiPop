"""
zones.py - which area each point lies in, and which area is nearest
(tool 1b, "Summaries by area"; BACKLOG 521, ruling R-61).

The GIS doors READ the layers - QGIS's and Pro's own readers, in one
coordinate system - and hand over plain coordinates: the points' x and
y, and each area's rings. The geometry is done HERE, once, so QGIS, Pro
and Python give the same answer and one test can hold all three to it
(tests/test_zones.py checks it against shapely).

An area is any number of rings: its outer boundary, its holes, its
islands. A point is INSIDE when it crosses those rings an odd number of
times (the even-odd rule, which handles holes and islands without
telling them apart), and ON THE BORDER when it lies within `tol` of a
ring. `tol` is a micrometre per kilometre of coordinate
size - about 7 mm at Swedish grid coordinates - so "on the border"
means what a person means by it.

Coordinates in DEGREES are allowed: they are placed on a local flat
grid in metres (an equirectangular projection about the data's mean
latitude) before anything is measured, so a snapping distance and the
nearest area are in metres. Over a country that is accurate to well
under a percent, which decides nothing here but ties and snap limits.
"""
from __future__ import annotations

import math

import numpy as np

#: points x segments per block, so memory stays small on big layers
_BLOCK = 2_000_000


def _segments(rings):
    """(k, 4) array x1 y1 x2 y2 of every edge of every ring."""
    segs = []
    for r in rings:
        r = np.asarray(r, float).reshape(-1, 2)
        if len(r) < 3:
            continue
        if not np.array_equal(r[0], r[-1]):
            r = np.vstack([r, r[:1]])
        segs.append(np.hstack([r[:-1], r[1:]]))
    return np.vstack(segs) if segs else np.zeros((0, 4))


def _dist_to_segments(px, py, s):
    """Each point's distance to the nearest of the segments s."""
    out = np.full(len(px), np.inf)
    if len(s) == 0 or len(px) == 0:
        return out
    step = max(1, _BLOCK // max(len(s), 1))
    x1, y1, x2, y2 = s.T
    dx, dy = x2 - x1, y2 - y1
    ll = dx * dx + dy * dy
    ll = np.where(ll > 0, ll, 1.0)
    for a in range(0, len(px), step):
        X = px[a:a + step, None]
        Y = py[a:a + step, None]
        t = np.clip(((X - x1) * dx + (Y - y1) * dy) / ll, 0.0, 1.0)
        d = np.hypot(X - (x1 + t * dx), Y - (y1 + t * dy))
        out[a:a + step] = d.min(axis=1)
    return out


def _odd_crossings(px, py, s):
    """True where a point crosses the segments an odd number of times."""
    out = np.zeros(len(px), bool)
    if len(s) == 0 or len(px) == 0:
        return out
    step = max(1, _BLOCK // max(len(s), 1))
    x1, y1, x2, y2 = s.T
    for a in range(0, len(px), step):
        X = px[a:a + step, None]
        Y = py[a:a + step, None]
        straddle = (y1 > Y) != (y2 > Y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xc = x1 + (Y - y1) * (x2 - x1) / (y2 - y1)
        out[a:a + step] = (straddle & (X < xc)).sum(axis=1) % 2 == 1
    return out


class Areas:
    """A layer of areas, ready to be asked where points are.

    rings : one list per area of its rings, each an (n, 2) sequence of
            x, y - outer boundaries, holes and islands alike.
    geographic : the coordinates are degrees (longitude, latitude).
    """

    def __init__(self, rings, geographic: bool = False):
        self.geographic = bool(geographic)
        raw = [[np.asarray(r, float).reshape(-1, 2) for r in area]
               for area in rings]
        allxy = [r for area in raw for r in area if len(r)]
        if self.geographic and allxy:
            lat0 = float(np.mean(np.vstack(allxy)[:, 1]))
            self._kx = 111_320.0 * math.cos(math.radians(lat0))
            self._ky = 110_574.0
        else:
            self._kx = self._ky = 1.0
        self.segs = [_segments([self._flat(r) for r in area])
                     for area in raw]
        box = np.full((len(raw), 4), np.nan)
        for j, s in enumerate(self.segs):
            if len(s):
                box[j] = (min(s[:, 0].min(), s[:, 2].min()),
                          min(s[:, 1].min(), s[:, 3].min()),
                          max(s[:, 0].max(), s[:, 2].max()),
                          max(s[:, 1].max(), s[:, 3].max()))
        self.box = box
        size = np.nanmax(np.abs(box)) if np.isfinite(box).any() else 1.0
        self.tol = 1e-9 * max(1.0, float(size))
        self.empty = [j for j, s in enumerate(self.segs) if len(s) == 0]

    def __len__(self):
        return len(self.segs)

    def _flat(self, xy):
        xy = np.asarray(xy, float).reshape(-1, 2)
        return np.column_stack([xy[:, 0] * self._kx, xy[:, 1] * self._ky])

    def flat_points(self, x, y):
        return (np.asarray(x, float) * self._kx,
                np.asarray(y, float) * self._ky)

    def locate(self, x, y):
        """Every (point, area) where the point is inside the area or on
        its border: three arrays - point index, area index, and True
        for inside, False for on the border."""
        px, py = self.flat_points(x, y)
        pi, aj, inside = [], [], []
        t = self.tol
        # the points sorted by x once, so each area looks only at the
        # points in its own x-range: 6,000 DeSO areas over a million
        # points is then a matter of seconds, not of scanning every
        # point 6,000 times (NaN sorts last and is never in range)
        order = np.argsort(px, kind="stable")
        sx = px[order]
        for j, s in enumerate(self.segs):
            if not len(s):
                continue
            x0, y0, x1, y1 = self.box[j]
            c = order[np.searchsorted(sx, x0 - t, "left"):
                      np.searchsorted(sx, x1 + t, "right")]
            cand = np.sort(c[(py[c] >= y0 - t) & (py[c] <= y1 + t)])
            if not len(cand):
                continue
            d = _dist_to_segments(px[cand], py[cand], s)
            on = d <= t
            odd = _odd_crossings(px[cand], py[cand], s)
            hit = on | odd
            pi.append(cand[hit])
            aj.append(np.full(int(hit.sum()), j))
            inside.append(~on[hit])
        if not pi:
            z = np.zeros(0, int)
            return z, z, np.zeros(0, bool)
        return (np.concatenate(pi), np.concatenate(aj),
                np.concatenate(inside))

    def nearest(self, x, y, among=None):
        """For each point: the nearest area's index (of `among`, or of
        all), its distance in metres (to the area's edge), and how many
        areas lie at that same distance - a tie goes to the first
        (R-61). Index -1 where there is no area to be near."""
        px, py = self.flat_points(x, y)
        cand = np.asarray(among if among is not None
                          else np.arange(len(self)), int)
        cand = np.array([j for j in cand if len(self.segs[j])], int)
        n = len(px)
        best = np.full(n, -1)
        dist = np.full(n, np.inf)
        ties = np.zeros(n, int)
        if not len(cand) or not n:
            return best, dist, ties
        b = self.box[cand]
        t = self.tol
        for i in range(n):
            # the distance to each box is a floor under the distance to
            # its area: look at areas in that order, stop when the next
            # floor is beyond the best found
            gx = np.maximum(np.maximum(b[:, 0] - px[i], 0.0),
                            px[i] - b[:, 2])
            gy = np.maximum(np.maximum(b[:, 1] - py[i], 0.0),
                            py[i] - b[:, 3])
            floor = np.hypot(gx, gy)
            order = np.lexsort((cand, floor))
            for o in order:
                if floor[o] > dist[i] + t:
                    break
                j = int(cand[o])
                d = float(_dist_to_segments(px[i:i + 1], py[i:i + 1],
                                            self.segs[j])[0])
                if d < dist[i] - t:
                    best[i], dist[i], ties[i] = j, d, 1
                elif abs(d - dist[i]) <= t:
                    ties[i] += 1
                    if j < best[i]:
                        best[i] = j
        return best, dist, ties

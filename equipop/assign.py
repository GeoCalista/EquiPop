"""
assign.py - machine 7, step 1: who goes where when destinations fill up.

Capacity-constrained accessibility assignment over bespoke
neighbourhoods (PROPOSALS.md section 3, "AGREED 22-23 NOVEMBER 2026";
BACKLOG 515; ruling R-56). Not called an agent-based model in print, and
every number it writes that comes from a draw is labelled as simulated.

People live at ORIGINS (points with a number of people). They go to
DESTINATIONS (points with a capacity, or none). Four methods:

  "nearest"   Groups of m people from every origin join ONE queue in a
              random order. Each group takes the nearest destination
              that still has room; if that one has less room than the
              group has people, it fills it and the rest go on to the
              next nearest. A full destination is full for everyone
              after it. (Random serial dictatorship, or random
              priority, in matching theory - a name from memory, to be
              checked before print.)
  "decay"     The same queue, but a group DRAWS its destination among
              those with room, each weighted by 2^(-metres/half-life)
              (a Huff model with exponential decay).
  "closest"   No queue and no draw: the closest person-destination pairs
              are matched first, then the next closest, until all are
              placed or nothing within reach has room. With people and
              destinations both ranking by distance this is the stable
              matching. For places where the nearest have priority
              (preschools, schools).
  "flows"     No capacity and no draw: each origin's people are spread
              over its destinations by the decay weights, as fractions.
              Each destination's load is then the PRESSURE on it.

With unlimited capacity the queue cannot matter: "nearest" gives every
origin its nearest destination, whatever the seed.

Distances are straight lines in metres; minutes are metres at one speed.
Friction, slope and modes come in step 3. Groups of equal size (10 by
default) keep a big origin from taking all its luck at once; a group of
1 is one person. Every source of randomness has its own seed stream: the
queue's order is drawn from (seed, run, 0), the choices from (seed, run,
1), so a run can be repeated exactly and two runs differ only where they
should.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

METHODS = ("nearest", "decay", "closest", "flows")

#: below this, an amount of people or room counts as none
EPS = 1e-9

# the columns written, named once (shapefiles keep 10 characters)
ORIGIN_COLS = ("People", "Sim_Placed", "Sim_Unmet", "Sim_Metres",
               "Sim_Mins", "Sim_Spread")
DEST_COLS = ("Capacity", "Sim_Load", "Sim_LoadSd", "Sim_Ratio",
             "Sim_Full", "Sim_Metres")
TRIP_COLS = ("Origin", "Dest", "People", "Metres", "Minutes")


@dataclass
class Assignment:
    """What assign() returns. Rows of `origins` and `destinations` are
    in the order given; `trips` names them by position (0, 1, ...)."""
    origins: pd.DataFrame
    destinations: pd.DataFrame
    trips: pd.DataFrame
    runs: int
    method: str


def assign(origins: pd.DataFrame, destinations: pd.DataFrame, *,
           method: str = "nearest", people: str | None = None,
           capacity: str | None = None, half_life: float | None = None,
           farthest: float | None = None, group_size: float = 10.0,
           runs: int = 20, seed: int = 1, speed_kmh: float = 5.0,
           candidates: int = 100, x: str = "x", y: str = "y",
           trips_min: float = 1.0) -> Assignment:
    """Send each origin's people to destinations; see the module text.

    `people` names a column of origins (empty = one person per row);
    `capacity` a column of destinations (empty = no limit). `farthest`
    in metres is the furthest anyone goes: beyond it a person is unmet.
    `candidates` is how many nearest destinations each origin looks at
    first. It changes the speed, not the answer: when all of them are
    full the rest are searched too, and with a decay it is widened
    until everything left out weighs under a millionth of what is
    looked at. `trips_min` drops flows of fewer people from the trips
    table (flows only; the loads keep them).
    """
    if method not in METHODS:
        raise ValueError(f"method is one of {', '.join(METHODS)}")
    ox = origins[x].to_numpy(float)
    oy = origins[y].to_numpy(float)
    dx = destinations[x].to_numpy(float)
    dy = destinations[y].to_numpy(float)
    pop = (np.ones(len(origins)) if not people
           else origins[people].to_numpy(float))
    cap = (np.full(len(destinations), np.inf) if not capacity
           else destinations[capacity].to_numpy(float))
    _check(pop, "people", "an origin")
    _check(cap, "capacity", "a destination", allow_inf=True)
    if not (np.isfinite(ox).all() and np.isfinite(oy).all()
            and np.isfinite(dx).all() and np.isfinite(dy).all()):
        raise ValueError("every origin and destination needs x and y")
    if len(destinations) == 0:
        raise ValueError("there are no destinations")
    if method in ("decay", "flows"):
        if half_life is None or not (half_life > 0):
            raise ValueError(f'"{method}" needs a half-life in metres, '
                             "above 0")
    if farthest is not None and not (farthest > 0):
        raise ValueError("the farthest distance is in metres, above 0")
    if not (group_size > 0):
        raise ValueError("a group is above 0 people")
    if not (speed_kmh > 0):
        raise ValueError("the speed is in km/h, above 0")
    runs = int(runs)
    if runs < 1:
        raise ValueError("at least one run")
    if method in ("closest", "flows"):
        runs = 1                                  # nothing is drawn
    s = _Space(ox, oy, dx, dy, farthest, half_life, candidates)

    n_o, n_d = len(ox), len(dx)
    placed = np.zeros((runs, n_o))
    o_metres = np.full((runs, n_o), np.nan)
    load = np.zeros((runs, n_d))
    d_metres = np.full((runs, n_d), np.nan)
    full = np.zeros((runs, n_d), bool)
    trips = None
    for r in range(runs):
        if method == "flows":
            pairs = s.flows(pop)
            left = cap.copy()
        elif method == "closest":
            pairs, left = s.closest(pop, cap)
        else:
            pairs, left = s.queue(pop, cap, group_size, method,
                                  np.random.default_rng([seed, r, 0]),
                                  np.random.default_rng([seed, r, 1]))
        i, j, n, d = pairs
        np.add.at(placed[r], i, n)
        np.add.at(load[r], j, n)
        om, dm = np.zeros(n_o), np.zeros(n_d)
        np.add.at(om, i, n * d)
        np.add.at(dm, j, n * d)
        with np.errstate(invalid="ignore", divide="ignore"):
            o_metres[r] = np.where(placed[r] > EPS, om / placed[r], np.nan)
            d_metres[r] = np.where(load[r] > EPS, dm / load[r], np.nan)
        full[r] = np.isfinite(cap) & (left <= EPS)
        if r == 0:
            trips = _trips(pairs, speed_kmh,
                           trips_min if method == "flows" else 0.0)

    o = pd.DataFrame(index=origins.index)
    o["People"] = pop
    o["Sim_Placed"] = placed.mean(axis=0)
    o["Sim_Unmet"] = np.maximum(pop - o["Sim_Placed"].to_numpy(), 0.0)
    o["Sim_Metres"] = _nanmean(o_metres)
    o["Sim_Mins"] = o["Sim_Metres"] / (speed_kmh * 1000.0 / 60.0)
    o["Sim_Spread"] = _nanspread(o_metres)
    de = pd.DataFrame(index=destinations.index)
    de["Capacity"] = np.where(np.isfinite(cap), cap, np.nan)
    de["Sim_Load"] = load.mean(axis=0)
    de["Sim_LoadSd"] = load.std(axis=0, ddof=1) if runs > 1 else 0.0
    with np.errstate(invalid="ignore", divide="ignore"):
        de["Sim_Ratio"] = np.where(np.isfinite(cap) & (cap > 0),
                                   de["Sim_Load"] / cap, np.nan)
    de["Sim_Full"] = full.mean(axis=0)
    de["Sim_Metres"] = _nanmean(d_metres)
    return Assignment(o, de, trips, runs, method)


def _check(v, what, row, allow_inf=False):
    bad = ~np.isfinite(v) if not allow_inf else np.isnan(v)
    if bad.any() or (v < 0).any():
        raise ValueError(f"{what}: every {row} needs a number of 0 or "
                         "more")


def _nanmean(a):
    with np.errstate(invalid="ignore"):
        ok = np.isfinite(a)
        n = ok.sum(axis=0)
        s = np.where(ok, a, 0.0).sum(axis=0)
        return np.where(n > 0, s / np.maximum(n, 1), np.nan)


def _nanspread(a):
    """The spread over runs of a mean distance: 0 with one run."""
    if a.shape[0] < 2:
        return np.where(np.isfinite(a[0]), 0.0, np.nan)
    ok = np.isfinite(a)
    n = ok.sum(axis=0)
    m = _nanmean(a)
    dev = np.where(ok, (a - m) ** 2, 0.0).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 1, np.sqrt(dev / np.maximum(n - 1, 1)),
                        np.where(n == 1, 0.0, np.nan))


def _trips(pairs, speed_kmh, least):
    i, j, n, d = pairs
    t = pd.DataFrame({"Origin": i, "Dest": j, "People": n, "Metres": d})
    t = (t.groupby(["Origin", "Dest"], sort=True)
          .agg(People=("People", "sum"), Metres=("Metres", "first"))
          .reset_index())
    t = t[t.People >= least].reset_index(drop=True)
    t["Minutes"] = t.Metres / (speed_kmh * 1000.0 / 60.0)
    return t[list(TRIP_COLS)]


class _Space:
    """Where the destinations lie seen from each origin: the nearest
    `candidates` first, all of them when those are full."""

    def __init__(self, ox, oy, dx, dy, farthest, half_life, candidates):
        from scipy.spatial import cKDTree
        self.ox, self.oy, self.dx, self.dy = ox, oy, dx, dy
        self.n_d = len(dx)
        self.far = np.inf if farthest is None else float(farthest)
        self.a = (math.log(2.0) / half_life) if half_life else None
        self.C = max(1, min(int(candidates), self.n_d))
        self.tree = cKDTree(np.c_[dx, dy])
        self._lists = {}
        self._near(self.C)
        if self.a is not None:
            # with a decay, look wide enough that every destination left
            # out weighs, together, under a millionth of those looked
            # at - so `candidates` changes the speed, not the shares
            while self.C < self.n_d:
                w = np.where(self.cd <= self.far, self.weights(self.cd),
                             0.0)
                rest = (self.n_d - self.C) * w[:, -1]
                if (rest <= 1e-6 * w.sum(axis=1)).all():
                    break
                self._near(min(self.n_d, self.C * 4))

    def _near(self, C):
        """Every origin's C nearest destinations, sorted by distance and
        then by position, so ties are always broken the same way."""
        self.C = C
        d, j = self.tree.query(np.c_[self.ox, self.oy], k=C)
        d = np.asarray(d, float).reshape(len(self.ox), C)
        j = np.asarray(j, np.int64).reshape(len(self.ox), C)
        order = np.lexsort((j, d), axis=-1)
        self.cd = np.take_along_axis(d, order, axis=1)
        self.cj = np.take_along_axis(j, order, axis=1)
        self._lists = {}

    def options(self, i, everything=False):
        """(metres, destinations) for origin i within the farthest
        distance: the nearest C, or with `everything` all of them."""
        if not everything or self.C >= self.n_d:
            d, j = self.cd[i], self.cj[i]
        else:
            if i not in self._lists:
                d = np.hypot(self.dx - self.ox[i], self.dy - self.oy[i])
                j = np.lexsort((np.arange(self.n_d), d))
                self._lists[i] = (d[j], j)
            d, j = self._lists[i]
        keep = d <= self.far
        return d[keep], j[keep]

    def weights(self, d):
        """Decay weights, RELATIVE to the nearest distance in each row.

        Every use divides by the row's total (flows), draws by the
        cumulative sum (the decay queue) or compares one weight with
        the row's sum (the widening), so subtracting the row's smallest
        distance before exponentiating changes no share - and keeps
        the numbers out of the floor: 1.67.0 computed exp(-ln 2 x
        20000 / 10) for a destination 20 km away with a 10 m half-life,
        which is 0.0 in floating point, and 90 people went unmet
        between two destinations 10 m apart (BACKLOG 524).
        """
        d = np.asarray(d, float)
        if d.ndim == 0 or d.size == 0:
            return np.exp(-self.a * d)
        base = np.nanmin(np.where(np.isfinite(d), d, np.nan),
                         axis=-1, keepdims=True)
        base = np.where(np.isfinite(base), base, 0.0)
        return np.exp(-self.a * (d - base))

    # -- the queue: "nearest" and "decay" ------------------------------
    def queue(self, pop, cap, m, method, rng_order, rng_choice):
        left = cap.astype(float).copy()
        sizes, owner = [], []
        for i, p in enumerate(pop):
            whole = int(p // m)
            rest = p - whole * m
            sizes.extend([m] * whole)
            owner.extend([i] * whole)
            if rest > EPS:
                sizes.append(rest)
                owner.append(i)
        sizes = np.asarray(sizes, float)
        owner = np.asarray(owner, np.int64)
        out_i, out_j, out_n, out_d = [], [], [], []
        for g in rng_order.permutation(len(sizes)):
            i, need = owner[g], sizes[g]
            everything = False
            d, j = self.options(i)
            w = self.weights(d) if method == "decay" else None
            while need > EPS:
                room = left[j] > EPS
                if not room.any():
                    if everything or self.C >= self.n_d:
                        break                      # unmet
                    everything = True
                    d, j = self.options(i, everything=True)
                    w = self.weights(d) if method == "decay" else None
                    continue
                if method == "nearest":
                    k = int(np.argmax(room))
                else:
                    ww = np.where(room, w, 0.0)
                    if not ww.sum() > 0:           # all too far to weigh
                        k = int(np.argmax(room))
                    else:
                        c = np.cumsum(ww)
                        k = int(np.searchsorted(c, rng_choice.random()
                                                * c[-1], side="right"))
                        k = min(k, len(c) - 1)
                        if not room[k]:            # rounding at an edge
                            k = int(np.argmax(room))
                take = min(need, left[j[k]])
                left[j[k]] -= take
                need -= take
                out_i.append(i)
                out_j.append(j[k])
                out_n.append(take)
                out_d.append(d[k])
        return (np.asarray(out_i, np.int64), np.asarray(out_j, np.int64),
                np.asarray(out_n, float), np.asarray(out_d, float)), left

    # -- "closest": the closest pairs first ----------------------------
    def closest(self, pop, cap):
        """The closest person-destination pairs first, exactly.

        Each origin's `candidates` nearest destinations are looked at
        first. That is exact unless an origin is still waiting when
        the list is done AND either some destination has room (it may
        find it farther out) or a pair was matched at a distance
        beyond that origin's horizon - the farthest destination it
        looked at - because an unseen pair of its could have come
        before that match. 1.67.0 stopped as soon as nothing was left:
        with 101 destinations and 100 looked at, the last place went
        to a person 7 m away while one 2 m away, whose 100 nearest were
        all full, went unmet (BACKLOG 524). Now the waiting origins'
        full lists are added and the matching is done again from the
        start, until no such origin remains.
        """
        n_o = len(pop)
        ii = np.repeat(np.arange(n_o), self.C)
        jj = self.cj.ravel()
        dd = self.cd.ravel()
        keep = dd <= self.far
        ii, jj, dd = ii[keep], jj[keep], dd[keep]
        horizon = self.cd[:, -1].copy()
        # origins whose every destination is already in the list
        whole = np.full(n_o, self.C >= self.n_d)
        while True:
            need = pop.astype(float).copy()
            left = cap.astype(float).copy()
            order = np.lexsort((jj, ii, dd))
            out = ([], [], [], [])
            for p in order:
                i, j = ii[p], jj[p]
                if need[i] <= EPS or left[j] <= EPS:
                    continue
                take = min(need[i], left[j])
                need[i] -= take
                left[j] -= take
                for lst, v in zip(out, (i, j, take, dd[p])):
                    lst.append(v)
            waiting = (need > EPS) & ~whole & (horizon <= self.far)
            if waiting.any():
                farthest_match = max(out[3]) if out[3] else -np.inf
                if (left > EPS).any() or \
                        farthest_match > horizon[waiting].min():
                    add_i, add_j, add_d = [], [], []
                    for i in np.nonzero(waiting)[0]:
                        d, j = self.options(i, everything=True)
                        new = ~np.isin(j, self.cj[i])
                        add_i.append(np.full(int(new.sum()), i))
                        add_j.append(j[new])
                        add_d.append(d[new])
                        whole[i] = True
                    ii = np.concatenate([ii] + add_i)
                    jj = np.concatenate([jj] + add_j)
                    dd = np.concatenate([dd] + add_d)
                    continue
            return (np.asarray(out[0], np.int64),
                    np.asarray(out[1], np.int64),
                    np.asarray(out[2], float),
                    np.asarray(out[3], float)), left

    # -- "flows": fractions by decay, no capacity ----------------------
    def flows(self, pop):
        d, j = self.cd, self.cj
        w = np.where(d <= self.far, self.weights(d), 0.0)
        tot = w.sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            share = np.where(tot[:, None] > 0, w / tot[:, None], 0.0)
        n = pop[:, None] * share
        keep = n > 0
        ii = np.repeat(np.arange(len(pop)), self.C).reshape(n.shape)
        return (ii[keep], j[keep], n[keep], d[keep])

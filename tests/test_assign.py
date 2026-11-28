"""Machine 7, step 1: who goes where when destinations fill up
(equipop/assign.py; BACKLOG 515; ruling R-56; PROPOSALS.md section 3).

The checks agreed on 22-23 November 2026 (PROPOSALS 3, point 10):
everyone who leaves arrives or is unmet; no destination goes over its
capacity; the same seed gives the same numbers; unlimited capacity gives
the plain nearest assignment in any order; "closest" is the stable
matching; a decay draw approaches its weights; flows share exactly.
"""
import math

import numpy as np
import pandas as pd
import pytest
from scipy.spatial import cKDTree

from equipop.assign import METHODS, assign


def _town(seed=4, n_o=400, n_d=40, span=8000.0, cap=(5, 60)):
    rng = np.random.default_rng(seed)
    o = pd.DataFrame({"x": rng.uniform(0, span, n_o),
                      "y": rng.uniform(0, span, n_o),
                      "n": rng.integers(0, 30, n_o).astype(float)})
    d = pd.DataFrame({"x": rng.uniform(0, span, n_d),
                      "y": rng.uniform(0, span, n_d),
                      "c": rng.integers(*cap, n_d).astype(float)})
    return o, d


@pytest.mark.parametrize("method", METHODS)
def test_everyone_arrives_or_is_unmet_and_no_destination_overflows(method):
    """Conservation and capacity, in every method. BROKEN WITH: a group
    larger than a destination's room placed whole."""
    o, d = _town()
    a = assign(o, d, method=method, people="n", capacity="c",
               half_life=1500.0, runs=3)
    got = a.origins
    np.testing.assert_allclose(got.Sim_Placed + got.Sim_Unmet, o.n)
    assert (got.Sim_Unmet >= -1e-9).all()
    if method != "flows":                       # flows ignore capacity
        assert (a.destinations.Sim_Load <= d.c + 1e-9).all()
        # demand exceeds capacity here, so every place fills
        assert a.destinations.Sim_Load.sum() == pytest.approx(
            min(o.n.sum(), d.c.sum()))
    if a.runs == 1 and method != "flows":   # the trips are that run
        t = a.trips.groupby("Origin").People.sum()
        np.testing.assert_allclose(
            t.reindex(range(len(o)), fill_value=0).to_numpy(),
            got.Sim_Placed.to_numpy())


def test_unlimited_capacity_gives_everyone_their_nearest_whatever_the_seed():
    """No capacity, no farthest: the queue cannot matter, so every
    origin's people all go to its nearest destination (cKDTree). BROKEN
    WITH: the first candidate taken before the list is sorted."""
    o, d = _town(seed=9)
    near_d, near_j = cKDTree(d[["x", "y"]].to_numpy()).query(
        o[["x", "y"]].to_numpy())
    for seed in (1, 2, 77):
        a = assign(o, d, people="n", runs=2, seed=seed, group_size=3)
        has = o.n > 0
        np.testing.assert_allclose(a.origins.Sim_Metres[has],
                                   near_d[has.to_numpy()])
        assert (a.origins.Sim_Spread[has] < 1e-9).all()
        assert (a.trips.Dest.to_numpy()
                == near_j[a.trips.Origin.to_numpy()]).all()


def test_the_same_seed_gives_the_same_numbers_and_another_seed_differs():
    o, d = _town()
    kw = dict(people="n", capacity="c", runs=4)
    one, two = assign(o, d, seed=5, **kw), assign(o, d, seed=5, **kw)
    pd.testing.assert_frame_equal(one.origins, two.origins)
    pd.testing.assert_frame_equal(one.trips, two.trips)
    other = assign(o, d, seed=6, **kw)
    assert not np.allclose(other.origins.Sim_Metres.fillna(0),
                           one.origins.Sim_Metres.fillna(0))


def test_closest_first_is_the_stable_matching():
    """No person and destination would both rather be matched to each
    other: a destination nearer to someone than their own is full, and
    everyone in it lives at least as near. BROKEN WITH: the pairs taken
    in the origins' order rather than by distance."""
    o, d = _town(seed=2, n_o=150, n_d=25, cap=(3, 25))
    a = assign(o, d, method="closest", people="n", capacity="c")
    t = a.trips
    D = np.hypot(o.x.to_numpy()[:, None] - d.x.to_numpy()[None, :],
                 o.y.to_numpy()[:, None] - d.y.to_numpy()[None, :])
    full = a.destinations.Sim_Full.to_numpy() == 1
    worst_in = t.groupby("Dest").Metres.max().reindex(range(len(d)))
    for i in range(len(o)):
        if o.n[i] == 0:
            continue
        mine = t[t.Origin == i].Metres
        own = mine.max() if len(mine) and a.origins.Sim_Unmet[i] < 1e-9 \
            else np.inf
        for j in np.flatnonzero(D[i] < own - 1e-9):
            assert full[j], (i, j)
            assert worst_in[j] <= D[i, j] + 1e-9, (i, j)


def test_closest_first_hand_case():
    """A at 0 and B at 10 m, one person each; X at 5 m holds one, Y at
    100 m holds one. A and B are equally near X: the tie goes to the
    first row, so A gets X and B walks 90 m to Y."""
    o = pd.DataFrame({"x": [0.0, 10.0], "y": [0.0, 0.0], "n": [1.0, 1.0]})
    d = pd.DataFrame({"x": [5.0, 100.0], "y": [0.0, 0.0], "c": [1.0, 1.0]})
    a = assign(o, d, method="closest", people="n", capacity="c")
    assert a.origins.Sim_Metres.tolist() == [5.0, 90.0]
    assert a.destinations.Sim_Full.tolist() == [1.0, 1.0]


def test_a_decay_draw_approaches_its_weights():
    """One origin, 3,000 people one by one, three destinations at 0, 1
    and 2 half-lives with no capacity: shares 4:2:1 of 7."""
    o = pd.DataFrame({"x": [0.0], "y": [0.0], "n": [3000.0]})
    d = pd.DataFrame({"x": [0.0, 1000.0, 2000.0], "y": [0.0] * 3})
    a = assign(o, d, method="decay", people="n", half_life=1000.0,
               group_size=1, runs=4)
    share = a.destinations.Sim_Load.to_numpy() / 3000.0
    np.testing.assert_allclose(share, [4 / 7, 2 / 7, 1 / 7], atol=0.02)


def test_flows_share_exactly_by_the_decay_weights():
    o = pd.DataFrame({"x": [0.0, 0.0], "y": [0.0, 0.0], "n": [70.0, 7.0]})
    d = pd.DataFrame({"x": [0.0, 1000.0, 2000.0], "y": [0.0] * 3,
                      "c": [1.0, 1.0, 1.0]})
    a = assign(o, d, method="flows", people="n", capacity="c",
               half_life=1000.0)
    np.testing.assert_allclose(a.destinations.Sim_Load, [44, 22, 11])
    np.testing.assert_allclose(a.destinations.Sim_Ratio, [44, 22, 11])
    assert a.origins.Sim_Metres[0] == pytest.approx(
        (2 / 7) * 1000 + (1 / 7) * 2000)


def test_beyond_the_farthest_distance_people_are_unmet():
    o = pd.DataFrame({"x": [0.0, 5000.0], "y": [0.0, 0.0], "n": [4.0, 6.0]})
    d = pd.DataFrame({"x": [100.0], "y": [0.0]})
    for method in METHODS:
        a = assign(o, d, method=method, people="n", farthest=1000.0,
                   half_life=500.0)
        assert a.origins.Sim_Unmet.tolist() == [0.0, 6.0], method
        assert math.isnan(a.origins.Sim_Metres[1])


def test_the_number_of_candidates_changes_the_speed_not_the_answer():
    o, d = _town(seed=12, n_d=120)
    for method in METHODS:
        a = assign(o, d, method=method, people="n", capacity="c",
                   half_life=2500.0, runs=2, candidates=3)
        b = assign(o, d, method=method, people="n", capacity="c",
                   half_life=2500.0, runs=2, candidates=500)
        pd.testing.assert_frame_equal(a.origins, b.origins, atol=1e-9)
        pd.testing.assert_frame_equal(a.destinations, b.destinations,
                                      atol=1e-9)


def test_groups_and_minutes():
    """25 people in groups of 10 are 10 + 10 + 5; minutes are metres at
    the speed (5 km/h: 1,000 m is 12 minutes)."""
    o = pd.DataFrame({"x": [0.0], "y": [0.0], "n": [25.0]})
    d = pd.DataFrame({"x": [1000.0], "y": [0.0], "c": [100.0]})
    a = assign(o, d, people="n", capacity="c", runs=1)
    assert a.origins.Sim_Mins[0] == pytest.approx(12.0)
    assert a.trips.People.tolist() == [25.0]


@pytest.mark.parametrize("kw, says", [
    (dict(method="walk"), "method is one of"),
    (dict(method="decay"), "half-life"),
    (dict(farthest=0), "farthest"),
    (dict(group_size=0), "group"),
    (dict(speed_kmh=0), "speed"),
    (dict(runs=0), "at least one run"),
])
def test_what_is_refused(kw, says):
    o, d = _town(n_o=5, n_d=3)
    with pytest.raises(ValueError, match=says):
        assign(o, d, people="n", **kw)
    with pytest.raises(ValueError, match="0 or more"):
        assign(o.assign(n=-1.0), d, people="n")


# ------------------------------------- the 1.67.0 review, 28 November
def _ring_case():
    """The review's case, built: 100 destinations on a 1 m ring round
    A, each already taken by a person standing on it; D at 2 m from A;
    B at 7 m from D. A's 100 nearest are the full ring, so with 100
    candidates A never saw D."""
    ang = np.linspace(0, 2 * np.pi, 100, endpoint=False)
    dx, dy = list(np.cos(ang)), list(np.sin(ang))
    dx.append(2.0)
    dy.append(0.0)
    d = pd.DataFrame({"x": dx, "y": dy, "c": 1.0})
    o = pd.DataFrame({"x": list(np.cos(ang)) + [0.0, 9.0],
                      "y": list(np.sin(ang)) + [0.0, 0.0]})
    return o, d


def test_closest_first_serves_the_2_m_person_not_the_7_m_one():
    """BACKLOG 524. BROKEN WITH 1.67.0's stopping rule: with 100
    candidates A (2 m from D) was unmet and B (7 m) got D's last place;
    with 101 the reverse. The answer must not depend on `candidates`."""
    o, d = _ring_case()
    for C in (100, 101, 3):
        a = assign(o, d, method="closest", capacity="c", candidates=C)
        assert a.origins.Sim_Placed.tolist()[100:] == [1.0, 0.0], C
        assert a.origins.Sim_Metres.tolist()[100] == pytest.approx(2.0)


def _closest_by_hand(o, d, pop, cap, far=np.inf):
    """Every pair, by distance then origin then destination, greedily:
    the definition, with no candidate list at all."""
    D = np.hypot(o.x.to_numpy()[:, None] - d.x.to_numpy()[None, :],
                 o.y.to_numpy()[:, None] - d.y.to_numpy()[None, :])
    need, left = pop.astype(float).copy(), cap.astype(float).copy()
    placed = np.zeros(len(o))
    metres = np.zeros(len(o))
    for i, j in sorted(((i, j) for i in range(len(o))
                        for j in range(len(d)) if D[i, j] <= far),
                       key=lambda ij: (D[ij], ij[0], ij[1])):
        if need[i] <= 1e-9 or left[j] <= 1e-9:
            continue
        take = min(need[i], left[j])
        need[i] -= take
        left[j] -= take
        placed[i] += take
        metres[i] += take * D[i, j]
    return placed, np.where(placed > 0, metres / np.where(placed > 0,
                                                          placed, 1), np.nan)


@pytest.mark.parametrize("seed", range(12))
def test_closest_first_equals_the_exhaustive_matching(seed):
    """Small towns, every candidate count from 1 up, against the
    definition computed over all pairs: the same people placed, the
    same distances. BROKEN WITH: the stopping rule of 1.67.0 (seeds
    where capacity binds and a far match precedes a waiting origin's
    unseen pairs)."""
    rng = np.random.default_rng(seed)
    n_o, n_d = int(rng.integers(5, 30)), int(rng.integers(2, 12))
    o = pd.DataFrame({"x": rng.uniform(0, 1000, n_o),
                      "y": rng.uniform(0, 1000, n_o),
                      "n": rng.integers(1, 6, n_o).astype(float)})
    d = pd.DataFrame({"x": rng.uniform(0, 1000, n_d),
                      "y": rng.uniform(0, 1000, n_d),
                      "c": rng.integers(1, 9, n_d).astype(float)})
    far = 700.0 if seed % 3 == 0 else None
    want_p, want_m = _closest_by_hand(o, d, o.n.to_numpy(), d.c.to_numpy(),
                                      np.inf if far is None else far)
    for C in (1, 2, 3, n_d):
        a = assign(o, d, method="closest", people="n", capacity="c",
                   candidates=C, farthest=far)
        np.testing.assert_allclose(a.origins.Sim_Placed, want_p,
                                   err_msg=f"seed {seed}, candidates {C}")
        np.testing.assert_allclose(a.origins.Sim_Metres, want_m,
                                   equal_nan=True,
                                   err_msg=f"seed {seed}, candidates {C}")


def test_flows_20_km_away_with_a_10_m_half_life_still_share_2_to_1():
    """BACKLOG 524. BROKEN WITH: weights taken from distance 0, which
    underflow to nothing at 20 km, so 1.67.0 reported 100% unmet."""
    o = pd.DataFrame({"x": [0.0], "y": [0.0], "n": [90.0]})
    d = pd.DataFrame({"x": [20000.0, 20010.0], "y": [0.0, 0.0]})
    a = assign(o, d, method="flows", people="n", half_life=10.0)
    got = a.trips.set_index("Dest").People
    assert got[0] == pytest.approx(60.0) and got[1] == pytest.approx(30.0)
    assert a.origins.Sim_Unmet[0] == 0
    # the decay queue draws by the same weights: far away, it still
    # prefers the nearer place 2 to 1, not the first with room
    a = assign(o, d, method="decay", people="n", half_life=10.0,
               group_size=1.0, runs=40, seed=3)
    assert 0.55 < a.destinations.Sim_Load[0] / 90.0 < 0.78

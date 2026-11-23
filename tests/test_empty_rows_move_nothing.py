"""R-54 (BACKLOG 511): a place with nobody in it does not move anyone's
distance.

The external review of 23 November 2026 found it in tool 3b: people
enter the pixel tool's search with no mass, and a second person at 150 m
moved the first person's Dist_1_5 from 158.11 to 176.78 m. Claude then
found it in the main engines: R-11 says a row outside the reference is
"nobody's neighbour", but when k was reached partway through a ring, the
interpolation started from the PREVIOUS NEIGHBOUR, empty or not. R-11's
own tests used radius counts, which never interpolate, so it passed
unseen.

Each test here compares the same places run with and without empty rows,
alone, together, in subsets and in batches - and with k reached partway
through a ring, not only on whole rings or totals.
"""
import io
from contextlib import redirect_stdout

import numpy as np
import pandas as pd
import pytest

from equipop.analysis import run_knn, run_knn_stats
from equipop.cells import CellData
from equipop.datasets import load
from equipop.fastcounts import run_knn_counts
from equipop.friction import run_knn_friction
from equipop.pixels import reach

UNIT = 100.0
#: crossed partway for most places, and one that is never reached
KS = [7, 55, 230, 99999]


def _quiet(fn, *a, **kw):
    with redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def _town(seed=3, n=120, n_empty=70, span=20):
    """Populated cells, and empty cells among them, on a 100 m lattice."""
    rng = np.random.default_rng(seed)
    spots = rng.permutation(span * span)[:n + n_empty]
    E = (spots % span).astype(float) * UNIT
    N = (spots // span).astype(float) * UNIT
    pop = np.r_[rng.integers(1, 40, n).astype(float), np.zeros(n_empty)]
    grp = np.r_[rng.binomial(pop[:n].astype(int), 0.3).astype(float),
                np.zeros(n_empty)]
    return E, N, pop, grp, n


def _fast(E, N, pop, grp):
    cd = CellData(E=E, N=N, n=pop, binary_sums={"g": grp}, unit_size=UNIT)
    r = _quiet(run_knn_counts, cd, KS, report=False)
    return r.assign(Id=np.arange(len(E)))


def _stats(E, N, pop, grp):
    cd = CellData(E=E, N=N, n=pop, binary_sums={"g": grp}, unit_size=UNIT)
    r = _quiet(run_knn_stats, cd, KS, stats={"g": ["ratio"]})
    key = dict(zip(zip(E, N), range(len(E))))
    return r.assign(Id=[key[(e, n)] for e, n in zip(r.EastWest,
                                                    r.NorthSouth)])


def _grid(E, N, pop, grp):
    cells = pd.DataFrame({"E_grid": E, "N_grid": N, "FullPop": pop,
                          "Treatment": grp, "id": np.arange(len(E))})
    return _quiet(run_knn, cells, KS, unit_size=UNIT, max_radius_units=60)


def _grid_seq(E, N, pop, grp):
    cells = pd.DataFrame({"E_grid": E, "N_grid": N, "FullPop": pop,
                          "Treatment": grp, "id": np.arange(len(E))})
    return _quiet(run_knn, cells, KS, unit_size=UNIT, max_radius_units=60,
                  tie_mode="sequential")


def _effort(E, N, pop, grp):
    p = pd.DataFrame({"x": E, "y": N, "count_all": pop,
                      "count_group": grp, "id": np.arange(len(E))})
    return _quiet(run_knn_friction, p, KS, unit_size=UNIT, id_col="id")


@pytest.mark.parametrize("engine", [_fast, _stats, _grid, _grid_seq,
                                    _effort],
                         ids=["fast", "stats", "grid", "grid-sequential",
                              "effort"])
def test_empty_rows_move_no_one_s_distance_in_any_engine(engine):
    """170 places with people, then the same with 70 empty rows among
    them. Every place with people keeps its N_k and Dist_k exactly.
    BROKEN WITH: the crossing ring interpolated from the previous
    neighbour whatever it holds (fastcounts' dd[lo - 1]) - the fast and
    stats engines then move dozens of places by metres."""
    E, N, pop, grp, n = _town()
    alone = engine(E[:n], N[:n], pop[:n], grp[:n]).set_index("Id")
    mixed = engine(E, N, pop, grp).set_index("Id").loc[alone.index]
    for k in KS:
        for col in (f"N_{k}", f"Dist_{k}"):
            np.testing.assert_allclose(mixed[col].to_numpy(float),
                                       alone[col].to_numpy(float),
                                       rtol=0, atol=1e-9, err_msg=col)


def test_the_engines_agree_with_empty_rows_present():
    """The fast engine and the grid engine - which has always skipped an
    empty ring - give the same Dist_k with empty rows in the data."""
    E, N, pop, grp, n = _town(seed=8)
    fast = _fast(E, N, pop, grp).set_index("Id").iloc[:n]
    grid = _grid(E, N, pop, grp).set_index("Id").loc[fast.index]
    for k in KS:
        np.testing.assert_allclose(fast[f"Dist_{k}"], grid[f"Dist_{k}"],
                                   rtol=0, atol=1e-9, err_msg=str(k))


def test_counts_hand_case_an_empty_row_between_two_full_ones():
    """100 people each at 0, 1000 and 2000 m, k = 150. The person at 0
    gathers half of the 1000 m ring: sqrt(56.42^2 / 2 + 1000^2 / 2) =
    708.23 m. An empty row at 500 m made it 790.57 m."""
    for E in ([0.0, 1000.0, 2000.0], [0.0, 1000.0, 2000.0, 500.0]):
        pop = [100.0, 100.0, 100.0, 0.0][:len(E)]
        cd = CellData(E=np.array(E), N=np.zeros(len(E)), n=np.array(pop),
                      unit_size=UNIT)
        r = _quiet(run_knn_counts, cd, [150], report=False)
        own = UNIT / np.sqrt(np.pi)
        assert r.Dist_150[0] == pytest.approx(
            np.sqrt(own ** 2 / 2 + 1000.0 ** 2 / 2))


def test_the_review_s_three_pixels():
    """Three 1 ha pixels at 100, 200 and 300 m, a person at 0, k = 1.5
    ha: 158.11 m, alone or with a second person at 150 m."""
    mass = pd.DataFrame({"x": [100.0, 200.0, 300.0], "y": [0.0] * 3,
                         "ha": [1.0] * 3})
    one = reach(pd.DataFrame({"x": [0.0], "y": [0.0]}), mass, [1.5])
    two = reach(pd.DataFrame({"x": [0.0, 150.0], "y": [0.0, 0.0]}), mass,
                [1.5])
    assert one.Dist_1_5[0] == pytest.approx(np.sqrt(
        (100.0 ** 2 + 200.0 ** 2) / 2))
    assert two.Dist_1_5[0] == one.Dist_1_5[0]


def test_tool_3b_gives_each_person_the_same_answer_alone_together_or_in_batches():
    """Gridby's green and 240 people: run together, in four batches,
    every fourth person, and twelve one at a time. The review found 46
    of 590 Dist_5 values differ between all people and every fourth.
    BROKEN WITH: the interpolation from the previous neighbour - people
    are neighbours with no mass."""
    g = load("gridby")
    people = g["people"].sample(240, random_state=11).reset_index(drop=True)
    ks = [0.3, 1, 5, 20]
    together = _quiet(reach, people, g["green"], ks)
    batches = pd.concat([_quiet(reach, people.iloc[i:i + 60], g["green"],
                                ks) for i in range(0, 240, 60)])
    fourth = _quiet(reach, people.iloc[::4], g["green"], ks)
    for k in ks:
        col = f"Dist_{k}".replace(".", "_")
        want = together[col].to_numpy()
        np.testing.assert_array_equal(batches[col].to_numpy(), want)
        np.testing.assert_array_equal(fourth[col].to_numpy(), want[::4])
        for i in range(0, 240, 20):
            one = _quiet(reach, people.iloc[[i]], g["green"], ks)
            assert one[col].iloc[0] == want[i] or (
                np.isnan(want[i]) and np.isnan(one[col].iloc[0]))

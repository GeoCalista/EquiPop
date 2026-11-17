"""Gridby planted truths must be recoverable, or the city is fired."""
import numpy as np
import pandas as pd

from equipop.datasets import load
from equipop.cells import CellData
from equipop.fastcounts import run_knn_counts
from equipop.friction import run_knn_friction


def test_gridby_planted_truths():
    g = load("gridby")
    p = g["people"]
    # deterministic
    assert load("gridby")["meta"] == g["meta"]

    # 1. the gradient: west-edge context share ~0.1ish, east ~0.6ish
    cd = CellData(E=p.x.to_numpy(), N=p.y.to_numpy(),
                  n=p.count_all.to_numpy(),
                  binary_sums={"g": p.count_group.to_numpy()},
                  value_arrays={}, unit_size=100.0)
    out = run_knn_counts(cd, [400])
    west = out[out.EastWest < 500]["R_g_400"].mean()
    east = out[out.EastWest > 5500]["R_g_400"].mean()
    assert west < 0.18 and east > 0.50 and east - west > 0.3

    # 2. the river: a 3-round isochrone from a river-hugging cell
    # holds far fewer people than from an interior cell (half the
    # disk is behind a friction-6 wall)
    fr = g["friction"]
    res = run_knn_friction(p, [], fr=fr, unit_size=100.0,
                           tau_values=[3])
    res = res.set_index(["EastWest", "NorthSouth"])
    hug = res[res.index.get_level_values(0).isin([2950, 3150])
              ]["N_tau3"].median()
    interior = res[res.index.get_level_values(0).isin([1050, 4950])
                   ]["N_tau3"].median()
    assert hug < 0.72 * interior      # the wall visibly bites

    # 3. the hill: altitude peak where planted
    alt = g["altitude"].reshape(60, 40)
    cx, cy = np.unravel_index(alt.argmax(), alt.shape)
    assert (cx, cy) == (48, 30) and abs(alt.max() - 90) < 1

    # 4. jobs cluster: >60% of jobs west of the river
    j = g["jobs"]
    assert j[j.x < 3000].jobs.sum() / j.jobs.sum() > 0.6


def test_datasets_loader_municipality():
    p, j = load("municipality")
    assert len(j) == 870 and np.isclose(j.Jobs.sum(), 7142)


# ---------------------------------------------------------------------
# 17 November 2026: the network (walkers and drivers) and the job
# market. Gridby became the one teaching town, so the friction,
# barrier and FCA chapters need it to carry what they used to borrow
# from real places.
# ---------------------------------------------------------------------
import hashlib

from equipop.friction import FrictionGrid, paths_to_friction
from equipop.gridby import network_paths
from scipy.sparse.csgraph import dijkstra


def _fingerprint(df):
    """The values as little-endian float64, with the column names.
    Not to_csv(): pandas ends its lines with os.linesep, so the same
    town hashed differently on Windows (CI, 17 November 2026)."""
    h = hashlib.sha256(",".join(df.columns).encode())
    h.update(np.ascontiguousarray(df.to_numpy(dtype="<f8")).tobytes())
    return h.hexdigest()[:16]


def test_the_town_is_unchanged_draw_for_draw():
    """The network and the job market come from their OWN random
    stream. Drawing them from the town's stream would have moved every
    person and job, and with them every figure in the Book and every
    reference table. Fingerprints taken from 1.64.2, before they were
    added. The hill is not fingerprinted: it is a formula with no draws
    in it, and its last bits differ between maths libraries (CI on
    macOS and Python 3.15); test_gridby_planted_truths checks it.
    BROKEN WITH: one extra draw from the town's stream before the
    jobs."""
    g = load("gridby")
    assert _fingerprint(g["people"]) == "aa24b67ceeb72922"
    assert _fingerprint(g["jobs"]) == "40635d29670df0d6"
    assert _fingerprint(g["friction"]) == "f939a2b9c3cfb654"


def _effort(g, fr, a, b):
    """Rounds from square a to square b, (column, row) each."""
    grid = FrictionGrid(g["people"], fr, 100.0)
    na = grid.node_of(np.array([a[0] * 100 + 50.0]),
                      np.array([a[1] * 100 + 50.0]))
    nb = grid.node_of(np.array([b[0] * 100 + 50.0]),
                      np.array([b[1] * 100 + 50.0]))
    return float(dijkstra(grid.graph, directed=True, indices=na)[0, nb[0]])


def test_each_crossing_serves_the_mode_it_was_built_for():
    """Two squares either side of each crossing: one step each for the
    mode the crossing serves, a long way round for the other.
    BROKEN WITH: the footbridge coded (0, -0.5), open to cars."""
    g = load("gridby")
    walk, drive = g["friction_walk"], g["friction_drive"]
    # Mill Footbridge, row 8: walkers only
    assert _effort(g, walk, (29, 8), (31, 8)) == 2.0
    assert _effort(g, drive, (29, 8), (31, 8)) > 20
    # Link Bridge, row 33: drivers only
    assert _effort(g, drive, (29, 33), (31, 33)) < 1
    assert _effort(g, walk, (29, 33), (31, 33)) > 20
    # East Motorway, column 45: fenced for walkers, fast for drivers
    assert _effort(g, walk, (44, 14), (46, 14)) > 10
    assert _effort(g, drive, (44, 14), (46, 14)) < 1.5
    # ... and the walkers' crossings in it: the underpass and High Street
    assert _effort(g, walk, (44, 8), (46, 8)) == 2.0
    assert _effort(g, walk, (44, 20), (46, 20)) == 2.0
    # the railway: the station footbridge for walkers only
    assert _effort(g, walk, (22, 11), (22, 13)) == 2.0
    assert _effort(g, drive, (22, 11), (22, 13)) > 15
    # and the Old Bridge for both
    assert _effort(g, walk, (29, 20), (31, 20)) == 2.0
    assert _effort(g, drive, (29, 20), (31, 20)) == 1.0


def test_the_network_lines_give_the_friction_tables():
    """A class in QGIS or Pro gets the LINES, not the tables, and
    rasterizes them itself. The lines must give exactly the tables the
    Python reader is handed, or two students doing the same exercise
    get two answers. BROKEN WITH: a piece drawn centre to centre, which
    loses every one-square crossing."""
    g = load("gridby")
    net = g["network"]
    for mode in ("walk", "drive"):
        fr = paths_to_friction(network_paths(net), values=net[mode],
                               unit_size=100.0, say=None)
        fr = fr[fr.friction != 0].sort_values(["x", "y"],
                                              ignore_index=True)
        pd.testing.assert_frame_equal(fr, g[f"friction_{mode}"])


def test_the_motorway_divides_walkers_and_joins_drivers():
    """Planted: the minority share rises eastward, and the motorway
    runs north-south. For walkers it is a wall, so each side's
    neighbourhood is gathered from its own side and the two sides
    differ MORE than with no network; for drivers it is the fastest
    road in town and they differ LESS. BROKEN WITH: the motorway
    coded (0, 0)."""
    g = load("gridby")
    p = g["people"]

    def gap(fr):
        r = run_knn_friction(p, [400], fr=fr, unit_size=100.0)
        east = r[(r.EastWest > 4500) & (r.EastWest < 4800)].R_400.mean()
        west = r[(r.EastWest > 4200) & (r.EastWest < 4500)].R_400.mean()
        return east - west

    plain = gap(None)
    assert gap(g["friction_walk"]) > plain + 0.01
    assert gap(g["friction_drive"]) < plain - 0.01


def test_the_job_market_is_planted():
    """The workers are the town's people and the workplaces its jobs,
    split by education, in the columns of load("municipality")."""
    g = load("gridby")
    w, j, p = g["workers"], g["workplaces"], g["people"]
    assert list(w.columns) == ["x", "y", "LowEdu_sum", "Working_sum",
                               "Population", "Working_group",
                               "LowEdu_group"]
    assert list(j.columns) == ["x", "y", "LowEdu_jobs", "Jobs"]
    # the same squares and the same people
    assert np.array_equal(w.Population.to_numpy(), p.count_all.to_numpy())
    assert (w.Working_sum <= w.Population).all()
    assert (w.LowEdu_sum <= w.Working_sum).all()
    assert (w.Working_group <= p.count_group.to_numpy()).all()
    assert (w.Working_group <= w.Working_sum).all()
    assert (w.LowEdu_group <= w.LowEdu_sum).all()
    assert (w.LowEdu_group <= w.Working_group).all()
    # the same jobs, square for square
    jj = g["jobs"].reset_index(drop=True)
    assert np.array_equal(j[["x", "y"]].to_numpy(), jj[["x", "y"]].to_numpy())
    assert np.array_equal(j.Jobs.to_numpy(), jj.jobs.to_numpy())
    assert (j.LowEdu_jobs <= j.Jobs).all()
    # low education rises northward (planted 15% -> 50%) ...
    north = w.y > 2000
    low_n = w[north].LowEdu_sum.sum() / w[north].Working_sum.sum()
    low_s = w[~north].LowEdu_sum.sum() / w[~north].Working_sum.sum()
    assert low_n > low_s + 0.12
    # ... and the low-education jobs are the dispersed ones
    east = j.x > 3100
    other = j.Jobs - j.LowEdu_jobs
    assert (j[east].LowEdu_jobs.sum() / j.LowEdu_jobs.sum()
            > 3 * other[east].sum() / other.sum())


def test_on_foot_the_east_end_is_far_from_work():
    """The lesson the job market and the network make together: with
    the jobs west of the river, walking access east of the motorway is
    a fraction of the west's, and driving narrows the gap. BROKEN
    WITH: the walkers' and drivers' tables swapped."""
    from equipop.decay import Decay
    from equipop.fca import fca
    g = load("gridby")
    dec = Decay(model="negexp", half_life_m=10)      # read in ROUNDS
    flat = np.zeros(60 * 40)
    ratio = {}
    for mode in ("walk", "drive"):
        d, _ = fca(g["workers"], g["workplaces"], "Working_sum", "Jobs",
                   decay=dec, reach="effort", altitude=flat,
                   fr=g[f"friction_{mode}"])
        ratio[mode] = d[d.x > 4600].A.mean() / d[d.x < 3000].A.mean()
    assert ratio["walk"] < 0.4
    assert ratio["drive"] > ratio["walk"] + 0.15


def test_the_minority_is_slightly_more_often_low_educated():
    """John, 17 November: a reinforced negative is worth showing. The
    minority's workers are planted 8 points more often low-educated
    than the majority's, on top of the south-north rise, so the
    minority is over-represented among the low-educated - slightly.
    BROKEN WITH: LOWEDU_GROUP_EXTRA = 0."""
    g = load("gridby")
    w = g["workers"]
    low_g = w.LowEdu_group.sum() / w.Working_group.sum()
    low_o = ((w.LowEdu_sum - w.LowEdu_group).sum()
             / (w.Working_sum - w.Working_group).sum())
    assert 0.05 < low_g - low_o < 0.11
    share_workers = w.Working_group.sum() / w.Working_sum.sum()
    share_low = w.LowEdu_group.sum() / w.LowEdu_sum.sum()
    assert share_low > share_workers + 0.03


def test_the_reinforced_negative_on_foot():
    """What the over-representation is for: the minority lives east,
    where the motorway walls walkers off, so its low-educated workers
    reach fewer low-education jobs on foot than the majority's do - and
    the car halves the gap. BROKEN WITH: Working_group drawn from the
    majority (hypergeometric with good and bad swapped)."""
    from equipop.decay import Decay
    from equipop.fca import fca
    g = load("gridby")
    w = g["workers"]
    dec = Decay(model="negexp", half_life_m=10)      # read in ROUNDS
    ratio = {}
    for mode in ("walk", "drive"):
        d, _ = fca(w, g["workplaces"], "LowEdu_sum", "LowEdu_jobs",
                   decay=dec, reach="effort", altitude=np.zeros(60 * 40),
                   fr=g[f"friction_{mode}"])
        minority = np.average(d.A, weights=d.LowEdu_group)
        majority = np.average(d.A, weights=d.LowEdu_sum - d.LowEdu_group)
        ratio[mode] = minority / majority
    assert ratio["walk"] < 0.9
    assert ratio["drive"] > ratio["walk"] + 0.04

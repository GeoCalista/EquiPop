"""
gridby.py - Gridby, the synthetic teaching city (founded 1848).

Lives INSIDE the package (moved here in 1.19.0) because it is the
first thing a reader of the Book types - `load("gridby")` - and it
used to be reachable only from a git clone: the generator sat in
examples/, which pip does not install. A student who installed from
PyPI got ModuleNotFoundError on line one.

Nothing here needs a data file. The town is GENERATED, deterministic
from seed 1848, so shipping it costs nothing but this module.

A 6 x 4 km town on a 100 m grid, generated deterministically with
PLANTED, documented properties so every figure in the Book can
demonstrate exactly one phenomenon:

  1. A west-east SEGREGATION GRADIENT: the minority share rises
     linearly from 10% (west) to 60% (east).
  2. A RIVER running north-south through the middle (friction 6),
     with ONE bridge - straight-line distance lies about the far bank.
  3. A HILL in the north-east (Gaussian, ~90 m) - climbing costs.
  4. A JOBS CLUSTER west of the river (70% of jobs), the rest
     scattered - competition has a geography.

  5. A TRANSPORT NETWORK (17 November 2026): roads, a motorway, a
     railway, the river and every crossing, each piece coded with a
     friction for WALKERS and one for DRIVERS - the footbridge only
     walkers can use, the link bridge only drivers can, the motorway
     that carries cars and fences walkers out.
  6. A JOB MARKET by education: the same people and the same jobs,
     split into low-education workers and jobs, in the columns of
     load("municipality") so the FCA examples run on either, plus the
     minority's own workers (Working_group, LowEdu_group), who are
     slightly more often low-educated.

Ground truths live in meta() and double as test fixtures: if EquiPop
cannot recover a planted truth, the tests fail.

5 and 6 are drawn from a SEPARATE random stream, so 1 to 4 are
unchanged draw for draw: every figure, test and reference built on
Gridby before them is exactly as it was (tests/test_gridby.py holds
the fingerprints).
"""
import numpy as np
import pandas as pd

SEED = 1848
NX, NY, U = 60, 40, 100.0          # 6 x 4 km
RIVER_COL = 30                      # cell column of the river
BRIDGE_ROW = 20                     # the one bridge
HILL = (48, 30, 90.0, 8.0)          # cx, cy, height_m, sd_cells

# ------------------------------------------------ 5. the network
#: Friction for (WALKERS, DRIVERS). Entering a square costs 1 + friction
#: rounds (Book chapter 9). Local streets run through every square, so
#: a square that is on no line here costs one round for both. For
#: drivers that is 20 km/h, and a negative friction is a faster road:
#: -0.5 is 40 km/h, -0.7 about 67, -0.8 is 100. A WALL costs 50, the
#: Book's "essentially never": people cross at a crossing. That
#: includes the river, which here is a wall with bridges; the simpler
#: g["friction"] keeps its river at 6, a delay, as chapter 9 teaches.
KINDS = {
    "river":           (50.0, 50.0),   # a wall: cross at a bridge
    "road bridge":     (0.0, -0.5),    # High Street over the river
    "footbridge":      (0.0, 50.0),    # walkers only: a car meets the river
    "link bridge":     (50.0, -0.7),   # no pavement: a walker meets the river
    "motorway":        (50.0, -0.8),   # fenced for walkers, 100 km/h
    "underpass":       (0.0, -0.8),    # a footpath under the motorway
    "junction":        (0.0, -0.8),    # High Street meets the motorway
    "railway":         (50.0, 50.0),   # fenced for both
    "level crossing":  (0.0, -0.5),    # West Avenue over the railway
    "rail footbridge": (0.0, 50.0),    # walkers only
    "main road":       (0.0, -0.5),    # pavements both sides
    "link road":       (0.0, -0.7),    # pavements, faster for cars
}

#: Every piece: (name, kind, first square, last square), squares as
#: (column, row), inclusive, one straight run each. Where two lines
#: cross, the square belongs to ONE piece, so no square is counted
#: twice and the overlap rule never matters.
NETWORK = [
    ("River", "river", (30, 0), (30, 7)),
    ("Mill Footbridge", "footbridge", (30, 8), (30, 8)),
    ("River", "river", (30, 9), (30, 19)),
    ("Old Bridge", "road bridge", (30, 20), (30, 20)),
    ("River", "river", (30, 21), (30, 32)),
    ("Link Bridge", "link bridge", (30, 33), (30, 33)),
    ("River", "river", (30, 34), (30, 39)),
    ("East Motorway", "motorway", (45, 0), (45, 7)),
    ("School Underpass", "underpass", (45, 8), (45, 8)),
    ("East Motorway", "motorway", (45, 9), (45, 19)),
    ("High Street junction", "junction", (45, 20), (45, 20)),
    ("East Motorway", "motorway", (45, 21), (45, 39)),
    ("Railway", "railway", (0, 12), (11, 12)),
    ("West Avenue crossing", "level crossing", (12, 12), (12, 12)),
    ("Railway", "railway", (13, 12), (21, 12)),
    ("Station Footbridge", "rail footbridge", (22, 12), (22, 12)),
    ("Railway", "railway", (23, 12), (29, 12)),
    ("High Street", "main road", (0, 20), (29, 20)),
    ("High Street", "main road", (31, 20), (44, 20)),
    ("High Street", "main road", (46, 20), (59, 20)),
    ("West Avenue", "main road", (12, 0), (12, 11)),
    ("West Avenue", "main road", (12, 13), (12, 19)),
    ("West Avenue", "main road", (12, 21), (12, 39)),
    ("North Link", "link road", (13, 33), (29, 33)),
    ("North Link", "link road", (31, 33), (44, 33)),
]

# ------------------------------------------------ 6. the job market
WORKING_SHARE = 0.55                # of residents, everywhere
LOWEDU_SOUTH, LOWEDU_NORTH = 0.15, 0.50   # of workers, rising northward
LOWEDU_GROUP_EXTRA = 0.08           # ... and 8 points more in the minority
LOWJOB_CLUSTER, LOWJOB_SCATTERED = 0.20, 0.70   # of jobs


def gridby(seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    gx, gy = np.meshgrid(np.arange(NX), np.arange(NY), indexing="ij")
    gx, gy = gx.ravel(), gy.ravel()
    x = gx * U + U / 2
    y = gy * U + U / 2

    pop = rng.poisson(8, NX * NY).astype(float)
    pop[gx == RIVER_COL] = 0.0                       # nobody lives IN the river
    share = 0.10 + 0.50 * gx / (NX - 1)              # planted gradient
    grp = rng.binomial(pop.astype(int), share).astype(float)

    live = pop > 0
    people = pd.DataFrame({"x": x[live], "y": y[live],
                           "count_all": pop[live],
                           "count_group": grp[live]})

    river = (gx == RIVER_COL) & (gy != BRIDGE_ROW)
    friction = pd.DataFrame({"x": x[river], "y": y[river],
                             "friction": 6})

    cx, cy, h, sd = HILL
    altitude = h * np.exp(-((gx - cx) ** 2 + (gy - cy) ** 2)
                          / (2 * sd ** 2))           # per DOMAIN cell

    n_jobs = 2000
    west = rng.normal([12 * U, 20 * U], [6 * U, 6 * U], (int(n_jobs * .7), 2))
    scat = np.c_[rng.uniform(0, NX * U, int(n_jobs * .3)),
                 rng.uniform(0, NY * U, int(n_jobs * .3))]
    jx = np.clip(np.vstack([west, scat]), 0, [NX * U - 1, NY * U - 1])
    jobs = (pd.DataFrame({"x": np.floor(jx[:, 0] / U) * U + U / 2,
                          "y": np.floor(jx[:, 1] / U) * U + U / 2,
                          "jobs": 1.0})
            .groupby(["x", "y"], as_index=False).sum())
    jobs = jobs[~((np.floor(jobs.x / U) == RIVER_COL))]   # not in the river

    # 5 and 6, from their own stream: nothing above may move
    network, fr_walk, fr_drive = _network()
    workers, workplaces = _job_market(np.random.default_rng([seed, 6]),
                                      np.random.default_rng([seed, 7]),
                                      people, jx, len(west))

    meta = {"seed": seed, "nx": NX, "ny": NY, "unit": U,
            "gradient": "minority share 0.10 (west) -> 0.60 (east), linear",
            "river_col": RIVER_COL, "bridge_row": BRIDGE_ROW,
            "hill": {"cx": cx, "cy": cy, "height_m": h},
            "jobs_cluster": "70% west of river around cell (12, 20)",
            "population": float(people.count_all.sum()),
            "minority": float(people.count_group.sum()),
            "network": "river crossings: Old Bridge (row 20, both), "
                       "Mill Footbridge (row 8, walkers only), Link "
                       "Bridge (row 33, drivers only); East Motorway "
                       "(column 45) fenced for walkers, who cross at "
                       "rows 8 and 20; railway (row 12, west bank) "
                       "fenced for both, crossed at column 12 by both "
                       "and at column 22 by walkers",
            "job_market": "55% of residents work; low education "
                          "15% of workers (south) -> 50% (north), "
                          "linear, NOT the minority's direction, plus "
                          "8 points for minority workers (a slight "
                          "over-representation: the reinforced "
                          "negative); low-education jobs 20% of the "
                          "western cluster, 70% of the scattered jobs",
            "low_edu_group_workers": float(workers.LowEdu_group.sum()),
            "workers": float(workers.Working_sum.sum()),
            "low_edu_workers": float(workers.LowEdu_sum.sum()),
            "jobs": float(workplaces.Jobs.sum()),
            "low_edu_jobs": float(workplaces.LowEdu_jobs.sum())}
    return {"people": people, "jobs": jobs, "friction": friction,
            "altitude": altitude, "network": network,
            "friction_walk": fr_walk, "friction_drive": fr_drive,
            "workers": workers, "workplaces": workplaces, "meta": meta}


def _network():
    """The NETWORK pieces as straight lines, and the friction table
    each mode gets from them. A piece runs from the outer edge of its
    first square to the outer edge of its last, along their centre
    line, so it lies inside exactly its own squares and touches the
    next piece only at a point."""
    rows, walk, drive = [], {}, {}
    for name, kind, (i0, j0), (i1, j1) in NETWORK:
        w, d = KINDS[kind]
        if j0 == j1:                                   # east-west
            x0, x1 = i0 * U, (i1 + 1) * U
            y0 = y1 = j0 * U + U / 2
        else:                                          # north-south
            assert i0 == i1, name
            x0 = x1 = i0 * U + U / 2
            y0, y1 = j0 * U, (j1 + 1) * U
        rows.append((name, kind, w, d, x0, y0, x1, y1))
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                key = (i * U + U / 2, j * U + U / 2)
                assert key not in walk, f"square {i, j} is on two pieces"
                walk[key], drive[key] = w, d
    network = pd.DataFrame(rows, columns=["name", "kind", "walk", "drive",
                                          "x0", "y0", "x1", "y1"])

    def table(costs):
        t = pd.DataFrame([(x, y, f) for (x, y), f in costs.items() if f],
                         columns=["x", "y", "friction"])
        return t.sort_values(["x", "y"], ignore_index=True)
    return network, table(walk), table(drive)


def network_paths(network: pd.DataFrame) -> list:
    """The network as coordinate paths for friction.paths_to_friction,
    which needs no geopandas:

        from equipop.friction import paths_to_friction
        fr = paths_to_friction(network_paths(net), values=net.walk)

    gives the same squares and costs as g["friction_walk"], plus the
    roads whose cost for walkers is 0."""
    return [{"type": "line", "parts": [[(r.x0, r.y0), (r.x1, r.y1)]]}
            for r in network.itertuples()]


def _job_market(rng, rng_jobs, people, jx, n_cluster):
    """Workers by education on the people's squares, and the town's
    jobs typed by education, job for job (the first n_cluster rows of
    jx are the western cluster, the rest the scattered jobs).

    John, 17 November: a REINFORCED NEGATIVE is worth being able to
    show - a minority that is also slightly over-represented among the
    low-educated, as in many real towns. So the workers are split by
    group (hypergeometric: which of a square's workers are minority),
    and low education is drawn for each group, the minority's
    LOWEDU_GROUP_EXTRA higher. Working_sum is drawn first and exactly
    as before, so the job-access numbers in Book ch09 do not move. The
    jobs have had their own stream since, so changing the workers
    never moves them."""
    n = people.count_all.to_numpy().astype(int)
    g = people.count_group.to_numpy().astype(int)
    work = rng.binomial(n, WORKING_SHARE)
    work_g = rng.hypergeometric(g, n - g, work)
    row = np.floor(people.y.to_numpy() / U)
    p_low = LOWEDU_SOUTH + (LOWEDU_NORTH - LOWEDU_SOUTH) * row / (NY - 1)
    low_g = rng.binomial(work_g, p_low + LOWEDU_GROUP_EXTRA)
    low_o = rng.binomial(work - work_g, p_low)
    workers = pd.DataFrame({"x": people.x.to_numpy(),
                            "y": people.y.to_numpy(),
                            "LowEdu_sum": (low_g + low_o).astype(float),
                            "Working_sum": work.astype(float),
                            "Population": people.count_all.to_numpy(),
                            "Working_group": work_g.astype(float),
                            "LowEdu_group": low_g.astype(float)})

    p_job = np.where(np.arange(len(jx)) < n_cluster,
                     LOWJOB_CLUSTER, LOWJOB_SCATTERED)
    low_job = rng_jobs.random(len(jx)) < p_job
    workplaces = (pd.DataFrame({"x": np.floor(jx[:, 0] / U) * U + U / 2,
                                "y": np.floor(jx[:, 1] / U) * U + U / 2,
                                "LowEdu_jobs": low_job.astype(float),
                                "Jobs": 1.0})
                  .groupby(["x", "y"], as_index=False).sum())
    workplaces = workplaces[~(np.floor(workplaces.x / U) == RIVER_COL)]
    return workers, workplaces.reset_index(drop=True)


if __name__ == "__main__":
    g = gridby()
    print({k: (v.shape if hasattr(v, "shape") else len(v))
           for k, v in g.items() if k != "meta"})
    print(g["meta"])

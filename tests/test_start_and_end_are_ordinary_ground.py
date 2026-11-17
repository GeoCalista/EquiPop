"""R-52 (John, 17 November 2026): "free from friction in the start and
end square ... same everywhere (for logic)".

A trip pays the friction of the squares it PASSES THROUGH. The square it
starts in was never charged; the square it ends in now costs what
ordinary ground costs. A 100 m square cannot tell a home beside the
railway from one on it: before this rule, the trip home paid the whole
wall, and a home beside the motorway was reached at motorway speed.

The town here is one row of five squares, so every number can be worked
out by hand: friction 50 (a wall) or -0.8 (a motorway) on square 2.
"""
import numpy as np
import pandas as pd
import pytest

from equipop.friction import FrictionGrid

U = 100.0
XS = [50.0, 150.0, 250.0, 350.0, 450.0]


def _strip(value):
    pop = pd.DataFrame({"x": XS, "y": [50.0] * 5,
                        "count_all": 1.0, "count_group": 0.0})
    fr = pd.DataFrame({"x": [250.0], "y": [50.0], "friction": [value]})
    return pop, fr


def _node(grid, i):
    return int(grid.node_of(XS[i], 50.0))


def test_a_wall_is_paid_only_when_passed_through():
    """BROKEN WITH: effort_from returning the plain Dijkstra (the end
    square charged its friction)."""
    pop, fr = _strip(50.0)
    g = FrictionGrid(pop, fr, U)
    out = g.effort_from([_node(g, 0)])[0]
    # 1 to the next square, 1 more to the wall square where the trip
    # ends, and 51 to pass through it
    assert out[[_node(g, i) for i in range(5)]].tolist() == \
        [0.0, 1.0, 2.0, 53.0, 54.0]


def test_the_way_home_to_a_wall_square_costs_ordinary_ground():
    """The home on the wall square: leaving was always free, and now
    so is arriving. BROKEN WITH: effort_to returning the plain reversed
    Dijkstra (the way home paid the wall)."""
    pop, fr = _strip(50.0)
    g = FrictionGrid(pop, fr, U)
    home = _node(g, 2)
    back = g.effort_to([home])[0]
    assert back[[_node(g, i) for i in range(5)]].tolist() == \
        [2.0, 1.0, 0.0, 1.0, 2.0]


def test_a_home_beside_the_motorway_is_not_reached_at_motorway_speed():
    """Same everywhere: a facilitator is paid only when passed through
    too. The motorway square itself is reached for a full round; the
    square beyond it for 0.2 + 1."""
    pop, fr = _strip(-0.8)
    g = FrictionGrid(pop, fr, U)
    out = g.effort_from([_node(g, 1)])[0]
    assert out[_node(g, 2)] == pytest.approx(1.0)
    assert out[_node(g, 3)] == pytest.approx(1.2)


def test_on_a_slope_the_last_climb_is_paid_and_the_friction_is_not():
    """The square a trip ends in costs ordinary ground - which on a hill
    is the climb into it."""
    from equipop.slope import SlopeGrid, slope_penalty
    pop, fr = _strip(50.0)
    alt = np.array([0.0, 0.0, 10.0, 10.0, 10.0])      # a 10 m step up
    g = SlopeGrid(pop, fr, U, altitude=alt, model="tobler")
    out = g.effort_from([_node(g, 1)])[0]
    climb = slope_penalty("tobler")(10.0 / U)
    assert out[_node(g, 2)] == pytest.approx(climb)


def test_fca_round_trip_from_a_home_on_a_wall():
    """The case that found it (BACKLOG 502): a home on a wall square, a
    job next door. Out 1, back 1: an effort of 1, where it was
    (1 + 51) / 2 = 26."""
    from equipop.fca import _effort_matrix
    pop, fr = _strip(50.0)
    demand = pop.iloc[[2]][["x", "y"]]
    supply = pop.iloc[[3]][["x", "y"]]
    # the FCA grid spans the demand and supply squares only: two
    E = _effort_matrix(demand, supply, np.zeros(2), "tobler", True,
                       U, chunk=10, fr=fr)
    assert E[0, 0] == pytest.approx(1.0)


def test_effort_potential_round_trip_from_a_home_on_a_wall():
    from equipop.access import effort_potential
    from equipop.decay import Decay
    pop, fr = _strip(50.0)
    mass = pd.DataFrame({"x": [350.0], "y": [50.0], "mass": [1.0]})
    dec = Decay(model="negexp", half_life_m=1.0)     # rounds
    out = effort_potential(pop, mass, dec, altitude=np.zeros(5), fr=fr,
                           roundtrip=True)
    home = out[out.x == 250.0].A.iloc[0]
    assert home == pytest.approx(0.5)                # one round away


def test_gridby_homes_on_the_railway_keep_their_job_access():
    """What the rule is for, in the teaching town: the 30 squares of the
    railway are walls on foot, and people live on them. Their walking
    job access is now that of their neighbours, not near zero."""
    from equipop.datasets import load
    from equipop.decay import Decay
    from equipop.fca import fca
    g = load("gridby")
    d, _ = fca(g["workers"], g["workplaces"], "Working_sum", "Jobs",
               decay=Decay(model="negexp", half_life_m=10),
               reach="effort", altitude=np.zeros(60 * 40),
               fr=g["friction_walk"])
    west = d[d.x < 3000]
    rail = west[west.y == 1250].A.mean()
    beside = west[west.y.isin([1150.0, 1350.0])].A.mean()
    assert rail > 0.8 * beside

"""
assigndoor.py - tool 7, WHO GOES WHERE: the half both GIS doors share
(machine 7, step 1; BACKLOG 515; ruling R-56).

The engine is equipop/assign.py. What is shared here: reading the boxes
as a person types them, running, saying what happened, and saying what
each new column holds. What each door keeps for itself: reading the two
point layers and writing three layers back.

The boxes, as a person types them:
    People               a point layer; a field of how many live at each
                         point (empty = one per point)
    Destinations         a point layer; a field of how many each takes
                         (empty = no limit)
    How people choose    one of METHOD_LABELS
    Half-life            metres - for "chosen by distance decay" and
                         "flows": a place this far off weighs half
    Farthest             metres anyone goes (empty = no limit)
    Group size           10        people who move together in the queue
    Runs                 20        repeated draws, averaged
    Seed                 1         the same seed gives the same numbers
    Speed                5         km/h, for minutes
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .numbers import BadNumber, is_blank, to_float, to_int

#: How people choose - the same words, in this order, in both doors.
METHOD_LABELS = (
    "Random order: the nearest with room",
    "Random order: drawn by distance decay",
    "Closest first: no randomness",
    "Flows: the pressure on each destination (capacity ignored)",
)
METHOD_KEYS = ("nearest", "decay", "closest", "flows")


def method_of(choice) -> str:
    """The engine's name for a choice: its label, its position, or the
    engine's own name."""
    if choice is None or (isinstance(choice, str) and is_blank(choice)):
        return METHOD_KEYS[0]
    if isinstance(choice, (int, np.integer)):
        if 0 <= int(choice) < len(METHOD_KEYS):
            return METHOD_KEYS[int(choice)]
    t = str(choice).strip()
    if t in METHOD_KEYS:
        return t
    for label, key in zip(METHOD_LABELS, METHOD_KEYS):
        if t.lower() == label.lower():
            return key
    if t.isdigit() and int(t) < len(METHOD_KEYS):
        return METHOD_KEYS[int(t)]
    raise BadNumber("How people choose is one of: "
                    + "; ".join(METHOD_LABELS) + ".")


def _metres(text, box, required=False):
    if is_blank(text):
        if required:
            raise BadNumber(f"{box} is needed here: a distance in metres "
                            "above 0, such as 1000.")
        return None
    v = to_float(text)
    if v is None or not v > 0:
        raise BadNumber(f"{box} is one distance in metres above 0, such "
                        "as 1000.")
    return float(v)


def parse_boxes(method="", half_life="", farthest="", group_size="",
                runs="", seed="", speed="") -> dict:
    """The typed boxes -> assign()'s settings, or a sentence saying what
    is wrong."""
    m = method_of(method)
    hl = _metres(half_life, "The half-life",
                 required=m in ("decay", "flows"))
    far = _metres(farthest, "The farthest distance")
    g = 10.0 if is_blank(group_size) else to_float(group_size)
    if g is None or not g > 0:
        raise BadNumber("The group size is a number of people above 0, "
                        "such as 10 (1 = one person at a time).")
    n = 20 if is_blank(runs) else to_int(runs)
    if n is None or not 1 <= n <= 10_000:
        raise BadNumber("Runs is a whole number from 1 to 10,000, such "
                        "as 20.")
    s = 1 if is_blank(seed) else to_int(seed)
    if s is None or s < 0:
        raise BadNumber("The seed is a whole number, 0 or more, such "
                        "as 1.")
    v = 5.0 if is_blank(speed) else to_float(speed)
    if v is None or not v > 0:
        raise BadNumber("The speed is in km/h, above 0 - 5 for walking, "
                        "15 for cycling.")
    return dict(method=m, half_life=hl, farthest=far, group_size=float(g),
                runs=int(n), seed=int(s), speed_kmh=float(v))


def run(origins: pd.DataFrame, destinations: pd.DataFrame, *,
        people=None, capacity=None, method="", half_life="", farthest="",
        group_size="", runs="", seed="", speed="", layer_is_metric=True,
        same_crs=True, say=print):
    """Both doors' run. `origins` and `destinations` hold x and y in
    metres; `people` and `capacity` are arrays (or None: one person per
    point, no limit). Returns equipop.assign.Assignment."""
    from ..assign import assign
    kw = parse_boxes(method, half_life, farthest, group_size, runs, seed,
                     speed)
    if not layer_is_metric:
        raise BadNumber(
            "The layers must be in a projected coordinate system in "
            "metres - distances are metres. Project them first (QGIS: "
            "Vector > Data Management Tools > Reproject Layer; Pro: "
            "Project).")
    if not same_crs:
        raise BadNumber(
            "The people and the destinations are in different "
            "coordinate systems. Project one to the other's first.")
    o = pd.DataFrame({"x": np.asarray(origins["x"], float),
                      "y": np.asarray(origins["y"], float)})
    d = pd.DataFrame({"x": np.asarray(destinations["x"], float),
                      "y": np.asarray(destinations["y"], float)})
    if len(o) == 0:
        raise BadNumber("The people layer has no points.")
    if len(d) == 0:
        raise BadNumber("The destinations layer has no points.")
    for frame, what in ((o, "people"), (d, "destinations")):
        bad = ~(np.isfinite(frame.x) & np.isfinite(frame.y))
        if bad.any():
            raise BadNumber(f"{int(bad.sum()):,} {what} points have no "
                            "location. Remove them, or give them one.")
    if people is not None:
        o["n"] = _values(people, "people", "a number of people")
    if capacity is not None:
        d["c"] = _values(capacity, "destinations",
                         "a capacity (0 for closed)")
    m = kw["method"]
    total = o["n"].sum() if people is not None else float(len(o))
    room = d["c"].sum() if capacity is not None else np.inf
    say(f"[assign] {total:,.0f} people at {len(o):,} points; "
        f"{len(d):,} destinations "
        + (f"with {room:,.0f} places" if np.isfinite(room)
           else "with no limit"))
    say(f"[assign] how people choose: "
        f"{METHOD_LABELS[METHOD_KEYS.index(m)]}"
        + (f"; half-life {kw['half_life']:,.0f} m"
           if kw["half_life"] else "")
        + (f"; at most {kw['farthest']:,.0f} m" if kw["farthest"]
           else ""))
    if m in ("nearest", "decay"):
        say(f"[assign] groups of {kw['group_size']:g} in a random order; "
            f"{kw['runs']} run{'s' if kw['runs'] != 1 else ''}, seed "
            f"{kw['seed']}")
    if m == "flows" and capacity is not None:
        say("[assign] flows ignore capacity: Sim_Ratio is the pressure - "
            "the expected load over the places there are")
    try:
        a = assign(o, d, people="n" if people is not None else None,
                   capacity="c" if capacity is not None else None, **kw)
    except ValueError as e:
        raise BadNumber(str(e)) from None
    placed = a.origins.Sim_Placed.sum()
    unmet = a.origins.Sim_Unmet.sum()
    w = a.origins.Sim_Placed.to_numpy()
    mm = a.origins.Sim_Metres.to_numpy()
    ok = np.isfinite(mm) & (w > 0)
    mean = float(np.average(mm[ok], weights=w[ok])) if ok.any() else np.nan
    say(f"[assign] placed {placed:,.1f} of {total:,.0f} "
        f"({(placed / total if total else 0):.0%}); unmet {unmet:,.1f}; "
        + (f"the average trip is {mean:,.0f} m, "
           f"{mean / (kw['speed_kmh'] * 1000 / 60):,.1f} minutes at "
           f"{kw['speed_kmh']:g} km/h" if np.isfinite(mean)
           else "nobody was placed"))
    say("[assign] The new columns:")
    for layer, cols in describe(m, kw["runs"], capacity is not None,
                                kw["speed_kmh"]).items():
        for col, text in cols:
            say(f"[assign]   {layer}, {col}: {text}")
    return a


def tables(a, has_capacity=True, speed_kmh=5.0) -> dict:
    """The three layers a door writes, with exactly the columns
    describe() names: {"origins", "destinations", "trips"}. Trips name
    their points by row, counted from 1, as a GIS table shows them."""
    cols = describe(a.method, a.runs, has_capacity, speed_kmh)
    out = {
        "origins": a.origins[[c for c, _ in cols["origins"]]],
        "destinations": a.destinations[[c for c, _ in
                                        cols["destinations"]]],
    }
    t = a.trips.copy()
    t["Origin"] = t["Origin"].astype(np.int64) + 1
    t["Dest"] = t["Dest"].astype(np.int64) + 1
    out["trips"] = t[[c for c, _ in cols["trips"]]]
    return out


def _values(v, what, needs):
    v = np.asarray(pd.to_numeric(pd.Series(v), errors="coerce"), float)
    bad = ~np.isfinite(v) | (v < 0)
    if bad.any():
        raise BadNumber(f"{int(bad.sum()):,} {what} points have no "
                        f"usable value: each needs {needs}, 0 or more "
                        "(an empty value is not read as 0).")
    return v


def describe(method, runs=20, has_capacity=True, speed_kmh=5.0) -> dict:
    """{layer: [(column, what it holds)]} - the run log's last lines,
    and each field's alias where the format keeps one."""
    sim = method in ("nearest", "decay")
    avg = (f"averaged over {runs} run{'s' if runs != 1 else ''} "
           "(simulated)" if sim else "")
    tag = f", {avg}" if avg else ""
    # No People and no Capacity column: the layers are COPIED, so the
    # population and capacity fields are already there under the
    # person's own names - and writing them again under ours broke Pro
    # where those names were the same (John, 24 November 2026: "field
    # 'Capacity' exist").
    origins = [
        ("Sim_Placed", f"people who found a place{tag}"),
        ("Sim_Unmet", "people who found no place within reach - every "
                      f"destination there was full{tag}"
                      if method != "flows" else
                      "people with no destination within reach"),
        ("Sim_Metres", f"the average trip of those placed, in metres"
                       f"{tag}"),
        ("Sim_Mins", f"the same trip in minutes at {speed_kmh:g} km/h"),
        ("Sim_Spread", "how much Sim_Metres differs from run to run "
                       "(standard deviation; 0 when nothing is drawn)"),
    ]
    load = ("the expected number of people coming here - the pressure"
            if method == "flows" else f"people placed here{tag}")
    dests = [
        ("Sim_Load", load),
        ("Sim_LoadSd", "how much Sim_Load differs from run to run"),
        ("Sim_Ratio", "Sim_Load over the places in the capacity field: "
                      "above 1 is more people than places"
                      if method == "flows" else
                      "Sim_Load over the places in the capacity field, "
                      "0 to 1"),
        ("Sim_Full", "the share of runs in which it filled (0 to 1)"),
        ("Sim_Metres", f"the average trip of the people placed here, in "
                       f"metres{tag}"),
    ]
    if not has_capacity:
        dests = [c for c in dests if c[0] not in ("Sim_Ratio",
                                                  "Sim_Full")]
    trips = [
        ("Origin", "the people point the trip starts from (its row, from "
                   "1)"),
        ("Dest", "the destination it goes to (its row, from 1)"),
        ("People", "how many make this trip"
                   + (" in run 1 - the trips of one run, not an "
                      "average" if sim else "")),
        ("Metres", "the straight-line distance"),
        ("Minutes", f"the same at {speed_kmh:g} km/h"),
    ]
    return {"origins": origins, "destinations": dests, "trips": trips}

"""
areasdoor.py - tool 1b, SUMMARIES BY AREA: the half both GIS doors share
(BACKLOG 521; rulings R-61 and R-62).

Points - people, addresses, grid centres, or the output of tools 1, 2
or 7 - are summarised over areas: wards, tracts, DeSO, municipalities,
counties, which may overlap. The geometry is equipop/zones.py; the
statistics are tool 2's (equipop/wstats.py), per person.

The boxes, as a person types them:
    Points               a point layer
    Areas                a polygon layer (they may overlap)
    Area name field      names each area in the output (optional)
    Level field          e.g. municipality / county: which areas belong
                         together, when they overlap (optional)
    People per point     a count field (empty = one per point)
    Count fields         summed, and shared among the area's people
    Value fields         summarised with the statistics below
    Statistics           any of STAT_LABELS (default mean and median)
    Hide below           areas with fewer people show no statistics
    Points in no area    snapped to the nearest area, or left out
    Snap only within     metres (empty = any distance)

R-61, which area a point counts in (John, 27 November 2026):
  * inside one area: that area;
  * exactly on a border: the FIRST of the areas whose border it is on,
    never two - "if we include them we increase the total population";
  * in no area: the nearest area by default, or left out, as chosen;
    at the same distance from two, the first; beyond "snap only
    within", left out;
  * all of this WITHIN EACH LEVEL when a level field is given: a person
    lives in one municipality AND one county. Without one, a point
    inside overlapping areas counts in every one of them.
R-62, what an area reports: per person (weighted by the people field),
with tool 2's definitions (variance over n - 1, the median
interpolated); an area with fewer people than the threshold shows its
N and nothing else.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .numbers import BadNumber, is_blank, to_float
from ..stats import stat_prefix

#: The statistics a person can tick, engine name and words, in order.
STAT_LABELS = (
    ("mean", "Mean"), ("median", "Median"),
    ("min", "Minimum"), ("max", "Maximum"), ("sum", "Sum"),
    ("var", "Variance"), ("sd", "Standard deviation"), ("range", "Range"),
    ("gini", "Gini"), ("theil", "Theil"),
    ("p10", "10th percentile"), ("p25", "25th percentile"),
    ("p75", "75th percentile"), ("p90", "90th percentile"),
)
STAT_KEYS = tuple(k for k, _ in STAT_LABELS)
DEFAULT_STATS = ("mean", "median")

#: Points in no area - the same words, in this order, in both doors.
OUTSIDE_LABELS = ("Snapped to the nearest area (default)",
                  "Left out, and counted in the messages")
OUTSIDE_KEYS = ("nearest", "leave")

#: More than this share of points exactly on borders gets a warning.
BORDER_WARN = 0.05


def stats_of(chosen) -> list[str]:
    """The ticked statistics -> engine names (labels, keys or
    positions); none ticked means the default."""
    if chosen is None or (isinstance(chosen, str) and is_blank(chosen)):
        return list(DEFAULT_STATS)
    items = (chosen if isinstance(chosen, (list, tuple))
             else re.split(r"[;,]\s*", str(chosen)))
    out = []
    for c in items:
        if isinstance(c, (int, np.integer)) or str(c).strip().isdigit():
            i = int(c)
            if not 0 <= i < len(STAT_KEYS):
                raise BadNumber(f"There is no statistic number {i}.")
            out.append(STAT_KEYS[i])
            continue
        t = str(c).strip()
        if not t:
            continue
        for k, label in STAT_LABELS:
            if t.lower() in (k, label.lower()):
                out.append(k)
                break
        else:
            raise BadNumber(f'"{t}" is not one of the statistics: '
                            + ", ".join(l for _, l in STAT_LABELS) + ".")
    return list(dict.fromkeys(out)) or list(DEFAULT_STATS)


def outside_of(choice) -> str:
    if choice is None or (isinstance(choice, str) and is_blank(choice)):
        return OUTSIDE_KEYS[0]
    if isinstance(choice, (int, np.integer)):
        return OUTSIDE_KEYS[int(choice)]
    t = str(choice).strip()
    if t in OUTSIDE_KEYS:
        return t
    for label, key in zip(OUTSIDE_LABELS, OUTSIDE_KEYS):
        if t.lower() == label.lower():
            return key
    raise BadNumber("Points in no area are one of: "
                    + "; ".join(OUTSIDE_LABELS) + ".")


def parse_boxes(stats=None, min_people="", outside="",
                snap_within="") -> dict:
    """The typed boxes -> run()'s settings, or a sentence."""
    mp = 0.0
    if not is_blank(min_people):
        mp = to_float(min_people)
        if mp is None or mp < 0:
            raise BadNumber("Hide areas with fewer than ... people takes "
                            "one number of 0 or more, such as 10.")
    sw = None
    if not is_blank(snap_within):
        sw = to_float(snap_within)
        if sw is None or not sw > 0:
            raise BadNumber("Snap only within takes one distance in metres "
                            "above 0, such as 500, or nothing for any "
                            "distance.")
    return {"stats": stats_of(stats), "min_people": float(mp),
            "outside": outside_of(outside), "snap_within": sw}


# ------------------------------------------------------------------ R-61
def belong(zones, x, y, levels=None, outside="nearest",
           snap_within=None):
    """Which area(s) each point counts in, by R-61.

    zones  : an equipop.zones.Areas
    levels : one label per area, or None (no level field)
    Returns (pairs, report): pairs is a DataFrame of point, area (a
    point appears once per level it counts in); report holds the
    counts the messages say.
    """
    n = len(x)
    good = np.isfinite(x) & np.isfinite(y)
    pi, aj, inside = zones.locate(x, y)
    lev = (np.asarray(levels, dtype=object) if levels is not None
           else np.full(len(zones), "", dtype=object))
    names = list(dict.fromkeys(lev.tolist()))
    rep = {"points": n, "no_xy": int((~good).sum()), "border": 0, "shared_border": 0, "overlap": 0,
           "snapped": 0, "snap_max": 0.0, "ties": 0, "left_out": 0,
           "beyond": 0, "levels": names if levels is not None else []}
    out_p, out_a = [], []
    on_border = np.zeros(n, bool)
    for L in names:
        in_level = np.nonzero(lev == L)[0]
        m = np.isin(aj, in_level)
        p, a, ins = pi[m], aj[m], inside[m]
        # inside: every area (no level field: nested layers all count);
        # within a declared level, only the first (an overlap is an error)
        order = np.lexsort((a, p))
        p, a, ins = p[order], a[order], ins[order]
        got = np.zeros(n, bool)
        pin, ain = p[ins], a[ins]
        if levels is not None and len(pin):
            first = np.r_[True, pin[1:] != pin[:-1]]
            rep["overlap"] += int((~first).sum())
            pin, ain = pin[first], ain[first]
        out_p.append(pin)
        out_a.append(ain)
        got[pin] = True
        # on a border: the first of those areas only (R-61). Within a
        # declared level only if the point is inside none of the level;
        # without a level field always - inside a county and on the
        # border of two municipalities, it counts in the county AND in
        # the first municipality
        pb, ab = p[~ins], a[~ins]
        if levels is not None:
            keep = ~got[pb]
            pb, ab = pb[keep], ab[keep]
        if len(pb):
            first = np.r_[True, pb[1:] != pb[:-1]]
            shared = np.bincount(pb, minlength=n)[pb[first]] > 1
            rep["shared_border"] += int(shared.sum())
            out_p.append(pb[first])
            out_a.append(ab[first])
            got[pb[first]] = True
            on_border[pb[first]] = True
        # in no area of this level
        lost = np.nonzero(~got & good)[0]
        if not len(lost):
            continue
        if outside == "leave":
            rep["left_out"] += len(lost)
            continue
        best, d, ties = zones.nearest(x[lost], y[lost], among=in_level)
        ok = best >= 0
        if snap_within is not None:
            far = ok & (d > snap_within)
            rep["beyond"] += int(far.sum())
            ok &= ~far
        rep["left_out"] += int((~ok).sum())
        rep["snapped"] += int(ok.sum())
        rep["ties"] += int((ties[ok] > 1).sum())
        if ok.any():
            rep["snap_max"] = max(rep["snap_max"], float(d[ok].max()))
        out_p.append(lost[ok])
        out_a.append(best[ok])
    rep["border"] = int(on_border.sum())
    pairs = pd.DataFrame({
        "point": np.concatenate(out_p) if out_p else np.zeros(0, int),
        "area": np.concatenate(out_a) if out_a else np.zeros(0, int)})
    return pairs.sort_values(["point", "area"], kind="stable"), rep


# ------------------------------------------------------------------ R-62
def summarise(n_areas, pairs, points: pd.DataFrame, *, people=None,
              counts=(), values=(), stats=DEFAULT_STATS,
              min_people=0.0) -> pd.DataFrame:
    """One row per area (all of them, empty ones too): N people, Npts
    points, T_ and R_ for each count field, a column per statistic for
    each value field, and Hidden."""
    from ..wstats import weighted_stats
    w_all = (points[people].to_numpy(float) if people
             else np.ones(len(points)))
    rows = []
    by = {a: g["point"].to_numpy() for a, g in pairs.groupby("area")}
    cnt = {c: points[c].to_numpy(float) for c in counts}
    val = {v: points[v].to_numpy(float) for v in values}
    for j in range(n_areas):
        idx = by.get(j, np.zeros(0, int))
        w = w_all[idx]
        N = float(np.nansum(w))
        rec = {"N": N, "Npts": int(len(idx))}
        hidden = min_people > 0 and N < min_people
        for c in counts:
            t = float(np.nansum(cnt[c][idx]))
            rec[f"T_{c}"] = np.nan if hidden else t
            rec[f"R_{c}"] = (np.nan if hidden or not N > 0 else t / N)
        for v in values:
            x = val[v][idx]
            ok = np.isfinite(x) & np.isfinite(w) & (w > 0)
            res = (weighted_stats(stats, x[ok], w[ok]) if ok.any()
                   else {s: np.nan for s in stats})
            for s in stats:
                rec[f"{stat_prefix(s)}_{v}"] = (np.nan if hidden
                                                else res[s])
        rec["Hidden"] = int(hidden)
        rows.append(rec)
    return pd.DataFrame(rows)


def suffix_of(label) -> str:
    """A level's label as a column suffix: letters, digits and _."""
    s = re.sub(r"[^0-9A-Za-z]+", "_", str(label)).strip("_")
    return s or "level"


def on_points(n_points, pairs, table: pd.DataFrame, names, levels=None):
    """Each point with its area's name and results - one set of columns
    per level. Without a level field a point may only be in one area:
    the caller refuses first (overlapping()). A point in no area keeps
    empty columns."""
    cols = [c for c in table.columns if c != "Npts"]
    lev = (np.asarray(levels, dtype=object) if levels is not None
           else None)
    out = {}
    groups = (list(dict.fromkeys(lev.tolist())) if lev is not None
              else [None])
    for L in groups:
        sfx = "" if L is None else "_" + suffix_of(L)
        p = pairs
        if L is not None:
            p = pairs[np.isin(pairs["area"], np.nonzero(lev == L)[0])]
        area = np.full(n_points, -1)
        area[p["point"].to_numpy()] = p["area"].to_numpy()
        has = area >= 0
        name = np.full(n_points, None, dtype=object)
        name[has] = np.asarray(names, dtype=object)[area[has]]
        out["Area" + sfx] = name
        for c in cols:
            v = np.full(n_points, np.nan)
            v[has] = table[c].to_numpy(float)[area[has]]
            out[c + sfx] = v
    return pd.DataFrame(out)


def overlapping(pairs) -> int:
    """How many points count in more than one area."""
    return int((pairs.groupby("point").size() > 1).sum()) if len(
        pairs) else 0


def run(points: pd.DataFrame, x, y, zones, *, names=None, levels=None,
        people=None, counts=(), values=(), stats=DEFAULT_STATS,
        min_people=0.0, outside="nearest", snap_within=None,
        want_points=False, say=print):
    """Tool 1b from start to finish. Returns (areas table, points table
    or None, report)."""
    n_areas = len(zones)
    if n_areas == 0:
        raise BadNumber("The areas layer has no areas.")
    if len(points) == 0:
        raise BadNumber("The points layer has no points.")
    if people:
        w = points[people].to_numpy(float)
        if (w[np.isfinite(w)] < 0).any():
            raise BadNumber(f'The people field "{people}" holds negative '
                            "numbers; people per point are 0 or more.")
    for f in list(counts) + list(values):
        if f not in points:
            raise BadNumber(f'"{f}" is not a field of the points.')
    if zones.empty:
        say(f"[areas] {len(zones.empty):,} area(s) have no geometry; "
            "they are kept, with nobody in them")
    names = (list(names) if names is not None
             else [str(j + 1) for j in range(n_areas)])
    pairs, rep = belong(zones, np.asarray(x, float), np.asarray(y, float),
                        levels, outside, snap_within)
    table = summarise(n_areas, pairs, points, people=people,
                      counts=counts, values=values, stats=stats,
                      min_people=min_people)
    _say(rep, table, min_people, outside, snap_within, levels, say)
    pts = None
    if want_points:
        if levels is None and overlapping(pairs):
            raise BadNumber(
                f"{overlapping(pairs):,} points lie in more than one area "
                "- the areas overlap - so a point cannot hold its area's "
                "results in one set of columns. Give a level field (such "
                "as municipality or county) and the points get one set "
                "per level; the areas' own results do not need one.")
        pts = on_points(len(points), pairs, table, names, levels)
    return table, pts, rep


def _say(rep, table, min_people, outside, snap_within, levels, say):
    n = rep["points"]
    lev = (f" in {len(rep['levels'])} levels" if rep["levels"] else "")
    say(f"[areas] {n:,} points, {len(table):,} areas{lev}; "
        f"{table.N.sum():,.6g} people counted in them")
    if rep["no_xy"]:
        say(f"[areas] {rep['no_xy']:,} points have no coordinates and "
            "count in no area")
    if rep["border"]:
        say(f"[areas] {rep['border']:,} points lie exactly on a border "
            "(within a few millimetres); each counts in the FIRST of the "
            "areas it touches, once (R-61)")
        if rep["border"] > BORDER_WARN * n:
            say("[areas] NOTE: that is many. Are the points the CORNERS "
                "of grid cells rather than their centres? Corners sit on "
                "the borders of areas built from the same grid.")
    if rep["overlap"]:
        say(f"[areas] {rep['overlap']:,} times a point lay inside two "
            "areas of the same level - the areas overlap where they "
            "should not; it counted in the first. Check the layer.")
    if rep["snapped"]:
        say(f"[areas] {rep['snapped']:,} points in no area were given to "
            f"the nearest one (the farthest {rep['snap_max']:,.0f} m away)"
            + (f"; {rep['ties']:,} were as near to two, and went to the "
               "first" if rep["ties"] else ""))
    if rep["beyond"]:
        say(f"[areas] {rep['beyond']:,} points were farther than "
            f"{snap_within:,.0f} m from every area and were left out")
    if rep["left_out"] and outside == "leave":
        say(f"[areas] {rep['left_out']:,} points lie in no area and were "
            "left out, as chosen")
    empty = int((table.Npts == 0).sum())
    if empty:
        say(f"[areas] {empty:,} areas hold no points; they are kept, with "
            "N = 0")
    hid = int(table.Hidden.sum())
    if hid:
        say(f"[areas] {hid:,} areas have fewer than {min_people:,.6g} "
            "people: their statistics are hidden (Hidden = 1); N stays")
    if min_people > 0:
        say("[areas] Why EquiPop helps here: an area can hold three "
            "people; an EquiPop neighbourhood of k people always holds k. "
            f"With k of {min_people:,.6g} or more (tool 1 or 2), no value "
            "rests on fewer people, so nothing needs hiding. Overlapping "
            "neighbourhoods can still differ by a few people, so this "
            "reduces the risk of disclosure; it does not remove it.")


def describe(counts=(), values=(), stats=DEFAULT_STATS,
             levels=None) -> dict:
    """What each new column holds, for the messages and the help - the
    areas' columns, and the points' (one set per level)."""
    d = {"N": "people in the area (points, if no people field)",
         "Npts": "points in the area",
         "Hidden": "1 where the area has fewer people than the threshold "
                   "and its statistics are hidden",
         "Area": "the name of the area the point counts in"}
    for c in counts:
        d[f"T_{c}"] = f"the sum of {c} over the area's points"
        d[f"R_{c}"] = f"{c} as a share of the area's people"
    words = dict(STAT_LABELS)
    for v in values:
        for s in stats:
            d[f"{stat_prefix(s)}_{v}"] = (f"{words.get(s, s).lower()} of "
                                          f"{v}, per person")
    if levels is not None:
        base = dict(d)
        for L in dict.fromkeys(list(levels)):
            for k, text in base.items():
                d[f"{k}_{suffix_of(L)}"] = f"{text} ({L})"
    return d

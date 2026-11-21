"""
pixelsdoor.py - the shared half of tool 3b, "Pixels as mass: green
reach and share" (BACKLOG 508, the chain since BACKLOG 510).

The board's first target is image analysis; John, 19 November 2026:
doors to QGIS and Pro, in the EXISTING plugin and toolbox, with the
shared core in Python. equipop/pixels.py is that core (BACKLOG 507).
This module is what both GIS doors call, so that they stay THIN: a door
reads the people layer's coordinates and the raster's bands, checks the
two coordinate systems with its own GIS, and hands the typed boxes to
run(). Every decision about a number is made here or in
equipop/pixels.py and equipop/bandmath.py, once.

THE CHAIN (agreed with John on 21 November 2026, ruling R-53):

    bands -> value -> base and treatment -> hectares -> analysis cell
          -> k-nearest: Dist_k, T_k, R_k

The boxes, as a person types them:
    Value               1                    a band, as it is
                        (b8 - b4) / (b8 + b4) a formula over bands
                        ndvi(8, 4)           a named index
    Base (optional)     0,01 to 1            which pixels the k hectares
                        10 20                are counted from; empty =
                                             every pixel with a value
    Treatment (opt.)    0,7 to 1             which of those are looked
                                             for: gives T_k and R_k
    Hectares to gather  1 5 20               k, in hectares
    Radius (optional)   300                  metres: B_r, T_r, R_r
    Analysis cell (opt) 50                   metres; empty = the pixel

The raster arrives either as a file path (Python, the runner scripts)
or as a PAYLOAD the door read with its own GIS:

    {"bands": {8: a8, 4: a4}, "x_min": west, "y_max": north,
     "cell_w": w, "cell_h": h, "nodata": nd or {8: nd8, 4: nd4},
     "geographic": False}

(1.65.0's "array" key - one band, or all of them as a stack - is still
read.) The package never opens a GIS file inside Pro or QGIS (BACKLOG
509); bands_needed() tells a door which bands to read.
"""

from __future__ import annotations

import pandas as pd

from .numbers import BadNumber, is_blank, numlist, to_float

__all__ = ["parse_value", "parse_range", "parse_pixels", "parse_hectares",
           "parse_radius", "parse_cell", "bands_needed", "run",
           "result_names"]


def parse_value(text):
    """The value box -> a bandmath.Formula ('' is band 1)."""
    from ..bandmath import FormulaError, parse
    try:
        return parse(text)
    except FormulaError as e:
        raise BadNumber(str(e))


def bands_needed(value_text) -> tuple:
    """The band numbers a door must read for this value box."""
    return parse_value(value_text).bands


def parse_range(text, box="base", required=False):
    """'10 20' -> {'classes': [10, 20]}; '0,4 to 1' -> {'between':
    (0.4, 1.0)}; '' -> None (unless required). A decimal comma works,
    as in every EquiPop box."""
    t = str(text or "").strip()
    if is_blank(t):
        if required:
            raise BadNumber(
                "Which pixels count? Give land-cover class codes, such "
                "as 10 20, or a range of values, such as 0,4 to 1.")
        return None
    low = t.lower()
    if " to " in low:
        a, b = low.split(" to ", 1)
        lo, hi = to_float(a), to_float(b)
        if lo is None or hi is None:
            raise BadNumber(f"{box.capitalize()} '{t}': a range needs a "
                            "number on each side of 'to', such as "
                            "0,4 to 1.")
        if lo > hi:
            raise BadNumber(f"{box.capitalize()} '{t}': the first "
                            "number of a range must be the smaller one.")
        return {"between": (lo, hi)}
    vals = numlist(t)
    if not vals:
        raise BadNumber(f"{box.capitalize()} '{t}' holds no class codes. "
                        "Write them with spaces between, such as 10 20, "
                        "or a range with 'to', such as 0,4 to 1.")
    if any(v != int(v) for v in vals):
        raise BadNumber(
            f"{box.capitalize()} '{t}': class codes are whole numbers. "
            "For a range of values, write it with 'to', such as 0,4 to 1.")
    return {"classes": [int(v) for v in vals]}


def parse_pixels(text) -> dict:
    """1.65.0's 'which pixels count' box: a base that must be given."""
    return parse_range(text, "which pixels count", required=True)


def parse_hectares(text) -> list[float]:
    """'1 5 20' -> [1.0, 5.0, 20.0]; every k above 0; '' -> []."""
    ks = numlist(text)
    if not ks:
        if is_blank(text):
            return []
        raise BadNumber("Hectares to gather: give one or more, such as "
                        "1 5 20.")
    if min(ks) <= 0:
        raise BadNumber("Hectares to gather must all be above 0.")
    return sorted(set(ks))


def parse_radius(text):
    """'' -> None; '300' -> 300.0; refuses 0 and below."""
    if is_blank(text):
        return None
    r = to_float(text)
    if r is None or not r > 0:
        raise BadNumber("The radius must be one number above 0 metres, "
                        "such as 300, or left empty.")
    return float(r)


def parse_cell(text):
    """'' -> None (the image's own pixel); '50' -> 50.0 metres."""
    if is_blank(text):
        return None
    c = to_float(text)
    if c is None or not c > 0:
        raise BadNumber("The analysis cell must be one number above 0 "
                        "metres, such as 50, or left empty to use the "
                        "image's own pixel.")
    return float(c)


def _tag(k):
    """5 -> '5', 2.5 -> '2_5': a field name holds no '.' in a
    geodatabase, so the columns read Dist_2_5 for 2.5 ha."""
    from ..labels import numeric_tag
    return numeric_tag(k)


def result_names(hectares_text, radius_text="", treatment_text="") \
        -> list[str]:
    """The columns run() will add, in order - so a door can check its
    output (a shapefile's ten characters) before anything runs."""
    treat = parse_range(treatment_text, "treatment") is not None
    names = []
    for k in parse_hectares(hectares_text):
        names.append(f"Dist_{_tag(k)}")
        if treat:
            names += [f"T_{_tag(k)}", f"R_{_tag(k)}"]
    r = parse_radius(radius_text)
    if r is not None:
        names.append(f"B_r{_tag(r)}")
        if treat:
            names += [f"T_r{_tag(r)}", f"R_r{_tag(r)}"]
    return names


def _bands(raster, formula):
    """{band: float32 array, nodata as NaN} for the formula's bands, and
    where the grid lies."""
    import numpy as np
    want = formula.bands
    if isinstance(raster, dict):
        meta = {k: raster[k] for k in ("x_min", "y_max", "cell_w",
                                       "cell_h")}
        meta["geographic"] = bool(raster.get("geographic"))
        nd = raster.get("nodata")
        got = {}
        if "bands" in raster:
            have = raster["bands"]
            for b in want:
                if b not in have:
                    raise BadNumber(f"Band {b} was not read from the "
                                    "raster.")
                got[b] = have[b]
        else:                           # 1.65.0's payload
            a = np.asarray(raster["array"])
            n = a.shape[0] if a.ndim == 3 else 1
            for b in want:
                if b > n:
                    raise BadNumber(
                        f"The raster has {n} band{'s' if n > 1 else ''}; "
                        f"band {b} does not exist.")
                got[b] = a[b - 1] if a.ndim == 3 else a
        nds = {b: (nd.get(b) if isinstance(nd, dict) else nd)
               for b in want}
    else:
        from ..pixels import _need_rasterio
        rasterio = _need_rasterio()
        with rasterio.open(raster) as src:
            T = src.transform
            if T.b or T.d:
                raise BadNumber(f"{raster} is a rotated raster; warp it "
                                "to a north-up grid first.")
            for b in want:
                if b > src.count:
                    raise BadNumber(
                        f"The raster has {src.count} band"
                        f"{'s' if src.count > 1 else ''}; band {b} does "
                        "not exist.")
            got = {b: src.read(b) for b in want}
            nds = {b: src.nodatavals[b - 1] for b in want}
            meta = {"x_min": T.c, "y_max": T.f, "cell_w": T.a,
                    "cell_h": -T.e,
                    "geographic": bool(src.crs and src.crs.is_geographic)}
    out = {}
    for b, a in got.items():
        a = np.array(a, np.float32)            # a copy: NaN goes in
        if a.ndim != 2:
            raise BadNumber(f"Band {b} is not a single band.")
        v = nds.get(b)
        if v is not None and not (isinstance(v, float) and np.isnan(v)):
            a[a == np.float32(v)] = np.nan
        out[b] = a
    shapes = {a.shape for a in out.values()}
    if len(shapes) > 1:
        raise BadNumber("The bands are not on one grid. All bands of a "
                        "formula must come from one raster with one "
                        "pixel size.")
    return out, meta


def run(people: pd.DataFrame, raster, *, value="", base="", treatment="",
        hectares="", radius="", cell="", layer_is_metric: bool = True,
        same_crs: bool = True, say=print) -> pd.DataFrame:
    """For each row of `people` (x, y): the chain, as the module's top
    says. Rows without coordinates (an empty geometry) get empty
    results; the others are computed as if they were alone.

    layer_is_metric and same_crs are the door's own reading of its two
    layers: the distances are in the layer's units, so they must be
    metres, and the pixels are placed in the raster's coordinates, so
    the two must agree. Both are refused with a sentence that says what
    to do, never computed wrongly.

    Returns x, y and per k Dist_<k> (metres to gather k hectares of
    base; EMPTY where the raster holds less than k), with a treatment
    also T_<k> (its hectares among them) and R_<k> (T_<k> / k); with a
    radius B_r<r> (base hectares within r), and with a treatment
    T_r<r> and R_r<r> (T / B). A decimal is written with '_' for '.'.
    """
    import numpy as np

    from ..bandmath import evaluate
    from ..pixels import mass_from_values, reach
    if not layer_is_metric:
        raise BadNumber(
            "The people layer is not in metres (it is in degrees, or "
            "in feet). Distances and hectares need metres: save the "
            "layer in a projected coordinate system in metres (UTM, "
            "SWEREF99 TM, ETRS89 LAEA...), put the raster in the same "
            "one, and run again.")
    if not same_crs:
        raise BadNumber(
            "The raster and the people layer are in different "
            "coordinate systems. Project the raster to the layer's "
            "system first (QGIS: Raster > Projections > Warp; Pro: "
            "Project Raster), then run again.")
    formula = parse_value(value)
    base_spec = parse_range(base, "base")
    treat_spec = parse_range(treatment, "treatment")
    ks = parse_hectares(hectares)
    r = parse_radius(radius)
    if not ks and r is None:
        raise BadNumber("Give hectares to gather (such as 1 5 20), a "
                        "radius, or both.")
    cell_m = parse_cell(cell)
    bands, meta = _bands(raster, formula)
    v = evaluate(formula, bands)
    say(f"[pixels] value: {formula.text}"
        + ("" if formula.single_band else
           f" (bands {', '.join(map(str, formula.bands))})")
        + f", {v.shape[0]:,} x {v.shape[1]:,} pixels of "
          f"{abs(meta['cell_w']):g} x {abs(meta['cell_h']):g}; "
          f"{int(np.isfinite(v).sum()):,} with a value")
    try:
        mass = mass_from_values(
            v, meta["x_min"], meta["y_max"], meta["cell_w"],
            meta["cell_h"], geographic=meta["geographic"],
            base=base_spec, treatment=treat_spec, cell=cell_m)
    except ValueError as e:
        raise BadNumber(str(e))
    if mass.empty:
        raise BadNumber(
            "No pixel is in the base. Check the base"
            + (" and the value" if not formula.single_band else "")
            + " against the raster: Identify a few pixels to see their "
              "values.")
    say(f"[pixels] base: {mass.ha.sum():,.1f} ha"
        + (f" in {len(mass):,} analysis cells of {cell_m:g} m"
           if cell_m else "")
        + (f"; treatment: {mass.t_ha.sum():,.1f} ha of it"
           if treat_spec is not None else ""))
    if treat_spec is not None and not mass.t_ha.sum() > 0:
        say("[pixels] NOTE: no base pixel is in the treatment, so every "
            "T_ and R_ is 0. Check that the treatment lies inside the "
            "base.")
    x = people["x"].to_numpy(float)
    y = people["y"].to_numpy(float)
    have = np.isfinite(x) & np.isfinite(y)
    if not have.any():
        raise BadNumber("None of the people has coordinates.")
    if not have.all():
        say(f"[pixels] {int((~have).sum()):,} row(s) have no "
            "coordinates (empty geometry) and get empty results.")
    here = pd.DataFrame({"x": x[have], "y": y[have]})
    part = reach(here, mass, ks, r_values=[r] if r else [],
                 treat_col="t_ha" if treat_spec is not None else None)
    total = mass.ha.sum()
    for k in ks:
        short = int(part[f"Dist_{_tag(k)}"].isna().sum())
        if short:
            say(f"[pixels] NOTE: the raster holds {total:,.1f} ha of "
                f"base in all, less than {k:g}; Dist_{_tag(k)} is empty "
                f"for {short:,} place(s).")
    res = pd.DataFrame({"x": x, "y": y})
    for c in part.columns:
        if c in ("x", "y"):
            continue
        col = np.full(len(x), np.nan)
        col[have] = part[c].to_numpy(float)
        res[c] = col
    return res

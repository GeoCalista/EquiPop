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
    Rasters             one, or as many as a formula needs. A formula
                        names each by its LAYER NAME in quotes, as
                        Raster Calculator does - no list order to read
                        two ways, and no limit (John, 22 November 2026)
    Pixel value         (empty)              the one raster, as it is
                        ndvi("nir", "red")   a named index
                        ("nir" - "red") / ("nir" + "red")
                        ndvi("S2"[8], "S2"[4])  bands of a stack
    Base (optional)     0,01 to 1            which pixels the k hectares
                        10 20                are counted from; empty =
                                             every pixel with a value
    Treatment (opt.)    0,7 to 1             which of those are looked
                                             for: gives T_k and R_k
    Hectares to gather  1 5 20               k, in hectares
    Radius (optional)   100 200              metres: B_r, T_r, R_r
    Analysis cell (opt) 50                   metres; empty = the pixel

Each raster arrives either as a file path (Python, the runner scripts)
or as a PAYLOAD the door read with its own GIS:

    {"bands": {1: a1}, "x_min": west, "y_max": north, "cell_w": w,
     "cell_h": h, "nodata": nd or {1: nd1}, "geographic": False,
     "count": bands in the raster, "source": "its file, for the log"}

(1.65.0's "array" key - one band, or all of them as a stack - is still
read.) The rasters must share one pixel size and lie on one grid; where
their extents differ only the overlap is used. The package never opens
a GIS file inside Pro or QGIS (BACKLOG 509); bands_needed() tells a door
which bands of which raster to read.
"""

from __future__ import annotations

import re

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


def bands_needed(value_text, names) -> dict:
    """{raster name: (band numbers)} a door must read for this value
    box, the names being its rasters' (layer names): 'ndvi("nir",
    "red")' -> {'nir': (1,), 'red': (1,)}. Refuses a name that is not
    there, or a formula that names none when there are several."""
    f = parse_value(value_text)
    found = {}
    for ref in f.rasters:
        name = _resolve(ref, list(names))
        found.setdefault(name, set()).update(f.bands(ref))
    return {n: tuple(sorted(b)) for n, b in found.items()}


#: endings a raster's file can have, which a formula may leave out
_ENDINGS = (".tif", ".tiff", ".jp2", ".img", ".vrt", ".asc", ".nc",
            ".hdf", ".dem", ".bil", ".grd", ".sdat", ".png", ".jpg")


def _bare(name):
    """A name in lower case, without the ending of a raster file."""
    n = str(name).strip().lower()
    for e in _ENDINGS:
        if n.endswith(e) and len(n) > len(e):
            return n[: -len(e)]
    return n


def unused(value_text, names) -> list:
    """The rasters given that the formula does not name - a door says
    so, and does not read them."""
    try:
        want = bands_needed(value_text, names)
    except BadNumber:
        return []
    return [n for n in names if n not in want]


def _resolve(ref, names):
    """A formula's raster -> the name of one of the rasters given."""
    from ..bandmath import ONLY
    if len(set(names)) != len(names):
        dup = sorted({n for n in names if names.count(n) > 1})
        raise BadNumber(f"Two rasters are both called {dup[0]!r}. Rename "
                        "one of the layers, so a formula can tell them "
                        "apart.")
    if ref is ONLY:
        if len(names) == 1:
            return names[0]
        raise BadNumber(
            f"There are {len(names)} rasters, so the pixel value must "
            "name the one it means, in quotes: "
            + ", ".join(f'"{n}"' for n in names) + ".")
    if ref in names:
        return ref
    # Pro names a layer by its file, extension and all ("B04.tif");
    # QGIS without ("B04"). Either spelling finds either, whatever the
    # case, so one formula runs at both doors.
    for key in (str.lower, _bare):
        same = [n for n in names if key(n) == key(ref)]
        if len(same) == 1:
            return same[0]
        if len(same) > 1:
            raise BadNumber(
                f'"{ref}" could be any of '
                + ", ".join(f'"{n}"' for n in same)
                + ". Write the name exactly as the layer is called.")
    raise BadNumber(
        f'The pixel value names "{ref}", but no raster is called that. '
        "The rasters are: " + ", ".join(f'"{n}"' for n in names)
        + ". (A raster is named by its layer name; rename a layer to "
          "something short to type less.)")


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


def parse_radius(text) -> list[float]:
    """'' -> []; '300' -> [300.0]; '100 200' -> [100.0, 200.0].

    SEVERAL RADII, like the hectares box - never one number with a
    space for thousands. John, 22 November 2026, typed '100 200' and the
    box read 100,200 m: a 100 km circle round each of 9,185 points on
    Malta, hours of work for a number nobody asked for."""
    if is_blank(text):
        return []
    rs = numlist(text)
    if not rs or min(rs) <= 0:
        raise BadNumber("A radius is in metres and above 0: one or more "
                        "with spaces between, such as 100 200, or left "
                        "empty.")
    return sorted(set(float(r) for r in rs))


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
    for r in parse_radius(radius_text):
        names.append(f"B_r{_tag(r)}")
        if treat:
            names += [f"T_r{_tag(r)}", f"R_r{_tag(r)}"]
    return names


def _name_of(raster):
    """A raster's name when none was given: the payload's, or the
    file's name without its extension."""
    import os
    if isinstance(raster, dict):
        return str(raster.get("name") or "raster")
    return os.path.splitext(os.path.basename(str(raster)))[0]


def _read_one(raster, want, name):
    """One raster's bands `want` -> ({band: float32 array, nodata as
    NaN}, meta)."""
    import os

    import numpy as np
    label = f'"{name}"'
    if isinstance(raster, dict):
        meta = {k: raster[k] for k in ("x_min", "y_max", "cell_w",
                                       "cell_h")}
        meta["geographic"] = bool(raster.get("geographic"))
        meta["source"] = str(raster.get("source") or name)
        nd = raster.get("nodata")
        got = {}
        if "bands" in raster:
            have = raster["bands"]
            meta["count"] = raster.get("count", max(have) if have else 0)
            for b in want:
                if b not in have:
                    raise BadNumber(f"Band {b} of {label} was not read.")
                got[b] = have[b]
        else:                           # 1.65.0's payload
            a = np.asarray(raster["array"])
            n = a.shape[0] if a.ndim == 3 else 1
            meta["count"] = n
            for b in want:
                if b > n:
                    raise BadNumber(
                        f"{label} has {n} band{'s' if n > 1 else ''}; "
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
                raise BadNumber(f"{label} is rotated; warp it to a "
                                "north-up grid first.")
            for b in want:
                if b > src.count:
                    raise BadNumber(
                        f"{label} has {src.count} band"
                        f"{'s' if src.count > 1 else ''}; band {b} does "
                        "not exist.")
            got = {b: src.read(b) for b in want}
            nds = {b: src.nodatavals[b - 1] for b in want}
            meta = {"x_min": T.c, "y_max": T.f, "cell_w": T.a,
                    "cell_h": -T.e, "count": src.count,
                    "geographic": bool(src.crs and src.crs.is_geographic),
                    "source": os.path.basename(str(raster))}
    out = {}
    for b, a in got.items():
        a = np.array(a, np.float32)            # a copy: NaN goes in
        if a.ndim != 2:
            raise BadNumber(f"Band {b} of {label} is not a single band.")
        v = nds.get(b)
        if v is not None and not (isinstance(v, float) and np.isnan(v)):
            a[a == np.float32(v)] = np.nan
        out[b] = a
    shapes = {a.shape for a in out.values()}
    if len(shapes) > 1:                         # pragma: no cover
        raise BadNumber(f"The bands of {label} differ in size.")
    meta["shape"] = shapes.pop()
    return out, meta


def _named(rasters, raster=None):
    """The rasters as [(name, source)], from a dict {name: source}, a
    list of pairs, or a single raster."""
    pairs = []
    if isinstance(rasters, dict):
        pairs = list(rasters.items())
    elif rasters:
        pairs = [tuple(p) for p in rasters]
    if raster is not None:
        pairs.append((_name_of(raster), raster))
    if not pairs:
        raise BadNumber("Choose a raster.")
    return pairs


def _bands(rasters, formula, say=print):
    """{formula ref: array} for every raster and band the formula reads,
    cut to the rasters' common overlap, and where that lies. `rasters`
    is [(name, source)]."""
    names = [n for n, _ in rasters]
    sources = dict(rasters)
    which = {ref: _resolve(ref, names) for ref in formula.rasters}
    want = {}
    for ref, name in which.items():
        want.setdefault(name, set()).update(formula.bands(ref))
    read = {name: _read_one(sources[name], tuple(sorted(b)), name)
            for name, b in want.items()}
    first = next(iter(read))
    ref_meta = read[first][1]
    w, h = abs(float(ref_meta["cell_w"])), abs(float(ref_meta["cell_h"]))
    spans = {}
    for name, (_, m) in read.items():
        mw, mh = abs(float(m["cell_w"])), abs(float(m["cell_h"]))
        if abs(mw - w) > 1e-6 * w or abs(mh - h) > 1e-6 * h:
            raise BadNumber(
                f'"{name}" has {mw:g} x {mh:g} pixels and "{first}" '
                f"{w:g} x {h:g}. A formula needs one pixel size: resample "
                "one of them first (Sentinel-2's B11 and B12 are 20 m - "
                "resample them to 10 m), since EquiPop never resamples "
                "behind your back.")
        if m["geographic"] != ref_meta["geographic"]:
            raise BadNumber(f'"{name}" and "{first}" are in different '
                            "coordinate systems.")
        dc = (float(m["x_min"]) - float(ref_meta["x_min"])) / w
        dr = (float(ref_meta["y_max"]) - float(m["y_max"])) / h
        if abs(dc - round(dc)) > 1e-3 or abs(dr - round(dr)) > 1e-3:
            raise BadNumber(
                f'"{name}" is not on the grid of "{first}": its pixels '
                "are shifted by part of a pixel. Snap one to the other "
                "first (Pro: Environments > Snap Raster; QGIS: Align "
                "Rasters).")
        r0, c0 = int(round(dr)), int(round(dc))
        spans[name] = (r0, c0, r0 + m["shape"][0], c0 + m["shape"][1])
    r_lo = max(v[0] for v in spans.values())
    c_lo = max(v[1] for v in spans.values())
    r_hi = min(v[2] for v in spans.values())
    c_hi = min(v[3] for v in spans.values())
    if r_lo >= r_hi or c_lo >= c_hi:
        raise BadNumber("The rasters do not overlap.")
    cut = {}
    for name, (bands, m) in read.items():
        r0, c0 = spans[name][:2]
        for b, a in bands.items():
            cut[(name, b)] = a[r_lo - r0:r_hi - r0, c_lo - c0:c_hi - c0]
        n = m.get("count", len(bands))
        say(f'[pixels] "{name}" = {m["source"]}: {n} band'
            f"{'s' if n != 1 else ''}, {w:g} m pixels, "
            f"{m['shape'][0]:,} x {m['shape'][1]:,}")
    if len(read) > 1 and any(
            (v[2] - v[0], v[3] - v[1]) != (r_hi - r_lo, c_hi - c_lo)
            for v in spans.values()):
        say(f"[pixels] the rasters overlap in {r_hi - r_lo:,} x "
            f"{c_hi - c_lo:,} pixels; only the overlap is used")
    out = {(ref, b): cut[(name, b)] for ref, name in which.items()
           for b in formula.bands(ref)}
    meta = {"x_min": float(ref_meta["x_min"]) + c_lo * w,
            "y_max": float(ref_meta["y_max"]) - r_lo * h,
            "cell_w": w, "cell_h": h,
            "geographic": ref_meta["geographic"],
            "which": which,
            "sources": {k: m["source"] for k, (_, m) in read.items()}}
    return out, meta


#: Sentinel-2's band codes in a file name, and the codes each role of a
#: named index expects. A warning only: names can be anything.
_S2 = re.compile(r"(?<![A-Za-z0-9])B(0[1-9]|1[0-2]|8A)(?![0-9A-Za-z])")
_S2_ROLE = {"nir": {"08", "8A"}, "red": {"04"}, "green": {"03"},
            "swir": {"11", "12"}}


def _say_roles(formula, meta, say):
    """The run log's line per named index - which raster plays which
    part - and a warning when a Sentinel-2 band code in a raster's name
    or file does not fit its part."""
    from ..bandmath import roles
    for name, parts in roles(formula):
        words = []
        for role, (ref, band) in parts:
            raster = meta["which"][ref]
            shown = f'"{raster}"' + (f"[{band}]" if band != 1 else "")
            words.append(f"{role} = {shown}")
            if band == 1:
                text = f"{raster} {meta['sources'].get(raster, '')}"
                found = set(_S2.findall(text))
                if len(found) == 1 and not found & _S2_ROLE[role]:
                    say(f"[pixels] WARNING: {name}() takes {shown} as "
                        f"{role}, but its name says Sentinel-2 band "
                        f"B{found.pop()}, which is not {role}. Are two "
                        "rasters swapped?")
        say(f"[pixels] {name}: " + ", ".join(words))


def run(people: pd.DataFrame, raster=None, *, rasters=None, value="",
        base="", treatment="", hectares="", radius="", cell="",
        layer_is_metric: bool = True, same_crs: bool = True,
        say=print) -> pd.DataFrame:
    """For each row of `people` (x, y): the chain, as the module's top
    says. Rows without coordinates (an empty geometry) get empty
    results; the others are computed as if they were alone.

    `raster` is one raster; `rasters` = {name: raster} (or a list of
    (name, raster) pairs) gives any number, named for the formula. layer_is_metric and same_crs are the door's own
    reading of its layers (same_crs: EVERY raster in the people's
    system): the distances are in the layer's units, so they must be
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
    rs = parse_radius(radius)
    if not ks and not rs:
        raise BadNumber("Give hectares to gather (such as 1 5 20), a "
                        "radius, or both.")
    cell_m = parse_cell(cell)
    pairs = _named(rasters, raster)
    bands, meta = _bands(pairs, formula, say)
    _say_roles(formula, meta, say)
    v = evaluate(formula, bands)
    say(f"[pixels] value: {formula.text or 'the raster as it is'}, "
        f"{v.shape[0]:,} x "
        f"{v.shape[1]:,} pixels of {abs(meta['cell_w']):g} x "
        f"{abs(meta['cell_h']):g}; {int(np.isfinite(v).sum()):,} with a "
        "value")
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
            + (" and the pixel value" if formula.text else "")
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
    part = reach(here, mass, ks, r_values=rs,
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

"""
pixelsdoor.py - the shared half of tool 3b, "Pixels as mass: green
reach and share" (BACKLOG 508).

The board's first target is image analysis; John, 19 November 2026:
doors to QGIS and Pro, in the EXISTING plugin and toolbox, with the
shared core in Python. equipop/pixels.py is that core (BACKLOG 507).
This module is what both GIS doors call, so that they stay THIN: a door
reads the people layer's coordinates and the raster's file, checks the
two coordinate systems with its own GIS, and hands the three typed
boxes to run(). Every decision about a number is made here or in
equipop/pixels.py, once.

The raster arrives either as a file path (Python, the runner scripts)
or as a PAYLOAD the door read with its own GIS - a dict with the band
as an array and where it lies:

    {"array": a, "x_min": west, "y_max": north, "cell_w": w,
     "cell_h": h, "nodata": nd, "geographic": False}

the same keys Pro's elevation raster has used since BACKLOG 313. The
package never opens a GIS file inside Pro or QGIS (BACKLOG 509).

The boxes, as a person types them:
    Band                 1              which band of the raster
    Which pixels count   "10 20"        land-cover class codes
                         "0,4 to 1"     a range of an index (NDVI...)
    Hectares to gather   "1 5 20"       k, in hectares
    Radius (optional)    "300"          metres; adds the hectares
                                        within it and their share
"""

from __future__ import annotations

import pandas as pd

from .numbers import BadNumber, is_blank, numlist, to_float

__all__ = ["parse_pixels", "parse_hectares", "parse_radius", "run",
           "result_names"]


def parse_pixels(text) -> dict:
    """'10 20' -> {'classes': [10, 20]}; '0,4 to 1' -> {'between':
    (0.4, 1.0)}. A decimal comma works, as in every EquiPop box."""
    t = str(text or "").strip()
    if is_blank(t):
        raise BadNumber(
            "Which pixels count? Give land-cover class codes, such as "
            "10 20, or a range of an index, such as 0,4 to 1 for NDVI.")
    low = t.lower()
    if " to " in low:
        a, b = low.split(" to ", 1)
        lo, hi = to_float(a), to_float(b)
        if lo is None or hi is None:
            raise BadNumber(f"'{t}': a range needs a number on each "
                            "side of 'to', such as 0,4 to 1.")
        if lo > hi:
            raise BadNumber(f"'{t}': the first number of a range must "
                            "be the smaller one.")
        return {"between": (lo, hi)}
    vals = numlist(t)
    if not vals:
        raise BadNumber(f"'{t}' holds no class codes. Write them with "
                        "spaces between, such as 10 20.")
    if any(v != int(v) for v in vals):
        raise BadNumber(
            f"'{t}': class codes are whole numbers. For a range of an "
            "index, write it with 'to', such as 0,4 to 1.")
    return {"classes": [int(v) for v in vals]}


def parse_hectares(text) -> list[float]:
    """'1 5 20' -> [1.0, 5.0, 20.0]; every k above 0."""
    ks = numlist(text)
    if not ks:
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


def _tag(k):
    """5 -> '5', 2.5 -> '2_5': a field name holds no '.' in a
    geodatabase, so the doors' columns read Dist_2_5 for 2.5 ha."""
    k = int(k) if float(k).is_integer() else k
    return str(k).replace(".", "_")


def result_names(hectares_text, radius_text="") -> list[str]:
    """The columns run() will add, in order - so a door can check its
    output (a shapefile's ten characters) before anything runs."""
    names = []
    for k in parse_hectares(hectares_text):
        names += [f"Dist_{_tag(k)}", f"Got_{_tag(k)}"]
    r = parse_radius(radius_text)
    if r is not None:
        t = f"{r:g}".replace(".", "_")
        names += [f"Mass_r{t}", f"Share_r{t}"]
    return names


def _mass(raster, spec, band):
    from ..pixels import pixels_from_array, pixels_to_mass
    if isinstance(raster, dict):
        a = raster["array"]
        if getattr(a, "ndim", 2) == 3:
            if not 1 <= band <= a.shape[0]:
                raise BadNumber(f"The raster has {a.shape[0]} bands; "
                                f"band {band} does not exist.")
            a = a[band - 1]
        elif band != 1:
            raise BadNumber(f"The raster has one band; band {band} "
                            "does not exist.")
        return pixels_from_array(
            a, raster["x_min"], raster["y_max"], raster["cell_w"],
            raster["cell_h"], nodata=raster.get("nodata"),
            geographic=bool(raster.get("geographic")), **spec)
    try:
        return pixels_to_mass(raster, band=band, **spec)
    except ValueError as e:
        raise BadNumber(str(e))


def run(people: pd.DataFrame, raster_path, pixels_text, hectares_text,
        radius_text="", *, band=1, unit_size: float = 100.0,
        layer_is_metric: bool = True, same_crs: bool = True,
        say=print) -> pd.DataFrame:
    """Green reach (and share) for each row of `people` (x, y).

    raster_path is a file path or a payload the door read (see the
    top of this module). Rows without coordinates (an empty geometry)
    get empty results; the others are computed as if they were alone.

    layer_is_metric and same_crs are the door's own reading of its two
    layers: the distances are in the layer's units, so they must be
    metres, and the pixels are placed in the raster's coordinates, so
    the two must agree. Both are refused with a sentence that says what
    to do, never computed wrongly.

    Returns one row per person: Dist_<k> (metres to gather k hectares)
    and Got_<k> (hectares gathered: below k when the raster holds less),
    plus Mass_r<r> and Share_r<r> when a radius is given. A decimal
    k or r is written with '_' for '.': Dist_2_5 is 2.5 ha.
    """
    import numpy as np

    from ..pixels import reach, share_within
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
    spec = parse_pixels(pixels_text)
    ks = parse_hectares(hectares_text)
    radius = parse_radius(radius_text)
    b = band if isinstance(band, int) else to_float(band)
    band = 1 if b is None else int(b)
    if band < 1:
        raise BadNumber("The band is counted from 1.")
    mass = _mass(raster_path, spec, band)
    if mass.empty:
        what = (f"class {' '.join(map(str, spec['classes']))}"
                if "classes" in spec else
                f"values {spec['between'][0]:g} to {spec['between'][1]:g}")
        raise BadNumber(f"No pixel of the raster has {what}. Check the "
                        "codes or the range against the raster's legend.")
    say(f"[pixels] {len(mass):,} pixels count: {mass.ha.sum():,.1f} ha")
    x = people["x"].to_numpy(float)
    y = people["y"].to_numpy(float)
    have = np.isfinite(x) & np.isfinite(y)
    if not have.any():
        raise BadNumber("None of the people has coordinates.")
    if not have.all():
        say(f"[pixels] {int((~have).sum()):,} row(s) have no "
            "coordinates (empty geometry) and get empty results.")
    here = pd.DataFrame({"x": x[have], "y": y[have]})
    part = reach(here, mass, ks, unit_size=float(unit_size))
    for k in ks:
        kk = int(k) if float(k).is_integer() else k
        part = part.rename(columns={f"Dist_{kk}": f"Dist_{_tag(k)}",
                                    f"Got_{kk}": f"Got_{_tag(k)}"})
        short = int((part[f"Got_{_tag(k)}"] < k * (1 - 1e-9)).sum())
        if short:
            say(f"[pixels] NOTE: for {short:,} places the raster holds "
                f"less than {kk:g} ha in all; their Dist_{_tag(k)} is "
                "the distance to the last pixel, not a reach.")
    if radius is not None:
        sw = share_within(here, mass, radius)
        tag = f"{radius:g}".replace(".", "_")
        part[f"Mass_r{tag}"] = sw["Mass_r"].to_numpy()
        part[f"Share_r{tag}"] = sw["Share_r"].to_numpy()
    res = pd.DataFrame({"x": x, "y": y})
    for c in part.columns:
        if c in ("x", "y"):
            continue
        col = np.full(len(x), np.nan)
        col[have] = part[c].to_numpy(float)
        res[c] = col
    return res

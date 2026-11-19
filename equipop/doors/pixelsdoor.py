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

The boxes, as a person types them:
    Which pixels count   "10 20"        land-cover class codes
                         "0,4 to 1"     a range of an index (NDVI...)
    Hectares to gather   "1 5 20"       k, in hectares
    Radius (optional)    "300"          metres; adds the hectares
                                        within it and their share
"""

from __future__ import annotations

import pandas as pd

from .numbers import BadNumber, is_blank, numlist, to_float

__all__ = ["parse_pixels", "parse_hectares", "run"]


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


def run(people: pd.DataFrame, raster_path, pixels_text, hectares_text,
        radius_text="", *, layer_is_metric: bool = True,
        same_crs: bool = True, say=print) -> pd.DataFrame:
    """Green reach (and share) for each row of `people` (x, y).

    layer_is_metric and same_crs are the door's own reading of its two
    layers: the distances are in the layer's units, so they must be
    metres, and the pixels are placed in the raster's coordinates, so
    the two must agree. Both are refused with a sentence that says what
    to do, never computed wrongly.

    Returns one row per person: Dist_<k> (metres to gather k hectares)
    and Got_<k> (hectares gathered: below k when the raster holds less),
    plus Mass_r<r> and Share_r<r> when a radius is given.
    """
    from ..pixels import pixels_to_mass, reach, share_within
    if not layer_is_metric:
        raise BadNumber(
            "The people layer is in degrees. Distances need metres: "
            "save the layer in a projected coordinate system (UTM, "
            "SWEREF99 TM, ETRS89 LAEA...) and run again.")
    if not same_crs:
        raise BadNumber(
            "The raster and the people layer are in different "
            "coordinate systems. Project the raster to the layer's "
            "system first (QGIS: Raster > Projections > Warp; Pro: "
            "Project Raster), then run again.")
    spec = parse_pixels(pixels_text)
    ks = parse_hectares(hectares_text)
    radius = None if is_blank(radius_text) else to_float(radius_text)
    if radius is not None and radius <= 0:
        raise BadNumber("The radius must be above 0 metres, or left "
                        "empty.")
    mass = pixels_to_mass(raster_path, **spec)
    if mass.empty:
        what = (f"class {' '.join(map(str, spec['classes']))}"
                if "classes" in spec else
                f"values {spec['between'][0]:g} to {spec['between'][1]:g}")
        raise BadNumber(f"No pixel of the raster has {what}. Check the "
                        "codes or the range against the raster's legend.")
    say(f"[pixels] {len(mass):,} pixels count: {mass.ha.sum():,.1f} ha")
    res = reach(people, mass, ks)
    for k in ks:
        kk = int(k) if float(k).is_integer() else k
        short = int((res[f"Got_{kk}"] < k * (1 - 1e-9)).sum())
        if short:
            say(f"[pixels] NOTE: for {short:,} places the raster holds "
                f"less than {kk:g} ha in all; their Dist_{kk} is the "
                "distance to the last pixel, not a reach.")
    if radius is not None:
        sw = share_within(people, mass, radius)
        tag = f"{radius:g}".replace(".", "_")
        res[f"Mass_r{tag}"] = sw["Mass_r"].to_numpy()
        res[f"Share_r{tag}"] = sw["Share_r"].to_numpy()
    return res

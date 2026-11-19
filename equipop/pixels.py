"""
pixels.py - pixels as mass: how far to gather k hectares of something,
and how much of it lies around you (BACKLOG 507).

John, 19 November 2026: image analysis is the first of the board's
computational targets. EquiPop's engine counts MASS outward from a place
until it reaches k. Mass has meant people and jobs; a pixel can carry it
too - hectares of green, of water, of built-up land, of anything a
land-cover map or an index (NDVI, excess green, a hue band) can mark.

Three pieces, each small:

    pixels_to_mass(path, classes=[10, 20])     a raster -> the pixels
    pixels_to_mass(path, between=(0.4, 1.0))   that count, with their
                                               area in HECTARES
    reach(people, mass, [1, 5, 20])            Dist_k: from each person,
                                               the distance at which k
                                               hectares are gathered
    share_within(people, mass, radius)         the hectares within a
                                               radius - fixed, or each
                                               person's own (Dist_400 of
                                               a population run gives
                                               the share at the scale of
                                               400 people)

k is in HECTARES, not pixels, so a result does not change with the
resolution of the image: 5 ha is 5 ha in a 10 m map and in a 30 m map.

reach() is the ordinary k-nearest engine, run with the people as origins
and the pixels as the only mass, so everything the engine guarantees -
rings, the share of the ring that crosses k, distances in the units of
the coordinates - holds here unchanged. Coordinates must be metric.
"""

import math

import numpy as np
import pandas as pd

R_EARTH = 6371008.8


def _need_rasterio():
    try:
        import rasterio
        return rasterio
    except ImportError as e:                       # pragma: no cover
        raise ImportError("pixels_to_mass reads rasters and needs "
                          "rasterio: pip install rasterio") from e


def pixel_area_ha(transform, rows, geographic: bool) -> np.ndarray:
    """Area of each pixel in hectares. On a metric grid every pixel is
    |a x e|. On a latitude-longitude grid a pixel shrinks with the
    cosine of its latitude: a 30" WorldPop cell is 86 ha at the equator
    and 43 ha at 60 degrees north."""
    return _area_ha(abs(transform.a), abs(transform.e), transform.f,
                    rows, geographic)


def _area_ha(cell_w, cell_h, y_max, rows, geographic):
    rows = np.asarray(rows)
    if not geographic:
        return np.full(len(rows), cell_w * cell_h / 10_000.0)
    lat = y_max - (rows + 0.5) * cell_h
    dlon = math.radians(cell_w)
    # the exact area of a latitude band, not cos(centre) x a rectangle
    top = np.radians(lat + cell_h / 2)
    bottom = np.radians(lat - cell_h / 2)
    area = R_EARTH ** 2 * dlon * np.abs(np.sin(top) - np.sin(bottom))
    return area / 10_000.0


def pixels_from_array(a, x_min, y_max, cell_w, cell_h, *, nodata=None,
                      geographic: bool = False, classes=None,
                      between=None, name: str = "ha") -> pd.DataFrame:
    """pixels_to_mass for a band that is already in memory - the way
    the GIS doors hand it over (BACKLOG 509). A door reads the raster
    with its own GIS (arcpy in Pro, GDAL in QGIS) because the package
    must never open GIS files inside a host's Python: two GDALs in one
    Pro clone fight over their DLLs.

    a              the band, rows from the top (north) down
    x_min, y_max   the raster's west and north edges
    cell_w, cell_h the pixel's width and height, both positive
    nodata         the band's nodata value, or None
    geographic     True when the coordinates are degrees
    """
    if (classes is None) == (between is None):
        raise ValueError("give exactly one of classes= (codes to keep) "
                         "or between=(low, high) (a range to keep)")
    a = np.asarray(a)
    if a.ndim != 2:
        raise ValueError(f"one band at a time: got an array of shape "
                         f"{a.shape}")
    cell_w, cell_h = abs(float(cell_w)), abs(float(cell_h))
    if not (cell_w > 0 and cell_h > 0):
        raise ValueError("the pixel size must be above 0")
    ok = np.ones(a.shape, bool)
    if np.issubdtype(a.dtype, np.floating):
        ok &= np.isfinite(a)
    if nodata is not None and not (isinstance(nodata, float)
                                   and math.isnan(nodata)):
        ok &= a != nodata
    if classes is not None:
        keep = ok & np.isin(a, np.asarray(list(classes)))
    else:
        lo, hi = between
        keep = ok & (a >= lo) & (a <= hi)
    rows, cols = np.nonzero(keep)
    x = float(x_min) + (cols + 0.5) * cell_w
    y = float(y_max) - (rows + 0.5) * cell_h
    return pd.DataFrame({"x": x, "y": y,
                         name: _area_ha(cell_w, cell_h, float(y_max),
                                        rows, geographic)})


def pixels_to_mass(path, *, classes=None, between=None, band: int = 1,
                   name: str = "ha") -> pd.DataFrame:
    """The pixels of one raster band that count, as points with their
    area in hectares.

    classes : land-cover codes to keep, e.g. [10, 20] (trees, shrubs).
    between : (low, high) to keep a range of a continuous layer, e.g.
              (0.4, 1.0) of NDVI. Both ends included.
    Exactly one of the two. Nodata pixels never count.

    Returns x, y (pixel centres, in the raster's own coordinates) and
    `name` (hectares). Coordinates in degrees must be projected before
    reach() - use equipop.project_to_metric.
    """
    if (classes is None) == (between is None):
        raise ValueError("give exactly one of classes= (codes to keep) "
                         "or between=(low, high) (a range to keep)")
    rasterio = _need_rasterio()
    with rasterio.open(path) as src:
        if not 1 <= int(band) <= src.count:
            raise ValueError(f"{path} has {src.count} band(s); band "
                             f"{band} does not exist")
        a = src.read(int(band))
        T = src.transform
        nodata = src.nodata
        geographic = bool(src.crs and src.crs.is_geographic)
    if T.b or T.d:
        raise ValueError(f"{path} is a rotated raster; warp it to a "
                         "north-up grid first")
    out = pixels_from_array(a, T.c, T.f, T.a, T.e, nodata=nodata,
                            geographic=geographic, classes=classes,
                            between=between, name=name)
    print(f"[pixels] {path}: {len(out):,} of {a.size:,} pixels count, "
          f"{out[name].sum():,.1f} ha")
    return out


def reach(people: pd.DataFrame, mass: pd.DataFrame, k_values,
          *, x: str = "x", y: str = "y", mass_col: str = "ha",
          unit_size: float = 100.0) -> pd.DataFrame:
    """Dist_k from each person (row of `people`): the distance at which
    k hectares of `mass` have been gathered, for each k in k_values.

    Returns one row per person, in order: x, y, and per k Dist_<k> (in
    the coordinates' units) and Got_<k> (the hectares gathered - equal
    to k, or everything there is when the map holds less than k, in
    which case Dist_<k> is the distance to the last pixel and must not
    be read as a reach).

    unit_size is the size of the people's cells. The engine treats a
    person as spread over their own cell, so the search starts from that
    cell's mean radius (56 m for a 100 m cell): green inside the cell is
    reached sooner, green beyond it no sooner than that.
    """
    from .cells import CellData
    from .fastcounts import run_knn_counts
    # whole numbers stay whole, so the columns read Dist_5, not Dist_5.0
    k_values = sorted(int(k) if float(k).is_integer() else float(k)
                      for k in k_values)
    if not k_values or k_values[0] <= 0:
        raise ValueError("k_values are hectares and must be above 0")
    m = mass[mass[mass_col] > 0]
    n_p = len(people)
    E = np.concatenate([people[x].to_numpy(float), m[x].to_numpy(float)])
    N = np.concatenate([people[y].to_numpy(float), m[y].to_numpy(float)])
    n = np.concatenate([np.zeros(n_p), m[mass_col].to_numpy(float)])
    cd = CellData(E=E, N=N, n=n, unit_size=float(unit_size))
    res = run_knn_counts(cd, k_values, origins=np.arange(n_p),
                         report=False)
    out = pd.DataFrame({x: people[x].to_numpy(), y: people[y].to_numpy()})
    for k in k_values:
        out[f"Dist_{k}"] = res[f"Dist_{k}"].to_numpy()
        out[f"Got_{k}"] = res[f"N_{k}"].to_numpy()
    return out


def share_within(people: pd.DataFrame, mass: pd.DataFrame, radius,
                 *, x: str = "x", y: str = "y",
                 mass_col: str = "ha") -> pd.DataFrame:
    """The hectares of `mass` within `radius` of each person, and their
    share of the disc's area.

    radius : one number for everybody (300.0), or one per person - a
             column such as a population run's Dist_400, which gives the
             share at the scale of each person's nearest 400 people.

    Returns Mass_r (hectares) and Share_r (Mass_r / disc area; a disc
    reaching past the coast or the map's edge is still counted whole, so
    near an edge the share is low - the map holds nothing there).
    A pixel counts when its centre is within the radius.
    """
    from scipy.spatial import cKDTree
    m = mass[mass[mass_col] > 0]
    tree = cKDTree(np.column_stack([m[x].to_numpy(float),
                                    m[y].to_numpy(float)]))
    pts = np.column_stack([people[x].to_numpy(float),
                           people[y].to_numpy(float)])
    r = np.broadcast_to(np.asarray(radius, float), (len(pts),)).copy()
    ha = m[mass_col].to_numpy(float)
    got = np.zeros(len(pts))
    hits = tree.query_ball_point(pts, r)
    for i, idx in enumerate(hits):
        if idx:
            got[i] = ha[idx].sum()
    disc_ha = math.pi * r ** 2 / 10_000.0
    with np.errstate(divide="ignore", invalid="ignore"):
        share = np.where(disc_ha > 0, got / disc_ha, np.nan)
    return pd.DataFrame({x: pts[:, 0], y: pts[:, 1],
                         "Mass_r": got, "Share_r": share})

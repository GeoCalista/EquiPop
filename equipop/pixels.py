"""
pixels.py - pixels as mass: how far to gather k hectares of something,
and how much of it lies around you (BACKLOG 507).

John, 19 November 2026: image analysis is the first of the board's
computational targets. EquiPop's engine counts MASS outward from a place
until it reaches k. Mass has meant people and jobs; a pixel can carry it
too - hectares of green, of water, of built-up land, of anything a
land-cover map or an index (NDVI, excess green, a hue band) can mark.

THE CHAIN (BACKLOG 510, ruling R-53):

    value             one band, or a formula over bands (bandmath.py)
    mass_from_values  base and treatment -> each pixel's hectares ->
                      the analysis cell (hectares summed, never a mean)
    reach             Dist_k from each person, with a treatment T_k and
                      R_k, with a radius B_r, T_r and R_r

and, from 1.65.0 and kept for Python users:

    pixels_to_mass(path, classes=[10, 20])     a raster -> the pixels
    pixels_to_mass(path, between=(0.4, 1.0))   that count, with their
                                               area in HECTARES
    share_within(people, mass, radius)         the hectares within a
                                               radius and their share
                                               of the disc

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


def check_system(crs, label):
    """A raster file's coordinate system must be known, and in metres or
    degrees (BACKLOG 512 c): a raster in feet was read as metres - 1 ha
    for a 100 x 100 foot pixel of 0.093 ha. `crs` is rasterio's."""
    if crs is None:
        raise ValueError(
            f"{label} has no coordinate system, so its pixel size could "
            "be in metres, feet or degrees. Give it one first (QGIS: "
            "Raster > Projections > Assign Projection; Pro: Define "
            "Projection).")
    if crs.is_geographic:
        return
    unit, factor = crs.linear_units_factor
    if abs(float(factor) - 1.0) > 1e-9:
        raise ValueError(
            f"{label} is in {unit}, not metres. Project it to a system "
            "in metres first (QGIS: Raster > Projections > Warp; Pro: "
            "Project Raster).")


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
    out = pd.DataFrame({"x": x, "y": y,
                        name: _area_ha(cell_w, cell_h, float(y_max),
                                       rows, geographic)})
    if not geographic:
        out.attrs["cell_m"] = _side(cell_w, cell_h)
    return out


def _side(cell_w, cell_h) -> float:
    """The side of the square cell reach() spreads mass over (R-55): a
    pixel's own side, or for a non-square pixel the side of a square of
    the same area."""
    return math.sqrt(abs(float(cell_w)) * abs(float(cell_h)))


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
        check_system(src.crs, str(path))
        # the file's own validity mask, not only its nodata value
        # (BACKLOG 512 c): a masked pixel never counts
        a = src.read(int(band)).astype(np.float64)
        a[src.read_masks(int(band)) == 0] = np.nan
        T = src.transform
        nodata = src.nodata
        geographic = bool(src.crs.is_geographic)
    if T.b or T.d:
        raise ValueError(f"{path} is a rotated raster; warp it to a "
                         "north-up grid first")
    out = pixels_from_array(a, T.c, T.f, T.a, T.e, nodata=nodata,
                            geographic=geographic, classes=classes,
                            between=between, name=name)
    print(f"[pixels] {path}: {len(out):,} of {a.size:,} pixels count, "
          f"{out[name].sum():,.1f} ha")
    return out


def select(value, spec) -> np.ndarray:
    """Which pixels a base or treatment box takes: None = every pixel
    with a value; {"classes": [...]} = those codes; {"between": (lo,
    hi)} = that range, both ends included. NaN never counts."""
    value = np.asarray(value)
    ok = np.isfinite(value) if np.issubdtype(value.dtype, np.floating) \
        else np.ones(value.shape, bool)
    if spec is None:
        return ok
    if "classes" in spec:
        return ok & np.isin(value, np.asarray(list(spec["classes"])))
    lo, hi = spec["between"]
    with np.errstate(invalid="ignore"):
        return ok & (value >= lo) & (value <= hi)


def mass_from_values(value, x_min, y_max, cell_w, cell_h, *,
                     geographic: bool = False, base=None,
                     treatment=None, cell=None) -> pd.DataFrame:
    """THE CHAIN (BACKLOG 510, ruling R-53), from one value per pixel to
    the mass reach() counts:

        value           one band, or a formula's result (bandmath)
        base            which pixels the k hectares are counted from;
                        None = every pixel with a value
        treatment       which of the BASE pixels are looked for among
                        them (a treatment pixel outside the base does
                        not count); None = no treatment
        hectares        each pixel's own area (a latitude band's on a
                        degree grid)
        cell            the ANALYSIS CELL, in metres: the hectares are
                        summed into cells of this size on a grid
                        anchored at 0, 0, AFTER base and treatment were
                        decided pixel by pixel - never a mean value
                        thresholded afterwards. None = the image's own
                        pixel. A pixel goes to the cell its centre is in.

    Returns x, y and ha (base hectares), plus t_ha when a treatment is
    given: one row per pixel (or per analysis cell) holding any base.
    """
    v = np.asarray(value)
    if v.ndim != 2:
        raise ValueError(f"one value per pixel: got an array of shape "
                         f"{v.shape}")
    cell_w, cell_h = abs(float(cell_w)), abs(float(cell_h))
    if not (cell_w > 0 and cell_h > 0):
        raise ValueError("the pixel size must be above 0")
    in_base = select(v, base)
    rows, cols = np.nonzero(in_base)
    x = float(x_min) + (cols + 0.5) * cell_w
    y = float(y_max) - (rows + 0.5) * cell_h
    ha = _area_ha(cell_w, cell_h, float(y_max), rows, geographic)
    out = {"x": x, "y": y, "ha": ha}
    if treatment is not None:
        t = select(v[rows, cols], treatment)
        out["t_ha"] = np.where(t, ha, 0.0)
    df = pd.DataFrame(out)
    if cell is None or cell == "" or len(df) == 0:
        if not geographic:
            df.attrs["cell_m"] = _side(cell_w, cell_h)
        return df
    cell = float(cell)
    if geographic:
        raise ValueError("An analysis cell is in metres, and this "
                         "raster's coordinates are degrees.")
    if cell < max(cell_w, cell_h) * (1 - 1e-9):
        raise ValueError(f"The analysis cell ({cell:g} m) is smaller "
                         f"than the image's pixel ({max(cell_w, cell_h):g}"
                         " m): there is nothing to sum. Leave it empty "
                         "to use the pixel itself.")
    ix = np.floor(df.x.to_numpy() / cell).astype(np.int64)
    iy = np.floor(df.y.to_numpy() / cell).astype(np.int64)
    g = df.assign(ix=ix, iy=iy).groupby(["ix", "iy"], sort=True)
    agg = g[[c for c in ("ha", "t_ha") if c in df]].sum().reset_index()
    agg.insert(0, "y", (agg.pop("iy") + 0.5) * cell)
    agg.insert(0, "x", (agg.pop("ix") + 0.5) * cell)
    agg.attrs["cell_m"] = cell
    return agg


def reach(people: pd.DataFrame, mass: pd.DataFrame, k_values=(),
          *, r_values=(), x: str = "x", y: str = "y",
          mass_col: str = "ha", treat_col: str | None = None,
          unit_size: float | None = None) -> pd.DataFrame:
    """From each person (row of `people`), the k-nearest hectares of
    `mass` - EquiPop's own engine with pixels in place of people.

    Per k (hectares):
        Dist_<k>  the distance at which k hectares of mass are gathered.
                  EMPTY (NaN) where all the mass there is holds less
                  than k - a reach that never happens is not given a
                  distance (BACKLOG 510; 1.65.0 wrote the distance to
                  the last pixel and a Got_ column to warn of it).
        T_<k>     with treat_col: hectares of treatment among them
        R_<k>     with treat_col: T_<k> / k, the share
    Per radius r (metres), when r_values are given:
        B_r<r>    hectares of mass within r
        T_r<r>    with treat_col: hectares of treatment within r
        R_r<r>    with treat_col: T_r<r> / B_r<r>
    A decimal k or r is written with '_' for '.': Dist_2_5 is 2.5 ha.

    unit_size is the side, in metres, of the cells the mass lies in - a
    pixel, or an analysis cell (R-55): mass inside a cell is spread
    evenly over it, so a person standing in a cell with mass gathers it
    within that cell's own disc, and the first ring around anyone starts
    at the edge of it. Left out, it is the side mass_from_values() or
    pixels_from_array() recorded, or, when every point holds the same
    hectares, the side of a square of that area; otherwise it must be
    given. (Before BACKLOG 512 it was 100 m whatever the pixel: one 10 m
    pixel, k = 0.01 ha, gave 56.42 m, where the pixel's disc is 5.64 m.)
    """
    from .cells import CellData
    from .fastcounts import run_knn_counts
    from .labels import numeric_tag
    # whole numbers stay whole, so the columns read Dist_5, not Dist_5.0
    k_values = sorted(int(k) if float(k).is_integer() else float(k)
                      for k in k_values)
    r_values = sorted(float(r) for r in r_values)
    if not (k_values or r_values):
        raise ValueError("give hectares (k_values) and/or a radius")
    if k_values and k_values[0] <= 0:
        raise ValueError("k_values are hectares and must be above 0")
    if r_values and r_values[0] <= 0:
        raise ValueError("a radius must be above 0")
    unit_size = _unit_of(mass, mass_col, unit_size)
    m = mass[mass[mass_col] > 0]
    n_p = len(people)
    E = np.concatenate([people[x].to_numpy(float), m[x].to_numpy(float)])
    N = np.concatenate([people[y].to_numpy(float), m[y].to_numpy(float)])
    n = np.concatenate([np.zeros(n_p), m[mass_col].to_numpy(float)])
    sums = {}
    if treat_col is not None:
        sums["t"] = np.concatenate([np.zeros(n_p),
                                    m[treat_col].to_numpy(float)])
    cd = CellData(E=E, N=N, n=n, binary_sums=sums,
                  unit_size=float(unit_size))
    res = run_knn_counts(cd, k_values, r_values=r_values,
                         origins=np.arange(n_p), report=False)
    out = pd.DataFrame({x: people[x].to_numpy(), y: people[y].to_numpy()})
    for k in k_values:
        tag = numeric_tag(k)
        short = res[f"N_{k}"].to_numpy() < float(k) * (1 - 1e-9)
        d = res[f"Dist_{k}"].to_numpy(float).copy()
        d[short] = np.nan
        out[f"Dist_{tag}"] = d
        if treat_col is not None:
            t = res[f"T_t_{k}"].to_numpy(float).copy()
            t[short] = np.nan
            out[f"T_{tag}"] = t
            out[f"R_{tag}"] = t / float(k)
    for r in r_values:
        tag = numeric_tag(r)
        out[f"B_r{tag}"] = res[f"N_r{tag}"].to_numpy(float)
        if treat_col is not None:
            out[f"T_r{tag}"] = res[f"T_t_r{tag}"].to_numpy(float)
            out[f"R_r{tag}"] = res[f"R_t_r{tag}"].to_numpy(float)
    return out


def _unit_of(mass, mass_col, unit_size) -> float:
    """reach()'s cell side: given, recorded, or read off equal pixels."""
    if unit_size is None:
        unit_size = mass.attrs.get("cell_m")
    if unit_size is None:
        ha = np.unique(np.round(mass[mass_col].to_numpy(float), 12))
        ha = ha[ha > 0]
        if len(ha) != 1:
            raise ValueError(
                "give unit_size: the side, in metres, of the cells the "
                "mass lies in (the pixel, or the analysis cell). The "
                "points hold different hectares, so it cannot be read "
                "off them.")
        unit_size = math.sqrt(float(ha[0]) * 10_000.0)
    unit_size = float(unit_size)
    if not (np.isfinite(unit_size) and unit_size > 0):
        raise ValueError("unit_size is a side in metres, above 0")
    return unit_size


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

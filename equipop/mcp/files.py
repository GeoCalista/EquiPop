"""
files.py - the MCP server's reading and writing (BACKLOG 522, R-63).

Everything that touches the person's disk is here, under three rules:

  * LOOK WITHOUT ROWS. A file or folder is described - layers,
    columns, how many rows, the coordinate system, the extent, and per
    numeric column how many are missing, how many distinct values, the
    mean, the median and the 10th and 90th percentiles. No row and no
    single value of a person leaves this module unless the server was
    started with --rows (and then only through peek(), a handful).
  * NEW FILES ONLY. A result is written next to its input under a new
    name; a name that exists gets a number. Nothing is overwritten,
    nothing is deleted.
  * NAMED FILES ONLY. The server opens the file or folder it is given
    and nothing beside it.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from ..doors.numbers import BadNumber

TABLE = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".parquet", ".sav",
         ".dta", ".dbf")
VECTOR = (".gpkg", ".shp", ".geojson", ".fgb", ".json", ".zip")
RASTER = (".tif", ".tiff", ".vrt", ".img", ".asc")

PEEK_MAX = 20


def _say_into(bag: list):
    def say(*a, **k):
        bag.append(" ".join(str(x) for x in a))
    return say


def check_path(path, what="file") -> Path:
    """An absolute, existing path, or a sentence."""
    if path is None or not str(path).strip():
        raise BadNumber(f"Give the {what} - its full path on this "
                        "computer.")
    p = Path(os.path.expanduser(str(path).strip().strip('"')))
    if not p.exists():
        raise BadNumber(f"There is no {what} at {p}. Check the path; "
                        "the server opens only the file it is given.")
    return p.resolve()


def kind_of(p: Path) -> str:
    if p.is_dir():
        return "folder"
    ext = p.suffix.lower()
    if ext in RASTER:
        return "raster"
    if ext in VECTOR:
        return "vector"
    if ext in TABLE:
        return "table"
    return "other"


# ------------------------------------------------------------- look
def _column_summary(s: pd.Series) -> dict:
    out = {"name": str(s.name), "type": str(s.dtype),
           "missing": int(s.isna().sum())}
    if pd.api.types.is_numeric_dtype(s) and not \
            pd.api.types.is_bool_dtype(s):
        v = pd.to_numeric(s, errors="coerce").to_numpy(float)
        ok = np.isfinite(v)
        out["distinct"] = int(len(np.unique(v[ok])))
        if ok.any():
            out["mean"] = float(np.mean(v[ok]))
            out["median"] = float(np.median(v[ok]))
            out["p10"] = float(np.percentile(v[ok], 10))
            out["p90"] = float(np.percentile(v[ok], 90))
    else:
        out["distinct"] = int(s.nunique(dropna=True))
    return out


def _frame_summary(df: pd.DataFrame, context: str) -> dict:
    from ..io import guess_xy_fields
    fx, fy, degrees = guess_xy_fields(list(df.columns), context)
    out = {"rows": int(len(df)),
           "columns": [_column_summary(df[c]) for c in df.columns]}
    if fx and fy:
        x = pd.to_numeric(df[fx], errors="coerce")
        y = pd.to_numeric(df[fy], errors="coerce")
        out["x_field"], out["y_field"] = str(fx), str(fy)
        out["looks_like_degrees"] = bool(degrees)
        if x.notna().any() and y.notna().any():
            out["extent"] = [float(x.min()), float(y.min()),
                             float(x.max()), float(y.max())]
    else:
        out["x_field"] = out["y_field"] = None
        out["note"] = ("No coordinate pair was recognised among the "
                       "columns; name the x and y fields when running a "
                       "tool.")
    return out


def look(path, layer: str | None = None) -> dict:
    """Describe a file or a folder without returning any row."""
    p = check_path(path, "file or folder")
    kind = kind_of(p)
    out = {"path": str(p), "kind": kind}
    said: list = []
    if kind == "folder":
        files = []
        for q in sorted(p.iterdir()):
            try:
                size = q.stat().st_size if q.is_file() else None
            except OSError:
                size = None
            files.append({"name": q.name, "kind": kind_of(q),
                          "bytes": size})
        out["files"] = files
        try:
            from ..doors.inventory import inventory
            inv = inventory(str(p), say=_say_into(said), deep=False,
                            write=False)
            out["inventory"] = {k: v for k, v in inv.items()
                                if k in ("files", "lattices", "warnings")}
        except Exception as exc:            # pragma: no cover
            out["note"] = f"The folder's GIS files were not read: {exc}"
        return out
    if kind == "raster":
        try:
            import rasterio
        except ImportError:
            out["note"] = ("rasterio is not installed, so the raster "
                           "was not opened: pip install rasterio")
            return out
        with rasterio.open(p) as src:
            out.update({
                "bands": int(src.count),
                "width": int(src.width), "height": int(src.height),
                "pixel": [float(src.transform.a),
                          float(-src.transform.e)],
                "crs": str(src.crs) if src.crs else None,
                "geographic": bool(src.crs.is_geographic)
                if src.crs else None,
                "extent": [float(v) for v in src.bounds],
                "nodata": [None if v is None else float(v)
                           for v in src.nodatavals],
                "dtype": str(src.dtypes[0])})
        return out
    if kind == "vector":
        try:
            import pyogrio
            layers = [str(l[0]) for l in pyogrio.list_layers(str(p))]
        except Exception:
            layers = []
        if layers:
            out["layers"] = layers
            if layer and layer not in layers:
                raise BadNumber(f'"{layer}" is not a layer of {p.name}; '
                                "its layers are: " + ", ".join(layers))
            use = layer or layers[0]
            info = pyogrio.read_info(str(p), layer=use)
            out["layer"] = use
            out["crs"] = str(info.get("crs")) if info.get("crs") else None
            out["geometry"] = info.get("geometry_type")
            out["rows"] = int(info.get("features") or 0)
            raw = info.get("fields")
            out["columns"] = [] if raw is None else [str(x) for x in raw]
            if info.get("total_bounds") is not None:
                out["extent"] = [float(v) for v in info["total_bounds"]]
            if len(layers) > 1 and not layer:
                out["note"] = (f"{p.name} holds {len(layers)} layers; "
                               f'"{use}" is described. Name another '
                               "with layer=.")
            return out
    if kind in ("table", "vector"):
        df, meta = read_points(p, layer=layer, need_xy=False, said=said)
        out.update(_frame_summary(df, p.name))
        out.update(meta)
        if said:
            out["messages"] = said
        return out
    out["note"] = ("Not a file EquiPop reads. Tables: csv, tsv, xlsx, "
                   "parquet, dta, sav, dbf. Layers: gpkg, shp, geojson, "
                   "fgb. Rasters: tif, vrt, img, asc.")
    return out


# ------------------------------------------------------------- read
def read_points(path, layer: str | None = None, x_field: str | None = None,
                y_field: str | None = None, need_xy: bool = True,
                project: bool = False, said: list | None = None):
    """A table of points -> (DataFrame with x and y, meta).

    meta: crs_epsg (a layer's), unit ("metres", "degrees" or None),
    x_field, y_field, and `projected` when degrees were projected to
    UTM metres because project=True (the Stata door's rule: never
    silently).
    """
    from ..io import read_table
    p = check_path(path, "points file")
    if p.is_dir():
        raise BadNumber(f"{p} is a folder; give the points FILE in it.")
    bag = said if said is not None else []
    import contextlib
    import io as _io
    kw = {}
    if layer:
        kw["layer"] = layer
    buf = _io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            df = read_table(str(p), **kw)
    except ImportError as exc:
        raise BadNumber(str(exc))
    except Exception as exc:
        raise BadNumber(f"{p.name} could not be read: {exc}")
    bag.extend(l for l in buf.getvalue().splitlines() if l.strip())
    meta = {"crs_epsg": df.attrs.get("crs_epsg")}
    if not need_xy:
        return df, meta
    if x_field or y_field:
        if not (x_field and y_field):
            raise BadNumber("Give both the x field and the y field, or "
                            "neither.")
        for f in (x_field, y_field):
            if f not in df.columns:
                raise BadNumber(f'"{f}" is not a column of {p.name}. Its '
                                "columns: " + ", ".join(map(str, df.columns)))
        df = df.rename(columns={x_field: "x", y_field: "y"})
        degrees_named = False
    else:
        from ..io import guess_xy_fields
        fx, fy, degrees_named = guess_xy_fields(list(df.columns), p.name)
        if not (fx and fy):
            raise BadNumber(
                f"No coordinate pair was recognised in {p.name}; name "
                "the x field and the y field. Its columns: "
                + ", ".join(map(str, df.columns)))
        if (fx, fy) != ("x", "y"):
            df = df.rename(columns={fx: "x", fy: "y"})
        x_field, y_field = fx, fy
    df["x"] = pd.to_numeric(df["x"], errors="coerce")
    df["y"] = pd.to_numeric(df["y"], errors="coerce")
    meta.update({"x_field": str(x_field), "y_field": str(y_field)})
    # degrees: a layer's system says so; a table's names or values
    geographic = False
    epsg = meta["crs_epsg"]
    if epsg:
        try:
            from pyproj import CRS
            geographic = bool(CRS.from_epsg(int(epsg)).is_geographic)
        except Exception:               # pragma: no cover
            geographic = False
    elif degrees_named:
        geographic = True
    else:
        from ..utm import looks_like_degrees
        ok = df["x"].notna() & df["y"].notna()
        geographic = bool(ok.any() and looks_like_degrees(
            df.loc[ok, "x"].to_numpy(float), df.loc[ok, "y"].to_numpy(float)))
    if geographic:
        if not project:
            raise BadNumber(
                f"The coordinates of {p.name} are in DEGREES (longitude "
                "and latitude). Distances in degrees are not distances. "
                "Either give a file saved in metres, or run again with "
                "project=true to place the points in UTM metres for this "
                "run - the run then says which zone it used.")
        from ..stata_bridge import project_for_stata
        ok = df["x"].notna() & df["y"].notna()
        e, n, code, sentence = project_for_stata(
            df.loc[ok, "x"].to_numpy(float), df.loc[ok, "y"].to_numpy(float))
        df.loc[ok, "x"], df.loc[ok, "y"] = e, n
        meta.update({"crs_epsg": int(code), "unit": "metres",
                     "projected": sentence})
        bag.append(f"[mcp] {sentence}")
    else:
        meta["unit"] = "metres" if epsg or not degrees_named else None
        if epsg:
            try:
                from pyproj import CRS
                name = CRS.from_epsg(int(epsg)).axis_info[0].unit_name
                meta["unit"] = "metres" if name.startswith("met") else name
            except Exception:           # pragma: no cover
                pass
    return df, meta


# ------------------------------------------------------------ write
def new_path(beside, tag: str, ext: str) -> Path:
    """A path next to `beside` that does not exist yet:
    name_tag.ext, name_tag_2.ext, name_tag_3.ext ..."""
    beside = Path(beside)
    stem = f"{beside.stem}_{tag}"
    cand = beside.with_name(stem + ext)
    n = 1
    while cand.exists():
        n += 1
        cand = beside.with_name(f"{stem}_{n}{ext}")
    return cand


def write_result(df: pd.DataFrame, beside, tag: str, epsg=None,
                 geometry: str = "points") -> Path:
    """The result next to its input, never over anything: a .gpkg
    when the input was a layer and geopandas is there, else a .csv."""
    beside = Path(beside)
    ext = ".csv"
    if beside.suffix.lower() in VECTOR and geometry == "points":
        try:
            import geopandas  # noqa: F401
            ext = ".gpkg"
        except ImportError:
            ext = ".csv"
    out = new_path(beside, tag, ext)
    if ext == ".gpkg":
        import geopandas as gpd
        g = gpd.GeoDataFrame(
            df, geometry=gpd.points_from_xy(df["x"], df["y"]),
            crs=f"EPSG:{int(epsg)}" if epsg else None)
        g.to_file(out, driver="GPKG")
    else:
        df.to_csv(out, index=False)
    return out


def result_summary(df: pd.DataFrame, new_columns, texts: dict) -> list:
    """Each new column: what it means and its summary - never a row."""
    out = []
    for c in new_columns:
        if c not in df.columns:
            continue
        d = _column_summary(df[c])
        d["meaning"] = texts.get(c, "")
        out.append(d)
    return out


def peek(path, rows: int = 5, layer: str | None = None) -> dict:
    """The first rows of a file - ONLY when the server allows rows."""
    rows = max(1, min(int(rows), PEEK_MAX))
    df, meta = read_points(path, layer=layer, need_xy=False)
    head = df.head(rows)
    return {"rows_shown": int(len(head)), "of": int(len(df)),
            "columns": [str(c) for c in df.columns],
            "rows": head.astype(object).where(head.notna(), None)
            .values.tolist()}

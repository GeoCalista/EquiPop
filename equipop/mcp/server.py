"""
server.py - EquiPop's fourth door: an MCP server on the person's own
computer (BACKLOG 522; ruling R-63).

An AI assistant (Claude, ChatGPT, Copilot, VS Code ...) connects to
this server over stdio and gets a menu of tools: what EquiPop's tools
do and how to cite them, what is in a file, and the neighbourhood
tools themselves - tool 1 (counts and shares), tool 2 (value
statistics), tool 1b (summaries by area) and, with rasterio, tool 3b
(green reach) - on files the person names, with the same boxes and
the same words as the QGIS and Pro dialogs.

R-63, WHAT LEAVES THIS COMPUTER. Everything a tool returns goes to the
assistant, and so to the AI company's servers. So a tool returns
descriptions and summaries only: column names, N, the extent, the
coordinate system, and per column the mean, the median and the 10th
and 90th percentiles. The full result is written to a NEW file next
to the input, and the assistant gets the file's path. No row leaves
unless the server was started with --rows, and then only through
equipop_peek, at most twenty. Nothing is overwritten or deleted.

The engine half is the same as every door's (stata_bridge.dispatch,
areasdoor.run, pixelsdoor.run); this file only reads the boxes.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .. import __version__
from ..doors.numbers import BadNumber, intlist, numlist
from . import files as F

NAME = "equipop"
SERVER_NAME = "io.github.geocalista/equipop"

INSTRUCTIONS = """EquiPop measures the neighbourhood of every person \
or place: the k nearest people (an individualised neighbourhood) or a \
radius, and what they are like - counts and shares of groups, \
statistics of a value, segregation, accessibility. Start with \
equipop_tools to see what exists, equipop_help for a tool's boxes, and \
equipop_look at a file before running on it. Results are written to a \
new file next to the input; you receive its path and a summary of each \
new column, never the rows. Cite with equipop_cite."""

#: Tool 2's measures, the words of the dialog -> the engine's names
MEASURES = {"mean": "mean", "median": "median", "gini": "gini",
            "sd": "sd", "variance": "var", "var": "var", "se": "se",
            "min": "min", "max": "max", "count": "count", "sum": "sum",
            "range": "range", "mld": "mld", "theil": "theil"}

# the doors' defaults, passed EXPLICITLY (BACKLOG 99)
ORIGIN_RULE = "include"
OVERSHOOT = "proportional"
SELF_POTENTIAL = 1.0

VOCAB_MCP = {
    "showtools": "every tool is listed by equipop_tools.",
    "afterswitch": "they are listed by equipop_tools.",
    "target": "file",
    "container": "a new file next to the input",
    "formatnote": "",
    "temptable": "a new file next to the input",
    "selectby": "a filter on the file",
    "selectionrule": "every row of the file is used",
}


def _words(text) -> list[str]:
    if text is None:
        return []
    if isinstance(text, (list, tuple)):
        return [str(t).strip() for t in text if str(t).strip()]
    import re
    return [t for t in re.split(r"[,;\s]+", str(text).strip()) if t]


def _columns_exist(df, names, what, path):
    for f in names:
        if f not in df.columns:
            raise BadNumber(f'"{f}" ({what}) is not a column of '
                            f"{Path(path).name}. Its columns: "
                            + ", ".join(map(str, df.columns)))


def _numeric(df, names):
    import pandas as pd
    for f in names:
        df[f] = pd.to_numeric(df[f], errors="coerce")


def _cell(cell_size) -> float:
    from ..doors.rungs import check_cell_size
    try:
        return float(check_cell_size(cell_size if cell_size not in
                                     (None, "") else 100.0))
    except (BadNumber, ValueError) as bad:
        raise BadNumber(str(bad))


def _k_r(k, radius):
    from ..doors.numbers import check_k_and_r
    k_text = " ".join(_words(k))
    r_text = " ".join(_words(radius))
    check_k_and_r(k_text, r_text)
    kw = {}
    if k_text:
        kw["k_values"] = intlist(k_text)
    if r_text:
        kw["r_values"] = numlist(r_text)
    return kw, k_text, r_text


def _run_record(engine, df, path):
    from ..meta import record
    return record(engine, int(len(df)), {}, destination="",
                  source=str(path))


def _finish(df, res, order, beside, epsg, tag, kw, said):
    """Write the results beside the input and summarise them."""
    from ..describe import describe_all
    out = df.copy()
    for c in order:
        out[c] = res[c]
    written = F.write_result(out, beside, tag, epsg=epsg)
    texts = describe_all(order, kw)
    return {"written": str(written), "rows": int(len(out)),
            "new_columns": F.result_summary(out, order, texts),
            "messages": said}


def _capture():
    """Everything the engine prints, as the messages a GIS shows."""
    import contextlib
    import io as _io
    buf = _io.StringIO()
    return buf, contextlib.redirect_stdout(buf)


def _lines(buf) -> list:
    return [l for l in buf.getvalue().splitlines() if l.strip()]


# ------------------------------------------------------------ server
def build_server(rows: bool = False):
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError

    server = MCPServer(name=NAME, title="EquiPop", version=__version__,
                       instructions=INSTRUCTIONS,
                       website_url="https://github.com/GeoCalista/EquiPop")

    def guarded(fn):
        """A refusal is a sentence, never a traceback."""
        import functools

        @functools.wraps(fn)
        def inner(*a, **k):
            try:
                return fn(*a, **k)
            except BadNumber as bad:
                raise ToolError(str(bad)) from None
            except (ValueError, KeyError, ImportError) as exc:
                raise ToolError(f"{type(exc).__name__}: {exc}") from None
        return inner

    # ------------------------------------------------- describe
    @server.tool(name="equipop_tools")
    @guarded
    def equipop_tools() -> dict[str, Any]:
        """List EquiPop's tools: number and name, group, what each does
        in one paragraph, and whether this server can run it. Call
        this first."""
        from ..doors.help import LABELS, SUMMARY, fill
        from ..doors.toolset import EXTENDED, GROUPS, STANDARD
        runs_here = {"CountsShares": "equipop_counts_and_shares",
                     "ValueStatistics": "equipop_value_statistics",
                     "AreaSummaries": "equipop_summaries_by_area",
                     "PixelReach": "equipop_green_reach"}
        tools = []
        for t in list(STANDARD) + list(EXTENDED):
            if t == "ShowTools" or t not in LABELS:
                continue
            tools.append({"tool": t, "label": LABELS[t],
                          "group": GROUPS.get(t, ""),
                          "summary": fill(SUMMARY[t], VOCAB_MCP),
                          "runs_here": runs_here.get(t),
                          "in_gis": "QGIS and ArcGIS Pro"})
        return {"version": __version__, "tools": tools,
                "rows_leave_this_computer": bool(rows),
                "note": ("A tool with runs_here = null runs in QGIS, "
                         "ArcGIS Pro or Python today, not through this "
                         "server yet.")}

    @server.tool(name="equipop_help")
    @guarded
    def equipop_help(tool: str) -> dict[str, Any]:
        """A tool's help as its dialog shows it: what it does, how to
        approach it, and every box with its explanation. `tool` is a
        name from equipop_tools (such as CountsShares) or its number
        (1, 1b, 2, 3b, 7)."""
        from ..doors.help import HELP, LABELS, SUMMARY, USAGE, fill
        key = _tool_key(tool)
        boxes = BOXES.get(key, ())
        return {"tool": key, "label": LABELS[key],
                "summary": fill(SUMMARY[key], VOCAB_MCP),
                "usage": fill(USAGE.get(key, ""), VOCAB_MCP),
                "boxes": [{"box": b, "argument": ARGUMENT.get(b, b),
                           "help": fill(HELP.get(b, ""), VOCAB_MCP)}
                          for b in boxes],
                "runs_here": key in BOXES}

    @server.tool(name="equipop_cite")
    @guarded
    def equipop_cite(tool: str = "") -> dict[str, Any]:
        """How to cite EquiPop: the software report (for every use),
        the version, and the method paper behind a tool or an aspect
        of a run (decay, friction, slope, fca, autocorrelation), as
        text and BibTeX. These are the real references; do not invent
        others."""
        from .. import cite
        key = ""
        if tool:
            try:
                key = _tool_key(tool)
            except BadNumber:
                key = tool
        return cite.for_tool(key)

    @server.tool(name="equipop_columns")
    @guarded
    def equipop_columns(columns: str) -> dict[str, Any]:
        """What EquiPop's result columns mean - Dist_500, T_old_500,
        R_old_500, Mean_inc_500, Gini_..., N, Hidden - given their
        names, space- or comma-separated."""
        from ..describe import describe_all
        names = _words(columns)
        got = describe_all(names, {})
        return {"columns": [{"name": n, "meaning": got.get(n)}
                            for n in names],
                "note": "A null meaning is a column EquiPop did not "
                        "write, or a name it cannot read."}

    # ------------------------------------------------------ look
    @server.tool(name="equipop_look")
    @guarded
    def equipop_look(path: str, layer: str = "") -> dict[str, Any]:
        """What is in a file or a folder, without its rows: layers,
        columns and their types, how many rows, the coordinate fields
        and system, the extent, and per numeric column the missing
        count, distinct values, mean, median, 10th and 90th
        percentiles. Rasters: bands, pixel size, system, extent."""
        return F.look(path, layer or None)

    if rows:
        @server.tool(name="equipop_peek")
        @guarded
        def equipop_peek(path: str, rows: int = 5, layer: str = "") -> dict[str, Any]:
            """The first rows of a file (at most 20). Available only
            because this server was started with --rows: these rows
            leave the computer."""
            return F.peek(path, rows, layer or None)

    # ------------------------------------------------------- run
    @server.tool(name="equipop_counts_and_shares")
    @guarded
    def equipop_counts_and_shares(
            points: str, k: str = "", radius: str = "",
            people: str = "", count_fields: str = "",
            x_field: str = "", y_field: str = "", layer: str = "",
            cell_size: float = 100.0, decay: str = "",
            half_life: float = 0.0, project: bool = False) -> dict[str, Any]:
        """Tool 1, Counts and Shares: for every point, the distance to
        its k nearest people (Dist_k) and, for each count field, the
        number (T_) and share (R_) of them within that neighbourhood -
        or within a radius in metres. `k`: numbers of people, such as
        "100 500 2000"; `radius`: metres, such as "500 1000"; give at
        least one. `people`: the field with people per point (empty:
        one each). `count_fields`: fields to count, such as "old
        foreign". `decay`: negexp, expnormal, expsqrt, lognormal or
        power, with `half_life` in metres. `project`: true places
        points in degrees into UTM metres for the run. The result goes
        to a new file next to the input."""
        said: list = []
        df, meta = F.read_points(points, layer or None, x_field or None,
                                 y_field or None, project=project,
                                 said=said)
        kw, k_text, r_text = _k_r(k, radius)
        kw.update(unit_size=_cell(cell_size), treat_are_counts=True,
                  overshoot_mode=OVERSHOOT, self_rule=ORIGIN_RULE,
                  self_potential=SELF_POTENTIAL, seed=None)
        pop = (people or "").strip()
        treats = _words(count_fields)
        _columns_exist(df, ([pop] if pop else []) + treats, "a field",
                       points)
        _numeric(df, ([pop] if pop else []) + treats)
        if pop:
            kw["weight"] = df[pop].to_numpy(float)
        if treats:
            kw["treat"] = {t: df[t].to_numpy(float) for t in treats}
        model = (decay or "").strip().lower()
        if model:
            from ..doors.decaynames import (curve_in_plain_numbers,
                                            model_names)
            if model not in model_names():
                raise BadNumber(f'"{decay}" is not a decay model. They '
                                "are: " + ", ".join(model_names())
                                + ", or empty for none.")
            if not half_life or half_life <= 0:
                raise BadNumber("A decay needs a half-life in metres "
                                "above 0, such as 500.")
            kw.update(decay_model=model, half_life_m=float(half_life),
                      decay_calibration="half-life", decay_eps=1e-6)
            said.append(curve_in_plain_numbers(model, half_life))
        from ..doors.fields import predict_result_fields
        from ..stata_bridge import dispatch
        names = predict_result_fields("counts", k_text, r_text, "", treats,
                                      [], [], decaying=bool(model),
                                      efforting=False)
        buf, cap = _capture()
        with cap:
            res = dispatch("counts", df["x"].to_numpy(float),
                           df["y"].to_numpy(float),
                           provenance=_run_record("counts", df, points),
                           **kw)
        said.extend(_lines(buf))
        order = [n for n in names if n in res] + \
                [n for n in res if n not in names and n not in ("x", "y")]
        return _finish(df, res, order, points, meta.get("crs_epsg"),
                       "counts", kw, said)

    @server.tool(name="equipop_value_statistics")
    @guarded
    def equipop_value_statistics(
            points: str, value_fields: str, k: str = "",
            radius: str = "", statistics: str = "mean median gini",
            people: str = "", x_field: str = "", y_field: str = "",
            layer: str = "", cell_size: float = 100.0,
            project: bool = False) -> dict[str, Any]:
        """Tool 2, Value Statistics: for every point, statistics of a
        value (income, rent, age ...) over its k nearest people or a
        radius: mean, median, gini, sd, variance, se, min, max, count,
        sum, range, mld, theil, and percentiles as p10 p90. `k` and
        `radius` as in tool 1. `people`: a field weighting each point
        by its people. The result goes to a new file next to the
        input."""
        said: list = []
        df, meta = F.read_points(points, layer or None, x_field or None,
                                 y_field or None, project=project,
                                 said=said)
        vals = _words(value_fields)
        if not vals:
            raise BadNumber("Give at least one value field to summarise.")
        wanted = []
        for w in _words(statistics):
            lw = w.lower()
            if lw in MEASURES:
                wanted.append(MEASURES[lw])
            elif lw.startswith("p") and lw[1:].isdigit() and \
                    0 < int(lw[1:]) < 100:
                wanted.append(lw)
            else:
                raise BadNumber(f'"{w}" is not a statistic. They are: '
                                + ", ".join(MEASURES) + ", and p10 ... "
                                "p90 for percentiles.")
        wanted = list(dict.fromkeys(wanted)) or ["mean", "median", "gini"]
        kw, k_text, r_text = _k_r(k, radius)
        pop = (people or "").strip()
        _columns_exist(df, vals + ([pop] if pop else []), "a field", points)
        _numeric(df, vals + ([pop] if pop else []))
        kw.update(unit_size=_cell(cell_size), overshoot_mode=OVERSHOOT,
                  self_rule=ORIGIN_RULE, self_potential=SELF_POTENTIAL,
                  seed=None,
                  values={v: df[v].to_numpy(float) for v in vals},
                  stats={v: wanted for v in vals})
        if pop:
            kw["weight"] = df[pop].to_numpy(float)
        from ..doors.fields import predict_result_fields
        from ..stata_bridge import dispatch
        names = predict_result_fields("stats", k_text, r_text, "", [],
                                      vals, wanted, decaying=False,
                                      efforting=False)
        buf, cap = _capture()
        with cap:
            res = dispatch("stats", df["x"].to_numpy(float),
                           df["y"].to_numpy(float),
                           provenance=_run_record("stats", df, points),
                           **kw)
        said.extend(_lines(buf))
        order = [n for n in names if n in res] + \
                [n for n in res if n not in names and n not in ("x", "y")]
        return _finish(df, res, order, points, meta.get("crs_epsg"),
                       "stats", kw, said)

    @server.tool(name="equipop_summaries_by_area")
    @guarded
    def equipop_summaries_by_area(
            points: str, areas: str, area_name_field: str = "",
            level_field: str = "", people: str = "",
            count_fields: str = "", value_fields: str = "",
            statistics: str = "mean median", hide_below: str = "",
            points_in_no_area: str = "nearest", snap_within: str = "",
            x_field: str = "", y_field: str = "", points_layer: str = "",
            areas_layer: str = "", with_points: bool = False) -> dict[str, Any]:
        """Tool 1b, Summaries by area: points summarised over polygons
        (wards, tracts, municipalities, counties, which may overlap).
        Per area: N people, Npts, T_ and R_ per count field, and the
        statistics of each value field per person (mean, median, min,
        max, sum, var, sd, range, gini, theil, p10 p25 p75 p90). A
        point on a border counts once, in the first area; a point in
        no area is snapped to the nearest ("nearest") or left out
        ("leave"), within `snap_within` metres if given. `level_field`
        (municipality / county) gives one area per level. `hide_below`:
        areas with fewer people keep N and hide the rest. The areas
        file must be a layer (gpkg, shp, geojson) in the points'
        coordinate system. Results go to a new file next to the areas
        file and, with `with_points`, next to the points file."""
        from ..doors import areasdoor as D
        from ..zones import Areas
        said: list = []
        df, meta = F.read_points(points, points_layer or None,
                                 x_field or None, y_field or None,
                                 said=said)
        rings, names, levels, a_epsg = _read_areas(
            areas, areas_layer or None, area_name_field or None,
            level_field or None)
        if meta.get("crs_epsg") and a_epsg and \
                int(meta["crs_epsg"]) != int(a_epsg):
            raise BadNumber(
                f"The points are in EPSG:{meta['crs_epsg']} and the "
                f"areas in EPSG:{a_epsg}. Save the areas in the points' "
                "system (or the points in the areas') and run again; "
                "the QGIS and Pro tools do this for you.")
        kw = D.parse_boxes(_words(statistics) or None, hide_below,
                           points_in_no_area, snap_within)
        pop = (people or "").strip()
        counts, values = _words(count_fields), _words(value_fields)
        _columns_exist(df, ([pop] if pop else []) + counts + values,
                       "a field", points)
        _numeric(df, ([pop] if pop else []) + counts + values)
        buf, cap = _capture()
        with cap:
            table, pts, rep = D.run(
                df, df["x"].to_numpy(float), df["y"].to_numpy(float),
                Areas(rings), names=names, levels=levels,
                people=pop or None, counts=counts, values=values,
                want_points=bool(with_points), say=said.append, **kw)
        said.extend(_lines(buf))
        texts = D.describe(counts, values, kw["stats"], levels)
        import pandas as pd
        area_table = pd.DataFrame({"Area": names or
                                   [str(j + 1) for j in range(len(table))]})
        if levels is not None:
            area_table["Level"] = levels
        for c in table.columns:
            area_table[c] = table[c].to_numpy()
        out_a = F.new_path(areas, "areas", ".csv")
        area_table.to_csv(out_a, index=False)
        result = {"written_areas": str(out_a), "areas": int(len(table)),
                  "area_columns": F.result_summary(
                      area_table, list(table.columns), texts),
                  "messages": said,
                  "note": ("The areas' results are a table (csv) with "
                           "the area's name; join it to the polygons on "
                           "that name in a GIS, or run tool 1b in QGIS "
                           "or Pro to get the polygons with results.")}
        if pts is not None:
            out = df.copy()
            for c in pts.columns:
                out[c] = pts[c].to_numpy()
            written = F.write_result(out, points, "areas",
                                     epsg=meta.get("crs_epsg"))
            result["written_points"] = str(written)
            result["point_columns"] = F.result_summary(
                out, [c for c in pts.columns
                      if not str(c).startswith("Area")], texts)
        return result

    @server.tool(name="equipop_green_reach")
    @guarded
    def equipop_green_reach(
            points: str, raster: str, hectares: str = "",
            radius: str = "", base: str = "", treatment: str = "",
            value: str = "", cell: str = "", crs: str = "",
            x_field: str = "", y_field: str = "", layer: str = "") -> dict[str, Any]:
        """Tool 3b, Pixels as mass - green reach and share: from every
        point, how far one must go to gather `hectares` of the pixels
        that count (`base`: class codes such as "10 20" or a range
        "0.4 to 1"; empty: every pixel with a value), and optionally
        the hectares and share within a `radius`. `treatment`: the
        pixels among the base to report a share of. `value`: band
        maths such as "ndvi" or "(b4 - b3) / (b4 + b3)"; empty: band 1
        as it is. `crs`: the points' coordinate system when the points
        come from a table without one, such as "EPSG:3006"; the raster
        must be in the same system unless it is in degrees. Needs
        rasterio."""
        try:
            import rasterio
        except ImportError:
            raise BadNumber("Tool 3b needs rasterio on this computer: "
                            "pip install rasterio, then start the server "
                            "again.")
        from ..doors import pixelsdoor as P
        said: list = []
        df, meta = F.read_points(points, layer or None, x_field or None,
                                 y_field or None, said=said)
        rp = F.check_path(raster, "raster")
        with rasterio.open(rp) as src:
            r_crs = src.crs
        people_epsg = meta.get("crs_epsg")
        if crs:
            from pyproj import CRS
            try:
                people_epsg = CRS.from_user_input(crs).to_epsg()
            except Exception:
                raise BadNumber(f'"{crs}" is not a coordinate system I '
                                'can read; give one such as "EPSG:3006".')
        same = True
        if r_crs is not None and not r_crs.is_geographic:
            if people_epsg is None:
                raise BadNumber(
                    "The points come without a coordinate system. Give "
                    'it with crs="EPSG:...", the same as the raster '
                    f"({r_crs}), so the two can be checked against each "
                    "other.")
            same = (r_crs.to_epsg() == int(people_epsg))
        metric = meta.get("unit") in ("metres", None)
        buf, cap = _capture()
        with cap:
            res = P.run(df[["x", "y"]].copy(), raster=str(rp), value=value,
                        base=base, treatment=treatment, hectares=hectares,
                        radius=radius, cell=cell, layer_is_metric=metric,
                        same_crs=same,
                        people_crs=(f"EPSG:{people_epsg}" if people_epsg
                                    else None), say=said.append)
        said.extend(_lines(buf))
        order = [c for c in res.columns if c not in ("x", "y")]
        out = df.copy()
        for c in order:
            out[c] = res[c].to_numpy()
        written = F.write_result(out, points, "green", epsg=people_epsg)
        texts = dict(P.describe(value=value, base=base,
                                treatment=treatment, hectares=hectares,
                                radius=radius))
        return {"written": str(written), "rows": int(len(out)),
                "new_columns": F.result_summary(out, order, texts),
                "messages": said}

    return server


# --------------------------------------------------------- helpers
#: The boxes of each tool this server runs, in the dialogs' order, and
#: the argument each box is here. equipop_help reads the dialog's help
#: text for each.
BOXES = {
    "CountsShares": ("layer", "xfield", "yfield", "pop", "treat", "k",
                     "r", "unit", "model", "halflife"),
    "ValueStatistics": ("layer", "xfield", "yfield", "values",
                        "measures", "pop", "k", "r", "unit"),
    "AreaSummaries": ("areapoints", "areas", "areaname", "arealevel",
                      "areapeople", "areacounts", "areavalues",
                      "areastats", "areahide", "areaoutside",
                      "areasnap", "out_areas", "out_points"),
    "PixelReach": ("layer", "rasters", "value", "base", "treatment",
                   "hectares", "radius", "cell"),
}
ARGUMENT = {
    "layer": "points", "xfield": "x_field", "yfield": "y_field",
    "pop": "people", "treat": "count_fields", "r": "radius",
    "unit": "cell_size", "model": "decay", "halflife": "half_life",
    "values": "value_fields", "measures": "statistics",
    "areapoints": "points", "areaname": "area_name_field",
    "arealevel": "level_field", "areapeople": "people",
    "areacounts": "count_fields", "areavalues": "value_fields",
    "areastats": "statistics", "areahide": "hide_below",
    "areaoutside": "points_in_no_area", "areasnap": "snap_within",
    "out_areas": "(written next to the areas file)",
    "out_points": "with_points",
    "rasters": "raster",
}
NUMBERS = {"1": "CountsShares", "1b": "AreaSummaries",
           "2": "ValueStatistics", "3": "ContinentalRasters",
           "3b": "PixelReach", "4": "SpatialDemography",
           "5": "WorldPopCatalogue", "6": "FetchSelected",
           "7": "Assignment"}


def _tool_key(tool) -> str:
    from ..doors.help import LABELS
    t = str(tool or "").strip()
    if t in LABELS:
        return t
    if t.lower() in NUMBERS:
        return NUMBERS[t.lower()]
    low = t.lower()
    for key, label in LABELS.items():
        if low == label.lower() or low == key.lower() or \
                label.lower().startswith(low + ".") or \
                low in label.lower().split(". ", 1)[-1].lower():
            return key
    raise BadNumber(f'"{tool}" is not an EquiPop tool. Call equipop_tools '
                    "for the list.")


def _read_areas(path, layer, name_field, level_field):
    """A polygon layer -> (rings per area, names, levels, epsg)."""
    p = F.check_path(path, "areas file")
    try:
        import geopandas as gpd
    except ImportError:
        raise BadNumber("Reading the areas needs geopandas on this "
                        "computer: pip install geopandas")
    kw = {"layer": layer} if layer else {}
    try:
        g = gpd.read_file(p, **kw)
    except Exception as exc:
        raise BadNumber(f"{p.name} could not be read: {exc}")
    for f in (name_field, level_field):
        if f and f not in g.columns:
            raise BadNumber(f'"{f}" is not a column of {p.name}. Its '
                            "columns: " + ", ".join(map(str, g.columns)))
    rings = []
    for geom in g.geometry:
        area = []
        if geom is None or geom.is_empty:
            rings.append(area)
            continue
        parts = list(geom.geoms) if geom.geom_type == "MultiPolygon" \
            else [geom]
        for poly in parts:
            if poly.geom_type != "Polygon":
                raise BadNumber(f"{p.name} holds {poly.geom_type} "
                                "geometries; the areas must be polygons.")
            area.append([(float(x), float(y)) for x, y in
                         poly.exterior.coords])
            for hole in poly.interiors:
                area.append([(float(x), float(y)) for x, y in hole.coords])
        rings.append(area)
    names = ([("" if v is None else str(v)) for v in g[name_field]]
             if name_field else None)
    levels = ([("" if v is None else str(v)) for v in g[level_field]]
              if level_field else None)
    epsg = g.crs.to_epsg() if g.crs else None
    return rings, names, levels, epsg


def main(argv=None) -> int:
    """`equipop mcp [--rows]` and `python -m equipop.mcp`: the server
    on stdio, until the assistant closes it."""
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    rows = "--rows" in args or os.environ.get("EQUIPOP_MCP_ROWS") == "1"
    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0
    try:
        import mcp
        del mcp
    except ImportError:
        print("The MCP server needs the mcp package: "
              "pip install \"equipop[mcp]\"", file=sys.stderr)
        return 2
    build_server(rows=rows).run(transport="stdio")
    return 0

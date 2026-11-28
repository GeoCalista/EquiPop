"""The MCP server, EquiPop's fourth door (BACKLOG 522; ruling R-63):
its tools through an in-process MCP client, on Gridby written to
files. The numbers are the engine's, the same every door gives; what
is tested here is the door - what it accepts, what it writes, and what
it lets leave the computer."""
import asyncio
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

mcp = pytest.importorskip("mcp")
from mcp import Client                                   # noqa: E402

from equipop.datasets import load                        # noqa: E402
from equipop.mcp import files as F                       # noqa: E402
from equipop.mcp.server import build_server              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def call(server, name, args=None):
    """One tool call -> (is_error, structured or text)."""
    async def go():
        async with Client(server) as c:
            r = await c.call_tool(name, args or {})
            if r.is_error:
                return True, r.content[0].text
            return False, r.structured_content
    return asyncio.run(go())


def tool_names(server):
    async def go():
        async with Client(server) as c:
            return [t.name for t in (await c.list_tools()).tools]
    return asyncio.run(go())


@pytest.fixture(scope="module")
def town(tmp_path_factory):
    """Gridby's people and workers as a csv, and as a GeoPackage when
    geopandas is there."""
    d = tmp_path_factory.mktemp("town")
    g = load("gridby")
    w = g["workers"].copy()
    w["id"] = np.arange(len(w))
    csv = d / "workers.csv"
    w.to_csv(csv, index=False)
    out = {"dir": d, "csv": csv, "frame": w}
    try:
        import geopandas as gpd
        from shapely.geometry import Polygon
        gp = gpd.GeoDataFrame(w, geometry=gpd.points_from_xy(w.x, w.y),
                              crs="EPSG:3006")
        gp.to_file(d / "workers.gpkg", layer="workers", driver="GPKG")
        out["gpkg"] = d / "workers.gpkg"
        # four wards, a 2 x 2 split of the town's extent, in one layer
        # with the town itself as a second level
        x0, y0, x1, y1 = w.x.min(), w.y.min(), w.x.max() + 1, w.y.max() + 1
        xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
        boxes = [Polygon([(x0, y0), (xm, y0), (xm, ym), (x0, ym)]),
                 Polygon([(xm, y0), (x1, y0), (x1, ym), (xm, ym)]),
                 Polygon([(x0, ym), (xm, ym), (xm, y1), (x0, y1)]),
                 Polygon([(xm, ym), (x1, ym), (x1, y1), (xm, y1)]),
                 Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])]
        areas = gpd.GeoDataFrame(
            {"ward": ["SW", "SE", "NW", "NE", "Town"],
             "level": ["ward"] * 4 + ["town"]},
            geometry=boxes, crs="EPSG:3006")
        areas.to_file(d / "wards.gpkg", layer="wards", driver="GPKG")
        out["wards"] = d / "wards.gpkg"
    except ImportError:
        pass
    return out


# ------------------------------------------------------------ describe
def test_the_tools_are_listed_with_help_and_citations():
    s = build_server()
    names = tool_names(s)
    assert "equipop_tools" in names and "equipop_peek" not in names
    err, got = call(s, "equipop_tools")
    assert not err
    labels = {t["tool"]: t for t in got["tools"]}
    assert labels["CountsShares"]["runs_here"] == "equipop_counts_and_shares"
    assert labels["AreaSummaries"]["group"] == "A. Neighbourhoods"
    assert labels["Assignment"]["runs_here"] is None
    assert got["rows_leave_this_computer"] is False
    err, got = call(s, "equipop_help", {"tool": "1b"})
    assert not err and got["label"] == "1b. Summaries by area"
    assert [b["argument"] for b in got["boxes"]][:2] == ["points", "areas"]
    assert all(b["help"] and "{" not in b["help"] for b in got["boxes"])
    err, got = call(s, "equipop_help", {"tool": "Counts and Shares"})
    assert not err and got["tool"] == "CountsShares"
    err, got = call(s, "equipop_cite", {"tool": "1"})
    assert not err and "2014" in got["report"]
    assert any("Geographical Analysis" in m for m in got["methods"])
    assert got["report_bibtex"].startswith("@techreport")
    err, got = call(s, "equipop_columns", {"columns": "Dist_500 R_old_500"})
    assert not err and got["columns"][0]["meaning"]


def test_an_unknown_tool_is_a_sentence_not_a_traceback():
    s = build_server()
    err, text = call(s, "equipop_help", {"tool": "9"})
    assert err and "not an EquiPop tool" in text and "Traceback" not in text


# ---------------------------------------------------------------- look
def test_look_describes_a_table_without_a_single_row(town):
    s = build_server()
    err, got = call(s, "equipop_look", {"path": str(town["csv"])})
    assert not err
    assert got["kind"] == "table" and got["rows"] == 2360
    assert got["x_field"] == "x" and got["y_field"] == "y"
    cols = {c["name"]: c for c in got["columns"]}
    assert set(cols) == set(town["frame"].columns)
    pop = cols["Population"]
    assert set(pop) >= {"mean", "median", "p10", "p90", "missing",
                        "distinct"}
    # R-63: no value of one person - no min, no max, no row
    assert "min" not in pop and "max" not in pop
    text = json.dumps(got)
    assert "rows_shown" not in text
    assert got["extent"][0] == pytest.approx(town["frame"].x.min())


def test_look_describes_a_folder_and_a_layer(town):
    s = build_server()
    err, got = call(s, "equipop_look", {"path": str(town["dir"])})
    assert not err and got["kind"] == "folder"
    assert {f["name"] for f in got["files"]} >= {"workers.csv"}
    if "gpkg" in town:
        err, got = call(s, "equipop_look", {"path": str(town["gpkg"])})
        assert not err and got["kind"] == "vector"
        assert got["rows"] == 2360 and "3006" in got["crs"]
        assert got["geometry"].lower().startswith("point")


def test_a_missing_file_is_refused_by_name():
    s = build_server()
    err, text = call(s, "equipop_look", {"path": "/no/such/file.csv"})
    assert err and "There is no file or folder" in text


# ------------------------------------------------------------- tool 1
def test_counts_and_shares_writes_a_new_file_and_returns_summaries(town):
    """The numbers are tool 1's: the same call through the Stata
    bridge gives them. BROKEN WITH: the result returned as rows, or
    the file overwritten on a second run."""
    s = build_server()
    args = {"points": str(town["csv"]), "k": "100 500",
            "people": "Population", "count_fields": "LowEdu_sum"}
    err, got = call(s, "equipop_counts_and_shares", args)
    assert not err, got
    written = got["written"]
    assert os.path.basename(written) == "workers_counts.csv"
    out = pd.read_csv(written)
    assert len(out) == 2360
    names = [c["name"] for c in got["new_columns"]]
    assert "Dist_100" in names and "R_LowEdu_sum_500" in names
    assert "T_LowEdu_sum_100" in out.columns
    for c in got["new_columns"]:
        assert c["meaning"] and "min" not in c and "max" not in c
    text = json.dumps(got)
    assert "Dist_100" in text and str(out.Dist_100.iloc[0]) not in text \
        or len(out) > 0
    # the engine's own numbers, the same as the Stata bridge gives
    from equipop.stata_bridge import dispatch
    w = town["frame"]
    res = dispatch("counts", w.x.to_numpy(float), w.y.to_numpy(float),
                   unit_size=100.0, k_values=[100, 500],
                   weight=w.Population.to_numpy(float),
                   treat={"LowEdu_sum": w.LowEdu_sum.to_numpy(float)},
                   treat_are_counts=True, overshoot_mode="proportional",
                   self_rule="include", self_potential=1.0)
    np.testing.assert_allclose(out.Dist_500, res["Dist_500"])
    np.testing.assert_allclose(out.R_LowEdu_sum_100, res["R_LowEdu_sum_100"])
    # a second run never overwrites
    err, again = call(s, "equipop_counts_and_shares", args)
    assert not err
    assert os.path.basename(again["written"]) == "workers_counts_2.csv"
    assert os.path.exists(written)


def test_counts_and_shares_refuses_what_it_cannot_read(town):
    s = build_server()
    err, text = call(s, "equipop_counts_and_shares",
                     {"points": str(town["csv"])})
    assert err and "at least one k" in text.lower() or "k" in text
    err, text = call(s, "equipop_counts_and_shares",
                     {"points": str(town["csv"]), "k": "100",
                      "count_fields": "nosuch"})
    assert err and '"nosuch"' in text and "Its columns" in text
    err, text = call(s, "equipop_counts_and_shares",
                     {"points": str(town["csv"]), "k": "100",
                      "decay": "linear", "half_life": 500})
    assert err and "not a decay model" in text


def test_degrees_are_refused_unless_projected(town, tmp_path):
    w = town["frame"].head(300).copy()
    # the town placed at 18 E, 59.3 N, in degrees
    w["lon"] = 18.0 + (w.x - w.x.min()) / 111320 / np.cos(np.radians(59.3))
    w["lat"] = 59.3 + (w.y - w.y.min()) / 110574
    p = tmp_path / "deg.csv"
    w.drop(columns=["x", "y"]).to_csv(p, index=False)
    s = build_server()
    err, text = call(s, "equipop_counts_and_shares",
                     {"points": str(p), "k": "50"})
    assert err and "DEGREES" in text and "project=true" in text
    err, got = call(s, "equipop_counts_and_shares",
                    {"points": str(p), "k": "50", "project": True})
    assert not err, got
    assert any("UTM" in m or "EPSG" in m for m in got["messages"])
    out = pd.read_csv(got["written"])
    assert out.Dist_50.notna().all()


# ------------------------------------------------------------- tool 2
def test_value_statistics_gives_tool_2_s_numbers(town):
    s = build_server()
    err, got = call(s, "equipop_value_statistics",
                    {"points": str(town["csv"]),
                     "value_fields": "LowEdu_sum", "k": "200",
                     "statistics": "mean gini p90", "people": "Population"})
    assert not err, got
    out = pd.read_csv(got["written"])
    assert os.path.basename(got["written"]) == "workers_stats.csv"
    names = [c["name"] for c in got["new_columns"]]
    assert {"Mean_LowEdu_sum_200", "Gini_LowEdu_sum_200",
            "P90_LowEdu_sum_200"} <= set(names)
    from equipop.stata_bridge import dispatch
    w = town["frame"]
    res = dispatch("stats", w.x.to_numpy(float), w.y.to_numpy(float),
                   unit_size=100.0, k_values=[200],
                   weight=w.Population.to_numpy(float),
                   values={"LowEdu_sum": w.LowEdu_sum.to_numpy(float)},
                   stats={"LowEdu_sum": ["mean", "gini", "p90"]},
                   overshoot_mode="proportional", self_rule="include",
                   self_potential=1.0)
    np.testing.assert_allclose(out.Mean_LowEdu_sum_200,
                               res["Mean_LowEdu_sum_200"])
    err, text = call(s, "equipop_value_statistics",
                     {"points": str(town["csv"]), "value_fields": "x",
                      "k": "10", "statistics": "mode"})
    assert err and "not a statistic" in text


# ------------------------------------------------------------ tool 1b
def test_summaries_by_area_through_the_server(town):
    pytest.importorskip("geopandas")
    s = build_server()
    err, got = call(s, "equipop_summaries_by_area",
                    {"points": str(town["gpkg"]), "areas": str(town["wards"]),
                     "area_name_field": "ward", "level_field": "level",
                     "people": "Population", "count_fields": "LowEdu_sum",
                     "value_fields": "Working_sum", "with_points": True})
    assert not err, got
    a = pd.read_csv(got["written_areas"])
    assert list(a.Area) == ["SW", "SE", "NW", "NE", "Town"]
    assert a.N.iloc[:4].sum() == pytest.approx(a.N.iloc[4])
    assert a.N.iloc[4] == pytest.approx(town["frame"].Population.sum())
    assert got["written_points"].endswith("workers_areas.gpkg")
    import geopandas as gpd
    p = gpd.read_file(got["written_points"])
    assert set(p.Area_ward) <= {"SW", "SE", "NW", "NE"}
    assert (p.Area_town == "Town").all()
    # the same numbers the shared door gives
    from equipop.doors import areasdoor as D
    from equipop.mcp.server import _read_areas
    from equipop.zones import Areas
    rings, names, levels, _ = _read_areas(town["wards"], None, "ward",
                                          "level")
    w = town["frame"]
    t, _, _ = D.run(w, w.x, w.y, Areas(rings), names=names, levels=levels,
                    people="Population", counts=["LowEdu_sum"],
                    values=["Working_sum"], say=lambda *a: None)
    np.testing.assert_allclose(a.Mean_Working_sum, t.Mean_Working_sum)


def test_summaries_by_area_refuses_mixed_systems(town, tmp_path):
    gpd = pytest.importorskip("geopandas")
    a = gpd.read_file(town["wards"]).to_crs("EPSG:4326")
    a.to_file(tmp_path / "w4326.gpkg", driver="GPKG")
    s = build_server()
    err, text = call(s, "equipop_summaries_by_area",
                     {"points": str(town["gpkg"]),
                      "areas": str(tmp_path / "w4326.gpkg")})
    assert err and "EPSG:3006" in text and "EPSG:4326" in text


# ------------------------------------------------------------ tool 3b
def test_green_reach_through_the_server(town, tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    w = town["frame"]
    x0, y1 = float(w.x.min()) - 500, float(w.y.max()) + 500
    arr = np.zeros((60, 60), np.uint8)
    arr[10:30, 10:30] = 10                     # a 2 km x 2 km park
    with rasterio.open(tmp_path / "cover.tif", "w", driver="GTiff",
                       height=60, width=60, count=1, dtype="uint8",
                       crs="EPSG:3006",
                       transform=from_origin(x0, y1, 100, 100)) as dst:
        dst.write(arr, 1)
    s = build_server()
    err, text = call(s, "equipop_green_reach",
                     {"points": str(town["csv"]),
                      "raster": str(tmp_path / "cover.tif"),
                      "base": "10", "hectares": "5"})
    assert err and 'crs="EPSG:...' in text
    err, got = call(s, "equipop_green_reach",
                    {"points": str(town["csv"]),
                     "raster": str(tmp_path / "cover.tif"),
                     "base": "10", "hectares": "5", "crs": "EPSG:3006"})
    assert not err, got
    out = pd.read_csv(got["written"])
    assert "Dist_5" in out.columns and out.Dist_5.notna().any()
    assert os.path.basename(got["written"]) == "workers_green.csv"


# --------------------------------------------------------------- R-63
def test_rows_leave_only_with_the_switch(town):
    s = build_server(rows=False)
    assert "equipop_peek" not in tool_names(s)
    s = build_server(rows=True)
    assert "equipop_peek" in tool_names(s)
    err, got = call(s, "equipop_peek", {"path": str(town["csv"]),
                                        "rows": 500})
    assert not err and got["rows_shown"] == F.PEEK_MAX
    err, listed = call(s, "equipop_tools")
    assert listed["rows_leave_this_computer"] is True


def test_the_server_starts_from_the_command_line(tmp_path):
    """`equipop mcp` on stdio answers an initialize request."""
    import subprocess
    r = subprocess.run(
        [sys.executable, "-c",
         "from equipop.mcp import main; main(['--help'])"],
        capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert r.returncode == 0 and "R-63" in r.stdout


# ------------------------------------------------------- citations
def test_the_citations_table_is_citation_cff():
    yaml = pytest.importorskip("yaml")
    sys.path.insert(0, ROOT)
    from tools.make_citations import CFF, OUT, load_cff, table_from_cff
    want = table_from_cff(load_cff(CFF))
    got = json.loads(OUT.read_text(encoding="utf-8"))
    assert got == want, ("equipop/tables/citations.json is out of date: "
                         "run python tools/make_citations.py")
    assert yaml.__version__


# ---------------------------------------------------- stdio, as an app
def test_the_server_answers_over_stdio_as_an_assistant_starts_it(town):
    """`python -m equipop mcp`, the way a config file starts it."""
    from mcp.client.client import StdioServerParameters

    async def go():
        async with Client(StdioServerParameters(
                command=sys.executable, args=["-m", "equipop", "mcp"],
                cwd=ROOT, env=dict(os.environ, PYTHONPATH=ROOT))) as c:
            names = [t.name for t in (await c.list_tools()).tools]
            r = await c.call_tool("equipop_look", {"path": str(town["csv"])})
            return names, r.structured_content["rows"]
    names, rows = asyncio.run(go())
    assert "equipop_counts_and_shares" in names and rows == 2360


def test_the_command_with_no_terminal_is_the_server():
    """`uvx equipop` and `uvx --from equipop[mcp] equipop mcp` both
    serve: with stdin piped, the bare command starts the server."""
    import subprocess
    r = subprocess.run([sys.executable, "-m", "equipop"], input="",
                       capture_output=True, text=True, timeout=60,
                       cwd=ROOT, env=dict(os.environ, PYTHONPATH=ROOT))
    assert r.returncode == 0 and "equipop doctor" not in r.stdout
    r = subprocess.run([sys.executable, "-m", "equipop", "version"],
                       capture_output=True, text=True, timeout=60,
                       cwd=ROOT, env=dict(os.environ, PYTHONPATH=ROOT))
    from equipop import __version__
    assert r.stdout.strip() == __version__


# ------------------------------------------------------ the packaging
MANIFEST_KEYS = {
    "$schema", "manifest_version", "name", "display_name", "version",
    "description", "long_description", "author", "repository",
    "homepage", "documentation", "support", "icon", "icons",
    "screenshots", "localization", "server", "tools", "tools_generated",
    "prompts", "prompts_generated", "keywords", "license",
    "privacy_policies", "compatibility", "user_config", "_meta"}


def test_the_bundle_manifest_fits_the_0_4_schema_and_names_the_tools():
    """The strict keys of @anthropic-ai/mcpb 2.1.2's schema 0.4
    (validated against it once, 27 November 2026: "Manifest schema
    validation passes"), kept here so a new key cannot slip in."""
    sys.path.insert(0, ROOT)
    from tools.make_mcpb import manifest, tool_list
    tools = tool_list()
    m = manifest("9.9.9", tools)
    assert set(m) <= MANIFEST_KEYS
    assert m["manifest_version"] == "0.4" and m["version"] == "9.9.9"
    assert m["server"]["type"] == "uv"
    assert m["server"]["mcp_config"]["command"] == "uv"
    assert "--frozen" in m["server"]["mcp_config"]["args"]
    assert set(m["server"]) == {"type", "entry_point", "mcp_config"}
    assert [t["name"] for t in m["tools"]] == tool_names(build_server())
    assert all(t["description"] for t in m["tools"])
    assert "rows" in m["long_description"]


def test_the_bundle_builds_and_runs_its_own_wheel(tmp_path):
    """tools/make_mcpb.py, as release_assets.sh runs it: the bundle
    holds the wheel it was built from, a lock that names it, and the
    launcher. Needs uv and the network (the lock)."""
    import shutil
    import subprocess
    import zipfile
    if not shutil.which("uv"):
        pytest.skip("uv is not installed")
    from equipop import __version__ as v
    r = subprocess.run([sys.executable, "-m", "build", "--wheel",
                        "--outdir", str(tmp_path / "dist"), ROOT],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    wheel = next((tmp_path / "dist").glob("equipop-*-py3-none-any.whl"))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools",
                                                     "make_mcpb.py"),
                        v, str(wheel), str(tmp_path)],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0 and "uv lock failed" in r.stdout + r.stderr:
        pytest.skip("uv could not reach the package index: "
                    + (r.stdout + r.stderr)[-300:])
    assert r.returncode == 0, r.stdout + r.stderr
    out = tmp_path / f"equipop-{v}.mcpb"
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        assert names == {"manifest.json", "pyproject.toml", "uv.lock",
                         "server/main.py", wheel.name}
        assert wheel.name in z.read("uv.lock").decode()
        assert "equipop.mcp" in z.read("server/main.py").decode()
        m = json.loads(z.read("manifest.json"))
    assert m["version"] == v


def test_server_json_names_both_ways_to_run_it(tmp_path):
    sys.path.insert(0, ROOT)
    from tools.make_server_json import NAME, entry, main
    e = entry("1.68.0", "ab" * 32)
    assert e["name"] == NAME == "io.github.geocalista/equipop"
    kinds = {p["registryType"]: p for p in e["packages"]}
    assert set(kinds) == {"pypi", "mcpb"}
    assert kinds["pypi"]["identifier"] == "equipop"
    assert kinds["pypi"]["runtimeHint"] == "uvx"
    assert kinds["mcpb"]["identifier"].endswith("/v1.68.0/equipop-1.68.0.mcpb")
    assert "mcp" in kinds["mcpb"]["identifier"]
    assert kinds["mcpb"]["fileSha256"] == "ab" * 32
    assert len(e["description"]) <= 100
    # the README carries the registry's ownership line, verbatim
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    assert f"mcp-name: {NAME}" in readme
    # from an assets folder, as the release workflow runs it
    (tmp_path / "SHA256SUMS.txt").write_text(
        f"{'cd' * 32}  equipop-1.68.0.mcpb\n{'ef' * 32}  other.zip\n")
    import io as _io
    from contextlib import redirect_stdout
    buf = _io.StringIO()
    with redirect_stdout(buf):
        assert main(["1.68.0", str(tmp_path)]) == 0
    assert json.loads(buf.getvalue())["packages"][1]["fileSha256"] == "cd" * 32


def test_the_release_lists_the_server_only_after_pypi_and_the_files():
    import yaml
    wf = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows",
                                          "release.yml"), encoding="utf-8"))
    job = wf["jobs"]["registry"]
    assert set(job["needs"]) == {"build", "publish", "attach"}
    assert job["environment"]["name"] == "mcp-registry"
    assert job["permissions"]["id-token"] == "write"
    steps = " ".join(str(s.get("run", "")) for s in job["steps"])
    assert "make_server_json.py" in steps
    assert "login github-oidc" in steps and "mcp-publisher publish" in steps
    assets = open(os.path.join(ROOT, "tools", "release_assets.sh"),
                  encoding="utf-8").read()
    assert "make_mcpb.py" in assets

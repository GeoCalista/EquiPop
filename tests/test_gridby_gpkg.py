"""Gridby as a GeoPackage for a QGIS or ArcGIS Pro class (17 November
2026, BACKLOG 504). John: Europe, any simple UTM."""
import numpy as np
import pandas as pd
import pytest

gpd = pytest.importorskip("geopandas")
pyproj = pytest.importorskip("pyproj")

from equipop.gridby import CRS, LAYERS, ORIGIN, gridby, write_gridby


@pytest.fixture(scope="module")
def gpkg(tmp_path_factory):
    return write_gridby(tmp_path_factory.mktemp("gridby") / "gridby.gpkg")


def _layer(path, name):
    return gpd.read_file(path, layer=name)


def test_every_layer_is_there_in_utm_33n(gpkg):
    import pyogrio
    names = [n for n, _ in pyogrio.list_layers(gpkg)]
    assert sorted(names) == sorted(LAYERS)
    for name in LAYERS:
        assert _layer(gpkg, name).crs.to_epsg() == 25833


def test_the_town_sits_in_open_sea_between_oland_and_gotland(gpkg):
    """Öland's east coast is near 17.1 E at this latitude and Gotland's
    west coast near 18.1 E; the town spans about 17.55-17.65 E. Moved
    by mistake (a wrong origin, a wrong zone), it would land on
    somebody's real town."""
    to_wgs = pyproj.Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    x0, y0 = ORIGIN
    for dx, dy in ((0, 0), (6000, 0), (0, 4000), (6000, 4000)):
        lon, lat = to_wgs.transform(x0 + dx, y0 + dy)
        assert 17.45 < lon < 17.75 and 57.15 < lat < 57.25, (lon, lat)


def test_the_files_hold_the_same_town(gpkg):
    """Every count, column and coordinate is Gridby's own, shifted by
    ORIGIN and nothing else."""
    g = gridby()
    x0, y0 = ORIGIN
    for name, key in (("people", "people"), ("jobs", "jobs"),
                      ("workers", "workers"), ("workplaces", "workplaces"),
                      ("friction_walk", "friction_walk"),
                      ("friction_drive", "friction_drive"),
                      ("friction_river", "friction")):
        got = _layer(gpkg, name)
        want = g[key].reset_index(drop=True)
        assert np.allclose(got.geometry.x - x0, want.x)
        assert np.allclose(got.geometry.y - y0, want.y)
        for col in want.columns.drop(["x", "y"]):
            assert np.array_equal(got[col].to_numpy(), want[col].to_numpy()), (name, col)
    alt = _layer(gpkg, "altitude")
    top = alt.loc[alt.altitude_m.idxmax()]
    assert (top.geometry.x - x0, top.geometry.y - y0) == (48 * 100 + 50, 30 * 100 + 50)


def test_a_class_rasterizing_the_lines_gets_the_python_tables(gpkg):
    """The QGIS and Pro route: open the network lines, hand the `walk`
    or `drive` field to the barrier tool. EquiPop's own
    features_to_friction on those lines must give exactly the tables
    a Python reader is handed, or two students doing the same exercise
    get two answers. BROKEN WITH: ORIGIN = (654_050, 6_340_000), which
    puts every line on the edge between two squares."""
    from equipop.friction import features_to_friction
    g = gridby()
    x0, y0 = ORIGIN
    net = _layer(gpkg, "network")
    for mode in ("walk", "drive"):
        fr = features_to_friction(net, value_field=mode, unit_size=100.0)
        fr = fr[fr.friction != 0].assign(x=lambda d: d.x - x0,
                                         y=lambda d: d.y - y0)
        fr = fr.sort_values(["x", "y"], ignore_index=True)
        pd.testing.assert_frame_equal(fr, g[f"friction_{mode}"],
                                      check_dtype=False)


# ---------------------------------------------------------------------
# BACKLOG 514 (the external review, finding 6): Gridby never deletes a
# file it did not write. Until 1.66.0 write_gridby removed whatever was
# at the path before writing, so a teacher's own layer was lost, and a
# write failing halfway left nothing.
# ---------------------------------------------------------------------

def _teacher_file(tmp_path):
    """A GeoPackage with a layer of the teacher's own in it."""
    path = tmp_path / "gridby.gpkg"
    gpd.GeoDataFrame({"note": ["my exercise"]},
                     geometry=gpd.points_from_xy([0.0], [0.0]),
                     crs=CRS).to_file(path, layer="my_layer", driver="GPKG")
    return path


def _leftovers(folder):
    return sorted(p.name for p in folder.iterdir() if p.name != "gridby.gpkg")


def test_an_existing_file_is_refused_and_left_as_it_was(tmp_path):
    """BROKEN WITH: the old os.remove() put back - the teacher's file
    is deleted and no error is raised."""
    path = _teacher_file(tmp_path)
    before = path.read_bytes()
    with pytest.raises(FileExistsError) as e:
        write_gridby(path)
    assert str(path) in str(e.value) and "overwrite=True" in str(e.value)
    assert path.read_bytes() == before
    assert _leftovers(tmp_path) == []


def test_overwrite_replaces_it_with_the_whole_town(tmp_path):
    import pyogrio
    path = _teacher_file(tmp_path)
    write_gridby(path, overwrite=True)
    names = sorted(n for n, _ in pyogrio.list_layers(path))
    assert names == sorted(LAYERS)          # the teacher asked for this
    assert _leftovers(tmp_path) == []       # no temporary file left


def test_a_write_failing_halfway_leaves_the_old_file_untouched(
        tmp_path, monkeypatch):
    """BROKEN WITH: writing straight into `path` after removing it -
    the fifth layer's failure leaves a file with four layers, or none."""
    path = _teacher_file(tmp_path)
    before = path.read_bytes()
    real = gpd.GeoDataFrame.to_file
    calls = []

    def fail_on_fifth(self, *a, **k):
        calls.append(k.get("layer"))
        if len(calls) == 5:
            raise OSError("disk full")
        return real(self, *a, **k)

    monkeypatch.setattr(gpd.GeoDataFrame, "to_file", fail_on_fifth)
    with pytest.raises(OSError, match="disk full"):
        write_gridby(path, overwrite=True)
    assert path.read_bytes() == before
    assert _leftovers(tmp_path) == []


def test_a_failed_first_write_leaves_no_half_file(tmp_path, monkeypatch):
    path = tmp_path / "gridby.gpkg"

    def fail(self, *a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(gpd.GeoDataFrame, "to_file", fail)
    with pytest.raises(OSError):
        write_gridby(path)
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


def test_a_layer_missing_from_the_new_file_stops_the_replace(
        tmp_path, monkeypatch):
    """The check before the rename: a writer that silently skipped a
    layer must not replace a good file."""
    path = _teacher_file(tmp_path)
    before = path.read_bytes()
    real = gpd.GeoDataFrame.to_file

    def skip_green(self, *a, **k):
        if k.get("layer") == "green":
            return None
        return real(self, *a, **k)

    monkeypatch.setattr(gpd.GeoDataFrame, "to_file", skip_green)
    with pytest.raises(RuntimeError, match="green"):
        write_gridby(path, overwrite=True)
    assert path.read_bytes() == before

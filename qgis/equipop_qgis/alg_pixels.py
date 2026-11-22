# -*- coding: utf-8 -*-
"""
alg_pixels.py - tool 3b, PIXELS AS MASS: green reach and share, QGIS
side (BACKLOG 509).

The board's first computational target is image analysis (John, 19
November 2026), in the existing plugin and toolbox, with the shared
core in Python. equipop/pixels.py is that core and
equipop/doors/pixelsdoor.py the half both doors call. What is QGIS's
own here is short: reading the people from a layer, reading ONE BAND
of the raster with QGIS's own GDAL, and comparing the two coordinate
systems with QGIS's own objects.

THE PACKAGE NEVER OPENS THE RASTER. It would need rasterio, which a
QGIS install does not have and should not be asked to have (in Pro it
is worse: two GDALs in one Python). The door reads the band and hands
over an array and where it lies.
"""
import os

from qgis.core import (QgsProcessingException,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterRasterLayer,
                       QgsProcessingParameterString)
from qgis.core import Qgis  # BACKLOG 464: scoped enums, QGIS 3.38 to 4.x

import numpy as np

from .base import EquipopAlgorithm

#: A raster QGIS can show but GDAL cannot open as a file (a web
#: service, a virtual layer) is read through QGIS's provider, one value
#: at a time. Fine for a small clip, hopeless for a city at 10 m.
PROVIDER_LIMIT = 4_000_000


class PixelReach(EquipopAlgorithm):
    """Green reach (Dist_k in hectares) and green share around points."""

    EQP_TOOL = "PixelReach"
    OUT = "outfc"

    def name(self):
        return "pixelreach"

    # WRITTEN DOWN, NOT IMPORTED (BACKLOG 218, 78): displayName runs
    # while QGIS builds the toolbox, before the package is known to be
    # there. tests/test_toolset.py holds it to LABELS.
    EQP_LABEL = "3b. Pixels as mass: green reach and share"

    def displayName(self):
        return self.EQP_LABEL

    def initAlgorithm(self, config=None):
        self.add(QgsProcessingParameterFeatureSource(
            "layer", "1. The people - a point layer in metres",
            [Qgis.ProcessingSourceType.VectorPoint]))
        self.add(QgsProcessingParameterRasterLayer(
            "raster", "2. The image or land-cover map (same coordinate "
                      "system as the people)"))
        # v1.66.0, BACKLOG 510: the chain. The value box replaces 1.65.0's
        # band box (a band number still works); base and treatment
        # replace "which pixels count".
        self.add(QgsProcessingParameterString(
            "value", "3. Value of each pixel - a band (1), a formula "
                     "((b8 - b4) / (b8 + b4)) or ndvi(8, 4)",
            defaultValue="1"))
        self.add(QgsProcessingParameterString(
            "base", "4. Base: which pixels count (10 20, or 0,01 to 1; "
                    "empty = all)", optional=True))
        self.add(QgsProcessingParameterString(
            "treatment", "5. Treatment: which of them to look for "
                         "(0,7 to 1; optional)", optional=True))
        self.add(QgsProcessingParameterString(
            "hectares", "6. Hectares to gather, with spaces between "
                        "(1 5 20)", defaultValue="1 5 20", optional=True))
        self.add(QgsProcessingParameterString(
            "radius", "7. Radius in metres, with spaces between (100 200; "
                      "optional)", optional=True))
        self.add(QgsProcessingParameterString(
            "cell", "8. Analysis cell in metres (optional; empty = the "
                    "image's pixel)", optional=True))
        self.add(QgsProcessingParameterFeatureSink(
            self.OUT, "Results"))

    def checkParameterValues(self, parameters, context):
        """The typed boxes refused while the dialog is still open."""
        from equipop.doors.numbers import BadNumber
        from equipop.doors.pixelsdoor import (parse_cell, parse_hectares,
                                              parse_radius, parse_range,
                                              parse_value)
        box = lambda name: self.parameterAsString(parameters, name,
                                                  context)
        try:
            parse_value(box("value"))
            parse_range(box("base"), "base")
            parse_range(box("treatment"), "treatment")
            ks = parse_hectares(box("hectares"))
            rs = parse_radius(box("radius"))
            parse_cell(box("cell"))
            if not ks and not rs:
                return False, ("Give hectares to gather (such as 1 5 20), "
                               "a radius, or both.")
        except BadNumber as bad:
            return False, str(bad)
        return super().checkParameterValues(parameters, context)

    # -----------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):
        from equipop.doors.numbers import BadNumber
        from equipop.doors.pixelsdoor import (bands_needed, result_names,
                                              run)
        from equipop.doors.report import stage

        from .base import check_versions

        ch = self.channel(feedback)
        check_versions(ch)
        source = self.parameterAsSource(parameters, "layer", context)
        if source is None:
            raise QgsProcessingException("Box 1: choose the people "
                                         "layer.")
        raster = self.parameterAsRasterLayer(parameters, "raster",
                                             context)
        if raster is None:
            raise QgsProcessingException("Box 2: choose the raster.")
        boxes = {name: self.parameterAsString(parameters, name, context)
                 for name in ("value", "base", "treatment", "hectares",
                              "radius", "cell")}
        try:
            names = result_names(boxes["hectares"], boxes["radius"],
                                 boxes["treatment"])
            wanted = bands_needed(boxes["value"])
        except BadNumber as bad:
            raise QgsProcessingException(str(bad))
        self.check_target(parameters, names, feedback)

        # Checked on the layer AS IT IS, before reading: the shared
        # reader would quietly reproject a layer in degrees to UTM,
        # and the raster - still in its own system - would then be
        # refused with advice to project it to the wrong one.
        import pandas as pd

        from .base import _crs_unit_name
        crs = source.sourceCrs()
        # metres, or a unit the system does not state; a projection
        # in FEET is refused - a pixel's hectares are its width times
        # its height in the system's units (BACKLOG 160)
        metric = (not crs.isGeographic()
                  and _crs_unit_name(crs) in ("metres", "map units"))
        same = same_crs(raster.crs(), crs)
        if not (metric and same):
            if metric:
                ch.warning(f"The people are in {crs.authid()}, the "
                           f"raster in {raster.crs().authid()}.")
            try:
                run(pd.DataFrame({"x": [], "y": []}), None,
                    layer_is_metric=metric, same_crs=same, say=ch.info,
                    **boxes)
            except BadNumber as bad:
                raise QgsProcessingException(str(bad))
        with stage(ch, "reading the people"):
            pts = self.read_points(source, feedback)
        with stage(ch, "reading the raster"):
            payload = read_bands(raster, wanted, ch)
        people = pd.DataFrame({"x": pts.data["x"], "y": pts.data["y"]})
        try:
            with stage(ch, "calculating"):
                res = run(people, payload, say=ch.info, **boxes)
        except BadNumber as bad:
            raise QgsProcessingException(str(bad))
        order = [c for c in res.columns if c not in ("x", "y")]
        result = {c: res[c].to_numpy(float) for c in order}
        with stage(ch, "writing output"):
            dest = self.write(parameters, context, source, result, order,
                              feedback, descriptions=_descriptions(order))
        return {self.OUT: dest}


def same_crs(a, b):
    """The same system: equal objects, or the same authority code. A
    GeoTIFF and a GeoPackage can carry one system in two spellings of
    WKT; refusing them as different would send a person to warp a
    raster that is already right."""
    try:
        if a == b:
            return True
        ida, idb = a.authid(), b.authid()
        return bool(ida) and ida == idb
    except Exception:
        return False


def _descriptions(order):
    """One sentence per column, given to each field as its alias."""
    out = {}
    for c in order:
        what, _, k = c.partition("_")
        k = k.replace("_", ".")
        if what == "Dist":
            out[c] = f"metres to gather {k} ha of base"
        elif what == "T" and not k.startswith("r"):
            out[c] = f"hectares of treatment among the nearest {k} ha"
        elif what == "R" and not k.startswith("r"):
            out[c] = f"share of treatment among the nearest {k} ha (0-1)"
        elif what == "B":
            out[c] = f"hectares of base within {k[1:]} m"
        elif what == "T":
            out[c] = f"hectares of treatment within {k[1:]} m"
        elif what == "R":
            out[c] = (f"share of treatment in the base within {k[1:]} m "
                      "(0-1)")
    return out


def read_bands(raster, bands, ch):
    """The bands a value box needs, of a QGIS raster layer, as the
    payload pixelsdoor.run takes: {"bands": {n: array}}, the west and
    north edges, the pixel size, each band's nodata, and whether the
    coordinates are degrees.

    GDAL first - every QGIS has it, and it reads a file in one call.
    Through QGIS's provider otherwise (a raster that is not a file),
    which reads one value at a time and is refused above
    PROVIDER_LIMIT pixels rather than left to run for an hour.
    """
    geographic = bool(raster.crs().isGeographic())
    path = str(raster.source() or "").split("|")[0]
    ds = None
    if path and os.path.exists(path):
        try:
            from osgeo import gdal
            ds = gdal.Open(path)
        except ImportError:                          # pragma: no cover
            ds = None
    if ds is not None:
        gt = ds.GetGeoTransform()
        if gt[2] or gt[4]:
            raise QgsProcessingException(
                "The raster is rotated. Warp it to a north-up grid "
                "first (Raster > Projections > Warp).")
        _check_count(ds.RasterCount, bands)
        arrays, nodata = {}, {}
        for b in bands:
            band = ds.GetRasterBand(b)
            arrays[b] = band.ReadAsArray()
            nodata[b] = band.GetNoDataValue()
        ch.info(f"Raster read by GDAL: band(s) "
                f"{', '.join(map(str, bands))} of {ds.RasterCount}, "
                f"{ds.RasterYSize:,} x {ds.RasterXSize:,} pixels of "
                f"{gt[1]:g} x {abs(gt[5]):g}.")
        return {"bands": arrays, "x_min": gt[0], "y_max": gt[3],
                "cell_w": gt[1], "cell_h": abs(gt[5]),
                "nodata": nodata, "geographic": geographic}
    w, h = raster.width(), raster.height()
    if w * h > PROVIDER_LIMIT:
        raise QgsProcessingException(
            f"The raster is {w:,} x {h:,} pixels and is not a file "
            "GDAL can open, so QGIS would read it one value at a time. "
            "Save it as a GeoTIFF (right-click > Export > Save As) and "
            "run again on that.")
    provider = raster.dataProvider()
    _check_count(raster.bandCount(), bands)
    ext = raster.extent()
    arrays, nodata = {}, {}
    for b in bands:
        block = provider.block(b, ext, w, h)
        arrays[b] = np.array([[block.value(r, c) for c in range(w)]
                              for r in range(h)], dtype=float)
        nodata[b] = provider.sourceNoDataValue(b)
    ch.info(f"Raster read through QGIS: band(s) "
            f"{', '.join(map(str, bands))}, {h:,} x {w:,} pixels.")
    return {"bands": arrays, "x_min": float(ext.xMinimum()),
            "y_max": float(ext.yMaximum()),
            "cell_w": float(ext.width()) / w,
            "cell_h": float(ext.height()) / h,
            "nodata": nodata, "geographic": geographic}


def _check_count(count, bands):
    missing = [b for b in bands if b > count]
    if missing:
        raise QgsProcessingException(
            f"The raster has {count} band{'s' if count != 1 else ''}; "
            f"band {missing[0]} does not exist.")

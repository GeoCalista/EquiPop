# -*- coding: utf-8 -*-
"""
alg_areas.py - tool 1b, SUMMARIES BY AREA, QGIS side (BACKLOG 521;
rulings R-61 and R-62).

The half both doors share is equipop/doors/areasdoor.py, and the
geometry is equipop/zones.py. What is QGIS's own here: reading the
points (in degrees they are placed in metres, as every tool does), the
areas in the same system by QGIS's own transform, and writing the areas
- and, if asked, the points - back with their results.
"""
from qgis.core import (Qgis, QgsCoordinateTransform, QgsGeometry,
                       QgsProcessingException, QgsProcessingParameterEnum,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterField,
                       QgsProcessingParameterString, QgsProject,
                       QgsWkbTypes)

import numpy as np

from .base import EquipopAlgorithm


#: the layer's distance unit, as the messages say it (the 1.67.0
#: review: a 50-foot snap was reported as "50 m away")
_UNIT_SHORT = {"metres": "m", "map units": "map units", "feet": "ft",
               "US survey feet": "ft (US)", "kilometres": "km",
               "yards": "yd", "miles": "mi", "degrees": "degrees"}


class AreaSummaries(EquipopAlgorithm):
    """Points summarised over areas: wards, tracts, municipalities."""

    EQP_TOOL = "AreaSummaries"
    EQP_GROUP = "A. Neighbourhoods"
    OUT = "out_areas"

    def name(self):
        return "areasummaries"

    # WRITTEN DOWN, NOT IMPORTED (BACKLOG 218, 78); tests hold it to
    # equipop.doors.help.LABELS, and the choices below to areasdoor.
    EQP_LABEL = "1b. Summaries by area"

    def displayName(self):
        return self.EQP_LABEL

    STAT_LABELS = ("Mean", "Median", "Minimum", "Maximum", "Sum",
                   "Variance", "Standard deviation", "Range", "Gini",
                   "Theil", "10th percentile", "25th percentile",
                   "75th percentile", "90th percentile")
    OUTSIDE_LABELS = ("Snapped to the nearest area (default)",
                      "Left out, and counted in the messages")

    def initAlgorithm(self, config=None):
        self.add(QgsProcessingParameterFeatureSource(
            "areapoints", "1. The points - people, addresses, grid "
                          "centres, or a tool's output",
            [Qgis.ProcessingSourceType.VectorPoint]))
        self.add(QgsProcessingParameterFeatureSource(
            "areas", "2. The areas - wards, tracts, municipalities (may "
                     "overlap)",
            [Qgis.ProcessingSourceType.VectorPolygon]))
        self.add(QgsProcessingParameterField(
            "areaname", "3. The field that names each area (optional)",
            parentLayerParameterName="areas", optional=True))
        self.add(QgsProcessingParameterField(
            "arealevel", "4. Level field - which areas belong together, "
                         "when they overlap (optional)",
            parentLayerParameterName="areas", optional=True))
        self.add(QgsProcessingParameterField(
            "areapeople", "5. People per point (empty = one each)",
            parentLayerParameterName="areapoints",
            type=Qgis.ProcessingFieldParameterDataType.Numeric,
            optional=True))
        self.add(QgsProcessingParameterField(
            "areacounts", "6. Count fields to sum and share (optional)",
            parentLayerParameterName="areapoints",
            type=Qgis.ProcessingFieldParameterDataType.Numeric,
            allowMultiple=True, optional=True))
        self.add(QgsProcessingParameterField(
            "areavalues", "7. Value fields to summarise (optional)",
            parentLayerParameterName="areapoints",
            type=Qgis.ProcessingFieldParameterDataType.Numeric,
            allowMultiple=True, optional=True))
        self.add(QgsProcessingParameterEnum(
            "areastats", "8. Statistics of the value fields",
            options=list(self.STAT_LABELS), allowMultiple=True,
            defaultValue=[0, 1], optional=True))
        self.add(QgsProcessingParameterString(
            "areahide", "9. Hide areas with fewer than ... people "
                        "(empty = hide none)", optional=True))
        self.add(QgsProcessingParameterEnum(
            "areaoutside", "10. Points in no area",
            options=list(self.OUTSIDE_LABELS), defaultValue=0))
        self.add(QgsProcessingParameterString(
            "areasnap", "11. Snap only within ... metres (empty = any "
                        "distance)", optional=True))
        self.add(QgsProcessingParameterFeatureSink(
            "out_areas", "The areas, with their results"))
        self.add(QgsProcessingParameterFeatureSink(
            "out_points", "The points, with their area's results "
                          "(optional)", optional=True,
            createByDefault=False))

    def _boxes(self, parameters, context):
        from equipop.doors.areasdoor import OUTSIDE_KEYS, STAT_KEYS
        ticked = self.parameterAsEnums(parameters, "areastats", context)
        choice = self.parameterAsEnum(parameters, "areaoutside", context)
        return dict(stats=[STAT_KEYS[int(i)] for i in (ticked or [])],
                    min_people=self.parameterAsString(
                        parameters, "areahide", context),
                    outside=OUTSIDE_KEYS[int(choice or 0)],
                    snap_within=self.parameterAsString(
                        parameters, "areasnap", context))

    def checkParameterValues(self, parameters, context):
        """The typed boxes refused while the dialog is still open."""
        from equipop.doors.areasdoor import parse_boxes
        from equipop.doors.numbers import BadNumber
        try:
            parse_boxes(**self._boxes(parameters, context))
        except BadNumber as bad:
            return False, str(bad)
        return super().checkParameterValues(parameters, context)

    # -----------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):
        import pandas as pd
        from equipop.doors.areasdoor import describe, parse_boxes, run
        from equipop.doors.numbers import BadNumber
        from equipop.doors.report import stage
        from equipop.zones import Areas

        from .alg_pixels import same_crs
        from .barriers import _paths_of
        from .base import _crs_unit_name, check_versions

        ch = self.channel(feedback)
        check_versions(ch)
        src_p = self.parameterAsSource(parameters, "areapoints", context)
        src_a = self.parameterAsSource(parameters, "areas", context)
        if src_p is None:
            raise QgsProcessingException("Box 1: choose the points "
                                         "layer.")
        if src_a is None:
            raise QgsProcessingException("Box 2: choose the areas layer.")
        try:
            kw = parse_boxes(**self._boxes(parameters, context))
        except BadNumber as bad:
            raise QgsProcessingException(str(bad))
        name_f = self.parameterAsString(parameters, "areaname", context)
        level_f = self.parameterAsString(parameters, "arealevel", context)
        people_f = self.parameterAsString(parameters, "areapeople",
                                          context)
        counts = list(self.parameterAsStrings(parameters, "areacounts",
                                              context) or [])
        values = list(self.parameterAsStrings(parameters, "areavalues",
                                              context) or [])
        if QgsWkbTypes.geometryType(src_a.wkbType()) != \
                Qgis.GeometryType.Polygon:
            raise QgsProcessingException(
                "Box 2 takes POLYGONS - the areas to summarise over.")

        with stage(ch, "reading the points"):
            po = self.read_points(src_p, feedback)
            feats_p = self._features
        work = self.working_crs
        unit = _crs_unit_name(work)
        if unit not in ("metres", "map units") and \
                kw["snap_within"] is not None:
            raise QgsProcessingException(
                f"The points are in {unit}, and 'snap only within' is "
                "read in metres. Leave that box empty, or save the "
                "points in a system in metres.")
        with stage(ch, "reading the areas"):
            feats_a = list(src_a.getFeatures())
            tr = None
            if not same_crs(src_a.sourceCrs(), work):
                ctx = (context.transformContext() if context is not None
                       else QgsProject.instance().transformContext())
                tr = QgsCoordinateTransform(src_a.sourceCrs(), work, ctx)
                ch.info(f"The areas are in {src_a.sourceCrs().authid()}; "
                        f"they are placed in the points' system "
                        f"({work.authid()}) by QGIS for this run. The "
                        "layer itself is not changed.")
            rings = []
            for f in feats_a:
                g = f.geometry()
                if g is None or g.isEmpty():
                    rings.append([])
                    continue
                if tr is not None:
                    g = QgsGeometry(g)
                    g.transform(tr)
                rings.append([r for part in _paths_of(g) for r in part])
            # without a name field the areas are numbered 1, 2, 3 in
            # the layer's order - in Pro too; a feature id is not (a
            # shapefile counts from 0, a GeoPackage from 1)
            names = ([("" if f[name_f] is None else str(f[name_f]))
                      for f in feats_a] if name_f else None)
            levels = ([("" if f[level_f] is None else str(f[level_f]))
                       for f in feats_a] if level_f else None)
        # one row per point even with every optional field blank: a
        # frame built from no columns has no rows, and 1.67.0 then said
        # "The points layer has no points" (the 1.67.0 review)
        n_pts = len(po.data["x"])
        frame = pd.DataFrame(index=pd.RangeIndex(n_pts))
        for c in [people_f] + counts + values:
            if c:
                frame[c] = pd.to_numeric(pd.Series(list(po.data[c])),
                                         errors="coerce").to_numpy()
        want_points = parameters.get("out_points") not in (None, "")
        try:
            with stage(ch, "calculating"):
                table, pts, _ = run(
                    frame, np.asarray(po.data["x"], float),
                    np.asarray(po.data["y"], float), Areas(rings),
                    names=names, levels=levels, people=people_f or None,
                    counts=counts, values=values,
                    want_points=want_points, say=ch.info,
                    unit=_UNIT_SHORT.get(unit, unit), **kw)
        except BadNumber as bad:
            raise QgsProcessingException(str(bad))
        texts = describe(counts, values, kw["stats"], levels)
        out = {}
        with stage(ch, "writing output"):
            order = list(table.columns)
            out["out_areas"] = self.write(
                parameters, context, src_a,
                {c: table[c].to_numpy(float) for c in order}, order,
                feedback, descriptions=texts, out="out_areas",
                features=feats_a)
            if pts is not None:
                order = list(pts.columns)
                words = [c for c in order
                         if not pd.api.types.is_numeric_dtype(pts[c])]
                out["out_points"] = self.write(
                    parameters, context, src_p,
                    {c: (pts[c].to_numpy(object) if c in words
                         else pts[c].to_numpy(float)) for c in order},
                    order, feedback, descriptions=texts, out="out_points",
                    features=feats_p, text_columns=words)
        return out

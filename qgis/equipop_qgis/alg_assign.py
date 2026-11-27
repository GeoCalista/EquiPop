# -*- coding: utf-8 -*-
"""
alg_assign.py - tool 7, WHO GOES WHERE: destinations that fill up, QGIS
side (machine 7, step 1; BACKLOG 515; ruling R-56).

The engine is equipop/assign.py and the half both doors share is
equipop/doors/assigndoor.py. What is QGIS's own here: reading two point
layers and their fields, checking they share one system in metres, and
writing three layers back - the people and the destinations with their
results, and the trips of the first run as lines.
"""
from qgis.core import (Qgis, QgsFeature, QgsField, QgsFields,
                       QgsGeometry, QgsPointXY, QgsProcessingException,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterField,
                       QgsProcessingParameterString)

from qgis.PyQt.QtCore import QMetaType    # QGIS 3.38+ (v1.29.3)

import numpy as np

from .base import EquipopAlgorithm


class Assignment(EquipopAlgorithm):
    """Who goes where when destinations fill up."""

    EQP_TOOL = "Assignment"
    EQP_GROUP = "F. Simulation"
    OUT = "out_origins"

    def name(self):
        return "assignment"

    # WRITTEN DOWN, NOT IMPORTED (BACKLOG 218, 78); tests hold it to
    # equipop.doors.help.LABELS.
    EQP_LABEL = "7. Who goes where: destinations that fill up"

    def displayName(self):
        return self.EQP_LABEL

    # WRITTEN DOWN, NOT IMPORTED, like the label: the dialog is built
    # before the package is known to be there. tests/test_assign_doors
    # holds them to equipop.doors.assigndoor.METHOD_LABELS.
    METHOD_LABELS = (
        "Random order: the nearest with room",
        "Random order: drawn by distance decay",
        "Closest first: no randomness",
        "Flows: the pressure on each destination (capacity ignored)",
    )

    def initAlgorithm(self, config=None):
        METHOD_LABELS = self.METHOD_LABELS
        self.add(QgsProcessingParameterFeatureSource(
            "origins", "1. The people - a point layer in metres",
            [Qgis.ProcessingSourceType.VectorPoint]))
        self.add(QgsProcessingParameterField(
            "peoplefield", "2. How many live at each point (empty = one "
                           "each)", parentLayerParameterName="origins",
            type=Qgis.ProcessingFieldParameterDataType.Numeric,
            optional=True))
        self.add(QgsProcessingParameterFeatureSource(
            "dests", "3. The destinations - a point layer, same system",
            [Qgis.ProcessingSourceType.VectorPoint]))
        self.add(QgsProcessingParameterField(
            "capfield", "4. How many each destination takes (empty = no "
                        "limit)", parentLayerParameterName="dests",
            type=Qgis.ProcessingFieldParameterDataType.Numeric,
            optional=True))
        self.add(QgsProcessingParameterEnum(
            "choose", "5. How people choose", options=list(METHOD_LABELS),
            defaultValue=0))
        self.add(QgsProcessingParameterString(
            "decayhalf", "6. Half-life in metres (for distance decay and "
                         "flows)", optional=True))
        self.add(QgsProcessingParameterString(
            "farthest", "7. Farthest anyone goes, in metres (empty = no "
                        "limit)", optional=True))
        self.add(QgsProcessingParameterString(
            "runs", "8. Runs - the random queue drawn this many times",
            defaultValue="20", optional=True))
        self.add(QgsProcessingParameterString(
            "speed", "9. Speed in km/h, for minutes (5 walking, 15 "
                     "cycling)", defaultValue="5", optional=True))
        self.add(QgsProcessingParameterString(
            "groupsize", "Group size - people who move together in the "
                         "queue", defaultValue="10", optional=True),
            advanced=True)
        self.add(QgsProcessingParameterString(
            "runseed", "Seed - the same seed gives the same numbers",
            defaultValue="1", optional=True), advanced=True)
        self.add(QgsProcessingParameterFeatureSink(
            "out_origins", "The people, with their results"))
        self.add(QgsProcessingParameterFeatureSink(
            "out_dests", "The destinations, with their load"))
        self.add(QgsProcessingParameterFeatureSink(
            "out_trips", "The trips of the first run (lines)"))

    def _boxes(self, parameters, context):
        from equipop.doors.assigndoor import METHOD_KEYS
        b = {n: self.parameterAsString(parameters, n, context)
             for n in ("decayhalf", "farthest", "groupsize", "runs",
                       "runseed", "speed")}
        choice = self.parameterAsEnum(parameters, "choose", context)
        return dict(method=METHOD_KEYS[int(choice or 0)],
                    half_life=b["decayhalf"], farthest=b["farthest"],
                    group_size=b["groupsize"], runs=b["runs"],
                    seed=b["runseed"], speed=b["speed"])

    def checkParameterValues(self, parameters, context):
        """The typed boxes refused while the dialog is still open."""
        from equipop.doors.assigndoor import parse_boxes
        from equipop.doors.numbers import BadNumber
        try:
            parse_boxes(**self._boxes(parameters, context))
        except BadNumber as bad:
            return False, str(bad)
        return super().checkParameterValues(parameters, context)

    # -----------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):
        from equipop.doors.assigndoor import describe, run, tables
        from equipop.doors.numbers import BadNumber
        from equipop.doors.report import stage

        from .alg_pixels import same_crs
        from .base import _crs_unit_name, check_versions

        ch = self.channel(feedback)
        check_versions(ch)
        src_o = self.parameterAsSource(parameters, "origins", context)
        src_d = self.parameterAsSource(parameters, "dests", context)
        if src_o is None:
            raise QgsProcessingException("Box 1: choose the people "
                                         "layer.")
        if src_d is None:
            raise QgsProcessingException("Box 3: choose the destinations "
                                         "layer.")
        boxes = self._boxes(parameters, context)
        pf = self.parameterAsString(parameters, "peoplefield", context)
        cf = self.parameterAsString(parameters, "capfield", context)

        # both layers AS THEY ARE: one system, in metres - checked
        # before anything is read, so nothing is reprojected behind the
        # person's back and two layers never end up in two UTM zones
        import pandas as pd
        crs = src_o.sourceCrs()
        metric = (not crs.isGeographic()
                  and _crs_unit_name(crs) in ("metres", "map units"))
        same = same_crs(src_d.sourceCrs(), crs)
        if not (metric and same):
            try:
                run(pd.DataFrame({"x": [0.0], "y": [0.0]}),
                    pd.DataFrame({"x": [0.0], "y": [0.0]}),
                    layer_is_metric=metric, same_crs=same, say=ch.info,
                    **boxes)
            except BadNumber as bad:
                raise QgsProcessingException(str(bad))
        with stage(ch, "reading the people"):
            po = self.read_points(src_o, feedback)
            feats_o = self._features
        with stage(ch, "reading the destinations"):
            pd_ = self.read_points(src_d, feedback)
            feats_d = self._features
        people = np.asarray(po.data[pf], float) if pf else None
        cap = np.asarray(pd_.data[cf], float) if cf else None
        try:
            with stage(ch, "calculating"):
                a = run(pd.DataFrame({"x": po.data["x"],
                                      "y": po.data["y"]}),
                        pd.DataFrame({"x": pd_.data["x"],
                                      "y": pd_.data["y"]}),
                        people=people, capacity=cap, say=ch.info, **boxes)
        except BadNumber as bad:
            raise QgsProcessingException(str(bad))
        from equipop.doors.assigndoor import parse_boxes
        kw = parse_boxes(**boxes)
        t = tables(a, cap is not None, kw["speed_kmh"])
        say = describe(a.method, a.runs, cap is not None, kw["speed_kmh"])
        out = {}
        with stage(ch, "writing output"):
            for key, src, feats, frame in (
                    ("out_origins", src_o, feats_o, t["origins"]),
                    ("out_dests", src_d, feats_d, t["destinations"])):
                order = list(frame.columns)
                layer = "origins" if key == "out_origins" else \
                    "destinations"
                out[key] = self.write(
                    parameters, context, src,
                    {c: frame[c].to_numpy(float) for c in order}, order,
                    feedback, descriptions=dict(say[layer]), out=key,
                    features=feats)
            out["out_trips"] = self._write_trips(
                parameters, context, crs, t["trips"], po.data, pd_.data,
                dict(say["trips"]), ch)
        return out

    def _write_trips(self, parameters, context, crs, trips, o, d, texts,
                     ch):
        fields = QgsFields()
        for name in ("Origin", "Dest"):
            f = QgsField(name, QMetaType.Type.LongLong)
            f.setAlias(texts.get(name, ""))
            fields.append(f)
        for name in ("People", "Metres", "Minutes"):
            f = QgsField(name, QMetaType.Type.Double)
            f.setAlias(texts.get(name, ""))
            fields.append(f)
        sink, dest = self.parameterAsSink(
            parameters, "out_trips", context, fields,
            Qgis.WkbType.LineString, crs)
        if sink is None:
            raise QgsProcessingException(
                "No trips layer was created - choose a destination for "
                "it.")
        ox, oy = np.asarray(o["x"], float), np.asarray(o["y"], float)
        dx, dy = np.asarray(d["x"], float), np.asarray(d["y"], float)
        written = 0
        for row in trips.itertuples(index=False):
            i, j = int(row.Origin) - 1, int(row.Dest) - 1
            nf = QgsFeature(fields)
            nf.setGeometry(QgsGeometry.fromPolylineXY(
                [QgsPointXY(ox[i], oy[i]), QgsPointXY(dx[j], dy[j])]))
            nf.setAttributes([int(row.Origin), int(row.Dest),
                              float(row.People), float(row.Metres),
                              float(row.Minutes)])
            if sink.addFeature(nf) is not False:
                written += 1
        if written != len(trips):
            raise QgsProcessingException(
                f"The trips layer kept only {written:,} of "
                f"{len(trips):,} lines. Try a GeoPackage destination.")
        ch.info(f"Wrote {written:,} trips (the first run) as lines.")
        return dest

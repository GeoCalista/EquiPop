# -*- coding: utf-8 -*-
"""EquiPop for QGIS - bespoke k-nearest neighbourhoods."""
__version__ = "1.68.0"


def classFactory(iface):
    from .plugin import EquipopPlugin
    return EquipopPlugin(iface)

# -*- coding: utf-8 -*-
"""When rasterio cannot be imported, the message says why (issue #7).

A Python that cannot FIND rasterio is told which Python it is, since
QGIS, Pro, Stata and a development environment are four Pythons. A
rasterio that is found but cannot LOAD (a DLL, a version clash) passes
on the real error instead of advising a reinstall.
"""
import builtins
import sys

import pytest

from equipop import rasterfolder


def _fail_import_of_rasterio(monkeypatch, error):
    real = builtins.__import__

    def fake(name, *args, **kwargs):
        if name == "rasterio":
            raise error
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake)


def test_a_missing_rasterio_names_the_python_that_looked(monkeypatch):
    _fail_import_of_rasterio(monkeypatch, ModuleNotFoundError(
        "No module named 'rasterio'", name="rasterio"))
    with pytest.raises(ImportError) as caught:
        rasterfolder.load_folder(["nowhere"])
    assert sys.executable in str(caught.value)
    assert "pip install rasterio" in str(caught.value)


def test_a_rasterio_that_will_not_load_says_why(monkeypatch):
    _fail_import_of_rasterio(monkeypatch, ImportError(
        "DLL load failed while importing _base"))
    with pytest.raises(ImportError) as caught:
        rasterfolder.load_folder(["nowhere"])
    assert "could not be loaded" in str(caught.value)
    assert "DLL load failed while importing _base" in str(caught.value)
"""
bandmath.py - one value per pixel, from one band or a formula over the
bands (BACKLOG 510).

John, 21 November 2026: "perhaps we could allow for a band calculator -
where we can generate indexes using mathematical expressions, and then
use the result in our expressions?" Tool 3b's value box takes:

    1                       band 1 as it is (the default)
    (b8 - b4) / (b8 + b4)   a formula over band numbers
    ndvi(8, 4)              a named index, with ITS band numbers given

THE BAND NUMBERS ARE THE FILE'S, NOT THE SATELLITE'S. A full Sentinel-2
L2A stack holds B08 as band 8, but a download of only B04 and B08 holds
them as bands 1 and 2 - so ndvi(2, 1). That is why the named indices
take their bands as arguments instead of guessing them from a sensor.

    ndvi(nir, red)     (nir - red) / (nir + red)          vegetation
    ndwi(green, nir)   (green - nir) / (green + nir)      open water
    ndbi(swir, nir)    (swir - nir) / (swir + nir)        built-up land
    savi(nir, red)     1.5 (nir - red) / (nir + red + 0.5)
                       vegetation where soil shows; needs reflectance
                       from 0 to 1 (Sentinel-2 L2A digital numbers are
                       reflectance x 10000: divide them first)

A FORMULA IS READ, NEVER RUN. It is parsed into a tree and every node is
checked against a short list - numbers, b<n>, + - * / **, brackets,
abs(), sqrt() and the four indices. Nothing else, no names, no
attributes, no Python. A formula is at most 300 characters.

Division by zero, or anything else that is not a finite number, gives
NO VALUE - the pixel is treated as nodata. Arithmetic runs in float32: a
13-band Sentinel-2 tile is 1.6 GB of float32 and twice that in float64.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass

import numpy as np

__all__ = ["Formula", "FormulaError", "parse", "evaluate", "INDICES",
           "MAX_LENGTH"]

MAX_LENGTH = 300

#: name -> (the bands it takes, in order; what it computes)
INDICES = {
    "ndvi": (("nir", "red"), "(nir - red) / (nir + red)"),
    "ndwi": (("green", "nir"), "(green - nir) / (green + nir)"),
    "ndbi": (("swir", "nir"), "(swir - nir) / (swir + nir)"),
    "savi": (("nir", "red"), "1.5 (nir - red) / (nir + red + 0.5)"),
}
_FUNCTIONS = {"abs": 1, "sqrt": 1}
_BAND = re.compile(r"^[bB](\d+)$")
_OPS = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply,
        ast.Div: np.divide, ast.Pow: np.power}


class FormulaError(ValueError):
    """A value box that cannot be read - with a sentence saying why."""


@dataclass(frozen=True)
class Formula:
    text: str            # as typed (tidied), for the run log
    tree: ast.AST | None  # None = a single band, as it is
    bands: tuple          # band numbers it reads, sorted, from 1

    @property
    def single_band(self):
        return self.tree is None


def parse(text) -> Formula:
    """The value box -> a Formula. '' or None is band 1."""
    t = "" if text is None else str(text).strip()
    if t == "":
        return Formula("1", None, (1,))
    if re.fullmatch(r"\d+", t):
        b = int(t)
        if b < 1:
            raise FormulaError("Bands are counted from 1.")
        return Formula(t, None, (b,))
    if len(t) > MAX_LENGTH:
        raise FormulaError(f"A formula is at most {MAX_LENGTH} "
                           "characters.")
    try:
        tree = ast.parse(t, mode="eval")
    except SyntaxError:
        raise FormulaError(
            f"'{t}' is not a formula EquiPop can read. Write it with band "
            "numbers, + - * / and brackets, e.g. (b8 - b4) / (b8 + b4), "
            "or a named index such as ndvi(8, 4).")
    bands = set()
    _check(tree.body, bands, t)
    if not bands:
        raise FormulaError("A formula needs at least one band, such as "
                           "b1.")
    return Formula(t, tree, tuple(sorted(bands)))


def _check(node, bands, text):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(
                node.value, (int, float)):
            raise FormulaError(f"'{text}': only numbers and bands can "
                               "stand in a formula.")
        return
    if isinstance(node, ast.Name):
        m = _BAND.match(node.id)
        if not m:
            raise FormulaError(
                f"'{node.id}' in '{text}' is not a band. Bands are "
                "written b1, b2, b3 ... (the file's own band numbers).")
        b = int(m.group(1))
        if b < 1:
            raise FormulaError("Bands are counted from 1.")
        bands.add(b)
        return
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        _check(node.left, bands, text)
        _check(node.right, bands, text)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op,
                                                     (ast.USub, ast.UAdd)):
        _check(node.operand, bands, text)
        return
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and not node.keywords:
        name = node.func.id.lower()
        if name in INDICES:
            want = INDICES[name][0]
            if len(node.args) != len(want):
                raise FormulaError(
                    f"{name}() takes {len(want)} band numbers - "
                    f"{name}({', '.join(want)}), e.g. "
                    + ("ndvi(8, 4) for a full Sentinel-2 stack."
                       if name == "ndvi" else f"{name}(...)."))
            for a in node.args:
                b = _band_arg(a, name, text)
                bands.add(b)
            return
        if name in _FUNCTIONS and len(node.args) == _FUNCTIONS[name]:
            for a in node.args:
                _check(a, bands, text)
            return
    if isinstance(node, ast.Tuple):
        raise FormulaError(
            f"'{text}' holds a comma outside a named index. In a formula "
            "a decimal is written with a point: 0.5, not 0,5.")
    raise FormulaError(
        f"'{text}' uses something a formula here cannot hold. Allowed: "
        "numbers, bands (b1, b2 ...), + - * / **, brackets, abs(), "
        "sqrt(), and the indices " + ", ".join(f"{n}()" for n in INDICES)
        + ".")


def _band_arg(a, name, text):
    """A named index's argument: a band number, 8 or b8."""
    if isinstance(a, ast.Constant) and isinstance(a.value, int) \
            and not isinstance(a.value, bool) and a.value >= 1:
        return int(a.value)
    if isinstance(a, ast.Name) and _BAND.match(a.id) \
            and int(_BAND.match(a.id).group(1)) >= 1:
        return int(_BAND.match(a.id).group(1))
    raise FormulaError(f"{name}() takes band numbers, such as "
                       f"{name}(8, 4); '{text}' gives it something else.")


def evaluate(formula: Formula, bands: dict) -> np.ndarray:
    """The formula over `bands` ({band number: 2-D array, nodata already
    NaN}) as one float32 array; anything not finite becomes NaN."""
    missing = [b for b in formula.bands if b not in bands]
    if missing:
        raise FormulaError(f"Band(s) {missing} were not read.")
    if formula.single_band:
        v = np.asarray(bands[formula.bands[0]], np.float32)
    else:
        with np.errstate(all="ignore"):
            v = np.asarray(_ev(formula.tree.body, bands), np.float32)
    if v.ndim == 0:                              # pragma: no cover
        raise FormulaError("A formula needs at least one band.")
    v = v.copy() if formula.single_band else v
    v[~np.isfinite(v)] = np.nan
    return v


def _f(b, bands):
    return np.asarray(bands[b], np.float32)


def _ev(node, bands):
    if isinstance(node, ast.Constant):
        return np.float32(node.value)
    if isinstance(node, ast.Name):
        return _f(int(_BAND.match(node.id).group(1)), bands)
    if isinstance(node, ast.BinOp):
        return _OPS[type(node.op)](_ev(node.left, bands),
                                   _ev(node.right, bands))
    if isinstance(node, ast.UnaryOp):
        v = _ev(node.operand, bands)
        return -v if isinstance(node.op, ast.USub) else v
    name = node.func.id.lower()
    if name in INDICES:
        a, b = (_f(_band_arg(x, name, ""), bands) for x in node.args)
        if name == "savi":
            return np.float32(1.5) * (a - b) / (a + b + np.float32(0.5))
        return (a - b) / (a + b)
    v = _ev(node.args[0], bands)
    return np.abs(v) if name == "abs" else np.sqrt(v)

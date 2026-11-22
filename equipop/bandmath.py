"""
bandmath.py - one value per pixel, from a raster as it is or a formula
over any number of rasters (BACKLOG 510).

John, 21 November 2026: "perhaps we could allow for a band calculator -
where we can generate indexes using mathematical expressions". On 22
November, on how to name the rasters: a list's order "bares potential
biases" - Pro shows rasters by folder, by drawing order - and "make sure
we do not limit to a few rasters". So a formula names each raster by its
LAYER NAME in quotes, as Raster Calculator does in Pro and in QGIS: no
order to mix up, and no limit. A layer can be renamed to something short
("nir", "red") to type less.

    (empty)                  the one raster given, as it is
    8                        band 8 of the one raster given
    "nir"                    the raster called nir (its first band)
    "S2 stack"[8]            band 8 of the raster called S2 stack
    ("nir" - "red") / ("nir" + "red")
    ndvi("nir", "red")       a named index, with ITS rasters given
    ndvi("S2 stack"[8], "S2 stack"[4])

    ndvi(nir, red)     (nir - red) / (nir + red)          vegetation
    ndwi(green, nir)   (green - nir) / (green + nir)      open water
    ndbi(swir, nir)    (swir - nir) / (swir + nir)        built-up land
    savi(nir, red)     1.5 (nir - red) / (nir + red + 0.5)
                       vegetation where soil shows; needs reflectance
                       from 0 to 1 (Sentinel-2 L2A digital numbers are
                       reflectance x 10000: divide them first)

The arithmetic: + - * /, powers as ** or ^, brackets; abs, sqrt, exp,
ln (natural), log10, floor, ceil, min(a, b, ...), max(a, b, ...);
comparisons < <= > >= == != giving 1 or 0, joined with and, or, not;
and where(condition, a, b). 'log' alone is refused - natural or base
10 is a choice the person must make (ln or log10).

A FORMULA IS READ, NEVER RUN. It is parsed into a tree and every node is
checked against that list. Nothing else - no other names, no attributes,
no Python. A formula is at most 500 characters.

NO VALUE STAYS NO VALUE. A pixel with nodata in any raster it uses, a
division by zero, a log of zero, or anything else that is not a finite
number, has no value: never 0, never "false". Arithmetic runs in
float32: a 13-band Sentinel-2 tile is 1.6 GB of float32, twice that in
float64.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass

import numpy as np

__all__ = ["Formula", "FormulaError", "parse", "evaluate", "INDICES",
           "FUNCTIONS", "MAX_LENGTH", "roles", "ONLY"]

MAX_LENGTH = 500

#: The raster a formula means when it names none: the only one given.
ONLY = None

#: name -> (the rasters or bands it takes, in order; what it computes)
INDICES = {
    "ndvi": (("nir", "red"), "(nir - red) / (nir + red)"),
    "ndwi": (("green", "nir"), "(green - nir) / (green + nir)"),
    "ndbi": (("swir", "nir"), "(swir - nir) / (swir + nir)"),
    "savi": (("nir", "red"), "1.5 (nir - red) / (nir + red + 0.5)"),
}
#: name -> (fewest arguments, most arguments or None for any)
FUNCTIONS = {"abs": (1, 1), "sqrt": (1, 1), "exp": (1, 1), "ln": (1, 1),
             "log10": (1, 1), "floor": (1, 1), "ceil": (1, 1),
             "min": (2, None), "max": (2, None), "where": (3, 3)}
_ONE = {"abs": np.abs, "sqrt": np.sqrt, "exp": np.exp, "ln": np.log,
        "log10": np.log10, "floor": np.floor, "ceil": np.ceil}
_OPS = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply,
        ast.Div: np.divide, ast.Pow: np.power, ast.BitXor: np.power}
_CMP = {ast.Lt: np.less, ast.LtE: np.less_equal, ast.Gt: np.greater,
        ast.GtE: np.greater_equal, ast.Eq: np.equal,
        ast.NotEq: np.not_equal}


class FormulaError(ValueError):
    """A value box that cannot be read - with a sentence saying why."""


@dataclass(frozen=True)
class Formula:
    text: str            # as typed (tidied), for the run log
    tree: ast.AST         # the checked expression
    refs: tuple           # ((raster name or ONLY, band), ...), sorted

    @property
    def rasters(self):
        """The raster names it uses; ONLY (None) = the one given."""
        return tuple(dict.fromkeys(r for r, _ in self.refs))

    def bands(self, name):
        """The band numbers it reads from raster `name`."""
        return tuple(sorted(b for r, b in self.refs if r == name))


def _key(ref):
    return ("" if ref[0] is None else ref[0], ref[1])


def parse(text) -> Formula:
    """The pixel value box -> a Formula. '' or None is the one raster
    given, as it is; a bare whole number n is its band n."""
    t = "" if text is None else str(text).strip()
    # quotes a word processor curled are still quotes
    t = t.translate(str.maketrans({"\u201c": '"', "\u201d": '"',
                                   "\u201e": '"', "\u2018": "'",
                                   "\u2019": "'", "\u00ab": '"',
                                   "\u00bb": '"'}))
    if t == "":
        return Formula("", ast.parse("_only_", mode="eval"),
                       ((ONLY, 1),))
    if t.isdigit():
        if int(t) < 1:
            raise FormulaError("Bands are counted from 1.")
        return Formula(t, ast.parse(f"_only_[{int(t)}]", mode="eval"),
                       ((ONLY, int(t)),))
    if len(t) > MAX_LENGTH:
        raise FormulaError(f"A formula is at most {MAX_LENGTH} "
                           "characters.")
    try:
        tree = ast.parse(t, mode="eval")
    except SyntaxError:
        raise FormulaError(
            f"'{t}' is not a formula EquiPop can read. Name each raster "
            "by its layer name in quotes and join them with + - * / ^ "
            "and brackets, e.g. (\"nir\" - \"red\") / (\"nir\" + "
            "\"red\"), or use a named index such as ndvi(\"nir\", "
            "\"red\").")
    refs = set()
    _check(tree.body, refs, t)
    if not refs:
        raise FormulaError("A formula needs at least one raster, such as "
                           "\"nir\".")
    return Formula(t, tree, tuple(sorted(refs, key=_key)))


def _ref(node, text):
    """A raster or a band of one: "nir" -> ('nir', 1); "S2"[8] ->
    ('S2', 8). None when the node is neither."""
    if isinstance(node, ast.Name) and node.id == "_only_":
        return (ONLY, 1)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        name = node.value.strip()
        if not name:
            raise FormulaError(f"'{text}': an empty name in quotes.")
        return (name, 1)
    if isinstance(node, ast.Subscript):
        inner = node.value
        sl = node.slice
        if isinstance(inner, ast.Name) and inner.id == "_only_":
            base = ONLY
        elif isinstance(inner, ast.Constant) \
                and isinstance(inner.value, str):
            base = inner.value.strip()
        else:
            raise FormulaError(
                f"'{text}': a band is a whole number in brackets after a "
                "raster's name, such as \"S2 stack\"[8].")
        if isinstance(sl, ast.Constant) and isinstance(sl.value, int) \
                and not isinstance(sl.value, bool):
            if sl.value < 1:
                raise FormulaError("Bands are counted from 1.")
            return (base, int(sl.value))
        raise FormulaError(
            f"'{text}': a band is a whole number in brackets after a "
            "raster's name, such as \"S2 stack\"[8].")
    return None


def _check(node, refs, text):
    if isinstance(node, ast.Constant) and not isinstance(node.value, str):
        if isinstance(node.value, bool) or not isinstance(
                node.value, (int, float)):
            raise FormulaError(f"'{text}': only numbers and rasters can "
                               "stand in a formula.")
        return
    r = _ref(node, text)
    if r is not None:
        refs.add(r)
        return
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        _check(node.left, refs, text)
        _check(node.right, refs, text)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(
            node.op, (ast.USub, ast.UAdd, ast.Not)):
        _check(node.operand, refs, text)
        return
    if isinstance(node, ast.Compare) and all(type(o) in _CMP
                                             for o in node.ops):
        _check(node.left, refs, text)
        for c in node.comparators:
            _check(c, refs, text)
        return
    if isinstance(node, ast.BoolOp):
        for v in node.values:
            _check(v, refs, text)
        return
    if isinstance(node, ast.Name):
        if node.id.lower() == "log":
            raise FormulaError("'log' could mean natural or base 10: "
                               "write ln(...) or log10(...).")
        raise FormulaError(
            f"'{node.id}' in '{text}' is not a raster. A raster is named "
            f"by its layer name IN QUOTES: \"{node.id}\". A band of one "
            "is written \"S2 stack\"[8].")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and not node.keywords:
        name = node.func.id.lower()
        if name in INDICES:
            want = INDICES[name][0]
            if len(node.args) != len(want):
                raise FormulaError(
                    f"{name}() takes {len(want)} rasters or bands - "
                    f"{name}({', '.join(want)}), e.g. "
                    + ("ndvi(\"nir\", \"red\")." if name == "ndvi"
                       else f"{name}(\"...\", \"...\")."))
            for a in node.args:
                refs.add(_index_arg(a, name, text))
            return
        if name == "log":
            raise FormulaError("'log' could mean natural or base 10: "
                               "write ln(...) or log10(...).")
        if name in FUNCTIONS:
            lo, hi = FUNCTIONS[name]
            n = len(node.args)
            if n < lo or (hi is not None and n > hi):
                want = f"{lo}" if lo == hi else f"at least {lo}"
                raise FormulaError(f"{name}() takes {want} argument"
                                   f"{'s' if lo != 1 else ''}; "
                                   f"'{text}' gives it {n}.")
            for a in node.args:
                _check(a, refs, text)
            return
    if isinstance(node, ast.Tuple):
        raise FormulaError(
            f"'{text}' holds a comma outside a function. In a formula a "
            "decimal is written with a point: 0.5, not 0,5.")
    raise FormulaError(
        f"'{text}' uses something a formula here cannot hold. Allowed: "
        "numbers, rasters by name in quotes, a band such as \"S2\"[8], "
        "+ - * / ** ^, brackets, comparisons with and/or/not, the "
        "functions " + ", ".join(f"{f}()" for f in FUNCTIONS)
        + ", and the indices " + ", ".join(f"{n}()" for n in INDICES)
        + ".")


def _index_arg(a, name, text):
    """A named index's argument: a raster ("nir"), a band ("S2"[8]), or
    a bare band number of the one raster given (8)."""
    if isinstance(a, ast.Constant) and isinstance(a.value, int) \
            and not isinstance(a.value, bool) and a.value >= 1:
        return (ONLY, int(a.value))
    r = _ref(a, text)
    if r is not None:
        return r
    raise FormulaError(f"{name}() takes rasters or bands, such as "
                       f"{name}(\"nir\", \"red\"); '{text}' gives it "
                       "something else.")


def roles(formula: Formula):
    """For each named index in the formula: (name, [(role, (raster,
    band)), ...]) - what the run log says, so a swap can be seen."""
    out = []
    for node in ast.walk(formula.tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id.lower() in INDICES:
            name = node.func.id.lower()
            out.append((name, list(zip(
                INDICES[name][0],
                (_index_arg(a, name, formula.text) for a in node.args)))))
    return out


def evaluate(formula: Formula, bands: dict) -> np.ndarray:
    """The formula over `bands` ({(raster name or ONLY, band): 2-D
    array, nodata already NaN}) as one float32 array; anything not
    finite becomes NaN."""
    missing = [r for r in formula.refs if r not in bands]
    if missing:
        raise FormulaError(f"{missing} were not read.")
    with np.errstate(all="ignore"):
        v = np.array(_ev(formula.tree.body, bands), np.float32)
    if v.ndim == 0:                              # pragma: no cover
        raise FormulaError("A formula needs at least one raster.")
    v[~np.isfinite(v)] = np.nan
    return v


def _flag(mask, *operands):
    """True/False as 1/0 - NaN wherever an operand has no value, so a
    comparison with a nodata pixel stays no value, never 'false'."""
    out = mask.astype(np.float32)
    for o in operands:
        out = np.where(np.isnan(o), np.float32(np.nan), out)
    return out


def _truth(v):
    return np.asarray(v, np.float32) != 0


def _ev(node, bands):
    if isinstance(node, ast.Constant) and not isinstance(node.value, str):
        return np.float32(node.value)
    r = _ref(node, "")
    if r is not None:
        return np.asarray(bands[r], np.float32)
    if isinstance(node, ast.BinOp):
        return _OPS[type(node.op)](_ev(node.left, bands),
                                   _ev(node.right, bands))
    if isinstance(node, ast.UnaryOp):
        v = _ev(node.operand, bands)
        if isinstance(node.op, ast.Not):
            return _flag(~_truth(v), np.asarray(v, np.float32))
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.Compare):
        left = np.asarray(_ev(node.left, bands), np.float32)
        result, seen = None, [left]
        for op, comp in zip(node.ops, node.comparators):
            right = np.asarray(_ev(comp, bands), np.float32)
            m = _CMP[type(op)](left, right)
            result = m if result is None else (result & m)
            seen.append(right)
            left = right
        return _flag(result, *seen)
    if isinstance(node, ast.BoolOp):
        vals = [np.asarray(_ev(v, bands), np.float32) for v in node.values]
        join = np.logical_and if isinstance(node.op, ast.And) \
            else np.logical_or
        m = _truth(vals[0])
        for v in vals[1:]:
            m = join(m, _truth(v))
        return _flag(m, *vals)
    name = node.func.id.lower()
    if name in INDICES:
        a, b = (np.asarray(bands[_index_arg(x, name, "")], np.float32)
                for x in node.args)
        if name == "savi":
            return np.float32(1.5) * (a - b) / (a + b + np.float32(0.5))
        return (a - b) / (a + b)
    args = [np.asarray(_ev(a, bands), np.float32) for a in node.args]
    if name in _ONE:
        return _ONE[name](args[0])
    if name == "where":
        cond, a, b = args
        return np.where(np.isnan(cond), np.float32(np.nan),
                        np.where(_truth(cond), a, b))
    pick = np.minimum if name == "min" else np.maximum
    out = args[0]
    for a in args[1:]:
        out = pick(out, a)                # NaN anywhere stays NaN
    return out

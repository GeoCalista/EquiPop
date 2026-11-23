"""The pixel value box of tool 3b: the one raster as it is, or a formula
over any number of rasters named by their layer names in quotes, read
and never run (BACKLOG 510; John, 22 November 2026)."""
import math

import numpy as np
import pytest

from equipop.bandmath import ONLY, FormulaError, evaluate, parse, roles


def _bands():
    red = np.array([[100.0, 200.0], [0.0, 50.0]], np.float32)
    nir = np.array([[300.0, 200.0], [0.0, np.nan]], np.float32)
    return {("red", 1): red, ("nir", 1): nir, ("S2 stack", 4): red,
            ("S2 stack", 8): nir}


@pytest.mark.parametrize("typed, refs", [
    ("", ((ONLY, 1),)), ("8", ((ONLY, 8),)),
    ('"nir"', (("nir", 1),)), ("'nir'", (("nir", 1),)),
    ("“nir”", (("nir", 1),)),
    ('"S2 stack"[8]', (("S2 stack", 8),)),
    ('("nir" - "red") / ("nir" + "red")', (("nir", 1), ("red", 1))),
    ('ndvi("nir", "red")', (("nir", 1), ("red", 1))),
    ('NDVI("S2 stack"[8], "S2 stack"[4])',
     (("S2 stack", 4), ("S2 stack", 8))),
    ("ndvi(8, 4)", ((ONLY, 4), (ONLY, 8))),
    ('"a" + "b" + "c" + "d" + "e" + "f" + "g" + "h" + "i" + "j"',
     tuple((x, 1) for x in "abcdefghij")),
])
def test_the_value_box_reads_rasters_by_name_without_limit(typed, refs):
    """Ten rasters as easily as one: no letters, no list order."""
    assert parse(typed).refs == refs


def test_a_formula_and_its_index_agree_and_bad_pixels_have_no_value():
    """ndvi("nir", "red") is ("nir" - "red") / ("nir" + "red"); 0 / 0 and
    a nodata pixel give no value. BROKEN WITH: ndvi's arguments taken
    the other way round - every NDVI changes sign."""
    b = _bands()
    by_hand = evaluate(parse('("nir" - "red") / ("nir" + "red")'), b)
    named = evaluate(parse('ndvi("nir", "red")'), b)
    stack = evaluate(parse('ndvi("S2 stack"[8], "S2 stack"[4])'), b)
    assert np.allclose(by_hand, named, equal_nan=True)
    assert np.allclose(by_hand, stack, equal_nan=True)
    assert by_hand[0, 0] == pytest.approx(0.5)
    assert by_hand[0, 1] == pytest.approx(0.0)
    assert np.isnan(by_hand[1, 0]) and np.isnan(by_hand[1, 1])
    assert by_hand.dtype == np.float32


def test_savi_and_the_other_indices_follow_their_definitions():
    b = {("x", 1): np.array([[0.3]], np.float32),
         ("y", 1): np.array([[0.1]], np.float32)}
    assert evaluate(parse('savi("x", "y")'), b)[0, 0] == pytest.approx(
        1.5 * 0.2 / 0.9, rel=1e-6)
    assert evaluate(parse('ndwi("y", "x")'), b)[0, 0] == pytest.approx(-0.5)
    assert evaluate(parse('ndbi("x", "y")'), b)[0, 0] == pytest.approx(0.5)


@pytest.mark.parametrize("typed, want", [
    ('"x" ** 2', 4.0), ('"x" ^ 2', 4.0), ('sqrt("x" * 8)', 4.0),
    ('exp("x")', math.e ** 2), ('ln("x")', math.log(2)),
    ('log10("x" * 50)', 2.0), ('floor("x" / 3)', 0.0),
    ('ceil("x" / 3)', 1.0), ('min("x", 1, 5)', 1.0),
    ('max("x", 1, 5)', 5.0), ('abs(-"x")', 2.0),
    ('"x" > 1', 1.0), ('"x" >= 3', 0.0), ('1 < "x" < 3', 1.0),
    ('"x" > 1 and "x" < 2', 0.0), ('"x" > 1 or "x" < 2', 1.0),
    ('not "x" > 1', 0.0), ('where("x" > 1, 10, 20)', 10.0),
    ('-1.5 * 2 + "x"', -1.0),
])
def test_the_arithmetic_john_asked_for(typed, want):
    """Powers as ** or ^ (John: 'your choice' - both), ln, exp, log10,
    sqrt, min, max, floor, ceil, comparisons, and/or/not, where. BROKEN
    WITH: ^ left as Python's bitwise xor - it is refused or wrong."""
    v = evaluate(parse(typed), {("x", 1): np.array([[2.0]], np.float32)})
    assert v[0, 0] == pytest.approx(want, rel=1e-6)


def test_no_value_stays_no_value_through_comparisons_and_where():
    """A nodata pixel compared with anything is still no value - never
    0, which would read as 'not green'. BROKEN WITH: comparisons
    returning plain 1/0, so NaN > 0.5 reads 0."""
    x = {("x", 1): np.array([[np.nan, 0.8, 0.0]], np.float32)}
    for typed in ('"x" > 0.5', 'not "x"', '"x" > 0 and 1',
                  'where("x" > 0.5, 1, 0)', 'max("x", 0)', 'ln("x")'):
        v = evaluate(parse(typed), x)
        assert np.isnan(v[0, 0]), typed
    assert np.isnan(evaluate(parse('ln("x")'), x)[0, 2])    # ln 0
    assert evaluate(parse('"x" > 0.5'), x)[0, 1] == 1.0


def test_the_one_raster_as_it_is_is_a_copy_of_its_band():
    a = np.array([[1.0, np.inf]], np.float32)
    v = evaluate(parse(""), {(ONLY, 1): a})
    assert np.isnan(v[0, 1]) and np.isinf(a[0, 1])


def test_the_run_log_can_name_each_role():
    assert roles(parse('ndvi("nir", "red") + ndwi("g", "S2"[8])')) == [
        ("ndvi", [("nir", ("nir", 1)), ("red", ("red", 1))]),
        ("ndwi", [("green", ("g", 1)), ("nir", ("S2", 8))])]


@pytest.mark.parametrize("typed, says", [
    ("nir - red", "IN QUOTES"),
    ("B8", "IN QUOTES"),
    ('"x" * 0,5', "point"),
    ("log('x')", "ln"),
    ("__import__('os')", "cannot hold"),
    ('"x".real', "cannot hold"),
    ('ndvi("x")', "takes 2"),
    ('ndvi(8, 4.5)', "rasters or bands"),
    ('"x"[1.5]', "whole number in brackets"),
    ('sqrt("x", 2)', "takes 1"),
    ('min("x")', "at least 2"),
    ("2 * 3", "at least one raster"),
    ('"x"[0] + 1', "from 1"),
    ("0", "from 1"),
    ('"x" +', "not a formula"),
    ('"x" + ' * 100, "500 characters"),
])
def test_anything_else_is_refused_with_a_sentence(typed, says):
    """A formula is parsed and checked node by node, never run. A name
    without quotes is refused, so B8 - Sentinel's band 8 - is never
    read as anything. BROKEN WITH: Attribute and any-name Calls let
    through - the __import__ line then reaches evaluate()."""
    with pytest.raises(FormulaError, match=says):
        parse(typed)


def test_a_huge_power_is_no_value_not_a_crash():
    v = evaluate(parse('"x" ** 1000'),
                 {("x", 1): np.full((2, 2), 9, np.float32)})
    assert np.isnan(v).all()


# --- BACKLOG 512 b: the external review, 23 November 2026 ----------------

@pytest.mark.parametrize("typed, want", [
    ('"x" ^ 2 + 1', 5.0), ('"x" ** 2 + 1', 5.0), ('1 + "x" ^ 2', 5.0),
    ('-"x" ^ 2', -4.0), ('-"x" ** 2', -4.0), ('(-"x") ^ 2', 4.0),
    ('"x" ^ 3 ^ 2', 512.0), ('"x" ** 3 ** 2', 512.0),
    ('"x" ^ -1', 0.5), ('2 * "x" ^ 2', 8.0), ('"x" ^ 2 / 4', 1.0),
    ('"a^b" + 1', 3.0),
])
def test_a_power_binds_as_in_ordinary_maths_whichever_sign(typed, want):
    """^ and ** are the same power, binding tighter than * and unary
    minus and from the right. A ^ inside a quoted name stays a name.
    BROKEN WITH: ^ parsed as Python's xor and mapped to a power after -
    "x" ^ 2 + 1 is then "x" ^ 3 = 8, and -"x" ^ 2 is 4."""
    b = {("x", 1): np.array([[2.0]], np.float32),
         ("a^b", 1): np.array([[2.0]], np.float32)}
    assert evaluate(parse(typed), b)[0, 0] == pytest.approx(want)


@pytest.mark.parametrize("typed", [
    '1 / "x" > 0', 'min(1 / "x", 5)', 'max(1 / "x", 5)',
    'where(1 / "x" > 0, 1, 0)', 'not 1 / "x"', '1 / "x" > 0 or 1',
    'abs(1 / "x") > 0', 'ln("x") < 0', '("x" - "x") / "x" == 0',
])
def test_an_infinity_is_no_value_at_once_not_at_the_end(typed):
    """At x = 0, 1 / "x" is infinite. Left to the final cleanup, a
    comparison or min() first turned it into a number: 1 / "x" > 0 read
    1, min(1 / "x", 5) read 5. BROKEN WITH: only the final result
    cleaned."""
    v = evaluate(parse(typed), {("x", 1): np.array([[0.0, 2.0]],
                                                  np.float32)})
    assert np.isnan(v[0, 0]), typed
    assert np.isfinite(v[0, 1]), typed

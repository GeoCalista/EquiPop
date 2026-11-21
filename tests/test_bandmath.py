"""The value box of tool 3b: one band, or a formula over bands, read and
never run (BACKLOG 510)."""
import numpy as np
import pytest

from equipop.bandmath import FormulaError, evaluate, parse


def _bands():
    red = np.array([[100.0, 200.0], [0.0, 50.0]], np.float32)
    nir = np.array([[300.0, 200.0], [0.0, np.nan]], np.float32)
    return {4: red, 8: nir}


@pytest.mark.parametrize("typed, bands", [
    ("", (1,)), ("1", (1,)), ("8", (8,)),
    ("(b8 - b4) / (b8 + b4)", (4, 8)), ("ndvi(8, 4)", (4, 8)),
    ("NDVI(b8, b4)", (4, 8)), ("abs(b2 - b3) * 0.5", (2, 3)),
])
def test_the_value_box_reads_bands_formulas_and_indices(typed, bands):
    assert parse(typed).bands == bands


def test_a_formula_and_its_index_agree_and_bad_pixels_have_no_value():
    """ndvi(8, 4) is (b8 - b4) / (b8 + b4); 0 / 0 and a nodata band give
    no value. BROKEN WITH: ndvi's arguments taken the other way round -
    every NDVI changes sign."""
    by_hand = evaluate(parse("(b8 - b4) / (b8 + b4)"), _bands())
    named = evaluate(parse("ndvi(8, 4)"), _bands())
    assert np.allclose(by_hand, named, equal_nan=True)
    assert by_hand[0, 0] == pytest.approx(0.5)
    assert by_hand[0, 1] == pytest.approx(0.0)
    assert np.isnan(by_hand[1, 0]) and np.isnan(by_hand[1, 1])
    assert by_hand.dtype == np.float32


def test_savi_and_the_other_indices_follow_their_definitions():
    b = {1: np.array([[0.3]], np.float32), 2: np.array([[0.1]], np.float32)}
    assert evaluate(parse("savi(1, 2)"), b)[0, 0] == pytest.approx(
        1.5 * 0.2 / 0.9, rel=1e-6)
    assert evaluate(parse("ndwi(2, 1)"), b)[0, 0] == pytest.approx(-0.5)
    assert evaluate(parse("ndbi(1, 2)"), b)[0, 0] == pytest.approx(0.5)


@pytest.mark.parametrize("typed, says", [
    ("b8 * 0,5", "point"),
    ("__import__('os')", "cannot hold"),
    ("b8.real", "cannot hold"),
    ("red + nir", "not a band"),
    ("ndvi(8)", "takes 2"),
    ("ndvi(8, 4.5)", "band numbers"),
    ("2 * 3", "at least one band"),
    ("b0 + 1", "from 1"),
    ("0", "from 1"),
    ("b1 +", "not a formula"),
    ("b1 + " * 80, "300 characters"),
])
def test_anything_else_is_refused_with_a_sentence(typed, says):
    """A formula is parsed and checked node by node, never run.
    BROKEN WITH: Attribute and any-name Calls let through - the
    __import__ line then reaches evaluate()."""
    with pytest.raises(FormulaError, match=says):
        parse(typed)


def test_a_huge_power_is_no_value_not_a_crash():
    v = evaluate(parse("b1 ** 1000"), {1: np.full((2, 2), 9, np.float32)})
    assert np.isnan(v).all()

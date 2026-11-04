"""Scoring: polygon areas, crush fraction, queueing score formula."""

from app.physics.social_force import _polygon_area
from app.scoring import crush_fraction, score_queueing


def test_polygon_area_square():
    assert abs(_polygon_area([[0, 0], [10, 0], [10, 10], [0, 10]]) - 100.0) < 1e-9


def test_polygon_area_concave_and_orientation():
    poly = [[0, 0], [20, 0], [20, 10], [10, 10], [10, 20], [0, 20]]
    area = _polygon_area(poly)
    assert abs(area - (20 * 20 - 10 * 10)) < 1e-6
    assert abs(_polygon_area(list(reversed(poly))) - area) < 1e-6


def test_crush_fraction_guards_zero():
    assert crush_fraction(0.0, 0.0) == 0.0
    assert crush_fraction(5.0, 20.0) == 0.25


def test_score_queueing_bounds_and_monotonicity():
    assert score_queueing(0.0, 0.0, 5.0) == 100
    assert score_queueing(50.0, 0.0, 3.0) == 0
    assert score_queueing(10.0, 0.0, 0.0) < score_queueing(2.0, 0.0, 0.0)
    assert score_queueing(1.0, 0.5, 3.0) < score_queueing(1.0, 0.0, 3.0)

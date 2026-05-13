"""Tests for the route matcher."""

from scraper.matcher import RouteMatcher


def test_explicit_label():
    m = RouteMatcher()
    result = m.extract_route_name("Route: Covered Bridge Loop. Meet at 8am.")
    assert result == "Covered Bridge Loop"


def test_keyword_anchor():
    m = RouteMatcher()
    result = m.extract_route_name("We'll be doing the Brandywine Loop on Saturday.")
    assert result is not None
    assert "loop" in result.lower()


def test_no_match_returns_none():
    m = RouteMatcher()
    result = m.extract_route_name("Bring water and snacks. Moderate pace.")
    assert result is None


def test_fuzzy_match():
    m = RouteMatcher(known_routes=["Valley Forge Century", "Covered Bridge Loop"])
    result = m.extract_route_name("Join us for the annual Valley Forge century ride.")
    assert result == "Valley Forge Century"


def test_empty_description():
    m = RouteMatcher()
    assert m.extract_route_name("") is None
    assert m.extract_route_name(None) is None

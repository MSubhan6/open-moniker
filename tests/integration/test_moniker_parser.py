"""Tests for moniker parsing."""

import pytest

from moniker_svc.moniker.parser import (
    parse_moniker,
    parse_path,
    MonikerParseError,
)
from moniker_svc.moniker.types import MonikerPath


class TestParsePath:
    def test_simple_path(self):
        path = parse_path("market-data/prices/equity")
        assert path.segments == ("market-data", "prices", "equity")
        assert str(path) == "market-data/prices/equity"

    def test_path_with_leading_slash(self):
        path = parse_path("/market-data/prices")
        assert path.segments == ("market-data", "prices")

    def test_path_with_trailing_slash(self):
        path = parse_path("market-data/prices/")
        assert path.segments == ("market-data", "prices")

    def test_empty_path(self):
        path = parse_path("")
        assert path.segments == ()
        assert path == MonikerPath.root()

    def test_root_path(self):
        path = parse_path("/")
        assert path.segments == ()

    def test_single_segment(self):
        path = parse_path("market-data")
        assert path.segments == ("market-data",)
        assert path.domain == "market-data"

    def test_invalid_segment_start(self):
        with pytest.raises(MonikerParseError):
            parse_path("-invalid")

    def test_invalid_segment_chars(self):
        with pytest.raises(MonikerParseError):
            parse_path("path/with spaces")


class TestMonikerPath:
    def test_domain(self):
        path = MonikerPath(("market-data", "prices", "equity"))
        assert path.domain == "market-data"

    def test_parent(self):
        path = MonikerPath(("market-data", "prices", "equity"))
        parent = path.parent
        assert parent is not None
        assert parent.segments == ("market-data", "prices")

    def test_parent_at_root(self):
        path = MonikerPath(("market-data",))
        assert path.parent is None

    def test_leaf(self):
        path = MonikerPath(("market-data", "prices", "equity"))
        assert path.leaf == "equity"

    def test_ancestors(self):
        path = MonikerPath(("a", "b", "c", "d"))
        ancestors = path.ancestors()
        assert len(ancestors) == 3
        assert str(ancestors[0]) == "a"
        assert str(ancestors[1]) == "a/b"
        assert str(ancestors[2]) == "a/b/c"

    def test_child(self):
        path = MonikerPath(("market-data", "prices"))
        child = path.child("equity")
        assert child.segments == ("market-data", "prices", "equity")

    def test_is_ancestor_of(self):
        parent = MonikerPath(("a", "b"))
        child = MonikerPath(("a", "b", "c", "d"))
        assert parent.is_ancestor_of(child)
        assert not child.is_ancestor_of(parent)
        assert not parent.is_ancestor_of(parent)


class TestParseMoniker:
    def test_with_scheme(self):
        m = parse_moniker("moniker://market-data/prices/equity")
        assert str(m.path) == "market-data/prices/equity"
        assert not m.params

    def test_without_scheme(self):
        m = parse_moniker("market-data/prices/equity")
        assert str(m.path) == "market-data/prices/equity"

    def test_with_query_params(self):
        m = parse_moniker("moniker://market-data/prices?version=latest&as_of=2024-01-01")
        assert m.params.version == "latest"
        assert m.params.as_of == "2024-01-01"

    def test_str_roundtrip(self):
        original = "moniker://market-data/prices/equity"
        m = parse_moniker(original)
        assert str(m) == original

    def test_str_with_params(self):
        m = parse_moniker("moniker://path?version=v1")
        assert "version=v1" in str(m)

    def test_empty_moniker(self):
        with pytest.raises(MonikerParseError):
            parse_moniker("")

    def test_invalid_scheme(self):
        with pytest.raises(MonikerParseError):
            parse_moniker("http://market-data/prices")

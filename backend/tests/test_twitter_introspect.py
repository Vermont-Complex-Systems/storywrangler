"""
Twitter host-form availability introspection (_introspect hook).

Generic mongo_introspect can't derive availability for a host-form dataset;
the twitter router registers a hook that walks its {n}grams/{lang} collections
for per-(ngram_size, lang) min/max. A fake pymongo client stands in — no live
Mongo, no network.
"""
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.twitter import _introspect


class _Coll:
    def __init__(self, lo, hi):
        self._lo, self._hi = lo, hi

    def find_one(self, _q, _proj, sort, max_time_ms=None):
        asc = sort[0][1] == 1
        val = self._lo if asc else self._hi
        return {"time": val} if val is not None else None


class _DB:
    def __init__(self, colls):
        self._colls = colls

    def list_collection_names(self):
        return list(self._colls)

    def __getitem__(self, name):
        return self._colls[name]


class _Client:
    """1grams: en, es ; 2grams: en — with distinct date ranges per collection."""
    def __init__(self):
        self._dbs = {
            "1grams": _DB({
                "en": _Coll(datetime(2008, 9, 1), datetime(2023, 1, 4)),
                "es": _Coll(datetime(2009, 3, 2), datetime(2022, 12, 30)),
            }),
            "2grams": _DB({"en": _Coll(datetime(2010, 1, 1), datetime(2022, 6, 1))}),
            "3grams": _DB({}),  # exists but empty
        }

    def __getitem__(self, name):
        return self._dbs.get(name, _DB({}))


def _dataset():
    return SimpleNamespace(
        domain="twitter",
        transform=SimpleNamespace(time_dimension="time"),
        data_schema={"word": "VARCHAR", "time": "TIMESTAMP"},
    )


class TestTwitterIntrospect:
    def test_per_slice_availability_tree(self):
        d = _introspect(_Client(), _dataset())
        av = d["availability"]
        assert av["1"]["en"] == {"min": "2008-09-01", "max": "2023-01-04"}
        assert av["1"]["es"] == {"min": "2009-03-02", "max": "2022-12-30"}
        assert av["2"]["en"] == {"min": "2010-01-01", "max": "2022-06-01"}
        assert "3" not in av  # empty database contributes nothing

    def test_filter_values_from_the_same_walk(self):
        d = _introspect(_Client(), _dataset())
        assert d["filter_values"]["lang"] == ["en", "es"]
        assert d["filter_values"]["ngram_size"] == [1, 2, 3]

    def test_navigable_by_availability_range_for(self):
        # The tree keys (ngram_size, lang) are what availability_range_for
        # matches on — the out-of-range teaching guard now works for twitter.
        from app.core.query_utils import availability_range_for
        ds = SimpleNamespace(manifest={"availability": _introspect(_Client(), _dataset())["availability"]})
        assert availability_range_for(ds, None, {"ngram_size": 1, "lang": "es"}) == (
            "2009-03-02", "2022-12-30")

    def test_empty_client_yields_nothing(self):
        class _Empty:
            def __getitem__(self, name):
                return _DB({})
        assert _introspect(_Empty(), _dataset()) == {}

    def test_mongo_introspect_dispatches_to_hook(self, monkeypatch):
        # mongo_introspect (host-form branch) calls the registered hook.
        import app.core.mongo_client as mc
        monkeypatch.setattr(mc, "get_mongo_client", lambda: _Client())
        ds = SimpleNamespace(
            domain="twitter", data_location="wranglerdb01a.uvm.edu:27017",
            data_schema={"word": "VARCHAR", "time": "TIMESTAMP"},
            transform=SimpleNamespace(time_dimension="time", filter_dimensions=["lang", "ngram_size"]),
        )
        derived = mc.mongo_introspect(ds)
        assert derived["data_schema"] == ds.data_schema
        assert derived["availability"]["1"]["en"]["max"] == "2023-01-04"
        assert derived["filter_values"]["lang"] == ["en", "es"]

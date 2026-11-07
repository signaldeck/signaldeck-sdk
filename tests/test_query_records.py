"""Compatibility of legacy history and new query API."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from signaldeck_sdk import PersistData, RecordsPage


class QueryStore:
    def __init__(self):
        self.calls = []

    def query_records(self, processor_name, fields, config, **kwargs):
        self.calls.append((processor_name, list(fields), config, kwargs))
        return RecordsPage(pd.DataFrame({"type": ["appointment"]}), "cursor-2")


def processor():
    instance = PersistData.__new__(PersistData)
    store = QueryStore()
    instance.config = {"processor_name": "socketio", "persist": [{"type": "sqlite"}]}
    instance.dataStores = {"sqlite": store}
    instance.ctx = SimpleNamespace(date=SimpleNamespace(now=lambda: datetime(2026, 1, 7, tzinfo=timezone.utc)))
    return instance, store


def test_legacy_get_records_still_uses_hist():
    target, store = processor()
    calls = []

    def fake_hist(field, **kwargs):
        calls.append((field, kwargs["days"], kwargs["fullDay"]))
        return pd.Series(["chat"], index=[pd.Timestamp("2026-01-07", tz="UTC")])

    target.hist = fake_hist
    result = target.get_records(fields=["type"], days=2)
    assert isinstance(result, pd.DataFrame)
    assert calls == [("type", 0, True), ("type", 1, True)]
    assert store.calls == []


def test_filtered_get_records_uses_datastore_and_returns_dataframe():
    target, store = processor()
    result = target.get_records(fields=["type"], days=None, filters={"type": "appointment"})
    assert result["type"].tolist() == ["appointment"]
    assert store.calls[0][3]["filters"] == {"type": "appointment"}
    assert store.calls[0][3]["date_from"] is None
    assert store.calls[0][3]["date_to"] is None


def test_query_page_forwards_cursor_and_limit_without_default_days():
    target, store = processor()
    result = target.get_records_page(fields=["type"], filters={"type": "appointment"}, limit=25, cursor="previous")
    assert result.next_cursor == "cursor-2"
    assert store.calls[0][3]["cursor"] == "previous"
    assert store.calls[0][3]["limit"] == 25


def test_unsupported_datastore_query_fails_instead_of_returning_unfiltered_data():
    target, _ = processor()
    target.dataStores = {"sqlite": object()}
    with pytest.raises(AttributeError):
        target.get_records_page(fields=["type"], filters={"type": "appointment"})

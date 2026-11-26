import unittest
from signaldeck_sdk import ValueProvider
from signaldeck_sdk.value_provider import HttpRequestError


class Source:
    name = "source"
    def __init__(self):
        self.refreshes = 0
        self.payload = None

    def refresh(self):
        self.refreshes += 1

    def getValue(self, field):
        return {"power": 12, "date": "2026-01-01T00:00:00Z"}[field]

    def processHTTPCall(self, **payload):
        self.payload = payload
        return {"status": "OK"}


class DataExchangeTests(unittest.TestCase):
    def test_publish_registration_and_resolution(self):
        vp = ValueProvider()
        source = Source()
        definition = {"name": "energy", "type": "http", "values": {"p": "power", "date": "date"}}
        vp.registerProcessor(source, {"values": [{"power": "power"}, {"date": "date"}], "publish": [definition]})
        self.assertEqual(vp.publish_definitions[("source", "energy")], definition)
        self.assertEqual(vp.getPublishValues(definition["values"]), {"p": 12, "date": "2026-01-01T00:00:00Z"})
        self.assertEqual(source.refreshes, 1)

    def test_legacy_and_explicit_http_receivers(self):
        vp = ValueProvider()
        source = Source()
        vp.registerProcessor(source, {"values": [{"power": "power"}], "http": [
            {"name": "read", "values": {"p": "power"}},
            {"name": "legacy", "values": {}},
            {"name": "new", "values": {}, "receive": True},
        ]})
        self.assertEqual(vp.dispatchHttp("read", "GET", {}), {"p": 12})
        self.assertEqual(vp.dispatchHttp("legacy", "GET", {"temp": "4"}), {"status": "OK"})
        self.assertEqual(vp.dispatchHttp("legacy", "POST", {"temp": "5"}), {"status": "OK"})
        self.assertEqual(vp.dispatchHttp("new", "POST", {"name": "test", "nested": {"p": 3}}), {"status": "OK"})
        self.assertEqual(source.payload["nested"], {"p": 3})
        with self.assertRaises(HttpRequestError) as err:
            vp.dispatchHttp("new", "GET", {"temp": "4"})
        self.assertEqual(err.exception.status, 405)
        with self.assertRaises(HttpRequestError) as err:
            vp.dispatchHttp("missing", "POST", {"temp": "4"})
        self.assertEqual(err.exception.status, 404)

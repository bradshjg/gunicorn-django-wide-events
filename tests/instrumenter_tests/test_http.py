# noqa INP001 intentionally not a package, part of pytest tests
from collections.abc import Generator

import pytest

from gunicorn_django_canonical_logs.event_context import Context
from gunicorn_django_canonical_logs.instrumenters.http import HTTPRequestCollector, HTTPRequestInstrumenter


@pytest.fixture
def instrumenter() -> Generator[HTTPRequestInstrumenter, None, None]:
    Context.reset()
    HTTPRequestCollector.reset()
    instrumenter = HTTPRequestInstrumenter()
    instrumenter.setup()
    yield instrumenter
    instrumenter.teardown()


def test_requests(instrumenter, client):
    Context.reset()
    HTTPRequestCollector.reset()
    resp = client.get("/http_requests/?count=3")
    assert resp.status_code == 200

    namespace = "http"

    instrumenter.call(None, None, None)

    assert Context.get("requests", namespace=namespace) == 3
    assert float(Context.get("request_time", namespace=namespace)) > 0


def test_collector_reset_on_call(instrumenter, client):
    Context.reset()
    HTTPRequestCollector.reset()
    resp = client.get("/http_requests/")
    assert resp.status_code == 200

    namespace = "http"

    instrumenter.call(None, None, None)

    assert Context.get("requests", namespace=namespace) == 1
    assert float(Context.get("request_time", namespace=namespace)) > 0

    Context.reset()
    instrumenter.call(None, None, None)

    assert namespace not in dict(Context.raw_items())


def test_does_not_set_context_if_no_http_requests(instrumenter, client):
    Context.reset()
    HTTPRequestCollector.reset()
    resp = client.get("/ok/")
    assert resp.status_code == 200

    namespace = "http"

    instrumenter.call(None, None, None)

    assert namespace not in dict(Context.raw_items())

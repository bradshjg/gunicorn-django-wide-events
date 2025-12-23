# noqa INP001 intentionally not a package, part of pytest tests
import time
from collections.abc import Generator

import pytest

from gunicorn_django_canonical_logs.event_context import Context
from gunicorn_django_canonical_logs.instrumenters.custom_timing import CustomTimingCollector, CustomTimingInstrumenter


@pytest.fixture
def instrumenter() -> Generator[CustomTimingInstrumenter, None, None]:
    Context.reset()
    CustomTimingCollector.reset()
    instrumenter = CustomTimingInstrumenter()
    instrumenter.setup()
    yield instrumenter
    instrumenter.teardown()


def test_time_without_namespace(instrumenter):
    with Context.time("foo"):
        time.sleep(0.2)

    instrumenter.call(None, None, None)

    assert 0.3 > float(Context.get("foo_time")) > 0.1


def test_time_with_namespace(instrumenter):
    with Context.time("foo", namespace="bar"):
        time.sleep(0.2)

    instrumenter.call(None, None, None)

    assert 0.3 > float(Context.get("foo_time", namespace="bar")) > 0.1


def test_time_overrides_existing_key_if_non_number(instrumenter):
    Context.set("foo_time", "bar")

    assert Context.get("foo_time") == "bar"

    with Context.time("foo"):
        time.sleep(0.2)

    instrumenter.call(None, None, None)

    assert 0.2 <= float(Context.get("foo_time")) < 0.3


def test_time_sums_multiple_calls(instrumenter):
    with Context.time("foo"):
        time.sleep(0.2)

    with Context.time("foo"):
        time.sleep(0.2)

    instrumenter.call(None, None, None)

    assert 0.4 <= float(Context.get("foo_time")) < 0.5

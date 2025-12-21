# noqa INP001 intentionally not a package, part of pytest tests
from collections.abc import Generator

import pytest

from gunicorn_django_canonical_logs import Context
from gunicorn_django_canonical_logs.instrumenters.saturation import SaturationInstrumenter


@pytest.fixture
def instrumenter() -> Generator[SaturationInstrumenter, None, None]:
    Context.reset()
    instrumenter = SaturationInstrumenter()
    instrumenter.setup()
    yield instrumenter
    instrumenter.teardown()


def test_adds_context_on_call(instrumenter):
    instrumenter.call(None, None, None)

    gunicorn_namespace = "g"
    assert Context.get("w_count", namespace=gunicorn_namespace) == 0
    assert Context.get("w_active", namespace=gunicorn_namespace) == 0
    assert Context.get("backlog", namespace=gunicorn_namespace) == 0

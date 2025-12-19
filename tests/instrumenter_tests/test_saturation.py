# noqa: INP001 intentionally not a package, part of pytest tests
from collections.abc import Generator

import pytest

from gunicorn_django_canonical_logs import Context
from gunicorn_django_canonical_logs.instrumenters.saturation import SaturationInstrumenter, WorkerStatus


@pytest.fixture
def instrumenter() -> Generator[SaturationInstrumenter, None, None]:
    Context.reset()
    instrumenter = SaturationInstrumenter()
    instrumenter.setup()
    yield instrumenter
    instrumenter.teardown()


def test_adds_context_on_call(instrumenter, mocker):
    backlog = "3"
    w_count = 5
    w_active = 1

    mock_backlog = mocker.PropertyMock()
    mock_backlog.return_value = backlog
    mocker.patch.object(SaturationInstrumenter, "backlog", mock_backlog)

    mock_worker_status = mocker.PropertyMock()
    mock_worker_status.return_value = WorkerStatus(w_count, w_active)
    mocker.patch.object(SaturationInstrumenter, "worker_status", mock_worker_status)

    instrumenter.call(None, None, None)

    gunicorn_namespace = "g"
    assert Context.get("w_count", namespace=gunicorn_namespace) == w_count
    assert Context.get("w_active", namespace=gunicorn_namespace) == w_active
    assert Context.get("backlog", namespace=gunicorn_namespace) == backlog

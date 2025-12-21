# noqa INP001 intentionally not a package, part of pytest tests
from collections.abc import Generator

import pytest
import requests

from gunicorn_django_canonical_logs.event_context import Context
from gunicorn_django_canonical_logs.instrumenters.exception import ExceptionInstrumenter


@pytest.fixture
def instrumenter() -> Generator[ExceptionInstrumenter, None, None]:
    Context.reset()
    instrumenter = ExceptionInstrumenter()
    instrumenter.setup()
    yield instrumenter
    instrumenter.teardown()


@pytest.mark.usefixtures("instrumenter")
def test_view_exception(live_server):
    url = live_server + "/view_exception/"
    resp = requests.get(url)
    assert resp.status_code == 500

    exc_namespace = "exc"

    assert Context.get("type", namespace=exc_namespace) == "MyError"
    assert Context.get("msg", namespace=exc_namespace) == "Oh noes!"
    assert "view_exception" in Context.get("loc", namespace=exc_namespace)
    assert "func_that_throws" in Context.get("cause_loc", namespace=exc_namespace)


@pytest.mark.usefixtures("instrumenter")
def test_view_exception_in_third_party(live_server):
    url = live_server + "/third_party_exception/"
    resp = requests.get(url)
    assert resp.status_code == 500

    exc_namespace = "exc"

    assert Context.get("type", namespace=exc_namespace) == "ConnectionError"
    assert "Name or service not known" in Context.get("msg", namespace=exc_namespace)
    assert "third_party_exception" in Context.get("loc", namespace=exc_namespace)
    assert "send" in Context.get("cause_loc", namespace=exc_namespace)


@pytest.mark.usefixtures("instrumenter")
def test_template_syntax_exception(live_server):
    url = live_server + "/template_syntax_exception/"
    resp = requests.get(url)
    assert resp.status_code == 500

    exc_namespace = "exc"

    assert Context.get("type", namespace=exc_namespace) == "TemplateSyntaxError"
    assert "Invalid block tag" in Context.get("msg", namespace=exc_namespace)
    assert "template_syntax_exception" in Context.get("loc", namespace=exc_namespace)
    assert "invalid_block_tag" in Context.get("cause_loc", namespace=exc_namespace)


@pytest.mark.usefixtures("instrumenter")
def test_template_callable_exception(live_server):
    url = live_server + "/template_callable_exception/"
    resp = requests.get(url)
    assert resp.status_code == 500

    exc_namespace = "exc"

    assert Context.get("type", namespace=exc_namespace) == "MyError"
    assert Context.get("msg", namespace=exc_namespace) == "Oh noes!"
    assert Context.get("template", namespace=exc_namespace) == "callable_exception.html:3"
    assert "template_callable_exception" in Context.get("loc", namespace=exc_namespace)
    assert "func_that_throws" in Context.get("cause_loc", namespace=exc_namespace)


@pytest.mark.usefixtures("instrumenter")
def test_no_exception(live_server):
    url = live_server + "/template_ok/"
    resp = requests.get(url)
    assert resp.status_code == 200

    exc_namespace = "exc"

    assert Context.get("type", namespace=exc_namespace) is None
    assert Context.get("msg", namespace=exc_namespace) is None
    assert Context.get("template", namespace=exc_namespace) is None
    assert Context.get("loc", namespace=exc_namespace) is None
    assert Context.get("cause_loc", namespace=exc_namespace) is None

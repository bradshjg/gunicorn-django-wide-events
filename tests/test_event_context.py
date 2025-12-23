# noqa INP001 intentionally not a package, part of pytest tests
import time

from gunicorn_django_canonical_logs.event_context import EventContext


def test_set_without_namespace():
    context = EventContext()
    context.set("foo", "bar")
    assert context.get("foo") == "bar"


def test_set_with_namespace():
    context = EventContext()
    context.set("foo", "bar", namespace="baz")
    assert context.get("foo", namespace="baz") == "bar"


def test_update_without_namespace():
    context = EventContext()
    context.update(context={"foo": "bar"})
    assert context.get("foo") == "bar"


def test_update_with_namespace():
    context = EventContext()
    context.update(context={"foo": "bar"}, namespace="baz")
    assert context.get("foo", namespace="baz") == "bar"


def test_update_and_put_at_beginning():
    context = EventContext()
    context.set("foo", "bar")
    context.update(context={"foo": "bar"}, namespace="beginning", beginning=True)
    assert next(iter(context.raw_items())) == ("beginning", {"foo": "bar"})


def test_reset():
    context = EventContext()
    context.set("foo", "bar")
    context.reset()
    assert context.get("foo") is None

from __future__ import annotations

import functools
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import ClassVar

from requests.sessions import Session

from gunicorn_django_canonical_logs.event_context import Context
from gunicorn_django_canonical_logs.instrumenters.protocol import InstrumenterProtocol
from gunicorn_django_canonical_logs.instrumenters.registry import register_instrumenter


class HTTPRequestCollector:
    _requests: ClassVar[dict[str, int | float]] = defaultdict(int)

    @classmethod
    def add(cls, duration: float):
        cls._requests["count"] += 1
        cls._requests["duration"] += duration

    @classmethod
    def reset(cls):
        cls._requests.clear()

    @classmethod
    def get_data(cls):
        return {
            "requests": cls._requests["count"],
            "request_time": cls._requests["duration"],
        }

    @classmethod
    @contextmanager
    def instrument(cls):
        start = time.monotonic()
        try:
            yield
        finally:
            duration = time.monotonic() - start
            cls.add(duration)


@register_instrumenter
class HTTPRequestInstrumenter(InstrumenterProtocol):
    NAMESPACE = "http"

    def __init__(self):
        self._orig_send = Session.send

    def setup(self):
        Session.send = self._instrumented_send

    def teardown(self):
        Session.send = self._orig_send

    def call(self, _req, _resp, _environ):
        data = HTTPRequestCollector.get_data()
        if data.get("requests", 0) > 0:
            Context.update(namespace=self.NAMESPACE, context=data)
        HTTPRequestCollector.reset()

    @property
    def _instrumented_send(self):
        orig_send = self._orig_send

        @functools.wraps(orig_send)
        def instrumented_send(self, request, **kwargs):
            with HTTPRequestCollector.instrument():
                return orig_send(self, request, **kwargs)

        return instrumented_send

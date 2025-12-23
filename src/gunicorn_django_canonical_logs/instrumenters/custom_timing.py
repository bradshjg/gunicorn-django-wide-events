from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from typing import ClassVar

from gunicorn_django_canonical_logs.event_context import Context
from gunicorn_django_canonical_logs.instrumenters.protocol import InstrumenterProtocol
from gunicorn_django_canonical_logs.instrumenters.registry import register_instrumenter


class CustomTimingCollector:
    _data: ClassVar[dict[str, dict[str, dict[str, int | float]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    @classmethod
    def add(cls, namespace, key, duration: float):
        cls._data[namespace][key]["count"] += 1
        cls._data[namespace][key]["duration"] += duration

    @classmethod
    def reset(cls):
        cls._data.clear()

    @classmethod
    def get_data(cls) -> dict[str, dict[str, int | float]]:
        data: dict[str, dict[str, str, int | float]] = defaultdict(dict)
        for namespace, namespace_context in cls._data.items():
            for key in namespace_context.keys():
                data[namespace][f"{key}_time"] = cls._data[namespace][key]["duration"]
                if cls._data[namespace][key]["count"] > 1:
                    data[namespace][f"{key}_count"] = cls._data[namespace][key]["count"]
        return data

    @classmethod
    @contextmanager
    def instrument(cls, key, namespace):
        start = time.monotonic()
        try:
            yield
        finally:
            duration = time.monotonic() - start
            cls.add(namespace, key, duration)


@register_instrumenter
class CustomTimingInstrumenter(InstrumenterProtocol):
    def call(self, _req, _resp, _environ):
        data = CustomTimingCollector.get_data()
        for namespace, namespace_context in data.items():
            Context.update(context=namespace_context, namespace=namespace)
        CustomTimingCollector.reset()

from __future__ import annotations

import uuid

from gunicorn_django_canonical_logs.event_context import Context
from gunicorn_django_canonical_logs.gunicorn_hooks import register_hook
from gunicorn_django_canonical_logs.instrumenters import (  # noqa F401 registers instrumenters
    database,
    exception,
    request,
)
from gunicorn_django_canonical_logs.instrumenters.registry import instrumenter_registry


@register_hook
def post_fork(_server, _worker):
    for instrumenter in instrumenter_registry.values():
        instrumenter.setup()


@register_hook
def pre_request(_worker, _req):
    Context.reset()
    Context.set("id", str(uuid.uuid4()), namespace="req")

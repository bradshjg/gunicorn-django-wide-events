from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from gunicorn import glogging

from gunicorn_django_canonical_logs.event_context import Context
from gunicorn_django_canonical_logs.instrumenters.registry import instrumenter_registry
from gunicorn_django_canonical_logs.logfmt import LogFmt

if TYPE_CHECKING:
    from gunicorn.http.message import Request
    from gunicorn.http.wsgi import Response


class Logger(glogging.Logger):
    EVENT_TYPE = "type"
    EVENT_NAMESPACE = "event"
    PRESERVE_EXISTING_LOGGER = os.environ.get("GUNICORN_PRESERVE_EXISTING_LOGGER", "0") == "1"

    def access(self, resp: Request, req: Request, environ: dict[str, Any], *_args, **_kwargs):
        # See https://github.com/bradshjg/gunicorn-django-canonical-logs/issues/7
        # The goal is to allow a smooth transition when existing logs are used in downstream systems
        if self.PRESERVE_EXISTING_LOGGER:
            super().access(resp, req, environ, *_args, **_kwargs)

        # gunicorn calls this on abort, but the data is weird (e.g. request timing is abort handler timing?); silence it
        if req.timed_out:
            return

        self._emit_log(req=req, resp=resp, environ=environ, event_type="request")

    def timeout(self, req: Request):
        self._emit_log(req=req, resp=None, environ=None, event_type="timeout")

    def _emit_log(
        self, *, req: Request, resp: Response | None, environ: dict[str, Any] | None, event_type: str
    ) -> None:
        Context.update(context={self.EVENT_TYPE: event_type}, namespace=self.EVENT_NAMESPACE, beginning=True)

        for instrumenter in instrumenter_registry.values():
            instrumenter.call(req, resp, environ)

        self.access_log.info(LogFmt.format(Context))

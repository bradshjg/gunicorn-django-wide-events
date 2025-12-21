from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from gunicorn.http.message import Request
    from gunicorn.http.wsgi import Response


class InstrumenterProtocol(Protocol):
    def setup(self) -> None:
        """Override to do any patching/configuration as necessary"""
        return None

    def teardown(self) -> None:
        """Override to revert any patching/configuration as necessary

        NB this isn't expected to be useful outside of testing
        """
        return None

    def call(self, req: Request | None, resp: Response | None, environ: dict[str, Any] | None) -> None:  # noqa ARG002 provides protocol
        """Override to add events to the context as necessary"""
        return None

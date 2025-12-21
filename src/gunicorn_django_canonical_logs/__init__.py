# SPDX-FileCopyrightText: 2025-present James Bradshaw <james.g.bradshaw@gmail.com>
#
# SPDX-License-Identifier: MIT
from gunicorn_django_canonical_logs import (
    instrumenters,  # noqa F401 registers hooks
    monitors,  # noqa F401 registers hooks
)
from gunicorn_django_canonical_logs.event_context import Context  # noqa F401 friendly namespace
from gunicorn_django_canonical_logs.instrumenters.registry import register_instrumenter  # noqa F401 friendly namespace

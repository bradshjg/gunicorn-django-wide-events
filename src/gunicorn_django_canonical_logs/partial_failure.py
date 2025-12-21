import sys
import traceback
from functools import wraps

from django.conf import settings

from gunicorn_django_canonical_logs.event_context import Context, EventContext
from gunicorn_django_canonical_logs.logfmt import LogFmt
from gunicorn_django_canonical_logs.stack_context import get_stack_loc_context


def on_error(*, return_value):
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            try:
                retval = function(*args, **kwargs)
            except Exception:
                if settings.DEBUG:
                    raise

                exc_type, exc_value, tb = sys.exc_info()
                exc_context = {
                    "type": exc_type.__name__,
                    "msg": str(exc_value),
                }
                loc_context = get_stack_loc_context(traceback.extract_tb(tb))
                exc_context.update(loc_context)

                request_id = Context.get("id", namespace="req")

                partial_failure_context = EventContext()
                partial_failure_context.set("type", "partial_failure", namespace="event")
                partial_failure_context.set("id", request_id, namespace="req")
                partial_failure_context.update(context=exc_context, namespace="exc")

                print(LogFmt.format(partial_failure_context), flush=True)  # noqa T201 "logging" to stdout, skipping all formatters

                return return_value
            else:
                return retval

        return wrapper

    return decorator

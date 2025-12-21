import sys
import threading
import traceback

from gunicorn.http.message import Request
from gunicorn.workers.base import Worker

from gunicorn_django_canonical_logs.event_context import Context
from gunicorn_django_canonical_logs.gunicorn_hooks.registry import register_hook
from gunicorn_django_canonical_logs.stack_context import get_stack_loc_context

TIMEOUT_BUFFER_SECONDS = 0.2


def on_timeout(timeout: int, worker: Worker, req: Request):
    main_thread_frame = sys._current_frames()[threading.main_thread().ident or 0]  # noqa SLF001 _current_frames is documented
    stack_summary = traceback.extract_stack(main_thread_frame)
    Context.set("time", timeout, namespace="resp")
    Context.update(namespace="timeout", context=get_stack_loc_context(stack_summary))
    req.timed_out = True

    worker.log.timeout(req)


@register_hook
def pre_request(worker, req):
    req.timed_out = False
    worker_timeout = worker.cfg.timeout  # N.B. timeout from config, worker.timeout is the notify interval
    timeout = max(worker_timeout - TIMEOUT_BUFFER_SECONDS, TIMEOUT_BUFFER_SECONDS)
    worker.timeout_timer = threading.Timer(timeout, on_timeout, args=(timeout, worker, req))
    worker.timeout_timer.start()


@register_hook
def post_request(worker, *_):
    worker.timeout_timer.cancel()

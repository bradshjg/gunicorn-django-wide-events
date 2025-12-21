import signal
import time
from pathlib import Path

import requests
from django.core.management import execute_from_command_line
from django.core.wsgi import get_wsgi_application
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path
from django.views.generic import TemplateView
from whitenoise import WhiteNoise

from gunicorn_django_canonical_logs import Context, register_instrumenter
from gunicorn_django_canonical_logs.instrumenters.protocol import InstrumenterProtocol
from gunicorn_django_canonical_logs.partial_failure import on_error


@register_instrumenter
class MyInstrumenter(InstrumenterProtocol):
    def call(self, _req, _resp, _environ):
        Context.set("key", "val")


class MyError(Exception):
    def __init__(self):
        super().__init__("Oh noes!")


def func_that_throws():
    raise MyError


def ok(_):
    return HttpResponse("OK!")


def view_exception(_):
    func_that_throws()
    return HttpResponse("We shouldn't get here!")


def third_party_exception(_):
    requests.get("http://no-way-this-will-resolve-in-dns.com")
    return HttpResponse("We shouldn't get here!")


def template_syntax_exception(request):
    return render(request, "syntax_exception.html")


def template_callable_exception(request):
    return render(request, "callable_exception.html", {"callable": func_that_throws})


def template_ok(request):
    return render(request, "ok.html", {"msg": "template OK!"})


def partial_failure(_):
    @on_error(return_value="partial failure")
    def will_throw():
        func_that_throws()

    msg = will_throw()

    return HttpResponse(msg)


class TemplateOKClassView(TemplateView):
    template_name = "ok.html"


def custom_event(_):
    Context.set("custom_event", 1)
    return HttpResponse("Added custom event!")


def custom_timing(_):
    with Context.time("custom"):
        time.sleep(0.2)

    return HttpResponse("OK!")


def sleep(request):
    duration = float(request.GET.get("duration", "1"))
    simulate_blocking(duration)
    return HttpResponse(f"Slept {duration} seconds!")


def rude_sleep(request):
    duration = float(request.GET["duration"])
    simulate_blocking_and_ignoring_signals(duration)
    return HttpResponse(f"Slept {duration} seconds!")


def db_queries(_):
    from db.models import Person  # noqa PLC0415 lazily import after configuration

    p = Person(first_name="first", last_name="last")
    p.save()
    p.refresh_from_db()
    p.refresh_from_db()
    return HttpResponse("OK")


def http_requests(request):
    count = int(request.GET.get("count", "1"))
    for _ in range(count):
        requests.get("https://www.google.com", timeout=2)
    return HttpResponse(f"Made {count} HTTP requests!")


def simulate_blocking(duration):
    time.sleep(duration)


def simulate_blocking_and_ignoring_signals(duration):
    signal.signal(signal.SIGABRT, signal.SIG_IGN)
    time.sleep(duration)
    signal.signal(signal.SIGABRT, signal.SIG_DFL)


urlpatterns = [
    path("ok/", ok),
    path("template_ok/", template_ok),
    path("template_ok_class_view/", TemplateOKClassView.as_view()),
    path("view_exception/", view_exception),
    path("third_party_exception/", third_party_exception),
    path("template_syntax_exception/", template_syntax_exception),
    path("template_callable_exception/", template_callable_exception),
    path("named_ok/", ok, name="named_ok_view"),
    path("custom_event/", custom_event),
    path("custom_timing/", custom_timing),
    path("sleep/", sleep),
    path("rude_sleep/", rude_sleep),
    path("db_queries/", db_queries),
    path("http_requests/", http_requests),
    path("partial_failure/", partial_failure),
]

application = get_wsgi_application()
whitenoise_app = WhiteNoise(application, root=str(Path(__file__).resolve().parent / "static"), prefix="static/")

if __name__ == "__main__":
    execute_from_command_line()

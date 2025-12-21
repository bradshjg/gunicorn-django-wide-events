# Gunicorn Django Canonical Logs

[![PyPI - Version](https://img.shields.io/pypi/v/gunicorn-django-canonical-logs.svg)](https://pypi.org/project/gunicorn-django-canonical-logs)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/gunicorn-django-canonical-logs.svg)](https://pypi.org/project/gunicorn-django-canonical-logs)

-----

`gunicorn-django-canonical-logs` provides extensible [canonical log lines](https://brandur.org/canonical-log-lines) for Gunicorn/Django applications.

## Table of Contents

- [Caveats](#caveats)
- [Installation](#installation)
- [Usage](#usage)
- [Overview](#overview)
  * [Example logs](#example-logs)
  * [Default intstrumenters](#default-instrumenters)
    - [Request intstrumenter](#request-instrumenter)
    - [Exception intstrumenter](#exception-instrumenter)
    - [Database intstrument](#database-instrumenter)
  * [Default monitors](#default-monitors)
    - [Saturation monitor](#saturation-monitor)
    - [Timeout monitor](#timeout-monitor)
  * [Extending gunicorn-django-canonical-logs](#extending-gunicorn-django-canonical-logs)
    - [Application-specific context](#application-specific-context)
    - [Application-specific timing](#application-specific-timing)
    - [Custom instrumenters](#custom-instrumenters)
- [License](#license)


## Caveats

> [!WARNING]
> This is alpha software. It has not (yet!) been battle-tested and patches the internals of libraries in order to support instrumentation in a way similar to OpenTelemetry libraries.
>
> This library currently requires running Gunicorn on Linux using sync workers listening on TCP sockets.

## Installation

```console
pip install gunicorn-django-canonical-logs
```

## Usage

Add the following to your Gunicorn configuration file:

```python
from gunicorn_django_canonical_logs.glogging import Logger
from gunicorn_django_canonical_logs.gunicorn_hooks import *  # register Gunicorn hooks and instrumenters

accesslog = "-"
logger_class = Logger
```

### Configuration

Minimal configuration is available via environment variables:

`GUNICORN_PRESERVE_EXISTING_LOGGER` (default `0`) - If set to `1`, will preserve existing gunicorn access logs in addition to canonical logs.
`GUNICORN_SATURATION_METRICS_INTERVAL` (default `10`) - Interval in seconds to capture/emit saturation metrics.

### Partial failure

This library also includes an `@on_error(return_value=...)` decorator that will emit a `partial_failure` event correlated to the request
log via `req_id` with exception context. See `tests/server/app.py:partial_failure` for an example.

The motivation is that some failure is expected and we'd prefer to return a degraded experience in some cases. In the event that's
necessary, correlated logs provide the opportunity to monitor the frequency and type of errors observed.

## Overview

The goal is to enhance obersvability by providing reasonable defaults and extensibility to answer:

* If a request was processed, what did it do?
* If a request timed out, what had it done and what was it doing?
* Are we seeing queueing or memory pressure?

A request will generate exactly one of these two `event_type`s:

* `request` - the worker process was able to successfully process the request and return a response
* `timeout` - the worker process timed out before returning a response

Additionally, `saturation_metrics` events will be regularly emitted.

## Example logs

Examples can be generated from the app used for integration testing:

* `cd tests/server`
* `DJANGO_SETTINGS_MODULE=settings python app.py migrate`
* `DJANGO_SETTINGS_MODULE=settings gunicorn -c gunicorn_config.py app`

And then, from another shell:

* `curl http://localhost:8080/db_queries/`
* `curl http://localhost:8080/rude_sleep/?duration=10`

### Request events

<details><summary>200 response from Django with DB queries</summary>

```
event_type="request"
req_method="GET"
req_path="/db_queries/"
req_referrer="localhost:8080"
req_user_agent="curl/7.88.1"
resp_view="app.db_queries"
resp_time="0.016"
resp_cpu_time="0.006"
resp_status="200"
db_queries="3"
db_time="0.007"
db_dup_queries="2"
db_dup_time="0.003"
```

</details>

<details><summary>404 response from Django</summary>

```
event_type="request"
req_method="GET"
req_path="/does-no-exist/"
req_referrer="-"
req_user_agent="curl/7.88.1"
resp_view="-"
resp_time="0.000"
resp_cpu_time="0.000"
resp_status="404"
```

</details>

<details><summary>500 response from Django</summary>

```
event_type="request"
req_method="GET"
req_path="/view_exception/"
req_referrer="-"
req_user_agent="curl/7.88.1"
exc_type="MyError"
exc_msg="Oh noes!"
exc_loc="app.py:38:view_exception"
exc_cause_loc="app.py:30:func_that_throws"
resp_view="app.view_exception"
resp_time="0.005"
resp_cpu_time="0.003"
resp_status="500"
g_w_count="1"
g_w_active="0"
g_backlog="0"
app_key="val"
```

</details>

<details><summary>200 response from Whitenoise (static assets)</summary>

```
event_type="request"
req_method="GET"
req_path="/static/foo.txt"
req_referrer="localhost:8080"
req_user_agent="curl/7.88.1"
resp_status="200"
g_w_count="1"
g_w_active="0"
g_backlog="0"
```

</details>

### Timeout events

<details><summary>timeout</summary>

```
event_type="timeout"
req_method="GET"
req_path="/rude_sleep/"
req_referrer="localhost:8080"
req_user_agent="curl/7.88.1"
resp_time="0.8"
timeout_loc="gunicorn_django_canonical_logs/instrumenters/request.py:25:context_middleware"
timeout_cause_loc="app.py:103:simulate_blocking_and_ignoring_signals"
g_w_count="1"
g_w_active="0"
g_backlog="0"
```

</details>

### Partial failure events

<details><summary>partial failure</summary>

```
event_type="partial_failure"
req_id="944e3dc1-14df-4dcd-aafe-00deea240c8b"
exc_type="MyError"
exc_msg="Oh noes!"
exc_loc="app.py:63:will_throw"
exc_cause_loc="app.py:31:func_that_throws"

event_type="request"
req_id="944e3dc1-14df-4dcd-aafe-00deea240c8b"
req_method="GET" req_path="/partial_failure/"
req_referrer="-"
req_user_agent="curl/7.88.1"
resp_view="app.partial_failure"
resp_time="0.006"
resp_cpu_time="0.005"
resp_status="200"
g_w_count="1"
g_w_active="0"
g_backlog="0"
```

</details>

### Saturation metrics events

<details><summary>Saturation metrics</summary>

```
event_type="saturation_metrics"
g_backlog="0"
g_workers_total="5"
g_workers_idle="3"
g_memory_usage_mib="140"
```

</details>

### Default instrumenters

#### Request instrumenter

* `req_method` (`string`) - HTTP method (e.g. `GET`/`POST`)
* `req_path` (`string`) - URL path
* `req_referer` (`string`) - `Referrer` HTTP header
* `req_user_agent` (`string`) - `User-Agent` HTTP header
* `resp_time` (`float`) - wall time spent processing the request (in seconds)
* `resp_view` (`string`) - Django view that generated the response
* `resp_cpu_time` (`float`) - CPU time (i.e. ignoring sleep/wait) spent processing the request (in seconds)
* `resp_status` (`int`) - HTTP status code of the response

#### Exception instrumenter

* `exc_type` (`string`) - `type` of the exception
* `exc_message` (`string`) - exception message
* `exc_loc` (`string`) - `{module}:{line_number}:{name}` of the top of the stack (i.e. the last place the
  exception could've been handled)
* `exc_cause_loc` (`string`) - `{module}:{line_number}:{name}` of the frame that threw the exception
* `exc_template` (`string`) - `{template_name}:{line_number}` (if raised during template rendering)

> [!NOTE]
> There's some subtlety in how `loc`/`cause_loc` work; they attempt to provide application-relevant info by
> ignoring frames in library code if application frames are available.

#### Database instrumenter

* `db_queries` (`int`) - total number of queries executed
* `db_time` (`float`) - total time spent executing queries (in seconds)
* `db_dup_queries` (`int`) - total number of non-unique queries; could indicate N+1 issues
* `db_dup_time` (`float`) - total time spent executing non-unique queries (in seconds); could indicate N+1 issues

#### Saturation metrics

* `g_workers_total` (`int`) - total number of Gunicorn workers
* `g_workers_idle` (`int`) - number of idle Gunicorn workers available to process requests
* `backlog` (`int`) - number of queued requests
* `memory_usage_mib` (`int`) - memory usage (in MiB) across all Gunicorn processes

> [!NOTE]
> These values are regularly sampled, and represent a snapshot. To derive useful data, analyze the values over time.

### Default monitors

#### Saturation monitor

The saturation monitor samples and aggregates Gunicorn data; it provides data on the current number of active/idle workers
as well as the number of queued requests that have not been assigned to a worker and the memory usage.

#### Timeout monitor

The timeout monitor wakes up slightly before the Gunicorn timeout in order to emit stack frame and instrumenter data before
Gunicorn recycles the worker.

## Extending gunicorn-django-canonical-logs

### Application-specific context

from anywhere in your application, use

```python
from gunicorn_django_canonical_logs import Context

Context.set("custom", "my_value")
```

This would add `app_custom="my_value"` to the log for the current request; context is cleared between requests.

### Application-specific timing

from anywhere in your application, use

```python
from gunicorn_django_canonical_logs import Context

with Context.time("custom"):
    do_thing_that_takes_time()
```

This would add `app_custom_time="{wall time in seconds}"` to the log for the current request based on the execution
time of `do_thing_that_takes_time()`; multiple timings using the same key are summed.

### Custom instrumenters

```python
from gunicorn_django_canonical_logs import Context, register_instrumenter

@register_instrumenter
class MyInstrumenter:
    def setup(self):
        pass  # called once after forking a Gunicorn worker

    def call(self, request, response, environ):
        pass  # called every time an event is emitted
```

> [!IMPORTANT]
> The application must import the instrumenter for it to register itself.

## License

`gunicorn-django-canonical-logs` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.

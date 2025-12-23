# noqa INP001 intentionally not a package, part of pytest tests
from __future__ import annotations

import concurrent.futures
import os
import re
import shlex
import subprocess
import tempfile
import time
from typing import IO, TYPE_CHECKING

import pytest
import requests
from server import gunicorn_config

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence


@pytest.fixture(scope="module")
def server() -> Generator[tuple[IO[str], IO[str]], None, None]:
    """Gunicorn process running Django on localhost:8080"""
    yield from _run_server(bind="127.0.0.1:8080", app="tests.server.app")


@pytest.fixture(scope="module")
def server_with_whitenoise() -> Generator[tuple[IO[str], IO[str]], None, None]:
    """Gunicorn process running Django with Whitenoise WSGI middleware on localhost:8081"""
    yield from _run_server(bind="127.0.0.1:8081", app="tests.server.app:whitenoise_app")


@pytest.fixture(scope="module")
def server_with_existing_logger_preserved() -> Generator[tuple[IO[str], IO[str]], None, None]:
    """Gunicorn process running with log preservation enabled on localhost:8082"""
    yield from _run_server(
        bind="127.0.0.1:8082", app="tests.server.app", env={"GUNICORN_PRESERVE_EXISTING_LOGGER": "1"}
    )


@pytest.fixture(scope="module")
def server_with_small_saturation_metrics_interval() -> Generator[tuple[IO[str], IO[str]], None, None]:
    """Gunicorn process running with log preservation enabled on localhost:8082"""
    yield from _run_server(
        bind="127.0.0.1:8083", app="tests.server.app", env={"GUNICORN_SATURATION_METRICS_INTERVAL": "0.5"}
    )


def _run_server(bind: str, app: str, env: dict[str, str] | None = None):
    fp_stdout = tempfile.TemporaryFile(mode="w+")  # noqa SIM115
    fp_stderr = tempfile.TemporaryFile(mode="w+")  # noqa SIM115

    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    s_proc = subprocess.Popen(
        ["gunicorn", "--bind", bind, "-c", gunicorn_config.__file__, app],
        stdout=fp_stdout,
        stderr=fp_stderr,
        bufsize=1,  # line buffered
        text=True,
        env=process_env,
    )

    time.sleep(5)  # HACK wait for server boot and saturation monitor to start emitting data

    try:
        yield fp_stdout, fp_stderr
    finally:
        s_proc.terminate()
        s_proc.wait()


def clear_output(fp: IO[str]) -> None:
    fp.seek(0)
    fp.truncate()


def read_log_lines(fp: IO[str]) -> list[str]:
    time.sleep(1)
    fp.flush()
    fp.seek(0)
    return fp.readlines()


def get_parsed_canonical_logs(fp: IO[str], event_types: Sequence[str] = ("request",)) -> list[dict[str, str]]:
    """Returns a list of dictionaries of the key-value pairs in canonical logs of the given event type.

    NB this is unable to parse lines a "real" logfmt parser would, e.g. it breaks on values with "=" in them.

    Example:

    ```
    event_type="request" req_method="GET" resp_time=0.001
    random other log line
    event_type="other" is="ignored"
    event_type="request" req_method="POST"
    ```

    -> [
      {"event_type": "request", "req_method": "GET", "resp_time": "0.001"},
      {"event_type": "request", "req_method": "POST"},
    ]
    """
    lines = read_log_lines(fp)
    canonical_lines = [line for line in lines if any(line.startswith(f'event_type="{type_}"') for type_ in event_types)]
    # HACK HACK HACK the idea behind this "parser" is to let shlex handle preserving spaces within quoted logfmt values
    parsed_lines = []
    for line in canonical_lines:
        word_split = shlex.split(" ".join(line.strip().split("=")))
        word_split_iter = iter(word_split)
        parsed_lines.append({pair[0]: pair[1] for pair in dict(zip(word_split_iter, word_split_iter)).items()})
    return parsed_lines


def test_context_reset_between_requests(server) -> None:
    stdout, _ = server
    clear_output(stdout)

    custom_event_key = "app_custom_event"

    requests.get("http://localhost:8080/custom_event/")

    logs = get_parsed_canonical_logs(stdout)
    assert len(logs) == 1
    assert logs[0][custom_event_key] == "1"
    first_request_id = logs[0]["req_id"]

    # context reset between requests
    clear_output(stdout)
    requests.get("http://localhost:8080/ok/")

    logs = get_parsed_canonical_logs(stdout)
    assert len(logs) == 1
    assert custom_event_key not in logs[0]
    second_request_id = logs[0]["req_id"]

    assert first_request_id != second_request_id


def test_access_event(server) -> None:
    stdout, _ = server
    clear_output(stdout)

    requests.get("http://localhost:8080/ok/")

    logs = get_parsed_canonical_logs(stdout)
    assert len(logs) == 1
    assert logs[0]["req_path"] == "/ok/"
    assert logs[0]["resp_status"] == "200"


def test_exception_event(server) -> None:
    stdout, _ = server
    clear_output(stdout)

    requests.get("http://localhost:8080/view_exception/")

    logs = get_parsed_canonical_logs(stdout)
    assert len(logs) == 1
    assert logs[0]["resp_status"] == "500"
    assert logs[0]["exc_type"] == "MyError"
    assert logs[0]["exc_msg"] == "Oh noes!"
    assert re.search(r"app.py:\d+:view_exception", logs[0]["exc_loc"])
    assert re.search(r"app.py:\d+:func_that_throws", logs[0]["exc_cause_loc"])


def test_template_exception_event(server) -> None:
    stdout, _ = server
    clear_output(stdout)

    requests.get("http://localhost:8080/template_callable_exception/")

    logs = get_parsed_canonical_logs(stdout)
    assert len(logs) == 1
    assert logs[0]["resp_status"] == "500"
    assert logs[0]["exc_type"] == "MyError"
    assert logs[0]["exc_msg"] == "Oh noes!"
    assert re.search(r"callable_exception.html:\d+", logs[0]["exc_template"])
    assert re.search(r"app.py:\d+:template_callable_exception", logs[0]["exc_loc"])
    assert re.search(r"app.py:\d+:func_that_throws", logs[0]["exc_cause_loc"])


@pytest.mark.django_db
def test_db_event(server) -> None:
    stdout, _ = server
    clear_output(stdout)

    requests.get("http://localhost:8080/db_queries/")

    logs = get_parsed_canonical_logs(stdout)
    assert len(logs) == 1
    assert logs[0]["resp_status"] == "200"
    assert logs[0]["db_queries"] == "3"


def test_http_request_event(server) -> None:
    stdout, _ = server
    clear_output(stdout)

    requests.get("http://localhost:8080/http_requests/")

    logs = get_parsed_canonical_logs(stdout)
    assert len(logs) == 1
    assert logs[0]["resp_status"] == "200"
    assert logs[0]["http_requests"] == "1"
    assert float(logs[0]["http_request_time"]) > 0


def test_custom_event(server) -> None:
    stdout, _ = server
    clear_output(stdout)

    requests.get("http://localhost:8080/custom_event/")

    logs = get_parsed_canonical_logs(stdout)
    assert len(logs) == 1
    assert logs[0]["app_custom_event"] == "1"


def test_custom_timing(server) -> None:
    stdout, _ = server
    clear_output(stdout)

    requests.get("http://localhost:8080/custom_timing/")

    logs = get_parsed_canonical_logs(stdout)
    assert len(logs) == 1
    assert re.search(r"0.2\d{2}", logs[0]["app_custom_time"])
    assert logs[0].get("app_custom_count") is None
    assert re.search(r"0.4\d{2}", logs[0]["app_custom_multiple_time"])
    assert logs[0]["app_custom_multiple_count"] == "2"


def test_app_instrumenter(server) -> None:
    stdout, _ = server
    clear_output(stdout)

    requests.get("http://localhost:8080/custom_event/")

    logs = get_parsed_canonical_logs(stdout)
    assert len(logs) == 1
    assert logs[0]["app_key"] == "val"


def test_timeout_event(server) -> None:
    stdout, _ = server
    clear_output(stdout)

    requests.get("http://localhost:8080/sleep/?duration=10")

    logs = get_parsed_canonical_logs(stdout, event_types=("timeout",))
    assert len(logs) == 1
    assert re.search(r"app\.py:\d+:sleep", logs[0]["timeout_loc"])
    assert re.search(r"app\.py:\d+:simulate_blocking", logs[0]["timeout_cause_loc"])


def test_sigkill_timeout_event(server) -> None:
    stdout, _ = server
    clear_output(stdout)

    with pytest.raises(requests.ConnectionError):  # worker SIGKILL will abort connection
        requests.get("http://localhost:8080/rude_sleep/?duration=10")

    logs = get_parsed_canonical_logs(stdout, event_types=("timeout",))
    assert len(logs) == 1
    assert re.search(r"app\.py:\d+:rude_sleep", logs[0]["timeout_loc"])
    assert re.search(r"app\.py:\d+:simulate_blocking_and_ignoring_signals", logs[0]["timeout_cause_loc"])


def test_successful_wsgi_middleware_static_file(server_with_whitenoise):
    stdout, _ = server_with_whitenoise
    clear_output(stdout)

    requests.get("http://localhost:8081/static/foo.txt", headers={"Referrer": "http://localhost:8080"})
    logs = get_parsed_canonical_logs(stdout)
    assert len(logs) == 1
    assert logs[0]["req_method"] == "GET"
    assert logs[0]["req_path"] == "/static/foo.txt"
    assert logs[0]["req_referrer"] == "http://localhost:8080"
    assert logs[0]["req_user_agent"].startswith("python-requests")
    assert logs[0]["resp_status"] == "200"


def test_preserve_existing_request_logger(server, server_with_existing_logger_preserved):
    server_stdout, _ = server
    clear_output(server_stdout)

    server_with_existing_logger_preserved_stdout, _ = server_with_existing_logger_preserved
    clear_output(server_with_existing_logger_preserved_stdout)

    requests.get("http://localhost:8080/ok/")  # existing logger disabled
    requests.get("http://localhost:8082/ok/")  # existing logger preserved

    server_log_lines = [
        line for line in read_log_lines(server_stdout) if not line.startswith('event_type="saturation_metrics"')
    ]
    server_with_existing_logger_preserved_log_lines = [
        line
        for line in read_log_lines(server_with_existing_logger_preserved_stdout)
        if not line.startswith('event_type="saturation_metrics"')
    ]

    assert len(server_log_lines) == 1, "expected one request event"
    assert server_log_lines[0].startswith('event_type="request"')

    assert len(server_with_existing_logger_preserved_log_lines) == 2, (
        "expected one request event and one default logger request log line"
    )
    assert server_with_existing_logger_preserved_log_lines[0].startswith("127.0.0.1")
    assert server_with_existing_logger_preserved_log_lines[1].startswith('event_type="request"')


def test_partial_failure_event(server) -> None:
    stdout, _ = server
    clear_output(stdout)

    resp = requests.get("http://localhost:8080/partial_failure/")

    assert resp.status_code == 200
    assert resp.content == b"partial failure"

    logs = get_parsed_canonical_logs(stdout, event_types=("request", "partial_failure"))
    assert len(logs) == 2

    assert logs[0]["req_id"] == logs[1]["req_id"]

    assert logs[0]["event_type"] == "partial_failure"
    assert logs[0]["exc_type"] == "MyError"
    assert logs[0]["exc_msg"] == "Oh noes!"
    assert logs[0]["exc_loc"].endswith("will_throw")
    assert logs[0]["exc_cause_loc"].endswith("func_that_throws")

    assert logs[1]["event_type"] == "request"


def test_saturation_metrics(server_with_small_saturation_metrics_interval):
    server_stdout, _ = server_with_small_saturation_metrics_interval
    clear_output(server_stdout)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(requests.get, "http://localhost:8083/sleep/?duration=1") for _ in range(3)]

    concurrent.futures.wait(futures)

    expected_saturated_event = {
        "g_backlog": "2",
        "g_workers_idle": "0",
        "g_workers_total": "1",
    }
    expected_idle_event = {
        "g_backlog": "0",
        "g_workers_idle": "1",
        "g_workers_total": "1",
    }

    saturation_metrics_events = get_parsed_canonical_logs(server_stdout, event_types=("saturation_metrics",))

    assert 20 < int(saturation_metrics_events[0]["g_memory_usage_mib"]) < 100, "excepted reasonable memory usage"

    assert any(
        all(event.get(k) == v for k, v in expected_saturated_event.items()) for event in saturation_metrics_events
    ), "excepted saturated event"
    assert any(all(event.get(k) == v for k, v in expected_idle_event.items()) for event in saturation_metrics_events), (
        "excepted idle event"
    )

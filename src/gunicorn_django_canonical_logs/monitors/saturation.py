from __future__ import annotations

import os
import socket
import struct
import threading
from typing import TYPE_CHECKING

import posix_ipc
import psutil

from gunicorn_django_canonical_logs.event_context import EventContext
from gunicorn_django_canonical_logs.gunicorn_hooks.registry import register_hook
from gunicorn_django_canonical_logs.logfmt import LogFmt

if TYPE_CHECKING:
    from gunicorn.arbiter import Arbiter
    from gunicorn.workers.base import Worker


class SaturationMonitor:
    shutdown_event = threading.Event()
    INTERVAL_SECONDS = float(os.environ.get("GUNICORN_SATURATION_METRICS_INTERVAL", "10"))

    def __init__(self, arbiter: Arbiter):
        self.arbiter = arbiter

    def start(self) -> None:
        self._emit_metrics()

        while not self.shutdown_event.wait(timeout=self.INTERVAL_SECONDS):
            self._emit_metrics()

    def shutdown(self):
        self.arbiter.log.info("Shutting down: Saturation monitor")
        self.shutdown_event.set()

    def _emit_metrics(self):
        backlog = self._get_backlog()
        memory_usage = self._get_memory_usage()
        workers = self._get_workers()

        saturation_metrics_context = EventContext()
        saturation_metrics_context.set("type", "saturation_metrics", namespace="event")
        metrics = {
            "backlog": backlog,
            "workers_total": workers[0],
            "workers_idle": workers[1],
            "memory_usage_mib": memory_usage,
        }
        saturation_metrics_context.update(context=metrics, namespace="g")

        print(LogFmt.format(saturation_metrics_context), flush=True)  # noqa T201 "logging" to stdout, skipping all formatters

    def _get_backlog(self) -> int:
        """Get the number of connections waiting to be accepted by a server"""
        total = 0
        for listener in self.arbiter.LISTENERS:
            if not listener.sock:
                continue

            tcp_info_fmt = "B" * 8 + "I" * 5  # tcp_info struct from /usr/include/linux/tcp.h
            tcp_info_size = 28
            tcpi_unacked_index = 12
            tcp_info_struct = listener.sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, tcp_info_size)
            total += struct.unpack(tcp_info_fmt, tcp_info_struct)[tcpi_unacked_index]

        return total

    def _get_memory_usage(self) -> int:
        """Return memory usage in MiB"""
        arbiter_proc = psutil.Process(self.arbiter.pid)
        arbiter_pss = arbiter_proc.memory_full_info().pss
        workers_pss = sum([worker.memory_full_info().pss for worker in arbiter_proc.children()])
        return (arbiter_pss + workers_pss) >> 20  # bytes -> mB

    def _get_workers(self) -> tuple[int, int]:
        """Returns tuple of (total_workers, idle_workers)"""
        total_workers = len(self.arbiter.WORKERS)
        idle_workers = sum([worker.request_semaphore.value for worker in self.arbiter.WORKERS.values()])
        return (total_workers, idle_workers)


@register_hook
def when_ready(arbiter: Arbiter):
    arbiter.log.info("Starting saturation monitor")
    arbiter.saturation_monitor = SaturationMonitor(arbiter)
    threading.Thread(target=arbiter.saturation_monitor.start).start()


@register_hook
def pre_fork(_, worker: Worker):
    worker.request_semaphore = posix_ipc.Semaphore(None, posix_ipc.O_CREX, initial_value=1)


@register_hook
def pre_request(worker: Worker, _):
    worker.request_semaphore.acquire()


@register_hook
def post_request(worker: Worker, *_):
    worker.request_semaphore.release()


@register_hook
def child_exit(_, worker: Worker):
    worker.request_semaphore.unlink()


@register_hook
def on_exit(arbiter: Arbiter):
    arbiter.saturation_monitor.shutdown()

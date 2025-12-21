from __future__ import annotations

import os
import socket
import struct
import threading
from typing import TYPE_CHECKING

import posix_ipc
import psutil

from gunicorn_django_canonical_logs.gunicorn_hooks.registry import register_hook

if TYPE_CHECKING:
    from gunicorn.arbiter import Arbiter
    from gunicorn.workers.base import Worker


class SaturationMonitor:
    shutdown_event = threading.Event()
    INTERVAL_SECONDS = float(os.environ.get("GUNICORN_SATURATION_METRICS_INTEVAL", "10"))

    def __init__(self, arbiter: Arbiter):
        self.arbiter = arbiter

    def start(self) -> None:
        self._emit_metrics()

        while not self.shutdown_event.wait(timeout=self.INTERVAL_SECONDS):
            self._emit_metrics()

    def shutdown(self):
        self.shutdown_event.set()

    def _emit_metrics(self):
        backlog = self._get_backlog()
        memory = self._get_memory()
        workers = self._get_workers()
        self.arbiter.log.info(f"{backlog=} {memory=} {workers=}")

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

    def _get_memory(self) -> int:
        """Return memory usage in MB"""
        arbiter_proc = psutil.Process(self.arbiter.pid)
        arbiter_pss = arbiter_proc.memory_full_info().pss
        workers_pss= sum([worker.memory_full_info().pss for worker in arbiter_proc.children()])
        return arbiter_pss + workers_pss

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
def pre_fork(arbiter: Arbiter, worker: Worker):
    worker.request_semaphore = posix_ipc.Semaphore((None, posix_ipc.O_CREX), initial_value=1)


@register_hook
def pre_request(worker: Worker, _):
    worker.request_semaphore.acquire(1)

@register_hook
def post_request(worker: Worker, *_):
    worker.request_semaphore.release()


@register_hook
def child_exit(_, worker: Worker):
    worker.request_semaphore.unlink()


@register_hook
def on_exit(arbiter: Arbiter):
    arbiter.saturation_monitor.shutdown()

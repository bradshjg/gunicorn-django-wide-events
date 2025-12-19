from __future__ import annotations

import socket
import struct
import sys
import threading
import time
from typing import TYPE_CHECKING, cast

from setproctitle import setproctitle

from gunicorn_django_canonical_logs.gunicorn_hooks.registry import register_hook

if TYPE_CHECKING:
    from gunicorn.arbiter import Arbiter
    from gunicorn.workers.base import Worker


class ProcTitle:
    @classmethod
    def set_worker(cls, worker: Worker, busy: bool):
        busy_text = "busy" if busy else "idle"
        setproctitle(f"gunicorn: worker [{worker.cfg.proc_name}] [status: {busy_text}]")

    @classmethod
    def set_arbiter(cls, arbiter: Arbiter, backlog: int):
        setproctitle(f"gunicorn: master [{arbiter.cfg.proc_name}] [backlog: {backlog}]")


class BacklogMonitor:
    shutdown_event = threading.Event()

    def __init__(self, arbiter: Arbiter):
        self.arbiter = arbiter

    @classmethod
    def shutdown(cls):
        cls.shutdown_event.set()

    def start(self):
        # HACK HACK HACK gunciorn sets the proctitle right after calling the ready hook.
        # Sleeping for just a little it in the thread to reset it.
        time.sleep(0.5)
        self.update_proctitle()

        while not self.shutdown_event.wait(timeout=10):
            self.update_proctitle()

    def update_proctitle(self):
        backlog = self.get_backlog()
        if backlog is not None:
            ProcTitle.set_arbiter(self.arbiter, backlog)

    def get_backlog(self) -> int | None:
        """Get the number of connections waiting to be accepted"""
        if sys.platform != "linux":
            return None

        total = None
        for listener in self.arbiter.LISTENERS:
            if not listener.sock:
                continue
            listener_socket = cast(socket.socket, listener.sock)
            if listener_socket.family not in (socket.AF_INET, socket.AF_INET6) or listener_socket.type != socket.SOCK_STREAM:
                continue

            try:
                tcp_info_fmt = "B" * 8 + "I" * 24  # tcp_info struct from include/uapi/linux/tcp.h
                tcp_info_size = 104
                tcpi_unacked_index = 12
                tcp_info_struct = listener.sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, tcp_info_size)
                unacked = struct.unpack(tcp_info_fmt, tcp_info_struct)[tcpi_unacked_index]
            except:  # do our best :-)
                continue
            else:
                if total is None:
                    total = unacked
                else:
                    total += unacked

        return total


@register_hook
def when_ready(arbiter: Arbiter):
    arbiter.log.info("Starting saturation monitor")
    backlog_monitor = BacklogMonitor(arbiter)
    threading.Thread(target=backlog_monitor.start).start()


@register_hook
def post_worker_init(worker: Worker):
    ProcTitle.set_worker(worker=worker, busy=False)


@register_hook
def pre_request(worker: Worker, _):
    ProcTitle.set_worker(worker=worker, busy=True)


@register_hook
def post_request(worker: Worker, *_):
    ProcTitle.set_worker(worker=worker, busy=False)


@register_hook
def on_exit(_arbiter):
    BacklogMonitor.shutdown()

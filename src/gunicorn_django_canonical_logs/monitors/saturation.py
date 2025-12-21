from __future__ import annotations

import dataclasses
import socket
import struct
import sys
import threading
import time
from multiprocessing import resource_tracker as _mprt
from multiprocessing import shared_memory as _mpshm
from typing import TYPE_CHECKING, Any

from gunicorn_django_canonical_logs.gunicorn_hooks.registry import register_hook

if TYPE_CHECKING:
    from gunicorn.arbiter import Arbiter
    from gunicorn.workers.base import Worker


# Patch versions of Python < 3.13 to support avoiding the memory tracker
if sys.version_info >= (3, 13):
    SharedMemory = _mpshm.SharedMemory
else:

    class SharedMemory(_mpshm.SharedMemory):
        __lock = threading.Lock()

        def __init__(
            self,
            name: str | None = None,
            create: bool = False,  # noqa FBT001 FBT002
            size: int = 0,
            *,
            track: bool = True,
        ) -> None:
            self._track = track

            # if tracking, normal init will suffice
            if track:
                return super().__init__(name=name, create=create, size=size)  # noqa PLE0101

            # lock so that other threads don't attempt to use the
            # register function during this time
            with self.__lock:
                # temporarily disable registration during initialization
                orig_register = _mprt.register
                _mprt.register = self.__tmp_register

                # initialize; ensure original register function is
                # re-instated
                try:
                    super().__init__(name=name, create=create, size=size)
                finally:
                    _mprt.register = orig_register

        @staticmethod
        def __tmp_register(*args, **kwargs) -> None:  # noqa ARG004
            return

        def unlink(self) -> None:
            if _mpshm._USE_POSIX and self._name:  # noqa SLF001
                _mpshm._posixshmem.shm_unlink(self._name)  # noqa SLF001
                if self._track:
                    _mprt.unregister(self._name, "shared_memory")


@dataclasses.dataclass
class SaturationStats:
    w_count: int = 0
    w_active: int = 0
    backlog: int = 0


class SaturationStatsShared:
    """Allow managing saturation stats across processes using shared memory.

    No synchronization is done. The assumption is that this will be atomic, or close enough to it.
    """

    STRUCT_FMT = 3 * "H"  # 3*uint16 (w_count, w_active, backlog)
    STRUCT_SIZE = struct.calcsize(STRUCT_FMT)

    def __init__(self, shm) -> None:
        self.shm: SharedMemory = shm

    @staticmethod
    def create():
        shm = SharedMemory(create=True, size=SaturationStatsShared.STRUCT_SIZE, track=False)
        inst = SaturationStatsShared(shm)
        inst.set(stats=SaturationStats())
        return inst

    @staticmethod
    def from_name(name):
        shm = SharedMemory(name, track=False)
        return SaturationStatsShared(shm)

    @property
    def name(self) -> str:
        return self.shm.name

    def set(self, *, stats: SaturationStats) -> None:
        values = [getattr(stats, field.name) for field in dataclasses.fields(stats)]
        struct.pack_into(self.STRUCT_FMT, self.shm.buf, 0, *values)  # type: ignore

    @property
    def value(self) -> SaturationStats:
        unpacked = struct.unpack_from(self.STRUCT_FMT, self.shm.buf, 0)  # type: ignore
        return SaturationStats(*unpacked)

    def close(self) -> None:
        self.shm.close()

    def unlink(self) -> None:
        self.shm.unlink()


class WorkerActiveShared:
    """Allow managing worker activness stats across processes using shared memory.

    No synchronization is done. The assumption is that this will be atomic, or close enough to it.
    """

    STRUCT_FMT = "?"  # boolean
    STRUCT_SIZE = struct.calcsize(STRUCT_FMT)

    def __init__(self, shm) -> None:
        self.shm: SharedMemory = shm

    @staticmethod
    def create():
        shm = SharedMemory(create=True, size=WorkerActiveShared.STRUCT_SIZE, track=False)
        inst = WorkerActiveShared(shm)
        inst.set(active=False)
        return inst

    @staticmethod
    def from_name(name):
        shm = SharedMemory(name, track=False)
        return WorkerActiveShared(shm)

    @property
    def name(self) -> str:
        return self.shm.name

    def set(self, *, active: bool) -> None:
        struct.pack_into(self.STRUCT_FMT, self.shm.buf, 0, active)  # type: ignore

    @property
    def value(self) -> bool:
        unpacked = struct.unpack_from(self.STRUCT_FMT, self.shm.buf, 0)  # type: ignore
        return unpacked[0]

    def close(self) -> None:
        self.shm.close()

    def unlink(self) -> None:
        self.shm.unlink()


def get_backlog(arbiter) -> int | None:
    """Get the number of connections waiting to be accepted by a server"""
    if sys.platform != "linux":
        return 0
    total = 0
    for listener in arbiter.LISTENERS:
        if not listener.sock:
            continue

        tcp_info_fmt = "B" * 8 + "I" * 5  # tcp_info struct from /usr/include/linux/tcp.h
        tcp_info_size = 28
        tcpi_unacked_index = 12
        tcp_info_struct = listener.sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, tcp_info_size)
        try:
            total += struct.unpack(tcp_info_fmt, tcp_info_struct)[tcpi_unacked_index]
        except struct.error:  # struct is private, do our best but settle for not updating the data
            return None

    return total


def get_w_active(arbiter: Arbiter, workers: list[Worker]) -> int:
    """Get the number of currently active workers"""
    w_active = 0
    for worker in workers:
        if not hasattr(worker, "saturation_stats_active_shm_name"):
            arbiter.log.debug("no activeness shm path available for worker with pid %s", worker.pid)
            continue

        try:
            active = WorkerActiveShared.from_name(worker.saturation_stats_active_shm_name).value
        except FileNotFoundError:
            arbiter.log.debug("no activeness shm file found for worker with pid %s", worker.pid)
            continue
        else:
            w_active += int(active)
    return w_active


def monitor_saturation(arbiter: Arbiter):
    """Monitor thread used to share stats with requests

    Saturation stats are updated with an interval combining data from the arbiter and workers.
    """
    update_interval_seconds = 1

    while True:
        if arbiter.saturation_stats_should_exit:
            arbiter.log.info("Stopping saturation monitor")
            break

        workers: list[Worker] = arbiter.WORKERS.values()
        w_count = len(workers)
        w_active = get_w_active(arbiter, workers)

        backlog = get_backlog(arbiter)

        if backlog is not None:
            arbiter.saturation_stats.set(stats=SaturationStats(w_count, w_active, backlog))

        time.sleep(update_interval_seconds)


class CurrentSaturationStats:
    stats: dict[str, Any] | None = None

    @classmethod
    def get(cls) -> dict[str, Any]:
        if cls.stats is None:
            return dataclasses.asdict(SaturationStats())
        return cls.stats

    @classmethod
    def set(cls, stats: SaturationStats) -> None:
        cls.stats = dataclasses.asdict(stats)


@register_hook
def when_ready(arbiter: Arbiter):
    arbiter.log.info("Starting saturation monitor")
    arbiter.saturation_stats = SaturationStatsShared.create()
    arbiter.saturation_stats_should_exit = False
    arbiter.saturation_stats_thread = threading.Thread(target=monitor_saturation, args=(arbiter,))
    arbiter.saturation_stats_thread.start()


@register_hook
def pre_fork(arbiter: Arbiter, worker: Worker):
    worker.saturation_stats_shm_name = arbiter.saturation_stats.name
    worker.saturation_stats_active = WorkerActiveShared.create()
    worker.saturation_stats_active_shm_name = worker.saturation_stats_active.name


@register_hook
def pre_request(worker: Worker, _):
    worker.saturation_stats_active.set(active=True)
    saturation_stats = SaturationStatsShared.from_name(worker.saturation_stats_shm_name).value
    CurrentSaturationStats.set(saturation_stats)


@register_hook
def post_request(worker: Worker, *_):
    worker.saturation_stats_active.set(active=False)


@register_hook
def worker_exit(_, worker: Worker):
    worker.saturation_stats_active.close()
    worker.saturation_stats_active.unlink()


@register_hook
def on_exit(arbiter: Arbiter):
    arbiter.saturation_stats_should_exit = True
    arbiter.saturation_stats_thread.join()
    arbiter.saturation_stats.close()
    arbiter.saturation_stats.unlink()

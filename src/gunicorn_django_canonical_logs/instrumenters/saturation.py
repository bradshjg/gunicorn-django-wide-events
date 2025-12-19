from __future__ import annotations

import dataclasses
import os
import re
import time
from functools import cached_property

import psutil

from gunicorn_django_canonical_logs.event_context import Context
from gunicorn_django_canonical_logs.instrumenters.protocol import InstrumenterProtocol
from gunicorn_django_canonical_logs.instrumenters.registry import register_instrumenter


@dataclasses.dataclass
class WorkerStatus:
    count: int
    active: int


@register_instrumenter
class SaturationInstrumenter(InstrumenterProtocol):
    """Regularly samples saturation stats"""
    arbiter_regex = re.compile(r"gunicorn: master .* \[backlog: (\d+)\]")
    worker_regex = re.compile(r"gunicorn: worker .* \[status: (idle|busy)\]")

    sample_interval_seconds = 10
    last_sampled = 0
    sample = None

    @cached_property
    def parent_process(self) -> psutil.Process:
        return psutil.Process(os.getppid())

    @property
    def worker_processes(self) -> list[psutil.Process]:
        return self.parent_process.children()

    @property
    def backlog(self) -> str:
        if match := self.arbiter_regex.match(self.parent_process.cmdline()[0]):
            return match.group(1)

    def active(self, worker_process: psutil.Process) -> bool:
        if match := self.worker_regex.match(worker_process.cmdline()[0]):
            return match.group(1) == "busy"
        return False

    @property
    def worker_status(self) -> WorkerStatus | None:
        try:
            status = list(map(self.active, self.worker_processes))
            return WorkerStatus(
                count=len(status),
                active=sum(status),
            )
        except:
            pass


    def call(self, _req, _resp, _environ):
        now = time.time()
        if now - self.last_sampled > self.sample_interval_seconds:
            saturation_data = {
                "backlog": self.backlog,
            }
            worker_status = self.worker_status
            if worker_status:
                saturation_data.update({
                    "w_count": worker_status.count,
                    "w_active": worker_status.active,
                })

            self.sample = saturation_data
            self.last_sampled = now
        Context.update(namespace="g", context=self.sample)

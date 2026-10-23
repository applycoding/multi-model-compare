from __future__ import annotations

import asyncio

from mmc.core.request import ResolvedRun
from mmc.records import RunRecord
from mmc.service import CompareService


class Busy(Exception):
    pass


class RunSupervisor:
    def __init__(self, service: CompareService, max_concurrent: int, grace_s: float) -> None:
        self._service = service
        self._sem = asyncio.Semaphore(max_concurrent)
        self._grace_s = grace_s
        self._accepting = True
        self._in_flight: set[asyncio.Task[RunRecord]] = set()

    @property
    def in_flight(self) -> int:
        return len(self._in_flight)

    async def start(self) -> None:
        return None

    async def submit(self, resolved: ResolvedRun) -> RunRecord:
        if not self._accepting:
            raise Busy("shutting down")
        if self._sem.locked():
            raise Busy("too many concurrent runs")

        await self._sem.acquire()

        async def run_wrapped() -> RunRecord:
            try:
                return await asyncio.shield(self._service.run(resolved))
            finally:
                self._sem.release()

        task = asyncio.create_task(run_wrapped())
        self._in_flight.add(task)
        try:
            return await asyncio.shield(task)
        finally:
            self._in_flight.discard(task)

    async def drain(self) -> None:
        self._accepting = False
        if not self._in_flight:
            return
        try:
            async with asyncio.timeout(self._grace_s):
                await asyncio.gather(*list(self._in_flight), return_exceptions=True)
        except TimeoutError:
            for task in list(self._in_flight):
                task.cancel()

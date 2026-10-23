from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    def perf(self) -> float: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def perf(self) -> float:
        import time

        return time.perf_counter()


class SteppingClock:
    def __init__(self, start: datetime, step: timedelta) -> None:
        self._current = start
        self._step = step

    def now(self) -> datetime:
        value = self._current
        self._current = self._current + self._step
        return value

    def perf(self) -> float:
        import time

        return time.perf_counter()

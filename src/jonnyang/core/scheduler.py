"""단일 스레드 스케줄러. 타이머·알람·리마인더가 모두 여기에 예약한다.

테스트에서는 스레드를 띄우지 않고 `run_pending(now)`을 직접 부른다.
콜백은 스케줄러 스레드에서 돈다. Windows COM(pycaw)은 여기서 부르면 안 된다.
"""

from __future__ import annotations

import heapq
import itertools
import threading
from datetime import datetime
from typing import Callable


class Scheduler:
    def __init__(self, clock: Callable[[], datetime]):
        self.clock = clock
        self._heap: list[tuple[datetime, int]] = []
        self._jobs: dict[int, Callable[[], None]] = {}
        self._ids = itertools.count(1)
        self._cond = threading.Condition()
        self._thread: threading.Thread | None = None
        self._stop = False
        self.on_error: Callable[[Exception], None] | None = None

    def schedule(self, when: datetime, callback: Callable[[], None]) -> int:
        with self._cond:
            job_id = next(self._ids)
            self._jobs[job_id] = callback
            heapq.heappush(self._heap, (when, job_id))
            self._cond.notify()
            return job_id

    def cancel(self, job_id: int) -> bool:
        with self._cond:
            return self._jobs.pop(job_id, None) is not None

    def run_pending(self, now: datetime | None = None) -> int:
        now = now or self.clock()
        due: list[Callable[[], None]] = []
        with self._cond:
            while self._heap and self._heap[0][0] <= now:
                _, job_id = heapq.heappop(self._heap)
                cb = self._jobs.pop(job_id, None)
                if cb:
                    due.append(cb)
        for cb in due:
            try:
                cb()
            except Exception as exc:  # 알림 하나 실패해도 스케줄러는 계속 돈다
                if self.on_error:
                    self.on_error(exc)
        return len(due)

    def _loop(self) -> None:
        while True:
            with self._cond:
                if self._stop:
                    return
                timeout = 1.0
                while self._heap and self._heap[0][1] not in self._jobs:
                    heapq.heappop(self._heap)
                if self._heap:
                    timeout = max(0.0, min(1.0, (self._heap[0][0] - self.clock()).total_seconds()))
                self._cond.wait(timeout)
            self.run_pending()

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="jonnyang-scheduler", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify()
        if self._thread:
            self._thread.join(timeout=2)

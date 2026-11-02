"""Per-key background runner that coalesces requests.

``CoalescingRunner`` runs ``job(key)`` in a daemon thread, one run at a time per
key. Requests that arrive while a run is in progress collapse into a single
extra run, so a burst of N requests costs at most two runs. An optional
``debounce_s`` waits for that many seconds without new requests before each run.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class _KeyState:
    pending: bool = False
    last_request: float = 0.0


class CoalescingRunner:
    """One background run at a time per key; requests during a run add one more."""

    def __init__(self, name: str, job: Callable[[int], None], *, debounce_s: float = 0.0) -> None:
        self.name = name
        self.debounce_s = debounce_s
        self._job = job
        self._cond = threading.Condition()
        self._states: dict[int, _KeyState] = {}
        self._locks: dict[int, threading.Lock] = {}

    def lock_for(self, key: int) -> threading.Lock:
        """The lock held while ``job(key)`` runs; other callers may take it too."""
        with self._cond:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    def request(self, key: int) -> bool:
        """Ask for a run of ``job(key)``. Always returns True."""
        with self._cond:
            state = self._states.get(key)
            if state is None:
                state = _KeyState()
                self._states[key] = state
                start = True
            else:
                start = False
            state.pending = True
            state.last_request = time.monotonic()
            self._cond.notify_all()
        if start:
            threading.Thread(
                target=self._worker, args=(key,), name=f"{self.name}-{key}", daemon=True
            ).start()
        return True

    def is_busy(self, key: int) -> bool:
        """True while a run of ``key`` is running or waiting to run."""
        with self._cond:
            return key in self._states

    def wait_idle(self, key: int, timeout: float) -> bool:
        """Block until ``key`` has no run in progress or pending; False on timeout."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while key in self._states:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return True

    def _worker(self, key: int) -> None:
        lock = self.lock_for(key)
        while True:
            with self._cond:
                state = self._states[key]
                while True:
                    wait = state.last_request + self.debounce_s - time.monotonic()
                    if wait <= 0:
                        break
                    self._cond.wait(wait)
                state.pending = False
            try:
                with lock:
                    self._job(key)
            except Exception:
                logger.exception("%s job failed for key %s", self.name, key)
            with self._cond:
                if state.pending:
                    continue
                del self._states[key]
                self._cond.notify_all()
                return

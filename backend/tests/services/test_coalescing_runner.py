import threading
import time

from rippermod_manager.services.coalescing_runner import CoalescingRunner


def test_requests_during_a_run_coalesce_into_one_more_run():
    calls: list[int] = []
    gate = threading.Event()
    started = threading.Event()

    def job(key: int) -> None:
        calls.append(key)
        started.set()
        gate.wait(2)

    r = CoalescingRunner("t", job)
    r.request(7)
    assert started.wait(2)
    for _ in range(5):
        r.request(7)
    gate.set()
    assert r.wait_idle(7, timeout=2) and calls == [7, 7]


def test_debounce_waits_for_a_quiet_period():
    stamps: list[float] = []
    r = CoalescingRunner("t", lambda _k: stamps.append(time.monotonic()), debounce_s=0.2)
    last = 0.0
    for _ in range(3):
        r.request(1)
        last = time.monotonic()
        time.sleep(0.05)
    assert r.wait_idle(1, timeout=2)
    assert len(stamps) == 1 and stamps[0] - last >= 0.2


def test_lock_is_held_while_the_job_runs():
    gate = threading.Event()
    started = threading.Event()

    def job(_key: int) -> None:
        started.set()
        gate.wait(2)

    r = CoalescingRunner("t", job)
    r.request(3)
    assert started.wait(2)
    assert r.is_busy(3) and r.lock_for(3).acquire(blocking=False) is False
    gate.set()
    assert r.wait_idle(3, timeout=2) and r.is_busy(3) is False


def test_a_failing_job_does_not_stop_later_runs():
    calls: list[int] = []

    def job(key: int) -> None:
        calls.append(key)
        if len(calls) == 1:
            raise RuntimeError("boom")

    r = CoalescingRunner("t", job)
    r.request(1)
    assert r.wait_idle(1, timeout=2)
    r.request(1)
    assert r.wait_idle(1, timeout=2)
    assert calls == [1, 1]


def test_request_returns_true_and_idle_key_is_not_busy():
    r = CoalescingRunner("t", lambda _k: None)
    assert r.is_busy(9) is False
    assert r.wait_idle(9, timeout=0.1) is True
    assert r.request(9) is True
    assert r.wait_idle(9, timeout=2)

"""Shared progress callback type for pipeline services."""

from collections.abc import Callable

ProgressCallback = Callable[[str, str, int], None]


def noop_progress(_phase: str, _msg: str, _pct: int) -> None:
    pass

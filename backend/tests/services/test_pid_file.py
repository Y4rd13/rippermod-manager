"""Tests for the PID-file helpers used by the orphan-cleanup mechanism."""

from __future__ import annotations

import os
from pathlib import Path

from rippermod_manager.services.pid_file import (
    PID_FILENAME,
    pid_path,
    remove_pid_file,
    write_pid_file,
)


def test_write_pid_file_creates_file_with_current_pid(tmp_path: Path) -> None:
    write_pid_file(tmp_path)
    content = (tmp_path / PID_FILENAME).read_text(encoding="utf-8")
    assert int(content.strip()) == os.getpid()


def test_write_pid_file_creates_parent_dir(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c"
    write_pid_file(nested)
    assert (nested / PID_FILENAME).is_file()


def test_remove_pid_file_when_present(tmp_path: Path) -> None:
    write_pid_file(tmp_path)
    assert pid_path(tmp_path).exists()
    remove_pid_file(tmp_path)
    assert not pid_path(tmp_path).exists()


def test_remove_pid_file_is_idempotent_when_missing(tmp_path: Path) -> None:
    remove_pid_file(tmp_path)
    remove_pid_file(tmp_path)


def test_write_pid_file_overwrites_existing(tmp_path: Path) -> None:
    (tmp_path / PID_FILENAME).write_text("99999999")
    write_pid_file(tmp_path)
    assert int((tmp_path / PID_FILENAME).read_text().strip()) == os.getpid()

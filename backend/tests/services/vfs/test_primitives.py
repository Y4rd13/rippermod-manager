import os

import pytest

from rippermod_manager.services.vfs.primitives import (
    AlreadyExistsError,
    NotFoundError,
    hardlink,
    unlink,
)


def test_hardlink_creates_link(tmp_volume):
    staging, target = tmp_volume
    src = staging / "a.txt"
    src.write_text("hello")
    dst = target / "a.txt"

    hardlink(src, dst)

    assert dst.exists()
    assert os.path.samefile(src, dst)


def test_hardlink_raises_if_dst_exists(tmp_volume):
    staging, target = tmp_volume
    src = staging / "a.txt"
    src.write_text("hello")
    dst = target / "a.txt"
    dst.write_text("existing")

    with pytest.raises(AlreadyExistsError):
        hardlink(src, dst)


def test_hardlink_raises_if_src_missing(tmp_volume):
    staging, target = tmp_volume
    src = staging / "missing.txt"
    dst = target / "a.txt"

    with pytest.raises(NotFoundError):
        hardlink(src, dst)


def test_unlink_removes_link(tmp_volume):
    staging, target = tmp_volume
    src = staging / "a.txt"
    src.write_text("hello")
    dst = target / "a.txt"
    hardlink(src, dst)

    unlink(dst)

    assert not dst.exists()
    assert src.exists()  # staging untouched
    assert src.read_text() == "hello"


def test_unlink_is_idempotent_when_absent(tmp_volume):
    _, target = tmp_volume
    dst = target / "ghost.txt"

    unlink(dst)  # should not raise

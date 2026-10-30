import os
import sys
from typing import ClassVar
from unittest.mock import patch

import pytest

from rippermod_manager.services.vfs.primitives import (
    AlreadyExistsError,
    NotFoundError,
    VfsError,
    hardlink,
    is_game_running,
    junction,
    probe_hardlink_support,
    remove_junction,
    same_volume,
    unlink,
    verify_link,
)

skip_if_not_windows = pytest.mark.skipif(
    sys.platform != "win32", reason="VFS junctions are Windows-only"
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


def test_verify_link_true_for_hardlink(tmp_volume):
    staging, target = tmp_volume
    src = staging / "a.txt"
    src.write_text("hi")
    dst = target / "a.txt"
    hardlink(src, dst)

    assert verify_link(src, dst) is True


def test_verify_link_false_for_separate_files(tmp_volume):
    staging, target = tmp_volume
    src = staging / "a.txt"
    src.write_text("hi")
    dst = target / "a.txt"
    dst.write_text("hi")  # same content, different inode

    assert verify_link(src, dst) is False


def test_verify_link_false_when_dst_missing(tmp_volume):
    staging, target = tmp_volume
    src = staging / "a.txt"
    src.write_text("hi")
    dst = target / "missing.txt"

    assert verify_link(src, dst) is False


def test_same_volume_true_for_siblings(tmp_volume):
    staging, target = tmp_volume
    assert same_volume(staging, target) is True


def test_same_volume_handles_missing_paths(tmp_path):
    """If paths don't exist yet, fall back to closest existing ancestor."""
    a = tmp_path / "nope_a"
    b = tmp_path / "nope_b"
    assert same_volume(a, b) is True


def test_probe_returns_true_when_supported(tmp_volume):
    staging, target = tmp_volume
    assert probe_hardlink_support(staging, target) is True


def test_probe_leaves_no_files(tmp_volume):
    staging, target = tmp_volume
    probe_hardlink_support(staging, target)
    assert list(staging.iterdir()) == []
    assert list(target.iterdir()) == []


def test_is_game_running_false_when_no_match():
    with patch("rippermod_manager.services.vfs.primitives.psutil") as mock_psutil:
        mock_psutil.process_iter.return_value = []
        assert is_game_running("Cyberpunk2077.exe") is False


def test_is_game_running_true_when_match():
    class FakeProc:
        info: ClassVar[dict[str, str]] = {"name": "Cyberpunk2077.exe"}

    with patch("rippermod_manager.services.vfs.primitives.psutil") as mock_psutil:
        mock_psutil.process_iter.return_value = [FakeProc()]
        assert is_game_running("Cyberpunk2077.exe") is True


def test_is_game_running_case_insensitive():
    class FakeProc:
        info: ClassVar[dict[str, str]] = {"name": "CYBERPUNK2077.EXE"}

    with patch("rippermod_manager.services.vfs.primitives.psutil") as mock_psutil:
        mock_psutil.process_iter.return_value = [FakeProc()]
        assert is_game_running("Cyberpunk2077.exe") is True


@skip_if_not_windows
def test_junction_creates_traversable_link(tmp_volume):
    staging, target = tmp_volume
    inner = staging / "inner"
    inner.mkdir()
    (inner / "file.txt").write_text("ok")

    link = target / "link"
    junction(inner, link)

    assert (link / "file.txt").read_text() == "ok"


@skip_if_not_windows
def test_remove_junction_removes_link_but_keeps_target(tmp_volume):
    staging, target = tmp_volume
    inner = staging / "inner"
    inner.mkdir()
    (inner / "file.txt").write_text("ok")
    link = target / "link"
    junction(inner, link)

    remove_junction(link)

    assert not link.exists()
    assert (inner / "file.txt").read_text() == "ok"


@skip_if_not_windows
def test_remove_junction_idempotent_when_absent(tmp_volume):
    _, target = tmp_volume
    link = target / "ghost"
    remove_junction(link)  # must not raise


def test_junction_rejects_cmd_metacharacters(tmp_volume):
    """junction() must refuse paths containing cmd.exe metacharacters.

    Validation happens before any cmd invocation, so this test is platform-agnostic.
    A malicious archive cannot escape via & to inject a second command.
    """
    staging, target = tmp_volume
    inner = staging / "inner"
    inner.mkdir()

    evil_link = target / "evil&deploy"
    with pytest.raises(VfsError, match=r"cmd\.exe"):
        junction(inner, evil_link)


class TestJunctionPointsInto:
    def test_symlink_into_root_is_ours(self, tmp_path):
        from rippermod_manager.services.vfs.primitives import junction_points_into

        root = tmp_path / "staging" / "ModA" / "mods" / "MyMod"
        root.mkdir(parents=True)
        link = tmp_path / "game" / "mods" / "MyMod"
        link.parent.mkdir(parents=True)
        os.symlink(root, link, target_is_directory=True)

        assert junction_points_into(link, root)
        assert junction_points_into(link, tmp_path / "staging" / "ModA")

    def test_symlink_elsewhere_is_foreign(self, tmp_path):
        from rippermod_manager.services.vfs.primitives import junction_points_into

        mine = tmp_path / "staging" / "ModA" / "mods" / "MyMod"
        theirs = tmp_path / "staging" / "ModB" / "mods" / "MyMod"
        mine.mkdir(parents=True)
        theirs.mkdir(parents=True)
        link = tmp_path / "game" / "MyMod"
        link.parent.mkdir(parents=True)
        os.symlink(theirs, link, target_is_directory=True)

        assert not junction_points_into(link, mine)

    def test_plain_directory_or_absent_path_is_not_ours(self, tmp_path):
        from rippermod_manager.services.vfs.primitives import junction_points_into

        root = tmp_path / "staging"
        root.mkdir()
        real_dir = tmp_path / "game" / "MyMod"
        real_dir.mkdir(parents=True)

        assert not junction_points_into(real_dir, root)
        assert not junction_points_into(tmp_path / "missing", root)

    def test_extended_length_prefix_is_stripped(self, tmp_path, monkeypatch):
        from rippermod_manager.services.vfs import primitives

        root = tmp_path / "staging"
        root.mkdir()
        link = tmp_path / "link"
        os.symlink(root, link, target_is_directory=True)
        monkeypatch.setattr(primitives.os, "readlink", lambda _p: "\\\\?\\" + str(root))

        assert primitives.junction_points_into(link, root)

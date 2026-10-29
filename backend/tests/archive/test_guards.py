from collections import namedtuple

import pytest

from rippermod_manager.archive import guards
from rippermod_manager.archive.handler import ArchiveEntry

_Usage = namedtuple("_Usage", "total used free")


@pytest.fixture
def plenty_of_space(monkeypatch):
    monkeypatch.setattr(guards.shutil, "disk_usage", lambda _p: _Usage(0, 0, 10 * 1024**4))


def test_constants_match_spec():
    assert guards.MAX_COMPRESSION_RATIO == 1000
    assert guards.RATIO_MIN_BYTES == 100 * 1024 * 1024
    assert guards.FREE_SPACE_MARGIN_BYTES == 1024 * 1024 * 1024


def test_rejects_total_over_free_minus_margin(monkeypatch, tmp_path):
    free = guards.FREE_SPACE_MARGIN_BYTES + 10
    monkeypatch.setattr(guards.shutil, "disk_usage", lambda _p: _Usage(0, 0, free))
    over = [ArchiveEntry("a", False, 6), ArchiveEntry("b", False, 5)]
    with pytest.raises(ValueError, match="free space"):
        guards.check_extraction_budget(over, tmp_path)
    fits = [ArchiveEntry("a", False, 6), ArchiveEntry("b", False, 4), ArchiveEntry("d/", True, 99)]
    guards.check_extraction_budget(fits, tmp_path)


def test_rejects_ratio_over_1000_above_100_mib(plenty_of_space, tmp_path):
    big = guards.RATIO_MIN_BYTES + 1
    with pytest.raises(ValueError, match="compression ratio"):
        guards.check_extraction_budget(
            [ArchiveEntry("bomb", False, big, compressed_size=big // 1001)], tmp_path
        )
    # At the size threshold (not above it) any ratio passes.
    guards.check_extraction_budget(
        [ArchiveEntry("edge", False, guards.RATIO_MIN_BYTES, compressed_size=1)], tmp_path
    )
    # Exactly 1000:1 above the size threshold passes.
    c = big // 1000 + 1
    guards.check_extraction_budget(
        [ArchiveEntry("ok", False, 1000 * c, compressed_size=c)], tmp_path
    )


def test_zero_compressed_size_counts_as_bomb(plenty_of_space, tmp_path):
    entry = ArchiveEntry("zero", False, guards.RATIO_MIN_BYTES + 1, compressed_size=0)
    with pytest.raises(ValueError, match="compression ratio"):
        guards.check_extraction_budget([entry], tmp_path)


def test_unknown_compressed_size_skips_ratio_check(plenty_of_space, tmp_path):
    entry = ArchiveEntry("solid", False, guards.RATIO_MIN_BYTES * 50, compressed_size=None)
    guards.check_extraction_budget([entry], tmp_path)

import sys

import pytest


@pytest.fixture
def tmp_volume(tmp_path):
    """Two sibling dirs guaranteed same volume."""
    staging = tmp_path / "staging"
    target = tmp_path / "target"
    staging.mkdir()
    target.mkdir()
    return staging, target


skip_if_not_windows = pytest.mark.skipif(
    sys.platform != "win32",
    reason="VFS primitives are Windows-only",
)

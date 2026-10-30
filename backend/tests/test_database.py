import os
import subprocess
import sys


def test_pool_connection_has_pragmas_after_startup(tmp_path):
    code = (
        "import rippermod_manager.models\nfrom sqlmodel import text\n"
        "from rippermod_manager.database import create_db_and_tables, get_session\n"
        "create_db_and_tables(); s = next(get_session())\n"
        "print(s.exec(text('PRAGMA foreign_keys')).one()[0], "
        "s.exec(text('PRAGMA synchronous')).one()[0])"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "RMM_DATA_DIR": str(tmp_path)},
    )
    assert out.stdout.split() == ["1", "1"]

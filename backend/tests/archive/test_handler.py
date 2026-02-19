import zipfile

import pytest

from chat_nexus_mod_manager.archive.handler import (
    ArchiveEntry,
    ZipHandler,
    open_archive,
)


def _make_zip(path, files: dict[str, bytes]) -> None:
    """Create a zip archive with the given filename -> content mapping."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


class TestZipHandler:
    def test_list_entries_returns_files(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        _make_zip(zip_path, {"file1.txt": b"hello", "file2.txt": b"world"})

        with ZipHandler(zip_path) as handler:
            entries = handler.list_entries()

        names = {e.filename for e in entries}
        assert "file1.txt" in names
        assert "file2.txt" in names

    def test_list_entries_correct_sizes(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        content = b"x" * 100
        _make_zip(zip_path, {"bigfile.bin": content})

        with ZipHandler(zip_path) as handler:
            entries = handler.list_entries()

        assert len(entries) == 1
        assert entries[0].size == 100

    def test_list_entries_marks_directories(self, tmp_path):
        zip_path = tmp_path / "dirs.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.mkdir("subdir")
            zf.writestr("subdir/nested.txt", b"nested content")

        with ZipHandler(zip_path) as handler:
            entries = handler.list_entries()

        dirs = [e for e in entries if e.is_dir]
        files = [e for e in entries if not e.is_dir]
        assert len(dirs) >= 1
        assert len(files) >= 1

    def test_read_file_returns_correct_bytes(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        expected = b"exact content bytes"
        _make_zip(zip_path, {"data.bin": expected})

        with ZipHandler(zip_path) as handler:
            entries = handler.list_entries()
            file_entry = next(e for e in entries if e.filename == "data.bin")
            data = handler.read_file(file_entry)

        assert data == expected

    def test_read_file_empty_content(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        _make_zip(zip_path, {"empty.txt": b""})

        with ZipHandler(zip_path) as handler:
            entries = handler.list_entries()
            entry = next(e for e in entries if e.filename == "empty.txt")
            data = handler.read_file(entry)

        assert data == b""

    def test_context_manager_closes_cleanly(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        _make_zip(zip_path, {"a.txt": b"a"})

        with ZipHandler(zip_path) as handler:
            entries = handler.list_entries()
        # No exception means close() was called successfully
        assert len(entries) == 1

    def test_list_entries_nested_paths(self, tmp_path):
        zip_path = tmp_path / "nested.zip"
        _make_zip(
            zip_path,
            {
                "dir/subdir/file.txt": b"deep",
                "top.txt": b"top",
            },
        )

        with ZipHandler(zip_path) as handler:
            entries = handler.list_entries()

        names = {e.filename for e in entries}
        assert "dir/subdir/file.txt" in names
        assert "top.txt" in names

    def test_entries_are_archive_entry_instances(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        _make_zip(zip_path, {"x.txt": b"x"})

        with ZipHandler(zip_path) as handler:
            entries = handler.list_entries()

        for entry in entries:
            assert isinstance(entry, ArchiveEntry)

    def test_read_all_files_batch(self, tmp_path):
        zip_path = tmp_path / "batch.zip"
        _make_zip(zip_path, {"a.txt": b"aaa", "b.txt": b"bbb", "c.txt": b"ccc"})

        with ZipHandler(zip_path) as handler:
            entries = handler.list_entries()
            result = handler.read_all_files(entries)

        assert result == {"a.txt": b"aaa", "b.txt": b"bbb", "c.txt": b"ccc"}

    def test_read_all_files_skips_directories(self, tmp_path):
        zip_path = tmp_path / "dirs.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.mkdir("subdir")
            zf.writestr("subdir/file.txt", b"content")

        with ZipHandler(zip_path) as handler:
            entries = handler.list_entries()
            result = handler.read_all_files(entries)

        assert "subdir/file.txt" in result
        assert "subdir/" not in result


class TestOpenArchive:
    def test_selects_zip_handler_for_zip(self, tmp_path):
        zip_path = tmp_path / "mod.zip"
        _make_zip(zip_path, {"readme.txt": b"readme"})

        handler = open_archive(zip_path)
        try:
            assert isinstance(handler, ZipHandler)
        finally:
            handler.close()

    def test_open_archive_uppercase_extension(self, tmp_path):
        # Extension matching should be case-insensitive
        zip_path = tmp_path / "mod.ZIP"
        _make_zip(zip_path, {"readme.txt": b"readme"})

        handler = open_archive(zip_path)
        try:
            assert isinstance(handler, ZipHandler)
        finally:
            handler.close()

    def test_unsupported_extension_raises_value_error(self, tmp_path):
        bad_path = tmp_path / "mod.exe"
        bad_path.write_bytes(b"not an archive")

        with pytest.raises(ValueError, match="Unsupported archive format"):
            open_archive(bad_path)

    def test_unsupported_tar_raises_value_error(self, tmp_path):
        tar_path = tmp_path / "mod.tar.gz"
        tar_path.write_bytes(b"fake tar")

        with pytest.raises(ValueError):
            open_archive(tar_path)

    def test_open_archive_returns_context_manager(self, tmp_path):
        zip_path = tmp_path / "cm.zip"
        _make_zip(zip_path, {"f.txt": b"f"})

        with open_archive(zip_path) as handler:
            entries = handler.list_entries()

        assert len(entries) == 1

    def test_corrupt_zip_raises(self, tmp_path):
        bad_zip = tmp_path / "corrupt.zip"
        bad_zip.write_bytes(b"this is not a zip file at all")

        with pytest.raises(zipfile.BadZipFile):
            open_archive(bad_zip)

from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlmodel import Session, select

from rippermod_manager.archive.handler import ArchiveEntry
from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.mod import ModFile, ModGroup
from rippermod_manager.models.nexus import NexusDownload, NexusModFile
from rippermod_manager.services.file_list_matcher import match_endorsed_to_local


def _make_game(session: Session) -> Game:
    game = Game(name="G", domain_name="g", install_path="/g")
    session.add(game)
    session.flush()
    session.add(GameModPath(game_id=game.id, relative_path="mods"))
    session.commit()
    session.refresh(game)
    _ = game.mod_paths
    return game


def _mock_archive(entries: list[ArchiveEntry]) -> MagicMock:
    handler = MagicMock()
    handler.list_entries.return_value = entries
    handler.__enter__ = MagicMock(return_value=handler)
    handler.__exit__ = MagicMock(return_value=False)
    return handler


_PATCH_ARCHIVES = "rippermod_manager.services.file_list_matcher.list_available_archives"
_PATCH_OPEN = "rippermod_manager.services.file_list_matcher.open_archive"


class TestFileListMatcher:
    def test_no_endorsed_mods(self, engine):
        with Session(engine) as s:
            game = _make_game(s)
            result = match_endorsed_to_local(game, s)
            assert result.checked == 0
            assert result.matched == 0

    def test_no_nexus_files_no_archive(self, engine):
        """Endorsed mod with no NexusModFile rows and no local archive."""
        with Session(engine) as s:
            game = _make_game(s)
            s.add(
                NexusDownload(
                    game_id=game.id,
                    nexus_mod_id=10,
                    mod_name="SomeMod",
                    version="1.0",
                    is_endorsed=True,
                )
            )
            s.commit()

            with patch(_PATCH_ARCHIVES, return_value=[]):
                result = match_endorsed_to_local(game, s)

            assert result.matched == 0

    def test_nexus_filename_match_with_size_match(self, engine):
        """CDN filename found locally, archive contents match with sizes."""
        with Session(engine) as s:
            game = _make_game(s)
            group = ModGroup(game_id=game.id, display_name="TestMod")
            s.add(group)
            s.flush()

            s.add(
                ModFile(
                    mod_group_id=group.id,
                    file_path="mods/test.lua",
                    filename="test.lua",
                    file_size=1000,
                )
            )
            s.add(
                ModFile(
                    mod_group_id=group.id,
                    file_path="mods/config.xml",
                    filename="config.xml",
                    file_size=500,
                )
            )

            dl = NexusDownload(
                game_id=game.id,
                nexus_mod_id=42,
                mod_name="TestMod",
                version="",
                is_endorsed=True,
            )
            s.add(dl)
            s.flush()

            s.add(
                NexusModFile(
                    nexus_mod_id=42,
                    file_id=1001,
                    file_name="TestMod-42-1-0-1700000000.zip",
                    version="1.0",
                    category_id=1,
                )
            )
            s.commit()

            archive_path = Path("/g/downloaded_mods/TestMod-42-1-0-1700000000.zip")
            mock_handler = _mock_archive(
                [
                    ArchiveEntry(
                        filename="mods/test.lua",
                        is_dir=False,
                        size=1000,
                    ),
                    ArchiveEntry(
                        filename="mods/config.xml",
                        is_dir=False,
                        size=500,
                    ),
                ]
            )

            with (
                patch(_PATCH_ARCHIVES, return_value=[archive_path]),
                patch(_PATCH_OPEN, return_value=mock_handler),
            ):
                result = match_endorsed_to_local(game, s)

            assert result.matched == 1
            assert result.checked == 1

            s.refresh(dl)
            assert dl.version == "1.0"

            corr = s.exec(select(ModNexusCorrelation)).first()
            assert corr is not None
            assert corr.method == "file_list"
            assert corr.score == 0.95
            assert corr.mod_group_id == group.id

    def test_nexus_filename_match_size_mismatch(self, engine):
        """CDN filename matches but file sizes differ -> sentinel version."""
        with Session(engine) as s:
            game = _make_game(s)
            group = ModGroup(game_id=game.id, display_name="OldMod")
            s.add(group)
            s.flush()

            s.add(
                ModFile(
                    mod_group_id=group.id,
                    file_path="mods/main.dll",
                    filename="main.dll",
                    file_size=2000,
                )
            )
            s.add(
                ModFile(
                    mod_group_id=group.id,
                    file_path="mods/data.bin",
                    filename="data.bin",
                    file_size=3000,
                )
            )

            dl = NexusDownload(
                game_id=game.id,
                nexus_mod_id=55,
                mod_name="OldMod",
                version="",
                is_endorsed=True,
            )
            s.add(dl)
            s.flush()

            s.add(
                NexusModFile(
                    nexus_mod_id=55,
                    file_id=2001,
                    file_name="OldMod-55-2-0-1700000000.zip",
                    version="2.0",
                    category_id=1,
                )
            )
            s.commit()

            archive_path = Path("/g/downloaded_mods/OldMod-55-2-0-1700000000.zip")
            mock_handler = _mock_archive(
                [
                    ArchiveEntry(
                        filename="mods/main.dll",
                        is_dir=False,
                        size=5000,
                    ),
                    ArchiveEntry(
                        filename="mods/data.bin",
                        is_dir=False,
                        size=6000,
                    ),
                ]
            )

            with (
                patch(_PATCH_ARCHIVES, return_value=[archive_path]),
                patch(_PATCH_OPEN, return_value=mock_handler),
            ):
                result = match_endorsed_to_local(game, s)

            assert result.matched == 1
            s.refresh(dl)
            assert dl.version == "0.0.0-unverified"

    def test_skips_already_correlated(self, engine):
        """Downloads with existing correlation are skipped."""
        with Session(engine) as s:
            game = _make_game(s)
            group = ModGroup(game_id=game.id, display_name="CorrMod")
            s.add(group)
            dl = NexusDownload(
                game_id=game.id,
                nexus_mod_id=77,
                mod_name="CorrMod",
                is_endorsed=True,
            )
            s.add(dl)
            s.flush()
            s.add(
                ModNexusCorrelation(
                    mod_group_id=group.id,
                    nexus_download_id=dl.id,
                    score=1.0,
                    method="exact",
                )
            )
            s.commit()

            with patch(_PATCH_ARCHIVES, return_value=[]):
                result = match_endorsed_to_local(game, s)

            assert result.checked == 0

    def test_low_match_ratio_skipped(self, engine):
        """< 50% archive entries matching local files -> no correlation."""
        with Session(engine) as s:
            game = _make_game(s)
            group = ModGroup(game_id=game.id, display_name="PartialMod")
            s.add(group)
            s.flush()

            s.add(
                ModFile(
                    mod_group_id=group.id,
                    file_path="mods/one.lua",
                    filename="one.lua",
                    file_size=100,
                )
            )

            dl = NexusDownload(
                game_id=game.id,
                nexus_mod_id=88,
                mod_name="PartialMod",
                is_endorsed=True,
            )
            s.add(dl)
            s.flush()

            s.add(
                NexusModFile(
                    nexus_mod_id=88,
                    file_id=3001,
                    file_name="PartialMod-88-1-0-1700000000.zip",
                    version="1.0",
                    category_id=1,
                )
            )
            s.commit()

            archive_path = Path("/g/downloaded_mods/PartialMod-88-1-0-1700000000.zip")
            mock_handler = _mock_archive(
                [
                    ArchiveEntry(
                        filename="mods/one.lua",
                        is_dir=False,
                        size=100,
                    ),
                    ArchiveEntry(
                        filename="mods/two.lua",
                        is_dir=False,
                        size=200,
                    ),
                    ArchiveEntry(
                        filename="mods/three.lua",
                        is_dir=False,
                        size=300,
                    ),
                ]
            )

            with (
                patch(_PATCH_ARCHIVES, return_value=[archive_path]),
                patch(_PATCH_OPEN, return_value=mock_handler),
            ):
                result = match_endorsed_to_local(game, s)

            assert result.matched == 0
            corr = s.exec(select(ModNexusCorrelation)).first()
            assert corr is None

    def test_skips_old_version_category(self, engine):
        """NexusModFile with category_id=4 (OLD_VERSION) is skipped."""
        with Session(engine) as s:
            game = _make_game(s)
            group = ModGroup(game_id=game.id, display_name="OldVer")
            s.add(group)
            s.flush()

            s.add(
                ModFile(
                    mod_group_id=group.id,
                    file_path="mods/main.lua",
                    filename="main.lua",
                    file_size=100,
                )
            )

            dl = NexusDownload(
                game_id=game.id,
                nexus_mod_id=99,
                mod_name="OldVer",
                is_endorsed=True,
            )
            s.add(dl)
            s.flush()

            # Only an OLD_VERSION file exists
            s.add(
                NexusModFile(
                    nexus_mod_id=99,
                    file_id=4001,
                    file_name="OldVer-99-0-5-1600000000.zip",
                    version="0.5",
                    category_id=4,  # OLD_VERSION
                )
            )
            s.commit()

            archive_path = Path("/g/downloaded_mods/OldVer-99-0-5-1600000000.zip")
            mock_handler = _mock_archive(
                [
                    ArchiveEntry(
                        filename="mods/main.lua",
                        is_dir=False,
                        size=100,
                    ),
                ]
            )

            with (
                patch(_PATCH_ARCHIVES, return_value=[archive_path]),
                patch(_PATCH_OPEN, return_value=mock_handler),
            ):
                result = match_endorsed_to_local(game, s)

            # No NexusModFile entries after filtering -> skipped_no_archive
            assert result.matched == 0

    def test_fallback_to_parse_filename(self, engine):
        """No NexusModFile rows -> fallback to parse_mod_filename regex."""
        with Session(engine) as s:
            game = _make_game(s)
            group = ModGroup(game_id=game.id, display_name="FallbackMod")
            s.add(group)
            s.flush()

            s.add(
                ModFile(
                    mod_group_id=group.id,
                    file_path="mods/fb.lua",
                    filename="fb.lua",
                    file_size=400,
                )
            )

            dl = NexusDownload(
                game_id=game.id,
                nexus_mod_id=111,
                mod_name="FallbackMod",
                is_endorsed=True,
            )
            s.add(dl)
            s.commit()

            # No NexusModFile rows for mod 111
            archive_path = Path("/g/downloaded_mods/FallbackMod-111-1-0-1700000000.zip")
            mock_handler = _mock_archive(
                [
                    ArchiveEntry(
                        filename="mods/fb.lua",
                        is_dir=False,
                        size=400,
                    ),
                ]
            )

            with (
                patch(_PATCH_ARCHIVES, return_value=[archive_path]),
                patch(_PATCH_OPEN, return_value=mock_handler),
            ):
                result = match_endorsed_to_local(game, s)

            assert result.matched == 1
            assert result.checked == 1

            corr = s.exec(select(ModNexusCorrelation)).first()
            assert corr is not None
            assert corr.score == 0.92
            assert corr.method == "file_list"

            s.refresh(dl)
            assert dl.version == "1.0"

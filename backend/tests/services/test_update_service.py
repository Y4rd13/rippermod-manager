from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session

from chat_nexus_mod_manager.models.correlation import ModNexusCorrelation
from chat_nexus_mod_manager.models.game import Game, GameModPath
from chat_nexus_mod_manager.models.install import InstalledMod
from chat_nexus_mod_manager.models.mod import ModGroup
from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta
from chat_nexus_mod_manager.services.update_service import (
    _check_update_for_installed_mod,
    _find_best_matching_file,
    check_correlation_updates,
    check_installed_mod_updates,
)


class TestFindBestMatchingFile:
    def test_empty_files_returns_none(self):
        mod = InstalledMod(game_id=1, name="Mod", upload_timestamp=1000, nexus_mod_id=10)
        assert _find_best_matching_file(mod, []) is None

    def test_exact_timestamp_match_returns_latest_in_category(self):
        mod = InstalledMod(game_id=1, name="Mod", upload_timestamp=1000, nexus_mod_id=10)
        files = [
            {"file_id": 1, "uploaded_timestamp": 1000, "category_id": 1, "version": "1.0"},
            {"file_id": 2, "uploaded_timestamp": 2000, "category_id": 1, "version": "2.0"},
            {"file_id": 3, "uploaded_timestamp": 3000, "category_id": 4, "version": "3.0"},
        ]
        result = _find_best_matching_file(mod, files)
        assert result is not None
        assert result["file_id"] == 2
        assert result["version"] == "2.0"

    def test_file_id_match(self):
        mod = InstalledMod(game_id=1, name="Mod", nexus_file_id=42, nexus_mod_id=10)
        files = [
            {"file_id": 41, "uploaded_timestamp": 1000, "category_id": 1, "version": "1.0"},
            {"file_id": 42, "uploaded_timestamp": 900, "category_id": 2, "version": "0.9"},
        ]
        result = _find_best_matching_file(mod, files)
        assert result is not None
        assert result["file_id"] == 42

    def test_fallback_main_category(self):
        mod = InstalledMod(game_id=1, name="Mod", nexus_mod_id=10)
        files = [
            {"file_id": 1, "uploaded_timestamp": 500, "category_id": 1, "version": "1.0"},
            {"file_id": 2, "uploaded_timestamp": 1000, "category_id": 1, "version": "2.0"},
            {"file_id": 3, "uploaded_timestamp": 2000, "category_id": 4, "version": "3.0"},
        ]
        result = _find_best_matching_file(mod, files)
        assert result is not None
        assert result["file_id"] == 2

    def test_fallback_any_file(self):
        mod = InstalledMod(game_id=1, name="Mod", nexus_mod_id=10)
        files = [
            {"file_id": 1, "uploaded_timestamp": 500, "category_id": 4, "version": "1.0"},
            {"file_id": 2, "uploaded_timestamp": 2000, "category_id": 4, "version": "2.0"},
        ]
        result = _find_best_matching_file(mod, files)
        assert result is not None
        assert result["file_id"] == 2


class TestCheckUpdateForInstalledMod:
    def test_newer_timestamp_detected(self):
        mod = InstalledMod(
            id=1,
            game_id=1,
            name="Mod",
            nexus_mod_id=10,
            upload_timestamp=1000,
            installed_version="1.0",
        )
        files = [
            {"file_id": 1, "uploaded_timestamp": 1000, "category_id": 1, "version": "1.0"},
            {"file_id": 2, "uploaded_timestamp": 2000, "category_id": 1, "version": "2.0"},
        ]
        meta = NexusModMeta(nexus_mod_id=10, name="Mod", author="Auth", game_domain="g")
        result = _check_update_for_installed_mod(mod, files, meta)
        assert result is not None
        assert result["source"] == "installed"
        assert result["nexus_timestamp"] == 2000
        assert result["local_timestamp"] == 1000

    def test_same_timestamp_no_update(self):
        mod = InstalledMod(
            id=1,
            game_id=1,
            name="Mod",
            nexus_mod_id=10,
            upload_timestamp=1000,
            installed_version="1.0",
        )
        files = [
            {"file_id": 1, "uploaded_timestamp": 1000, "category_id": 1, "version": "1.0"},
        ]
        meta = NexusModMeta(nexus_mod_id=10, name="Mod", version="1.0")
        result = _check_update_for_installed_mod(mod, files, meta)
        assert result is None

    def test_version_fallback_when_no_timestamps(self):
        mod = InstalledMod(
            id=1,
            game_id=1,
            name="Mod",
            nexus_mod_id=10,
            installed_version="1.0",
        )
        files = [
            {"file_id": 1, "category_id": 1, "version": "2.0"},
        ]
        meta = NexusModMeta(nexus_mod_id=10, name="Mod", version="2.0", author="A")
        result = _check_update_for_installed_mod(mod, files, meta)
        assert result is not None
        assert result["nexus_version"] == "2.0"

    def test_no_nexus_files_returns_none(self):
        mod = InstalledMod(
            id=1,
            game_id=1,
            name="Mod",
            nexus_mod_id=10,
            upload_timestamp=1000,
        )
        result = _check_update_for_installed_mod(mod, [], None)
        assert result is None


class TestCheckCorrelationUpdates:
    def test_semantic_version_no_false_positive(self, engine):
        """'1.0' vs '1.0.0' should NOT be flagged as an update."""
        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            group = ModGroup(game_id=game.id, display_name="Mod1")
            s.add(group)
            dl = NexusDownload(game_id=game.id, nexus_mod_id=10, mod_name="Mod1", version="1.0")
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
            s.add(NexusModMeta(nexus_mod_id=10, name="Mod1", version="1.0.0", author="A"))
            s.commit()

            result = check_correlation_updates(game.id, s)
            assert result.total_checked == 1
            assert len(result.updates) == 0

    def test_real_update_detected(self, engine):
        """'1.0' vs '2.0' should be detected as an update."""
        with Session(engine) as s:
            game = Game(name="G2", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            group = ModGroup(game_id=game.id, display_name="Mod2")
            s.add(group)
            dl = NexusDownload(
                game_id=game.id,
                nexus_mod_id=20,
                mod_name="Mod2",
                version="1.0",
                nexus_url="https://nexus/20",
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
            s.add(NexusModMeta(nexus_mod_id=20, name="Mod2", version="2.0", author="Auth"))
            s.commit()

            result = check_correlation_updates(game.id, s)
            assert result.total_checked == 1
            assert len(result.updates) == 1
            assert result.updates[0]["source"] == "correlation"
            assert result.updates[0]["nexus_version"] == "2.0"

    def test_empty_version_skipped(self, engine):
        with Session(engine) as s:
            game = Game(name="G3", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            group = ModGroup(game_id=game.id, display_name="Mod3")
            s.add(group)
            dl = NexusDownload(game_id=game.id, nexus_mod_id=30, mod_name="Mod3", version="")
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
            s.add(NexusModMeta(nexus_mod_id=30, name="Mod3", version="1.0", author="A"))
            s.commit()

            result = check_correlation_updates(game.id, s)
            assert len(result.updates) == 0


class TestCheckInstalledModUpdates:
    @pytest.mark.anyio
    async def test_no_installed_mods(self, engine):
        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.commit()

            client = AsyncMock()
            result = await check_installed_mod_updates(game.id, "g", client, s)
            assert result.total_checked == 0
            assert result.updates == []

    @pytest.mark.anyio
    async def test_timestamp_update_detected(self, engine):
        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            mod = InstalledMod(
                game_id=game.id,
                name="TestMod",
                nexus_mod_id=100,
                upload_timestamp=1000,
                installed_version="1.0",
            )
            s.add(mod)
            s.add(
                NexusModMeta(
                    nexus_mod_id=100,
                    name="TestMod",
                    version="2.0",
                    author="Auth",
                    game_domain="g",
                )
            )
            s.commit()

            client = AsyncMock()
            client.get_mod_files.return_value = {
                "files": [
                    {
                        "file_id": 1,
                        "uploaded_timestamp": 1000,
                        "category_id": 1,
                        "version": "1.0",
                    },
                    {
                        "file_id": 2,
                        "uploaded_timestamp": 2000,
                        "category_id": 1,
                        "version": "2.0",
                    },
                ]
            }

            result = await check_installed_mod_updates(game.id, "g", client, s)
            assert result.total_checked == 1
            assert len(result.updates) == 1
            assert result.updates[0]["nexus_timestamp"] == 2000
            assert result.updates[0]["source"] == "installed"

from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session

from chat_nexus_mod_manager.matching.variant_scorer import pick_best_file
from chat_nexus_mod_manager.models.correlation import ModNexusCorrelation
from chat_nexus_mod_manager.models.game import Game, GameModPath
from chat_nexus_mod_manager.models.install import InstalledMod
from chat_nexus_mod_manager.models.mod import ModGroup
from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta
from chat_nexus_mod_manager.services.update_service import (
    check_all_updates,
    check_correlation_updates,
    collect_tracked_mods,
)


class TestPickBestFile:
    def test_empty_files_returns_none(self):
        mod = InstalledMod(game_id=1, name="Mod", upload_timestamp=1000, nexus_mod_id=10)
        assert pick_best_file([], mod) is None

    def test_exact_timestamp_match_returns_latest_in_category(self):
        mod = InstalledMod(game_id=1, name="Mod", upload_timestamp=1000, nexus_mod_id=10)
        files = [
            {"file_id": 1, "uploaded_timestamp": 1000, "category_id": 1, "version": "1.0"},
            {"file_id": 2, "uploaded_timestamp": 2000, "category_id": 1, "version": "2.0"},
            {"file_id": 3, "uploaded_timestamp": 3000, "category_id": 4, "version": "3.0"},
        ]
        result = pick_best_file(files, mod)
        assert result is not None
        assert result["file_id"] == 2
        assert result["version"] == "2.0"

    def test_file_id_match(self):
        mod = InstalledMod(game_id=1, name="Mod", nexus_file_id=42, nexus_mod_id=10)
        files = [
            {"file_id": 41, "uploaded_timestamp": 1000, "category_id": 1, "version": "1.0"},
            {"file_id": 42, "uploaded_timestamp": 900, "category_id": 2, "version": "0.9"},
        ]
        result = pick_best_file(files, mod)
        assert result is not None
        assert result["file_id"] == 42

    def test_fallback_main_category(self):
        mod = InstalledMod(game_id=1, name="Mod", nexus_mod_id=10)
        files = [
            {"file_id": 1, "uploaded_timestamp": 500, "category_id": 1, "version": "1.0"},
            {"file_id": 2, "uploaded_timestamp": 1000, "category_id": 1, "version": "2.0"},
            {"file_id": 3, "uploaded_timestamp": 2000, "category_id": 4, "version": "3.0"},
        ]
        result = pick_best_file(files, mod)
        assert result is not None
        assert result["file_id"] == 2

    def test_fallback_any_file(self):
        mod = InstalledMod(game_id=1, name="Mod", nexus_mod_id=10)
        files = [
            {"file_id": 1, "uploaded_timestamp": 500, "category_id": 4, "version": "1.0"},
            {"file_id": 2, "uploaded_timestamp": 2000, "category_id": 4, "version": "2.0"},
        ]
        result = pick_best_file(files, mod)
        assert result is not None
        assert result["file_id"] == 2


class TestCollectTrackedMods:
    def test_installed_has_priority_over_correlation(self, engine):
        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))

            group = ModGroup(game_id=game.id, display_name="Mod1")
            s.add(group)
            dl = NexusDownload(game_id=game.id, nexus_mod_id=10, mod_name="Mod1", version="0.5")
            s.add(dl)
            s.flush()
            s.add(
                ModNexusCorrelation(
                    mod_group_id=group.id, nexus_download_id=dl.id, score=1.0, method="exact"
                )
            )
            installed = InstalledMod(
                game_id=game.id, name="Mod1", nexus_mod_id=10, installed_version="1.0"
            )
            s.add(installed)
            s.commit()

            tracked = collect_tracked_mods(game.id, "g", s)
            assert 10 in tracked
            assert tracked[10].source == "installed"
            assert tracked[10].local_version == "1.0"

    def test_endorsed_tracked_after_correlation(self, engine):
        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))

            dl = NexusDownload(
                game_id=game.id,
                nexus_mod_id=20,
                mod_name="Endorsed",
                version="1.0",
                is_endorsed=True,
            )
            s.add(dl)
            s.commit()

            tracked = collect_tracked_mods(game.id, "g", s)
            assert 20 in tracked
            assert tracked[20].source == "endorsed"
            assert tracked[20].local_version == "1.0"

    def test_deduplication_across_sources(self, engine):
        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))

            group = ModGroup(game_id=game.id, display_name="Mod")
            s.add(group)
            dl = NexusDownload(
                game_id=game.id,
                nexus_mod_id=10,
                mod_name="Mod",
                version="0.5",
                is_endorsed=True,
            )
            s.add(dl)
            s.flush()
            s.add(
                ModNexusCorrelation(
                    mod_group_id=group.id, nexus_download_id=dl.id, score=1.0, method="exact"
                )
            )
            s.commit()

            tracked = collect_tracked_mods(game.id, "g", s)
            assert len(tracked) == 1
            assert tracked[10].source == "correlation"


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

    def test_filename_parsed_version_detects_update(self, engine):
        """When file_name encodes version 1.0 but both download.version and meta.version
        are "2.0" (same API call), the filename-parsed version should expose the delta."""
        with Session(engine) as s:
            game = Game(name="G4", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            group = ModGroup(game_id=game.id, display_name="CET")
            s.add(group)
            dl = NexusDownload(
                game_id=game.id,
                nexus_mod_id=107,
                mod_name="CET",
                version="2.0",
                file_name="CET 1.37.1-107-1-37-1-1759193708.zip",
                nexus_url="https://nexus/107",
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
            s.add(NexusModMeta(nexus_mod_id=107, name="CET", version="2.0", author="A"))
            s.commit()

            result = check_correlation_updates(game.id, s)
            assert len(result.updates) == 1
            assert result.updates[0]["local_version"] == "1.37.1"
            assert result.updates[0]["nexus_version"] == "2.0"

    def test_fallback_to_download_version_when_no_filename(self, engine):
        """Without a file_name, should fall back to download.version as before."""
        with Session(engine) as s:
            game = Game(name="G5", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            group = ModGroup(game_id=game.id, display_name="Mod5")
            s.add(group)
            dl = NexusDownload(
                game_id=game.id,
                nexus_mod_id=50,
                mod_name="Mod5",
                version="1.0",
                file_name="",
                nexus_url="https://nexus/50",
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
            s.add(NexusModMeta(nexus_mod_id=50, name="Mod5", version="2.0", author="A"))
            s.commit()

            result = check_correlation_updates(game.id, s)
            assert len(result.updates) == 1
            assert result.updates[0]["local_version"] == "1.0"
            assert result.updates[0]["nexus_version"] == "2.0"

    def test_endorsed_mod_update_detected(self, engine):
        """Endorsed mods should also be checked for updates."""
        with Session(engine) as s:
            game = Game(name="G6", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            dl = NexusDownload(
                game_id=game.id,
                nexus_mod_id=60,
                mod_name="EndorsedMod",
                version="1.0",
                is_endorsed=True,
                nexus_url="https://nexus/60",
            )
            s.add(dl)
            s.add(
                NexusModMeta(
                    nexus_mod_id=60, name="EndorsedMod", version="2.0", author="A", game_domain="g"
                )
            )
            s.commit()

            result = check_correlation_updates(game.id, s)
            assert len(result.updates) == 1
            assert result.updates[0]["source"] == "endorsed"
            assert result.updates[0]["nexus_version"] == "2.0"

    def test_tracked_mod_update_detected(self, engine):
        """Tracked mods should also be checked for updates."""
        with Session(engine) as s:
            game = Game(name="G7", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            dl = NexusDownload(
                game_id=game.id,
                nexus_mod_id=70,
                mod_name="TrackedMod",
                version="1.0",
                is_tracked=True,
                nexus_url="https://nexus/70",
            )
            s.add(dl)
            s.add(
                NexusModMeta(
                    nexus_mod_id=70, name="TrackedMod", version="3.0", author="A", game_domain="g"
                )
            )
            s.commit()

            result = check_correlation_updates(game.id, s)
            assert len(result.updates) == 1
            assert result.updates[0]["source"] == "tracked"
            assert result.updates[0]["nexus_version"] == "3.0"


class TestCheckAllUpdates:
    @pytest.mark.anyio
    async def test_no_tracked_mods(self, engine):
        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.commit()

            client = AsyncMock()
            result = await check_all_updates(game.id, "g", client, s)
            assert result.total_checked == 0
            assert result.updates == []
            client.get_updated_mods.assert_not_called()

    @pytest.mark.anyio
    async def test_refreshes_only_recently_updated(self, engine):
        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))

            dl1 = NexusDownload(
                game_id=game.id,
                nexus_mod_id=10,
                mod_name="Updated",
                version="1.0",
                is_endorsed=True,
            )
            dl2 = NexusDownload(
                game_id=game.id,
                nexus_mod_id=20,
                mod_name="NotUpdated",
                version="1.0",
                is_endorsed=True,
            )
            s.add_all([dl1, dl2])
            s.add(NexusModMeta(nexus_mod_id=10, name="Updated", version="1.0", author="A"))
            s.add(NexusModMeta(nexus_mod_id=20, name="NotUpdated", version="1.0", author="B"))
            s.commit()

            client = AsyncMock()
            client.get_updated_mods.return_value = [
                {"mod_id": 10, "latest_file_update": 9999, "latest_mod_activity": 9999},
            ]
            client.get_mod_info.return_value = {"version": "2.0", "updated_timestamp": 9999}
            client.get_mod_files.return_value = {
                "files": [{"file_id": 1, "category_id": 1, "uploaded_timestamp": 9999}]
            }

            result = await check_all_updates(game.id, "g", client, s)

            client.get_updated_mods.assert_called_once_with("g", "1m")
            client.get_mod_info.assert_called_once_with("g", 10)
            assert result.total_checked == 2
            assert len(result.updates) == 1
            assert result.updates[0]["nexus_mod_id"] == 10
            assert result.updates[0]["nexus_version"] == "2.0"

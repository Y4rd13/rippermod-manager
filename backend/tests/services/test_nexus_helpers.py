from sqlmodel import Session, select

from chat_nexus_mod_manager.models.game import Game, GameModPath
from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta
from chat_nexus_mod_manager.services.nexus_helpers import upsert_nexus_mod


class TestUpsertNexusMod:
    def test_creates_new_download_with_version(self, engine):
        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            s.commit()

            info = {"name": "CoolMod", "version": "1.5", "category_id": 5}
            dl = upsert_nexus_mod(s, game.id, "g", 100, info, file_name="cool.zip")
            s.commit()

            assert dl.version == "1.5"
            assert dl.mod_name == "CoolMod"
            assert dl.file_name == "cool.zip"

    def test_preserves_version_on_existing_download(self, engine):
        """upsert_nexus_mod must NOT overwrite NexusDownload.version on existing records."""
        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))

            dl = NexusDownload(game_id=game.id, nexus_mod_id=100, mod_name="OldName", version="1.0")
            s.add(dl)
            s.commit()

            info = {"name": "NewName", "version": "2.0", "category_id": 5}
            updated = upsert_nexus_mod(s, game.id, "g", 100, info)
            s.commit()
            s.refresh(updated)

            assert updated.mod_name == "NewName"
            assert updated.version == "1.0"  # preserved, NOT overwritten to "2.0"

    def test_updates_metadata_version(self, engine):
        """upsert_nexus_mod should update NexusModMeta.version to latest."""
        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))

            meta = NexusModMeta(nexus_mod_id=100, game_domain="g", name="OldName", version="1.0")
            s.add(meta)
            s.commit()

            info = {"name": "NewName", "version": "2.0", "summary": "new", "author": "A"}
            upsert_nexus_mod(s, game.id, "g", 100, info)
            s.commit()

            refreshed = s.exec(select(NexusModMeta).where(NexusModMeta.nexus_mod_id == 100)).first()
            assert refreshed.version == "2.0"  # metadata SHOULD be updated
            assert refreshed.name == "NewName"

    def test_sets_version_on_new_download(self, engine):
        """New NexusDownload records should get the API version."""
        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            s.commit()

            info = {"name": "Fresh", "version": "3.0", "category_id": 1}
            dl = upsert_nexus_mod(s, game.id, "g", 200, info)
            s.commit()
            s.refresh(dl)

            assert dl.version == "3.0"

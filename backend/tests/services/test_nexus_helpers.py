from sqlmodel import Session, select

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.nexus import NexusDownload, NexusModMeta, NexusModRequirement
from rippermod_manager.services.nexus_helpers import (
    extract_dlc_requirements,
    upsert_mod_requirements,
    upsert_nexus_mod,
)


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


class TestUpsertModRequirements:
    def test_inserts_forward_requirements(self, engine):
        with Session(engine) as s:
            gql_reqs = [
                {
                    "modId": 200,
                    "modName": "Dep",
                    "url": "",
                    "notes": "",
                    "externalRequirement": False,
                }
            ]
            upsert_mod_requirements(s, 100, gql_reqs)
            s.commit()

            rows = s.exec(
                select(NexusModRequirement).where(NexusModRequirement.nexus_mod_id == 100)
            ).all()
            assert len(rows) == 1
            assert rows[0].required_mod_id == 200
            assert rows[0].is_reverse is False

    def test_replaces_forward_requirements(self, engine):
        with Session(engine) as s:
            s.add(NexusModRequirement(nexus_mod_id=100, required_mod_id=200, is_reverse=False))
            s.commit()

            upsert_mod_requirements(
                s, 100, [{"modId": 300, "modName": "New", "externalRequirement": False}]
            )
            s.commit()

            rows = s.exec(
                select(NexusModRequirement).where(
                    NexusModRequirement.nexus_mod_id == 100,
                    NexusModRequirement.is_reverse.is_(False),
                )
            ).all()
            assert len(rows) == 1
            assert rows[0].required_mod_id == 300

    def test_inserts_reverse_requirements(self, engine):
        with Session(engine) as s:
            upsert_mod_requirements(
                s,
                100,
                [],
                reverse_requirements=[
                    {"modId": 50, "modName": "Parent", "externalRequirement": False}
                ],
            )
            s.commit()

            rows = s.exec(
                select(NexusModRequirement).where(
                    NexusModRequirement.nexus_mod_id == 100,
                    NexusModRequirement.is_reverse.is_(True),
                )
            ).all()
            assert len(rows) == 1
            assert rows[0].required_mod_id == 50
            assert rows[0].is_reverse is True

    def test_does_not_delete_reverse_when_only_forward(self, engine):
        with Session(engine) as s:
            s.add(NexusModRequirement(nexus_mod_id=100, required_mod_id=50, is_reverse=True))
            s.commit()

            # Only update forward reqs, reverse_requirements not provided
            upsert_mod_requirements(
                s, 100, [{"modId": 200, "modName": "Fwd", "externalRequirement": False}]
            )
            s.commit()

            rev_rows = s.exec(
                select(NexusModRequirement).where(
                    NexusModRequirement.nexus_mod_id == 100,
                    NexusModRequirement.is_reverse.is_(True),
                )
            ).all()
            assert len(rev_rows) == 1

    def test_stores_dlc_requirements(self, engine):
        import json

        with Session(engine) as s:
            meta = NexusModMeta(nexus_mod_id=100, game_domain="g", name="Test")
            s.add(meta)
            s.commit()

            dlc = [{"expansion_name": "Phantom Liberty", "expansion_id": 1, "notes": ""}]
            upsert_mod_requirements(s, 100, [], dlc_requirements=dlc)
            s.commit()

            s.refresh(meta)
            stored = json.loads(meta.dlc_requirements)
            assert len(stored) == 1
            assert stored[0]["expansion_name"] == "Phantom Liberty"


class TestExtractDlcRequirements:
    def test_extracts_dlc_from_gql_mod(self):
        gql_mod = {
            "modRequirements": {
                "dlcRequirements": [
                    {
                        "gameExpansion": {"id": 1, "name": "Phantom Liberty"},
                        "notes": "Required",
                    }
                ]
            }
        }
        result = extract_dlc_requirements(gql_mod)
        assert len(result) == 1
        assert result[0]["expansion_name"] == "Phantom Liberty"
        assert result[0]["expansion_id"] == 1
        assert result[0]["notes"] == "Required"

    def test_empty_when_no_dlc(self):
        assert extract_dlc_requirements({}) == []
        assert extract_dlc_requirements({"modRequirements": {}}) == []
        assert extract_dlc_requirements({"modRequirements": {"dlcRequirements": []}}) == []

    def test_handles_missing_expansion(self):
        gql_mod = {"modRequirements": {"dlcRequirements": [{"notes": "test"}]}}
        result = extract_dlc_requirements(gql_mod)
        assert len(result) == 1
        assert result[0]["expansion_name"] == ""
        assert result[0]["expansion_id"] is None

"""Tests for FOMOD wizard API endpoints."""

import zipfile
from pathlib import Path

import pytest
from sqlmodel import Session

from rippermod_manager.models.game import Game, GameModPath


def _make_fomod_zip(
    path: Path, config_xml: str, extra_files: dict[str, bytes] | None = None
) -> None:
    """Create a zip archive with fomod/ModuleConfig.xml and optional extra files."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("fomod/ModuleConfig.xml", config_xml)
        for name, content in (extra_files or {}).items():
            zf.writestr(name, content)


SIMPLE_CONFIG = """\
<?xml version="1.0" encoding="utf-8"?>
<config>
  <moduleName>TestFOMOD</moduleName>
  <installSteps>
    <installStep name="Main">
      <optionalFileGroups>
        <group name="Options" type="SelectExactlyOne">
          <plugins>
            <plugin name="Option A">
              <description>Install A</description>
              <files>
                <file source="a.txt" destination="mods/a.txt" />
              </files>
              <typeDescriptor><type name="Recommended" /></typeDescriptor>
            </plugin>
            <plugin name="Option B">
              <description>Install B</description>
              <files>
                <file source="b.txt" destination="mods/b.txt" />
              </files>
              <typeDescriptor><type name="Optional" /></typeDescriptor>
            </plugin>
          </plugins>
        </group>
      </optionalFileGroups>
    </installStep>
  </installSteps>
</config>
"""


@pytest.fixture
def fomod_setup(tmp_path, client, engine):
    """Create a game with a FOMOD archive."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    staging = game_dir / "downloaded_mods"
    staging.mkdir()

    with Session(engine) as s:
        g = Game(name="FomodTestGame", domain_name="ftg", install_path=str(game_dir))
        s.add(g)
        s.flush()
        s.add(GameModPath(game_id=g.id, relative_path="mods"))
        s.commit()

    archive = staging / "TestFomod.zip"
    _make_fomod_zip(
        archive,
        SIMPLE_CONFIG,
        extra_files={"a.txt": b"content_a", "b.txt": b"content_b"},
    )

    return "FomodTestGame", game_dir, staging


class TestGetConfig:
    def test_returns_parsed_config(self, client, fomod_setup):
        game_name, _, _ = fomod_setup
        r = client.get(
            f"/api/v1/games/{game_name}/install/fomod/config",
            params={"archive_filename": "TestFomod.zip"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["module_name"] == "TestFOMOD"
        assert data["total_steps"] == 1
        assert len(data["steps"]) == 1
        assert len(data["steps"][0]["groups"]) == 1
        assert len(data["steps"][0]["groups"][0]["plugins"]) == 2
        assert data["steps"][0]["groups"][0]["type"] == "SelectExactlyOne"

    def test_non_fomod_archive_returns_400(self, client, fomod_setup):
        game_name, _, staging = fomod_setup
        plain = staging / "Plain.zip"
        with zipfile.ZipFile(plain, "w") as zf:
            zf.writestr("readme.txt", "hello")

        r = client.get(
            f"/api/v1/games/{game_name}/install/fomod/config",
            params={"archive_filename": "Plain.zip"},
        )
        assert r.status_code == 400

    def test_missing_archive_returns_404(self, client, fomod_setup):
        game_name, _, _ = fomod_setup
        r = client.get(
            f"/api/v1/games/{game_name}/install/fomod/config",
            params={"archive_filename": "ghost.zip"},
        )
        assert r.status_code == 404

    def test_game_not_found_returns_404(self, client):
        r = client.get(
            "/api/v1/games/NoGame/install/fomod/config",
            params={"archive_filename": "any.zip"},
        )
        assert r.status_code == 404

    def test_backward_compat_no_conditions(self, client, fomod_setup):
        """FOMOD without conditions returns visible=null, patterns=[]."""
        game_name, _, _ = fomod_setup
        r = client.get(
            f"/api/v1/games/{game_name}/install/fomod/config",
            params={"archive_filename": "TestFomod.zip"},
        )
        assert r.status_code == 200
        data = r.json()
        step = data["steps"][0]
        assert step["visible"] is None
        plugin = step["groups"][0]["plugins"][0]
        assert plugin["type_descriptor"]["patterns"] == []


CONDITIONAL_CONFIG = """\
<?xml version="1.0" encoding="utf-8"?>
<config>
  <moduleName>ConditionalFOMOD</moduleName>
  <installSteps>
    <installStep name="Choose">
      <optionalFileGroups>
        <group name="Flavor" type="SelectExactlyOne">
          <plugins>
            <plugin name="Enable Extra">
              <description>Enables step 2</description>
              <conditionFlags><flag name="extra">on</flag></conditionFlags>
              <files><file source="base.txt" destination="mods/base.txt" /></files>
              <typeDescriptor>
                <dependencyType>
                  <defaultType name="Optional" />
                  <patterns>
                    <pattern>
                      <dependencies operator="And">
                        <flagDependency flag="someFlag" value="yes" />
                      </dependencies>
                      <type name="Recommended" />
                    </pattern>
                  </patterns>
                </dependencyType>
              </typeDescriptor>
            </plugin>
            <plugin name="Skip Extra">
              <description>Skips step 2</description>
              <conditionFlags><flag name="extra">off</flag></conditionFlags>
              <files><file source="base.txt" destination="mods/base.txt" /></files>
              <typeDescriptor><type name="Optional" /></typeDescriptor>
            </plugin>
          </plugins>
        </group>
      </optionalFileGroups>
    </installStep>
    <installStep name="Extra Options">
      <visible>
        <flagDependency flag="extra" value="on" />
      </visible>
      <optionalFileGroups>
        <group name="Extras" type="SelectAny">
          <plugins>
            <plugin name="Extra A">
              <description>Extra option A</description>
              <files><file source="extra_a.txt" destination="mods/extra_a.txt" /></files>
              <typeDescriptor><type name="Optional" /></typeDescriptor>
            </plugin>
          </plugins>
        </group>
      </optionalFileGroups>
    </installStep>
    <installStep name="Nested Test">
      <visible>
        <dependencies operator="Or">
          <dependencies operator="And">
            <flagDependency flag="extra" value="on" />
            <flagDependency flag="someFlag" value="yes" />
          </dependencies>
          <flagDependency flag="alwaysShow" value="true" />
        </dependencies>
      </visible>
      <optionalFileGroups>
        <group name="Nested" type="SelectAny">
          <plugins>
            <plugin name="Nested Plugin">
              <description>Nested test</description>
              <files><file source="nested.txt" destination="mods/nested.txt" /></files>
              <typeDescriptor><type name="Optional" /></typeDescriptor>
            </plugin>
          </plugins>
        </group>
      </optionalFileGroups>
    </installStep>
  </installSteps>
</config>
"""


@pytest.fixture
def fomod_conditional_setup(tmp_path, client, engine):
    """Create a game with a conditional FOMOD archive."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    staging = game_dir / "downloaded_mods"
    staging.mkdir()

    with Session(engine) as s:
        g = Game(name="CondGame", domain_name="cg", install_path=str(game_dir))
        s.add(g)
        s.flush()
        s.add(GameModPath(game_id=g.id, relative_path="mods"))
        s.commit()

    archive = staging / "Conditional.zip"
    _make_fomod_zip(
        archive,
        CONDITIONAL_CONFIG,
        extra_files={
            "base.txt": b"base",
            "extra_a.txt": b"extra",
            "nested.txt": b"nested",
        },
    )

    return "CondGame", game_dir, staging


class TestGetConfigWithConditions:
    def test_returns_visible_conditions(self, client, fomod_conditional_setup):
        """Step with <visible> returns a composite dependency object."""
        game_name, _, _ = fomod_conditional_setup
        r = client.get(
            f"/api/v1/games/{game_name}/install/fomod/config",
            params={"archive_filename": "Conditional.zip"},
        )
        assert r.status_code == 200
        data = r.json()

        # Step 0 has no visible condition
        assert data["steps"][0]["visible"] is None

        # Step 1 has a visible condition on flag "extra" == "on"
        vis = data["steps"][1]["visible"]
        assert vis is not None
        assert vis["operator"] == "And"
        assert len(vis["flag_conditions"]) == 1
        assert vis["flag_conditions"][0]["name"] == "extra"
        assert vis["flag_conditions"][0]["value"] == "on"

    def test_returns_type_descriptor_patterns(self, client, fomod_conditional_setup):
        """Plugin with <dependencyType> returns populated patterns array."""
        game_name, _, _ = fomod_conditional_setup
        r = client.get(
            f"/api/v1/games/{game_name}/install/fomod/config",
            params={"archive_filename": "Conditional.zip"},
        )
        assert r.status_code == 200
        data = r.json()

        plugin = data["steps"][0]["groups"][0]["plugins"][0]
        td = plugin["type_descriptor"]
        assert td["default_type"] == "Optional"
        assert len(td["patterns"]) == 1
        pattern = td["patterns"][0]
        assert pattern["type"] == "Recommended"
        assert pattern["dependency"]["operator"] == "And"
        assert pattern["dependency"]["flag_conditions"][0]["name"] == "someFlag"
        assert pattern["dependency"]["flag_conditions"][0]["value"] == "yes"

    def test_nested_dependencies_serialize(self, client, fomod_conditional_setup):
        """Nested <dependencies> with AND/OR serialize to recursive nested array."""
        game_name, _, _ = fomod_conditional_setup
        r = client.get(
            f"/api/v1/games/{game_name}/install/fomod/config",
            params={"archive_filename": "Conditional.zip"},
        )
        assert r.status_code == 200
        data = r.json()

        # Step 2's <visible> wraps a single <dependencies operator="Or">
        vis = data["steps"][2]["visible"]
        assert vis["operator"] == "And"
        assert len(vis["nested"]) == 1

        # The Or-level contains a nested And-group + a top-level flag
        or_dep = vis["nested"][0]
        assert or_dep["operator"] == "Or"
        assert len(or_dep["nested"]) == 1
        assert or_dep["flag_conditions"][0]["name"] == "alwaysShow"

        and_dep = or_dep["nested"][0]
        assert and_dep["operator"] == "And"
        assert len(and_dep["flag_conditions"]) == 2


class TestPreview:
    def test_preview_returns_files(self, client, fomod_setup):
        game_name, _, _ = fomod_setup
        r = client.post(
            f"/api/v1/games/{game_name}/install/fomod/preview",
            json={
                "archive_filename": "TestFomod.zip",
                "selections": {"0": {"0": [0]}},
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total_files"] == 1
        assert data["files"][0]["game_relative_path"] == "mods/a.txt"


class TestInstall:
    def test_install_with_selections(self, client, fomod_setup):
        game_name, game_dir, _ = fomod_setup
        r = client.post(
            f"/api/v1/games/{game_name}/install/fomod/install",
            json={
                "archive_filename": "TestFomod.zip",
                "mod_name": "TestFOMOD",
                "selections": {"0": {"0": [0]}},
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["files_extracted"] == 1
        assert data["name"] == "TestFOMOD"
        assert (game_dir / "mods" / "a.txt").read_bytes() == b"content_a"
        assert not (game_dir / "mods" / "b.txt").exists()

    def test_install_option_b(self, client, fomod_setup):
        game_name, game_dir, _ = fomod_setup
        r = client.post(
            f"/api/v1/games/{game_name}/install/fomod/install",
            json={
                "archive_filename": "TestFomod.zip",
                "mod_name": "TestFOMOD_B",
                "selections": {"0": {"0": [1]}},
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["files_extracted"] == 1
        assert (game_dir / "mods" / "b.txt").read_bytes() == b"content_b"

    def test_install_missing_archive_returns_404(self, client, fomod_setup):
        game_name, _, _ = fomod_setup
        r = client.post(
            f"/api/v1/games/{game_name}/install/fomod/install",
            json={
                "archive_filename": "missing.zip",
                "mod_name": "X",
                "selections": {},
            },
        )
        assert r.status_code == 404

"""Tests for FOMOD install service (file list computation + extraction)."""

import os
import zipfile

import pytest
from sqlmodel import Session, select

from rippermod_manager.archive.handler import ArchiveEntry
from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.services.fomod_config_parser import (
    CompositeDependency,
    ConditionalInstallPattern,
    DependencyOperator,
    FileMapping,
    FlagCondition,
    FomodConfig,
    FomodGroup,
    FomodPlugin,
    FomodStep,
    GroupType,
    PluginType,
    TypeDescriptor,
)
from rippermod_manager.services.fomod_install_service import (
    ResolvedFile,
    compute_file_list,
    evaluate_dependency,
    install_fomod,
    is_step_visible,
)


def _make_plugin(
    name: str = "P",
    files: list[FileMapping] | None = None,
    condition_flags=None,
) -> FomodPlugin:
    return FomodPlugin(
        name=name,
        description="",
        image_path="",
        files=files or [],
        condition_flags=condition_flags or [],
        type_descriptor=TypeDescriptor(default_type=PluginType.OPTIONAL),
    )


def _make_entries(paths: list[str]) -> list[ArchiveEntry]:
    return [ArchiveEntry(filename=p, is_dir=False, size=100) for p in paths]


def _make_config(
    required: list[FileMapping] | None = None,
    steps: list[FomodStep] | None = None,
    conditional: list[ConditionalInstallPattern] | None = None,
) -> FomodConfig:
    return FomodConfig(
        module_name="Test",
        module_image="",
        required_install_files=required or [],
        steps=steps or [],
        conditional_file_installs=conditional or [],
    )


class TestComputeFileListRequired:
    def test_required_files_only(self):
        config = _make_config(
            required=[
                FileMapping(
                    source="core.dll", destination="bin/core.dll", priority=0, is_folder=False
                )
            ],
        )
        entries = _make_entries(["core.dll"])
        result = compute_file_list(config, {}, entries, "")
        assert len(result) == 1
        assert result[0].game_relative_path == "bin/core.dll"


class TestComputeFileListSelections:
    def test_single_step_selection(self):
        plugin = _make_plugin(
            files=[
                FileMapping(source="a.txt", destination="mods/a.txt", priority=0, is_folder=False)
            ]
        )
        step = FomodStep(
            name="S",
            groups=[FomodGroup(name="G", type=GroupType.SELECT_EXACTLY_ONE, plugins=[plugin])],
        )
        config = _make_config(steps=[step])
        entries = _make_entries(["a.txt"])
        selections = {0: {0: [0]}}
        result = compute_file_list(config, selections, entries, "")
        assert len(result) == 1
        assert result[0].game_relative_path == "mods/a.txt"

    def test_empty_selection_no_files(self):
        plugin = _make_plugin(
            files=[
                FileMapping(source="a.txt", destination="mods/a.txt", priority=0, is_folder=False)
            ]
        )
        step = FomodStep(
            name="S",
            groups=[FomodGroup(name="G", type=GroupType.SELECT_ANY, plugins=[plugin])],
        )
        config = _make_config(steps=[step])
        entries = _make_entries(["a.txt"])
        result = compute_file_list(config, {0: {0: []}}, entries, "")
        assert len(result) == 0


class TestFolderExpansion:
    def test_folder_expands_to_all_entries(self):
        plugin = _make_plugin(
            files=[FileMapping(source="data", destination="gamedata", priority=0, is_folder=True)]
        )
        step = FomodStep(
            name="S",
            groups=[FomodGroup(name="G", type=GroupType.SELECT_ANY, plugins=[plugin])],
        )
        config = _make_config(steps=[step])
        entries = _make_entries(["data/a.txt", "data/sub/b.txt", "other.txt"])
        selections = {0: {0: [0]}}
        result = compute_file_list(config, selections, entries, "")
        paths = sorted(r.game_relative_path for r in result)
        assert paths == ["gamedata/a.txt", "gamedata/sub/b.txt"]


class TestFileMappingWithDestination:
    def test_file_with_destination(self):
        plugin = _make_plugin(
            files=[
                FileMapping(
                    source="src/file.dll", destination="bin/file.dll", priority=0, is_folder=False
                )
            ]
        )
        step = FomodStep(
            name="S",
            groups=[FomodGroup(name="G", type=GroupType.SELECT_ANY, plugins=[plugin])],
        )
        config = _make_config(steps=[step])
        entries = _make_entries(["src/file.dll"])
        selections = {0: {0: [0]}}
        result = compute_file_list(config, selections, entries, "")
        assert result[0].game_relative_path == "bin/file.dll"

    def test_file_without_destination_uses_filename(self):
        plugin = _make_plugin(
            files=[FileMapping(source="src/file.dll", destination="", priority=0, is_folder=False)]
        )
        step = FomodStep(
            name="S",
            groups=[FomodGroup(name="G", type=GroupType.SELECT_ANY, plugins=[plugin])],
        )
        config = _make_config(steps=[step])
        entries = _make_entries(["src/file.dll"])
        selections = {0: {0: [0]}}
        result = compute_file_list(config, selections, entries, "")
        assert result[0].game_relative_path == "file.dll"


class TestPriorityResolution:
    def test_higher_priority_wins(self):
        p1 = _make_plugin(
            name="Low",
            files=[FileMapping(source="a.txt", destination="out.txt", priority=0, is_folder=False)],
        )
        p2 = _make_plugin(
            name="High",
            files=[FileMapping(source="b.txt", destination="out.txt", priority=5, is_folder=False)],
        )
        step = FomodStep(
            name="S",
            groups=[FomodGroup(name="G", type=GroupType.SELECT_ANY, plugins=[p1, p2])],
        )
        config = _make_config(steps=[step])
        entries = _make_entries(["a.txt", "b.txt"])
        selections = {0: {0: [0, 1]}}
        result = compute_file_list(config, selections, entries, "")
        assert len(result) == 1
        assert result[0].archive_path == "b.txt"

    def test_equal_priority_later_wins(self):
        p1 = _make_plugin(
            name="First",
            files=[FileMapping(source="a.txt", destination="out.txt", priority=0, is_folder=False)],
        )
        p2 = _make_plugin(
            name="Second",
            files=[FileMapping(source="b.txt", destination="out.txt", priority=0, is_folder=False)],
        )
        step = FomodStep(
            name="S",
            groups=[FomodGroup(name="G", type=GroupType.SELECT_ANY, plugins=[p1, p2])],
        )
        config = _make_config(steps=[step])
        entries = _make_entries(["a.txt", "b.txt"])
        selections = {0: {0: [0, 1]}}
        result = compute_file_list(config, selections, entries, "")
        assert len(result) == 1
        assert result[0].archive_path == "b.txt"


class TestEvaluateDependency:
    def test_and_all_true(self):
        dep = CompositeDependency(
            operator=DependencyOperator.AND,
            flag_conditions=[
                FlagCondition(name="a", value="1"),
                FlagCondition(name="b", value="2"),
            ],
        )
        assert evaluate_dependency(dep, {"a": "1", "b": "2"}) is True

    def test_and_one_false(self):
        dep = CompositeDependency(
            operator=DependencyOperator.AND,
            flag_conditions=[
                FlagCondition(name="a", value="1"),
                FlagCondition(name="b", value="2"),
            ],
        )
        assert evaluate_dependency(dep, {"a": "1", "b": "X"}) is False

    def test_or_one_true(self):
        dep = CompositeDependency(
            operator=DependencyOperator.OR,
            flag_conditions=[
                FlagCondition(name="a", value="1"),
                FlagCondition(name="b", value="2"),
            ],
        )
        assert evaluate_dependency(dep, {"a": "1", "b": "X"}) is True

    def test_or_none_true(self):
        dep = CompositeDependency(
            operator=DependencyOperator.OR,
            flag_conditions=[FlagCondition(name="a", value="1")],
        )
        assert evaluate_dependency(dep, {"a": "X"}) is False

    def test_nested_dependency(self):
        inner = CompositeDependency(
            operator=DependencyOperator.AND,
            flag_conditions=[FlagCondition(name="x", value="1")],
        )
        outer = CompositeDependency(
            operator=DependencyOperator.AND,
            flag_conditions=[FlagCondition(name="y", value="2")],
            nested=[inner],
        )
        assert evaluate_dependency(outer, {"x": "1", "y": "2"}) is True
        assert evaluate_dependency(outer, {"x": "1", "y": "X"}) is False

    def test_empty_dependency_is_true(self):
        dep = CompositeDependency(operator=DependencyOperator.AND)
        assert evaluate_dependency(dep, {}) is True


class TestStepVisibility:
    def test_visible_when_no_condition(self):
        assert is_step_visible(None, {}) is True

    def test_visible_when_condition_met(self):
        dep = CompositeDependency(
            operator=DependencyOperator.AND,
            flag_conditions=[FlagCondition(name="show", value="yes")],
        )
        assert is_step_visible(dep, {"show": "yes"}) is True

    def test_hidden_when_condition_not_met(self):
        dep = CompositeDependency(
            operator=DependencyOperator.AND,
            flag_conditions=[FlagCondition(name="show", value="yes")],
        )
        assert is_step_visible(dep, {}) is False


class TestConditionalFileInstalls:
    def test_conditional_pattern_applied(self):
        from rippermod_manager.services.fomod_config_parser import FlagSetter

        plugin = _make_plugin(
            name="Variant",
            condition_flags=[FlagSetter(name="variant", value="A")],
        )
        step = FomodStep(
            name="S",
            groups=[FomodGroup(name="G", type=GroupType.SELECT_ANY, plugins=[plugin])],
        )
        pattern = ConditionalInstallPattern(
            dependency=CompositeDependency(
                operator=DependencyOperator.AND,
                flag_conditions=[FlagCondition(name="variant", value="A")],
            ),
            files=[
                FileMapping(
                    source="special.dll", destination="bin/special.dll", priority=0, is_folder=False
                )
            ],
        )
        config = _make_config(steps=[step], conditional=[pattern])
        entries = _make_entries(["special.dll"])
        selections = {0: {0: [0]}}
        result = compute_file_list(config, selections, entries, "")
        assert any(r.game_relative_path == "bin/special.dll" for r in result)


class TestFomodPrefix:
    def test_prefix_strips_from_entries(self):
        plugin = _make_plugin(
            files=[
                FileMapping(
                    source="data.txt", destination="mods/data.txt", priority=0, is_folder=False
                )
            ]
        )
        step = FomodStep(
            name="S",
            groups=[FomodGroup(name="G", type=GroupType.SELECT_ANY, plugins=[plugin])],
        )
        config = _make_config(steps=[step])
        entries = _make_entries(["WrapperFolder/data.txt"])
        selections = {0: {0: [0]}}
        result = compute_file_list(config, selections, entries, "WrapperFolder")
        assert len(result) == 1
        assert result[0].archive_path == "WrapperFolder/data.txt"


class TestInstallFomod:
    @pytest.fixture
    def setup(self, tmp_path, engine):
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        staging = game_dir / "downloaded_mods"
        staging.mkdir()

        with Session(engine) as s:
            g = Game(name="FomodGame", domain_name="fg", install_path=str(game_dir))
            s.add(g)
            s.flush()
            s.add(GameModPath(game_id=g.id, relative_path="mods"))
            s.commit()
            s.refresh(g)
            game = g

        return game, game_dir, staging

    def test_happy_path(self, setup, engine):
        """FOMOD install writes to staging; game-dir path is accessible via hardlink."""
        game, game_dir, staging = setup
        archive = staging / "TestFomod.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("fomod/ModuleConfig.xml", "<config />")
            zf.writestr("data.txt", "content")

        resolved = [
            ResolvedFile(archive_path="data.txt", game_relative_path="mods/data.txt", priority=0),
        ]

        with Session(engine) as s:
            result = install_fomod(game, archive, s, resolved, "TestFomod")

        assert result.files_extracted == 1
        assert result.name == "TestFomod"
        # File is accessible at the canonical game-dir path (via hardlink from deploy)
        assert (game_dir / "mods" / "data.txt").read_text() == "content"
        # staging_dir is reported in result
        assert result.installed_mod_name_safe == "TestFomod"

    def test_staging_and_hardlink(self, setup, engine):
        """FOMOD-installed files live in staging; game-dir file is a hardlink to staging copy."""
        game, game_dir, staging = setup
        archive = staging / "VFSFomod.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("plugin.txt", "vfs-content")

        resolved = [
            ResolvedFile(
                archive_path="plugin.txt",
                game_relative_path="archive/pc/mod/plugin.txt",
                priority=0,
            ),
        ]

        with Session(engine) as s:
            result = install_fomod(game, archive, s, resolved, "VFSFomod")

        assert result.files_extracted == 1

        with Session(engine) as s:
            installed = s.exec(select(InstalledMod).where(InstalledMod.name == "VFSFomod")).one()
            assert installed.staging_dir == "VFSFomod"
            assert installed.deployed is True

            _ = installed.files
            assert len(installed.files) == 1
            f = installed.files[0]
            assert f.source_path == "archive/pc/mod/plugin.txt"
            assert f.link_kind == "hardlink"

        src = game_dir / "downloaded_mods" / "VFSFomod" / "archive" / "pc" / "mod" / "plugin.txt"
        dst = game_dir / "archive" / "pc" / "mod" / "plugin.txt"
        assert src.exists(), "Staging copy must exist"
        assert dst.exists(), "Game-dir hardlink must exist"
        assert os.path.samefile(src, dst), "src and dst must be the same inode (hardlink)"

    def test_path_traversal_blocked(self, setup, engine):
        game, _game_dir, staging = setup
        archive = staging / "Evil.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("evil.txt", "bad")

        resolved = [
            ResolvedFile(
                archive_path="evil.txt",
                game_relative_path="../../../etc/evil.txt",
                priority=0,
            ),
        ]

        with Session(engine) as s:
            result = install_fomod(game, archive, s, resolved, "Evil")

        assert result.files_extracted == 0
        assert result.files_skipped == 1

    def test_duplicate_name_raises(self, setup, engine):
        game, _, staging = setup
        archive = staging / "Dup.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("x.txt", "x")

        with Session(engine) as s:
            s.add(InstalledMod(game_id=game.id, name="Dup", source_archive="other.zip"))
            s.commit()

        with Session(engine) as s, pytest.raises(ValueError, match="already installed"):
            install_fomod(game, archive, s, [], "Dup")

    def test_auto_deploy_false_skips_deploy_and_modlist(self, setup, engine):
        """``auto_deploy=False`` must NOT call deploy() / write_modlist().

        This is the contract Collections install (#222 PR D) relies on so
        that batch installs run one deploy at the end of the run instead of
        N per-mod deploys.
        """
        from unittest.mock import patch

        game, _game_dir, staging = setup
        archive = staging / "Deferred.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("plugin.txt", "x")
        resolved = [
            ResolvedFile(
                archive_path="plugin.txt",
                game_relative_path="mods/plugin.txt",
                priority=0,
            )
        ]

        with (
            patch("rippermod_manager.services.vfs.deploy_service.deploy") as mdeploy,
            patch("rippermod_manager.services.modlist_service.write_modlist") as mmodlist,
            Session(engine) as s,
        ):
            install_fomod(game, archive, s, resolved, "Deferred", auto_deploy=False)

        mdeploy.assert_not_called()
        mmodlist.assert_not_called()

        with Session(engine) as s:
            installed = s.exec(select(InstalledMod).where(InstalledMod.name == "Deferred")).one()
            # Row is created (staging populated) but deploy hasn't run yet, so
            # ``deployed`` stays at its default False.
            assert installed.staging_dir == "Deferred"
            assert installed.deployed is False

"""Tests for redscript static analysis conflict detection."""

from pathlib import Path

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.schemas.redscript import RedscriptAnnotationType
from rippermod_manager.services.redscript_analysis import (
    _build_conflict_key,
    _normalize_param_types,
    check_redscript_conflicts,
    parse_reds_content,
)

# ---------------------------------------------------------------------------
# Fixture strings
# ---------------------------------------------------------------------------

REPLACE_METHOD_SIMPLE = """\
@replaceMethod(VehicleComponent)
protected func OnVehicleSpeedChange(speed: Float) -> Void {
    // modded logic
}
"""

REPLACE_GLOBAL_SIMPLE = """\
@replaceGlobal()
public func CalculateDamage(target: ref<GameObject>, weapon: ref<WeaponObject>) -> Float {
    return 999.0;
}
"""

WRAP_METHOD_SIMPLE = """\
@wrapMethod(PlayerPuppet)
protected func OnGameAttached() -> Void {
    wrappedMethod();
}
"""

MULTI_LINE_SIGNATURE = """\
@replaceMethod(InventoryManager)
public func AddItem(
    itemID: TweakDBID,
    quantity: Int32,
    addToEquipped: Bool
) -> Bool {
    // modded
}
"""

MULTIPLE_ANNOTATIONS = """\
@replaceMethod(VehicleComponent)
protected func OnVehicleSpeedChange(speed: Float) -> Void {
    // first replace
}

@wrapMethod(PlayerPuppet)
protected func OnGameAttached() -> Void {
    wrappedMethod();
}

@replaceGlobal()
public func CalculateDamage(target: ref<GameObject>, weapon: ref<WeaponObject>) -> Float {
    return 42.0;
}
"""

NO_RETURN_TYPE = """\
@replaceMethod(SomeClass)
public func DoSomething(val: Int32) {
    // no explicit return type
}
"""

STATIC_METHOD = """\
@replaceMethod(MathUtils)
public static func Clamp(value: Float, min: Float, max: Float) -> Float {
    return value;
}
"""

CB_FUNC = """\
@wrapMethod(PlayerPuppet)
protected cb func OnStatusEffectApplied(evt: ref<ApplyStatusEffectEvent>) -> Bool {
    return wrappedMethod(evt);
}
"""

EMPTY_FILE = ""

NO_ANNOTATIONS = """\
public class MyHelper {
    public func DoStuff() -> Void {
        // no annotations
    }
}
"""

COMMENTED_ANNOTATION = """\
// @replaceMethod(VehicleComponent)
// protected func OnVehicleSpeedChange(speed: Float) -> Void {
// }
"""

NO_PARAMS = """\
@replaceMethod(SomeClass)
public func Reset() -> Void {
    // no params
}
"""


# ---------------------------------------------------------------------------
# Unit tests: _normalize_param_types
# ---------------------------------------------------------------------------


class TestNormalizeParamTypes:
    def test_simple_params(self):
        assert _normalize_param_types("speed: Float") == ["Float"]

    def test_multiple_params(self):
        result = _normalize_param_types("target: ref<GameObject>, weapon: ref<WeaponObject>")
        assert result == ["ref<GameObject>", "ref<WeaponObject>"]

    def test_empty_string(self):
        assert _normalize_param_types("") == []

    def test_whitespace_only(self):
        assert _normalize_param_types("   ") == []

    def test_complex_generic_type(self):
        result = _normalize_param_types("items: array<ref<ItemData>>")
        assert result == ["array<ref<ItemData>>"]


# ---------------------------------------------------------------------------
# Unit tests: _build_conflict_key
# ---------------------------------------------------------------------------


class TestBuildConflictKey:
    def test_replace_method(self):
        key = _build_conflict_key(
            "VehicleComponent",
            "OnVehicleSpeedChange",
            ["Float"],
            "Void",
        )
        assert key == "VehicleComponent::OnVehicleSpeedChange(Float) -> Void"

    def test_replace_global(self):
        key = _build_conflict_key(
            None,
            "CalculateDamage",
            ["ref<GameObject>", "ref<WeaponObject>"],
            "Float",
        )
        assert key == "global::CalculateDamage(ref<GameObject>, ref<WeaponObject>) -> Float"

    def test_no_params(self):
        key = _build_conflict_key("Foo", "Bar", [], "Void")
        assert key == "Foo::Bar() -> Void"


# ---------------------------------------------------------------------------
# Unit tests: parse_reds_content
# ---------------------------------------------------------------------------


class TestParseRedsContent:
    def test_replace_method_simple(self):
        results = parse_reds_content(REPLACE_METHOD_SIMPLE)
        assert len(results) == 1
        target, line = results[0]
        assert target.annotation_type == RedscriptAnnotationType.REPLACE_METHOD
        assert target.class_name == "VehicleComponent"
        assert target.func_name == "OnVehicleSpeedChange"
        assert target.param_types == ["Float"]
        assert target.return_type == "Void"
        assert line == 1

    def test_replace_global_simple(self):
        results = parse_reds_content(REPLACE_GLOBAL_SIMPLE)
        assert len(results) == 1
        target, _ = results[0]
        assert target.annotation_type == RedscriptAnnotationType.REPLACE_GLOBAL
        assert target.class_name is None
        assert target.func_name == "CalculateDamage"
        assert target.param_types == ["ref<GameObject>", "ref<WeaponObject>"]
        assert target.return_type == "Float"

    def test_wrap_method_simple(self):
        results = parse_reds_content(WRAP_METHOD_SIMPLE)
        assert len(results) == 1
        target, _ = results[0]
        assert target.annotation_type == RedscriptAnnotationType.WRAP_METHOD
        assert target.class_name == "PlayerPuppet"
        assert target.func_name == "OnGameAttached"

    def test_multi_line_signature(self):
        results = parse_reds_content(MULTI_LINE_SIGNATURE)
        assert len(results) == 1
        target, _ = results[0]
        assert target.func_name == "AddItem"
        assert target.param_types == ["TweakDBID", "Int32", "Bool"]
        assert target.return_type == "Bool"

    def test_multiple_annotations(self):
        results = parse_reds_content(MULTIPLE_ANNOTATIONS)
        assert len(results) == 3
        types = {r[0].annotation_type for r in results}
        assert types == {
            RedscriptAnnotationType.REPLACE_METHOD,
            RedscriptAnnotationType.WRAP_METHOD,
            RedscriptAnnotationType.REPLACE_GLOBAL,
        }

    def test_no_return_type_defaults_to_void(self):
        results = parse_reds_content(NO_RETURN_TYPE)
        assert len(results) == 1
        assert results[0][0].return_type == "Void"

    def test_static_method(self):
        results = parse_reds_content(STATIC_METHOD)
        assert len(results) == 1
        target, _ = results[0]
        assert target.func_name == "Clamp"
        assert target.param_types == ["Float", "Float", "Float"]

    def test_cb_func(self):
        results = parse_reds_content(CB_FUNC)
        assert len(results) == 1
        target, _ = results[0]
        assert target.func_name == "OnStatusEffectApplied"
        assert target.param_types == ["ref<ApplyStatusEffectEvent>"]
        assert target.return_type == "Bool"

    def test_empty_file(self):
        assert parse_reds_content(EMPTY_FILE) == []

    def test_no_annotations(self):
        assert parse_reds_content(NO_ANNOTATIONS) == []

    def test_commented_annotation_ignored(self):
        results = parse_reds_content(COMMENTED_ANNOTATION)
        assert len(results) == 0

    def test_no_params(self):
        results = parse_reds_content(NO_PARAMS)
        assert len(results) == 1
        assert results[0][0].param_types == []
        assert results[0][0].conflict_key == "SomeClass::Reset() -> Void"

    def test_conflict_key_format(self):
        results = parse_reds_content(REPLACE_METHOD_SIMPLE)
        assert results[0][0].conflict_key == (
            "VehicleComponent::OnVehicleSpeedChange(Float) -> Void"
        )


# ---------------------------------------------------------------------------
# Integration tests: check_redscript_conflicts
# ---------------------------------------------------------------------------


class TestCheckRedscriptConflicts:
    def _setup(self, session, tmp_path) -> Game:
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        (game_dir / "r6" / "scripts").mkdir(parents=True)
        g = Game(
            name="RedscriptGame",
            domain_name="cyberpunk2077",
            install_path=str(game_dir),
        )
        session.add(g)
        session.flush()
        session.add(GameModPath(game_id=g.id, relative_path="r6/scripts"))
        session.commit()
        session.refresh(g)
        return g

    def _install_mod_with_reds(
        self,
        session,
        game: Game,
        mod_name: str,
        files: dict[str, str],
    ) -> InstalledMod:
        game_dir = Path(game.install_path)
        mod = InstalledMod(game_id=game.id, name=mod_name, source_archive=f"{mod_name}.zip")
        session.add(mod)
        session.flush()
        for rel_path, content in files.items():
            abs_path = game_dir / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(content, encoding="utf-8")
            session.add(InstalledModFile(installed_mod_id=mod.id, relative_path=rel_path))
        session.commit()
        session.refresh(mod)
        _ = mod.files
        return mod

    def test_no_conflicts_when_no_mods(self, session, tmp_path):
        game = self._setup(session, tmp_path)
        result = check_redscript_conflicts(game, session)
        assert result.total_reds_files == 0
        assert result.conflicts == []
        assert result.wraps == []

    def test_no_conflict_single_mod(self, session, tmp_path):
        game = self._setup(session, tmp_path)
        self._install_mod_with_reds(
            session,
            game,
            "ModA",
            {"r6/scripts/ModA/main.reds": REPLACE_METHOD_SIMPLE},
        )
        result = check_redscript_conflicts(game, session)
        assert result.total_reds_files == 1
        assert result.total_targets_found == 1
        assert result.conflicts == []

    def test_conflict_two_mods_replace_same_target(self, session, tmp_path):
        game = self._setup(session, tmp_path)
        self._install_mod_with_reds(
            session,
            game,
            "ModA",
            {"r6/scripts/ModA/main.reds": REPLACE_METHOD_SIMPLE},
        )
        self._install_mod_with_reds(
            session,
            game,
            "ModB",
            {"r6/scripts/ModB/main.reds": REPLACE_METHOD_SIMPLE},
        )
        result = check_redscript_conflicts(game, session)
        assert len(result.conflicts) == 1
        assert len(result.conflicts[0].mods) == 2
        mod_names = {m.installed_mod_name for m in result.conflicts[0].mods}
        assert mod_names == {"ModA", "ModB"}

    def test_wrap_method_is_not_a_conflict(self, session, tmp_path):
        game = self._setup(session, tmp_path)
        self._install_mod_with_reds(
            session,
            game,
            "ModA",
            {"r6/scripts/ModA/main.reds": WRAP_METHOD_SIMPLE},
        )
        self._install_mod_with_reds(
            session,
            game,
            "ModB",
            {"r6/scripts/ModB/main.reds": WRAP_METHOD_SIMPLE},
        )
        result = check_redscript_conflicts(game, session)
        assert result.conflicts == []
        assert len(result.wraps) == 1
        assert len(result.wraps[0].mods) == 2

    def test_replace_vs_wrap_same_target_not_conflict(self, session, tmp_path):
        game = self._setup(session, tmp_path)
        replace_content = """\
@replaceMethod(PlayerPuppet)
protected func OnGameAttached() -> Void {
    // modded
}
"""
        self._install_mod_with_reds(
            session,
            game,
            "ModA",
            {"r6/scripts/ModA/main.reds": replace_content},
        )
        self._install_mod_with_reds(
            session,
            game,
            "ModB",
            {"r6/scripts/ModB/main.reds": WRAP_METHOD_SIMPLE},
        )
        result = check_redscript_conflicts(game, session)
        assert result.conflicts == []
        assert len(result.wraps) == 1

    def test_disabled_mods_excluded(self, session, tmp_path):
        game = self._setup(session, tmp_path)
        mod = self._install_mod_with_reds(
            session,
            game,
            "DisabledMod",
            {"r6/scripts/Disabled/main.reds": REPLACE_METHOD_SIMPLE},
        )
        mod.disabled = True
        session.add(mod)
        session.commit()
        self._install_mod_with_reds(
            session,
            game,
            "EnabledMod",
            {"r6/scripts/Enabled/main.reds": REPLACE_METHOD_SIMPLE},
        )
        result = check_redscript_conflicts(game, session)
        assert result.conflicts == []

    def test_global_replace_conflict(self, session, tmp_path):
        game = self._setup(session, tmp_path)
        self._install_mod_with_reds(
            session,
            game,
            "ModA",
            {"r6/scripts/ModA/damage.reds": REPLACE_GLOBAL_SIMPLE},
        )
        self._install_mod_with_reds(
            session,
            game,
            "ModB",
            {"r6/scripts/ModB/damage.reds": REPLACE_GLOBAL_SIMPLE},
        )
        result = check_redscript_conflicts(game, session)
        assert len(result.conflicts) == 1
        assert result.conflicts[0].target_class is None
        assert result.conflicts[0].target_func == "CalculateDamage"

    def test_different_targets_no_conflict(self, session, tmp_path):
        game = self._setup(session, tmp_path)
        mod_a_content = """\
@replaceMethod(ClassA)
public func MethodA(x: Int32) -> Void {
}
"""
        mod_b_content = """\
@replaceMethod(ClassB)
public func MethodB(y: Float) -> Void {
}
"""
        self._install_mod_with_reds(
            session,
            game,
            "ModA",
            {"r6/scripts/ModA/main.reds": mod_a_content},
        )
        self._install_mod_with_reds(
            session,
            game,
            "ModB",
            {"r6/scripts/ModB/main.reds": mod_b_content},
        )
        result = check_redscript_conflicts(game, session)
        assert result.conflicts == []

    def test_same_mod_multiple_replaces_no_conflict(self, session, tmp_path):
        game = self._setup(session, tmp_path)
        content = REPLACE_METHOD_SIMPLE + "\n" + REPLACE_METHOD_SIMPLE
        self._install_mod_with_reds(
            session,
            game,
            "ModA",
            {"r6/scripts/ModA/main.reds": content},
        )
        result = check_redscript_conflicts(game, session)
        assert result.conflicts == []

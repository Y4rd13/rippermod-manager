"""Tests for the FOMOD choice resolver (#222 PR D)."""

from __future__ import annotations

from dataclasses import dataclass, field

from rippermod_manager.services.fomod_choice_resolver import resolve_choices


@dataclass
class _Plugin:
    name: str


@dataclass
class _Group:
    name: str
    plugins: list[_Plugin] = field(default_factory=list)


@dataclass
class _Step:
    name: str
    groups: list[_Group] = field(default_factory=list)


@dataclass
class _Config:
    steps: list[_Step] = field(default_factory=list)


def _make_config() -> _Config:
    return _Config(
        steps=[
            _Step(
                name="Main",
                groups=[
                    _Group(
                        name="Mode",
                        plugins=[_Plugin("Light"), _Plugin("Dark"), _Plugin("Auto")],
                    ),
                    _Group(name="Extras", plugins=[_Plugin("Pack A"), _Plugin("Pack B")]),
                ],
            ),
            _Step(
                name="Tweaks",
                groups=[_Group(name="Style", plugins=[_Plugin("Classic"), _Plugin("Modern")])],
            ),
        ]
    )


class TestResolveChoices:
    def test_empty_choices_returns_empty_selections(self):
        cfg = _make_config()
        assert resolve_choices(cfg, None) == {}
        assert resolve_choices(cfg, {}) == {}

    def test_happy_path_resolves_to_indices(self):
        cfg = _make_config()
        choices = {
            "Main": {"Mode": ["Dark"], "Extras": ["Pack A", "Pack B"]},
            "Tweaks": {"Style": ["Modern"]},
        }
        result = resolve_choices(cfg, choices)
        assert result == {0: {0: [1], 1: [0, 1]}, 1: {0: [1]}}

    def test_unknown_step_silently_dropped(self):
        cfg = _make_config()
        choices = {
            "Main": {"Mode": ["Light"]},
            "DoesNotExist": {"Anything": ["X"]},
        }
        result = resolve_choices(cfg, choices)
        assert result == {0: {0: [0]}}  # only Main/Mode/Light survives

    def test_unknown_group_silently_dropped(self):
        cfg = _make_config()
        choices = {"Main": {"Mode": ["Light"], "Phantom": ["Y"]}}
        result = resolve_choices(cfg, choices)
        assert result == {0: {0: [0]}}

    def test_unknown_plugin_silently_dropped(self):
        cfg = _make_config()
        choices = {"Main": {"Mode": ["Dark", "GhostPlugin"]}}
        result = resolve_choices(cfg, choices)
        assert result == {0: {0: [1]}}

    def test_all_plugins_in_group_unknown_drops_whole_group(self):
        cfg = _make_config()
        choices = {"Main": {"Mode": ["Ghost1", "Ghost2"]}}
        result = resolve_choices(cfg, choices)
        # Group ends up with zero selections, so it's omitted entirely.
        assert result == {}

    def test_matching_is_case_sensitive(self):
        cfg = _make_config()
        # "main" (lowercase) must NOT match "Main".
        result = resolve_choices(cfg, {"main": {"Mode": ["Light"]}})
        assert result == {}

    def test_duplicate_step_names_first_wins(self):
        """If a FOMOD has two steps with the same name (rare but legal),
        only the first index gets used -- mirrors Vortex's behavior."""
        cfg = _Config(
            steps=[
                _Step(name="Pick", groups=[_Group(name="G", plugins=[_Plugin("A")])]),
                _Step(name="Pick", groups=[_Group(name="G", plugins=[_Plugin("B")])]),
            ]
        )
        result = resolve_choices(cfg, {"Pick": {"G": ["A"]}})
        assert result == {0: {0: [0]}}

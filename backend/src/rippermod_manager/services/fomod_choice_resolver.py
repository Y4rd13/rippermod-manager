"""Translate Vortex-style FOMOD choice maps into our index-based selections.

A collection author records the plugins they picked when they assembled the
collection. Vortex (and our manifest schema) stores those choices as
*names*, not numeric indices, because:

  - Plugin order inside a FOMOD installer is mostly cosmetic from the
    author's perspective; they pick by display name in the wizard.
  - Mod authors sometimes reorder/insert steps between minor revisions.
    Name-based addressing is the only thing that survives that.

This module bridges the gap. Given:

  - a parsed :class:`FomodConfig` (from
    :func:`services.fomod_config_parser.parse_fomod_config`)
  - a name-keyed :class:`FomodChoiceMap`
    (``{step_name: {group_name: [plugin_name, ...]}}``)

…it returns the index-keyed ``selections`` dict the existing
:func:`services.fomod_install_service.compute_file_list` already understands:

  ``{step_index: {group_index: [plugin_index, ...]}}``

Unknown step / group / plugin names are logged and skipped, never raised.
The orchestrator (#222 PR C) prefers a partial install over crashing the
whole batch when a collection drifts from the mod's current FOMOD layout.

Strict name matching only (case-sensitive). FOMOD plugin names are
display-quality and stable; doing case-insensitive matching here would
silently mask real mismatches.
"""

from __future__ import annotations

import logging

from rippermod_manager.services.fomod_config_parser import FomodConfig

logger = logging.getLogger(__name__)

#: ``{step_name: {group_name: [plugin_name, ...]}}`` — what the collection
#: author recorded. Empty dict = pick required-only (no optional plugins).
type FomodChoiceMap = dict[str, dict[str, list[str]]]

#: ``{step_index: {group_index: [plugin_index, ...]}}`` — what
#: ``compute_file_list`` expects.
type FomodSelections = dict[int, dict[int, list[int]]]


def resolve_choices(config: FomodConfig, choices: FomodChoiceMap | None) -> FomodSelections:
    """Map name-based choices onto the FOMOD's current index structure.

    Pass ``None`` (or an empty dict) to install only the FOMOD's required
    files with zero optional plugins selected — equivalent to the user
    clicking through every step without ticking anything.
    """
    if not choices:
        return {}

    # Index step + group names for O(1) lookup. Steps are deduplicated by
    # name on a first-wins basis: if a FOMOD has two steps with the same
    # name (rare but legal), only the first matches — matches Vortex's
    # behavior.
    step_idx_by_name: dict[str, int] = {}
    for idx, step in enumerate(config.steps):
        step_idx_by_name.setdefault(step.name, idx)

    selections: FomodSelections = {}
    for step_name, groups_by_name in choices.items():
        step_idx = step_idx_by_name.get(step_name)
        if step_idx is None:
            logger.info("FOMOD choice resolver: step %r not in current config, skipping", step_name)
            continue
        step = config.steps[step_idx]

        group_idx_by_name: dict[str, int] = {}
        for gidx, group in enumerate(step.groups):
            group_idx_by_name.setdefault(group.name, gidx)

        group_selections: dict[int, list[int]] = {}
        for group_name, plugin_names in groups_by_name.items():
            group_idx = group_idx_by_name.get(group_name)
            if group_idx is None:
                logger.info(
                    "FOMOD choice resolver: group %r missing in step %r, skipping",
                    group_name,
                    step_name,
                )
                continue
            group = step.groups[group_idx]

            plugin_idx_by_name: dict[str, int] = {}
            for pidx, plugin in enumerate(group.plugins):
                plugin_idx_by_name.setdefault(plugin.name, pidx)

            resolved_indices: list[int] = []
            for plugin_name in plugin_names:
                plugin_idx = plugin_idx_by_name.get(plugin_name)
                if plugin_idx is None:
                    logger.info(
                        "FOMOD choice resolver: plugin %r missing in %r/%r, skipping",
                        plugin_name,
                        step_name,
                        group_name,
                    )
                    continue
                resolved_indices.append(plugin_idx)

            if resolved_indices:
                group_selections[group_idx] = resolved_indices

        if group_selections:
            selections[step_idx] = group_selections

    return selections

"""Build dependency pairs from NexusModRequirement for installed mods.

Maps Nexus requirements to installed mod IDs so the conflict detectors can
lower severity for conflicts between a mod and its dependency.
"""

from __future__ import annotations

from sqlmodel import Session, select

from rippermod_manager.models.install import InstalledMod
from rippermod_manager.models.nexus import NexusModRequirement

DependencyPairs = set[tuple[int, int]]


def build_dependency_pairs(
    installed_mods: list[InstalledMod],
    session: Session,
) -> DependencyPairs:
    """Return normalised (min, max) pairs of installed mod IDs linked by a Nexus requirement."""
    # Map nexus_mod_id → installed_mod.id (skip mods without nexus_mod_id)
    nexus_to_installed: dict[int, int] = {}
    for mod in installed_mods:
        if mod.nexus_mod_id is not None and mod.id is not None:
            nexus_to_installed[mod.nexus_mod_id] = mod.id

    if len(nexus_to_installed) < 2:
        return set()

    installed_nexus_ids = set(nexus_to_installed.keys())

    # Query requirements where both sides are installed
    reqs = session.exec(
        select(NexusModRequirement).where(
            NexusModRequirement.nexus_mod_id.in_(installed_nexus_ids),  # type: ignore[union-attr]
            NexusModRequirement.required_mod_id.in_(installed_nexus_ids),  # type: ignore[union-attr]
        )
    ).all()

    pairs: DependencyPairs = set()
    for req in reqs:
        a = nexus_to_installed.get(req.nexus_mod_id)
        b = nexus_to_installed.get(req.required_mod_id)  # type: ignore[arg-type]
        if a is not None and b is not None and a != b:
            pairs.add((min(a, b), max(a, b)))

    return pairs

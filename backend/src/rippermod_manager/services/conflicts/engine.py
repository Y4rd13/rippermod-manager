"""ConflictEngine: orchestrates all registered conflict detectors for a game."""

from __future__ import annotations

import logging
import time

from sqlmodel import Session, select

from rippermod_manager.models.conflict import ConflictEvidence, ConflictKind
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.services.conflicts.dependency_graph import build_dependency_pairs
from rippermod_manager.services.conflicts.detectors import get_all_detectors

logger = logging.getLogger(__name__)


class ConflictEngine:
    """Runs all registered conflict detectors and persists results.

    Each call to ``run()`` is a full reindex: existing evidence for the game
    is deleted and replaced with fresh results from all detectors.
    """

    def run(self, game: Game, session: Session) -> list[ConflictEvidence]:
        """Execute all detectors and persist the results."""
        start = time.perf_counter()

        installed_mods = list(
            session.exec(
                select(InstalledMod)
                .where(InstalledMod.game_id == game.id)
                .order_by(InstalledMod.installed_at)
            ).all()
        )
        for mod in installed_mods:
            _ = mod.files  # eager-load within session

        dependency_pairs = build_dependency_pairs(installed_mods, session)

        # Every detector runs before anything is written: a DELETE flushed after
        # the first one would hold SQLite's write lock through all the others,
        # and the reindex runs after each toggle, install and scan.
        detected: list[tuple[ConflictKind, list[ConflictEvidence]]] = []
        for detector in get_all_detectors():
            try:
                evidence = detector.detect(
                    game, installed_mods, session, dependency_pairs=dependency_pairs
                )
            except Exception:
                logger.exception("Detector %s failed for game %s", detector.kind, game.name)
                continue
            detected.append((detector.kind, evidence))
            logger.info(
                "Detector %s found %d conflicts for game %s",
                detector.kind,
                len(evidence),
                game.name,
            )

        # One short write: replace the evidence of each kind whose detector ran.
        # A failed detector keeps its old evidence.
        all_evidence: list[ConflictEvidence] = []
        for kind, evidence in detected:
            old = session.exec(
                select(ConflictEvidence).where(
                    ConflictEvidence.game_id == game.id,
                    ConflictEvidence.kind == kind,
                )
            ).all()
            for row in old:
                session.delete(row)
            all_evidence.extend(evidence)
        session.flush()
        for ev in all_evidence:
            session.add(ev)
        session.commit()

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "Conflict reindex for %s: %d conflicts in %dms",
            game.name,
            len(all_evidence),
            elapsed_ms,
        )
        return all_evidence


def reindex_game(game: Game, session: Session) -> list[ConflictEvidence]:
    """Refresh the archive index, then run every detector for *game* (full reindex)."""
    from rippermod_manager.services.archive_index_service import index_game_archives

    index_game_archives(game, session, force_reindex=False)
    return ConflictEngine().run(game, session)

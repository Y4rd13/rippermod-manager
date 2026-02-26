"""Conflicts core — post-install conflict analysis engine."""

from rippermod_manager.services.conflicts.detectors import get_all_detectors
from rippermod_manager.services.conflicts.engine import ConflictEngine

__all__ = ["ConflictEngine", "get_all_detectors"]

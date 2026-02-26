"""Static analysis of redscript (.reds) files for conflict detection.

Parses @replaceMethod, @replaceGlobal, and @wrapMethod annotations from
installed .reds files and detects conflicts where multiple mods replace
the same target.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.schemas.redscript import (
    RedscriptAnnotationType,
    RedscriptConflict,
    RedscriptConflictResult,
    RedscriptModEntry,
    RedscriptTarget,
    RedscriptWrapInfo,
)

logger = logging.getLogger(__name__)

_ANNOTATION_RE = re.compile(
    r"^\s*@(replaceMethod|replaceGlobal|wrapMethod)\(\s*(\w*)\s*\)",
    re.MULTILINE,
)

_FUNC_SIG_RE = re.compile(
    r"(?:public|protected|private)?\s*"
    r"(?:static\s+)?"
    r"(?:cb\s+)?"
    r"func\s+"
    r"(\w+)"
    r"\s*\(([^)]*)\)"  # NOTE: won't handle types with nested parens like Callback(Bool)
    r"(?:\s*->\s*(\S[^{;]*))?",
)

_ANN_TYPE_MAP = {
    "replaceMethod": RedscriptAnnotationType.REPLACE_METHOD,
    "replaceGlobal": RedscriptAnnotationType.REPLACE_GLOBAL,
    "wrapMethod": RedscriptAnnotationType.WRAP_METHOD,
}


def _normalize_param_types(param_str: str) -> list[str]:
    """Extract only types from a parameter list, discarding names."""
    if not param_str.strip():
        return []
    types: list[str] = []
    for param in param_str.split(","):
        param = param.strip()
        if not param:
            continue
        if ":" in param:
            type_part = param.split(":", 1)[1].strip()
            types.append(type_part)
        else:
            types.append(param)
    return types


def _build_conflict_key(
    class_name: str | None,
    func_name: str,
    param_types: list[str],
    return_type: str,
) -> str:
    """Build a canonical conflict key string."""
    scope = class_name if class_name else "global"
    params = ", ".join(param_types)
    ret = return_type.strip() if return_type else "Void"
    return f"{scope}::{func_name}({params}) -> {ret}"


def parse_reds_content(content: str) -> list[tuple[RedscriptTarget, int]]:
    """Parse a .reds file and extract all annotated targets.

    Returns list of (RedscriptTarget, line_number) tuples.
    """
    lines = content.splitlines()
    results: list[tuple[RedscriptTarget, int]] = []
    i = 0

    while i < len(lines):
        match = _ANNOTATION_RE.search(lines[i])
        if not match:
            i += 1
            continue

        annotation_name = match.group(1)
        class_arg = match.group(2) or None
        annotation_line = i + 1
        ann_type = _ANN_TYPE_MAP[annotation_name]

        sig_lines: list[str] = []
        j = i + 1
        max_lookahead = min(j + 10, len(lines))
        found_sig = False

        while j < max_lookahead:
            sig_lines.append(lines[j])
            joined = " ".join(sig_lines)

            sig_match = _FUNC_SIG_RE.search(joined)
            if sig_match:
                func_name = sig_match.group(1)
                raw_params = sig_match.group(2) or ""
                raw_return = (sig_match.group(3) or "Void").strip().rstrip("{").strip()
                if not raw_return:
                    raw_return = "Void"

                param_types = _normalize_param_types(raw_params)
                conflict_key = _build_conflict_key(class_arg, func_name, param_types, raw_return)

                target = RedscriptTarget(
                    annotation_type=ann_type,
                    class_name=class_arg,
                    func_name=func_name,
                    param_types=param_types,
                    return_type=raw_return,
                    conflict_key=conflict_key,
                )
                results.append((target, annotation_line))
                found_sig = True
                i = j + 1
                break
            j += 1

        if not found_sig:
            logger.debug(
                "Could not parse function signature after annotation at line %d",
                annotation_line,
            )
            i += 1

    return results


def _collect_reds_files_for_mod(
    game_install_path: Path,
    mod: InstalledMod,
) -> list[tuple[Path, str]]:
    """Collect .reds files belonging to an installed mod."""
    result: list[tuple[Path, str]] = []
    resolved_base = game_install_path.resolve()
    for f in mod.files:
        rel = f.relative_path.replace("\\", "/")
        if rel.lower().endswith(".reds"):
            abs_path = game_install_path / rel
            if abs_path.resolve().is_relative_to(resolved_base) and abs_path.is_file():
                result.append((abs_path, rel))
    return result


def check_redscript_conflicts(
    game: Game,
    session: Session,
) -> RedscriptConflictResult:
    """Analyze all installed mods for redscript annotation conflicts.

    Reads .reds files from disk for each enabled installed mod, parses
    annotations, and detects conflicts where >=2 mods use @replaceMethod
    or @replaceGlobal on the same target.
    """
    game_path = Path(game.install_path)
    mods = list(
        session.exec(
            select(InstalledMod)
            .where(
                InstalledMod.game_id == game.id,
                InstalledMod.disabled == False,  # noqa: E712
            )
            .options(selectinload(InstalledMod.files))  # type: ignore[arg-type]
        ).all()
    )

    replace_targets: dict[str, list[RedscriptModEntry]] = defaultdict(list)
    wrap_targets: dict[str, list[RedscriptModEntry]] = defaultdict(list)

    total_reds_files = 0
    total_targets = 0

    for mod in mods:
        reds_files = _collect_reds_files_for_mod(game_path, mod)
        for abs_path, rel_path in reds_files:
            total_reds_files += 1
            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                logger.warning("Could not read redscript file: %s", abs_path)
                continue

            parsed = parse_reds_content(content)
            for target, line_no in parsed:
                total_targets += 1
                entry = RedscriptModEntry(
                    installed_mod_id=mod.id,  # type: ignore[arg-type]
                    installed_mod_name=mod.name,
                    file_path=rel_path,
                    annotation_type=target.annotation_type,
                    line_number=line_no,
                )
                if target.annotation_type == RedscriptAnnotationType.WRAP_METHOD:
                    wrap_targets[target.conflict_key].append(entry)
                else:
                    replace_targets[target.conflict_key].append(entry)

    conflicts: list[RedscriptConflict] = []
    for key, entries in replace_targets.items():
        unique_mod_ids = {e.installed_mod_id for e in entries}
        if len(unique_mod_ids) >= 2:
            scope, rest = key.split("::", 1)
            func_part = rest.split("(", 1)[0]
            conflicts.append(
                RedscriptConflict(
                    conflict_key=key,
                    target_class=scope if scope != "global" else None,
                    target_func=func_part,
                    mods=entries,
                )
            )

    wraps: list[RedscriptWrapInfo] = []
    for key, entries in wrap_targets.items():
        scope, rest = key.split("::", 1)
        func_part = rest.split("(", 1)[0]
        wraps.append(
            RedscriptWrapInfo(
                conflict_key=key,
                target_class=scope if scope != "global" else None,
                target_func=func_part,
                mods=entries,
            )
        )

    conflicts.sort(key=lambda c: c.conflict_key)
    wraps.sort(key=lambda w: w.conflict_key)

    return RedscriptConflictResult(
        total_reds_files=total_reds_files,
        total_targets_found=total_targets,
        conflicts=conflicts,
        wraps=wraps,
    )

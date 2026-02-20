"""Shared helpers for creating/updating Nexus mod records."""

from typing import Any

from sqlmodel import Session, select

from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta


def upsert_nexus_mod(
    session: Session,
    game_id: int,
    game_domain: str,
    mod_id: int,
    info: dict[str, Any],
    *,
    file_name: str = "",
    file_id: int | None = None,
) -> NexusDownload:
    """Create or update NexusDownload + NexusModMeta from API response data."""
    nexus_url = f"https://www.nexusmods.com/{game_domain}/mods/{mod_id}"
    mod_name = info.get("name", "")
    version = info.get("version", "")

    existing_dl = session.exec(
        select(NexusDownload).where(
            NexusDownload.game_id == game_id,
            NexusDownload.nexus_mod_id == mod_id,
        )
    ).first()

    if not existing_dl:
        dl = NexusDownload(
            game_id=game_id,
            nexus_mod_id=mod_id,
            mod_name=mod_name,
            file_name=file_name,
            file_id=file_id,
            version=version,
            category=str(info.get("category_id", "")),
            nexus_url=nexus_url,
        )
        session.add(dl)
    else:
        dl = existing_dl
        if mod_name:
            dl.mod_name = mod_name
        # NOTE: intentionally do NOT overwrite dl.version — it represents
        # the version at time of discovery (FOMOD/MD5/snapshot) and must
        # be preserved for update detection.
        if file_name and not dl.file_name:
            dl.file_name = file_name
        if file_id and not dl.file_id:
            dl.file_id = file_id
        dl.nexus_url = nexus_url

    # Upsert mod metadata for vector search
    existing_meta = session.exec(
        select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)
    ).first()
    if not existing_meta:
        meta = NexusModMeta(
            nexus_mod_id=mod_id,
            game_domain=game_domain,
            name=mod_name,
            summary=info.get("summary", ""),
            author=info.get("author", ""),
            version=version,
            endorsement_count=info.get("endorsement_count", 0),
            category=str(info.get("category_id", "")),
            picture_url=info.get("picture_url", ""),
        )
        session.add(meta)
    else:
        if mod_name:
            existing_meta.name = mod_name
        if info.get("summary"):
            existing_meta.summary = info["summary"]
        if version:
            existing_meta.version = version
        if info.get("author"):
            existing_meta.author = info["author"]
        if info.get("endorsement_count") is not None:
            existing_meta.endorsement_count = info["endorsement_count"]
        if info.get("picture_url"):
            existing_meta.picture_url = info["picture_url"]

    return dl

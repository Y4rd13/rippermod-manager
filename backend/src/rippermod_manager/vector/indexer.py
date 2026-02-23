import logging

from sqlmodel import Session, select

from rippermod_manager.database import engine
from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.mod import ModGroup
from rippermod_manager.models.nexus import NexusDownload, NexusModMeta
from rippermod_manager.vector.store import (
    COLLECTION_CORRELATIONS,
    COLLECTION_MODS,
    COLLECTION_NEXUS,
    get_collection,
    reset_collection,
)

logger = logging.getLogger(__name__)


def index_mod_groups(game_id: int | None = None) -> int:
    collection = reset_collection(COLLECTION_MODS)

    with Session(engine) as session:
        stmt = select(ModGroup)
        if game_id is not None:
            stmt = stmt.where(ModGroup.game_id == game_id)
        groups = session.exec(stmt).all()

        if not groups:
            return 0

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, str | int | float]] = []

        for group in groups:
            _ = group.files
            file_names = [f.filename for f in group.files]
            file_paths = [f.file_path for f in group.files]
            source_folders = list({f.source_folder for f in group.files})

            doc = (
                f"Mod: {group.display_name}\n"
                f"Files ({len(group.files)}): {', '.join(file_names[:10])}\n"
                f"Paths: {', '.join(file_paths[:5])}\n"
                f"Source folders: {', '.join(source_folders)}\n"
                f"Grouping confidence: {group.confidence}"
            )

            ids.append(f"modgroup-{group.id}")
            documents.append(doc)
            metadatas.append(
                {
                    "type": "mod_group",
                    "mod_group_id": group.id or 0,
                    "game_id": group.game_id,
                    "display_name": group.display_name,
                    "file_count": len(group.files),
                    "confidence": group.confidence,
                }
            )

        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        logger.info("Indexed %d mod groups into vector store", len(ids))
        return len(ids)


def index_nexus_metadata(game_id: int | None = None) -> int:
    collection = reset_collection(COLLECTION_NEXUS)

    with Session(engine) as session:
        if game_id is not None:
            download_ids = session.exec(
                select(NexusDownload.nexus_mod_id).where(NexusDownload.game_id == game_id)
            ).all()
            mod_ids = set(download_ids)
            metas = session.exec(
                select(NexusModMeta).where(
                    NexusModMeta.nexus_mod_id.in_(mod_ids)  # type: ignore[union-attr]
                )
            ).all()
        else:
            metas = session.exec(select(NexusModMeta)).all()

        if not metas:
            return 0

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, str | int | float]] = []

        for meta in metas:
            doc = (
                f"Nexus Mod: {meta.name}\n"
                f"Author: {meta.author}\n"
                f"Summary: {meta.summary}\n"
                f"Version: {meta.version}\n"
                f"Category: {meta.category}\n"
                f"Endorsements: {meta.endorsement_count}\n"
                f"Game: {meta.game_domain}"
            )

            ids.append(f"nexus-{meta.nexus_mod_id}")
            documents.append(doc)
            metadatas.append(
                {
                    "type": "nexus_mod",
                    "nexus_mod_id": meta.nexus_mod_id,
                    "name": meta.name,
                    "author": meta.author,
                    "version": meta.version,
                    "game_domain": meta.game_domain,
                    "endorsement_count": meta.endorsement_count,
                }
            )

        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        logger.info("Indexed %d Nexus mod metadata into vector store", len(ids))
        return len(ids)


def index_correlations(game_id: int | None = None) -> int:
    collection = reset_collection(COLLECTION_CORRELATIONS)

    with Session(engine) as session:
        stmt = (
            select(ModNexusCorrelation, ModGroup, NexusDownload)
            .join(ModGroup, ModNexusCorrelation.mod_group_id == ModGroup.id)
            .join(NexusDownload, ModNexusCorrelation.nexus_download_id == NexusDownload.id)
        )
        if game_id is not None:
            stmt = stmt.where(ModGroup.game_id == game_id)

        results = session.exec(stmt).all()

        if not results:
            return 0

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, str | int | float]] = []

        for corr, group, download in results:
            meta = session.exec(
                select(NexusModMeta).where(NexusModMeta.nexus_mod_id == download.nexus_mod_id)
            ).first()

            summary = meta.summary if meta else ""
            author = meta.author if meta else ""

            doc = (
                f"Local mod '{group.display_name}' is matched to Nexus mod '{download.mod_name}'\n"
                f"Match method: {corr.method}, score: {corr.score}\n"
                f"Reasoning: {corr.reasoning}\n"
                f"Nexus version: {download.version}\n"
                f"Author: {author}\n"
                f"Summary: {summary}\n"
                f"Confirmed by user: {corr.confirmed_by_user}"
            )

            ids.append(f"corr-{corr.id}")
            documents.append(doc)
            metadatas.append(
                {
                    "type": "correlation",
                    "mod_group_id": corr.mod_group_id,
                    "nexus_mod_id": download.nexus_mod_id,
                    "score": corr.score,
                    "method": corr.method,
                    "local_name": group.display_name,
                    "nexus_name": download.mod_name,
                }
            )

        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        logger.info("Indexed %d correlations into vector store", len(ids))
        return len(ids)


def index_all(game_id: int | None = None) -> dict[str, int]:
    mods = index_mod_groups(game_id)
    nexus = index_nexus_metadata(game_id)
    corrs = index_correlations(game_id)
    return {"mod_groups": mods, "nexus_mods": nexus, "correlations": corrs}


def delete_game_vectors(game_id: int) -> None:
    """Remove all vectors associated with a game from the vector store.

    Must be called *before* cascading SQL deletes so NexusDownload rows are still available.
    """
    with Session(engine) as session:
        group_ids = list(session.exec(select(ModGroup.id).where(ModGroup.game_id == game_id)).all())
        nexus_mod_ids = list(
            session.exec(
                select(NexusDownload.nexus_mod_id).where(NexusDownload.game_id == game_id)
            ).all()
        )

    # mod_groups collection has game_id in metadata
    mods_col = get_collection(COLLECTION_MODS)
    mods_col.delete(where={"game_id": game_id})

    if group_ids:
        corr_col = get_collection(COLLECTION_CORRELATIONS)
        corr_col.delete(where={"mod_group_id": {"$in": group_ids}})

    if nexus_mod_ids:
        nexus_col = get_collection(COLLECTION_NEXUS)
        nexus_col.delete(ids=[f"nexus-{mid}" for mid in nexus_mod_ids])

    logger.info("Deleted vectors for game_id=%d", game_id)

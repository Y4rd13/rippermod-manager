import logging

import chromadb
from chromadb.config import Settings as ChromaSettings

from chat_nexus_mod_manager.config import settings

logger = logging.getLogger(__name__)

COLLECTION_MODS = "mod_groups"
COLLECTION_NEXUS = "nexus_mods"
COLLECTION_CORRELATIONS = "correlations"

_client: chromadb.ClientAPI | None = None


def get_chroma_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        settings.chroma_path.parent.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(settings.chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        logger.info("ChromaDB initialized at %s", settings.chroma_path)
    return _client


def get_collection(name: str) -> chromadb.Collection:
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection(name: str) -> chromadb.Collection:
    client = get_chroma_client()
    try:
        client.delete_collection(name)
    except Exception:
        pass
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )

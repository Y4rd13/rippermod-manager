import logging

from chat_nexus_mod_manager.vector.store import (
    COLLECTION_CORRELATIONS,
    COLLECTION_MODS,
    COLLECTION_NEXUS,
    get_collection,
)

logger = logging.getLogger(__name__)


def semantic_search(
    query: str,
    collections: list[str] | None = None,
    n_results: int = 5,
) -> list[dict[str, str]]:
    if collections is None:
        collections = [COLLECTION_MODS, COLLECTION_NEXUS, COLLECTION_CORRELATIONS]

    all_results: list[dict[str, str]] = []

    for coll_name in collections:
        try:
            collection = get_collection(coll_name)
            if collection.count() == 0:
                continue

            results = collection.query(
                query_texts=[query],
                n_results=min(n_results, collection.count()),
            )

            if results and results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    distance = results["distances"][0][i] if results["distances"] else 0
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    all_results.append({
                        "collection": coll_name,
                        "document": doc,
                        "distance": f"{distance:.3f}",
                        "type": metadata.get("type", "unknown"),
                    })
        except Exception:
            logger.warning("Failed to search collection %s", coll_name, exc_info=True)
            continue

    all_results.sort(key=lambda r: float(r["distance"]))
    return all_results[:n_results]


def search_mods_semantic(query: str, n_results: int = 5) -> list[dict[str, str]]:
    return semantic_search(query, collections=[COLLECTION_MODS], n_results=n_results)


def search_nexus_semantic(query: str, n_results: int = 5) -> list[dict[str, str]]:
    return semantic_search(query, collections=[COLLECTION_NEXUS], n_results=n_results)


def search_all_semantic(query: str, n_results: int = 8) -> str:
    results = semantic_search(query, n_results=n_results)
    if not results:
        return f"No relevant results found for '{query}'"

    output_parts: list[str] = []
    for r in results:
        output_parts.append(
            f"[{r['type']}] (relevance: {r['distance']})\n{r['document']}"
        )
    return "\n---\n".join(output_parts)

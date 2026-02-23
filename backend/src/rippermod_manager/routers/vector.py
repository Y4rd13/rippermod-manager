from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from rippermod_manager.database import get_session
from rippermod_manager.models.game import Game

router = APIRouter(prefix="/vector", tags=["vector"])


class IndexResult(BaseModel):
    mod_groups: int
    nexus_mods: int
    correlations: int


class SearchResult(BaseModel):
    collection: str
    document: str
    distance: str
    type: str


class CollectionStats(BaseModel):
    name: str
    count: int


@router.post("/reindex", response_model=IndexResult)
def reindex(
    game_name: str | None = None,
    session: Session = Depends(get_session),
) -> IndexResult:
    from rippermod_manager.vector.indexer import index_all

    game_id = None
    if game_name:
        game = session.exec(select(Game).where(Game.name == game_name)).first()
        if game:
            game_id = game.id

    counts = index_all(game_id)
    return IndexResult(**counts)


@router.get("/search", response_model=list[SearchResult])
def search(
    q: str = Query(..., min_length=1),
    n: int = Query(default=5, ge=1, le=20),
) -> list[SearchResult]:
    from rippermod_manager.vector.search import semantic_search

    results = semantic_search(q, n_results=n)
    return [SearchResult(**r) for r in results]


@router.get("/stats", response_model=list[CollectionStats])
def stats() -> list[CollectionStats]:
    from rippermod_manager.vector.store import (
        COLLECTION_CORRELATIONS,
        COLLECTION_MODS,
        COLLECTION_NEXUS,
        get_collection,
    )

    result = []
    for name in [COLLECTION_MODS, COLLECTION_NEXUS, COLLECTION_CORRELATIONS]:
        try:
            coll = get_collection(name)
            result.append(CollectionStats(name=name, count=coll.count()))
        except Exception:
            result.append(CollectionStats(name=name, count=0))
    return result

import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    PointStruct,
    Filter,
    FieldCondition,
    Range,
    MatchValue,
    PayloadSchemaType,
)
from config import settings

_client = QdrantClient(
    url=settings.qdrant_url,
    api_key=settings.qdrant_api_key,
)


def create_collection():
    """Create the mood_entries collection if it doesn't already exist."""
    collections = _client.get_collections().collections
    if not any(c.name == settings.collection_name for c in collections):
        _client.create_collection(
            collection_name=settings.collection_name,
            vectors_config=VectorParams(
                size=settings.embedding_dim,
                distance=Distance.COSINE,
            ),
            on_disk_payload=True,
        )

    # Ensure payload indexes exist for filtering
    _client.create_payload_index(
        collection_name=settings.collection_name,
        field_name="user_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    _client.create_payload_index(
        collection_name=settings.collection_name,
        field_name="timestamp",
        field_schema=PayloadSchemaType.INTEGER,
    )
    _client.create_payload_index(
        collection_name=settings.collection_name,
        field_name="entry_type",
        field_schema=PayloadSchemaType.KEYWORD,
    )


def upsert_entry(vector: list[float], payload: dict) -> str:
    """Store a mood entry point in Qdrant. Returns the generated point ID."""
    point_id = str(uuid.uuid4())
    _client.upsert(
        collection_name=settings.collection_name,
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload=payload,
            )
        ],
    )
    return point_id


def scroll_entries(
    user_id: str,
    date_from: int | None = None,
    date_to: int | None = None,
    limit: int = 100,
):
    """Scroll entries for a user within an optional timestamp window.
    Returns vectors alongside payloads (needed for centroid computation).
    """
    conditions = [
        FieldCondition(key="user_id", match=MatchValue(value=user_id))
    ]
    if date_from is not None:
        conditions.append(
            FieldCondition(key="timestamp", range=Range(gte=date_from))
        )
    if date_to is not None:
        conditions.append(
            FieldCondition(key="timestamp", range=Range(lt=date_to))
        )

    results, _ = _client.scroll(
        collection_name=settings.collection_name,
        scroll_filter=Filter(must=conditions),
        limit=limit,
        with_vectors=True,
    )
    return results


def search_similar(
    vector: list[float],
    user_id: str,
    limit: int = 5,
    date_before: int | None = None,
):
    """Find entries most similar to the given vector for a user."""
    conditions = [
        FieldCondition(key="user_id", match=MatchValue(value=user_id))
    ]
    if date_before is not None:
        conditions.append(
            FieldCondition(key="timestamp", range=Range(lt=date_before))
        )

    results = _client.query_points(
        collection_name=settings.collection_name,
        query=vector,
        query_filter=Filter(must=conditions),
        limit=limit,
    )
    return results.points


def search_coping_strategies(
    user_id: str,
    date_from: int | None = None,
    date_to: int | None = None,
    limit: int = 5,
):
    """Find coping strategy entries for a user within an optional date range."""
    conditions = [
        FieldCondition(key="user_id", match=MatchValue(value=user_id)),
        FieldCondition(key="entry_type", match=MatchValue(value="coping_strategy")),
    ]
    if date_from is not None:
        conditions.append(
            FieldCondition(key="timestamp", range=Range(gte=date_from))
        )
    if date_to is not None:
        conditions.append(
            FieldCondition(key="timestamp", range=Range(lt=date_to))
        )

    results, _ = _client.scroll(
        collection_name=settings.collection_name,
        scroll_filter=Filter(must=conditions),
        limit=limit,
        with_vectors=False,
    )
    return results


def delete_entries(user_id: str) -> int:
    """Delete all entries for a user. Returns count of deleted points."""
    # Get all point IDs for this user
    entries = scroll_entries(user_id=user_id, limit=1000)
    if not entries:
        return 0
    point_ids = [e.id for e in entries]
    _client.delete(
        collection_name=settings.collection_name,
        points_selector=point_ids,
    )
    return len(point_ids)

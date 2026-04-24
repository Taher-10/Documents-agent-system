from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, cast

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from agent_compliance.pdf_parser import assess_quality, docling_to_sections, parse_document
from agent_compliance.pdf_parser.docling_parser import ParseResult

from .document_meta import DocumentMeta
from .payload_builder import build_payload
from .utils import stable_uuid


QHSE_COLLECTION_NAME = "qhse_sections"
QHSE_VECTOR_SIZE = 1024
DEFAULT_MIN_CONFIDENCE = 0.6


class IngestionError(RuntimeError):
    """Raised when ingestion cannot safely proceed."""


@dataclass(slots=True)
class IngestResult:
    collection: str
    doc_id: str
    company_id: str
    total_sections: int
    ingested: int
    skipped_low_confidence: int
    skipped_empty_text: int
    skipped_embed_error: int
    skipped_quality_gate: int
    quality_tier: str
    min_confidence: float
    reason: str | None = None


def _existing_collections(qdrant_client: QdrantClient) -> set[str]:
    try:
        response = qdrant_client.get_collections()
        return {
            str(collection.name)
            for collection in getattr(response, "collections", [])
            if getattr(collection, "name", None)
        }
    except Exception as exc:
        raise IngestionError(f"Failed to list Qdrant collections: {exc}") from exc


def _extract_vector_size(vectors: object) -> int | None:
    if vectors is None:
        return None

    if isinstance(vectors, dict):
        dense = vectors.get("dense")
        if dense is not None:
            return _extract_vector_size(dense)
        if "size" in vectors and isinstance(vectors["size"], int):
            return int(vectors["size"])
        for value in vectors.values():
            size = _extract_vector_size(value)
            if size is not None:
                return size
        return None

    size = getattr(vectors, "size", None)
    if isinstance(size, int):
        return size

    dump = getattr(vectors, "model_dump", None)
    if callable(dump):
        dumped = cast(dict, dump())
        return _extract_vector_size(dumped)

    return None


def _collection_vector_size(qdrant_client: QdrantClient, collection: str) -> int | None:
    try:
        info = qdrant_client.get_collection(collection_name=collection)
    except Exception as exc:
        raise IngestionError(f"Failed to fetch collection '{collection}' metadata: {exc}") from exc

    config = getattr(info, "config", None)
    params = getattr(config, "params", None)
    vectors = getattr(params, "vectors", None)
    return _extract_vector_size(vectors)


def _ensure_payload_indexes(qdrant_client: QdrantClient, collection: str) -> None:
    qdrant_client.create_payload_index(collection, "company_id", PayloadSchemaType.KEYWORD)
    qdrant_client.create_payload_index(collection, "site_id", PayloadSchemaType.KEYWORD)
    qdrant_client.create_payload_index(collection, "section_type", PayloadSchemaType.KEYWORD)
    qdrant_client.create_payload_index(collection, "doc_type", PayloadSchemaType.KEYWORD)
    qdrant_client.create_payload_index(collection, "doc_level", PayloadSchemaType.INTEGER)


def ensure_qhse_collection(
    qdrant_client: QdrantClient,
    collection: str = QHSE_COLLECTION_NAME,
    vector_size: int = QHSE_VECTOR_SIZE,
) -> None:
    collections = _existing_collections(qdrant_client)

    if collection not in collections:
        qdrant_client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
    else:
        existing_size = _collection_vector_size(qdrant_client, collection)
        if existing_size is not None and existing_size != vector_size:
            raise IngestionError(
                f"Collection '{collection}' has vector size {existing_size}, expected {vector_size}."
            )

    _ensure_payload_indexes(qdrant_client, collection)


def _tenant_doc_filter(doc_id: str, company_id: str) -> Filter:
    return Filter(
        must=[
            FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
            FieldCondition(key="company_id", match=MatchValue(value=company_id)),
        ]
    )


def has_ingested_document(
    qdrant_client: QdrantClient,
    *,
    doc_id: str,
    company_id: str,
    collection: str = QHSE_COLLECTION_NAME,
) -> bool:
    result = qdrant_client.count(
        collection_name=collection,
        count_filter=_tenant_doc_filter(doc_id=doc_id, company_id=company_id),
        exact=True,
    )
    count = int(getattr(result, "count", 0) or 0)
    return count > 0


def _base_result(
    meta: DocumentMeta,
    collection: str,
    total_sections: int,
    quality_tier: str,
    min_confidence: float,
) -> IngestResult:
    return IngestResult(
        collection=collection,
        doc_id=meta.doc_id,
        company_id=meta.company_id,
        total_sections=total_sections,
        ingested=0,
        skipped_low_confidence=0,
        skipped_empty_text=0,
        skipped_embed_error=0,
        skipped_quality_gate=0,
        quality_tier=quality_tier,
        min_confidence=min_confidence,
        reason=None,
    )


def _parse_sections(file_path: str) -> tuple[ParseResult, list]:
    parse_result = parse_document(file_path, remove_headers_footers=True)
    sections = docling_to_sections(parse_result)
    return parse_result, sections


def ingest_document(
    meta: DocumentMeta,
    qdrant_client: QdrantClient,
    embed_fn: Callable[[str], list[float]],
    *,
    collection: str = QHSE_COLLECTION_NAME,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> IngestResult:
    ensure_qhse_collection(qdrant_client, collection=collection, vector_size=QHSE_VECTOR_SIZE)

    parse_result, sections = _parse_sections(meta.file_path)
    quality_tier, quality_min_confidence, _ = assess_quality(sections)
    result = _base_result(
        meta=meta,
        collection=collection,
        total_sections=len(sections),
        quality_tier=quality_tier,
        min_confidence=float(quality_min_confidence),
    )

    if quality_tier == "C":
        result.skipped_quality_gate = len(sections)
        result.reason = "low_quality_document"
        return result

    points: list[PointStruct] = []
    for section in sections:
        text = (section.raw_text or "").strip()
        if not text:
            result.skipped_empty_text += 1
            continue

        if float(section.extraction_confidence) < min_confidence:
            result.skipped_low_confidence += 1
            continue

        try:
            vector = embed_fn(text)
        except Exception:
            result.skipped_embed_error += 1
            continue

        if len(vector) != QHSE_VECTOR_SIZE:
            raise IngestionError(
                f"Embedding vector size {len(vector)} is invalid, expected {QHSE_VECTOR_SIZE}."
            )

        points.append(
            PointStruct(
                id=stable_uuid(meta.doc_id, section.id),
                vector=vector,
                payload=build_payload(section=section, meta=meta, result=parse_result),
            )
        )

    if points:
        qdrant_client.upsert(collection_name=collection, points=points)
        result.ingested = len(points)
    else:
        result.reason = "no_sections_ingested"

    return result

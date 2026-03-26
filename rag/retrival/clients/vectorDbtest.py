"""
Qdrant Test Script — tailored for the 'norms' collection
Covers: connect, collection info, sentinel check, scroll, count,
        payload filters, retrieve by UUID, upsert+delete round-trip,
        and vector similarity search.
"""

from __future__ import annotations

import os
import random
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, Filter, FieldCondition, MatchValue,
    PointIdsList, PointStruct, VectorParams,
)

# ── Config ────────────────────────────────────────────────────────────────────
QDRANT_HOST    = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT    = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
COLLECTION     = "norms"

# Reserved sentinel UUID (matches vector_store/qdrant_store.py)
SENTINEL_ID = "00000000-0000-0000-0000-000000000001"

SEP = "=" * 60

def sep(title: str) -> None:
    print(f"\n{SEP}\n  {title}\n{SEP}")

# ── Connect ───────────────────────────────────────────────────────────────────
sep("1. CONNECT")
client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_API_KEY)
print(f"  Connected to {QDRANT_HOST}:{QDRANT_PORT}")

# ── List collections ───────────────────────────────────────────────────────────
sep("2. LIST COLLECTIONS")
all_cols = [c.name for c in client.get_collections().collections]
print(f"  Collections: {all_cols}")
assert COLLECTION in all_cols, f"'{COLLECTION}' not found!"

# ── Collection info ────────────────────────────────────────────────────────────
sep("3. COLLECTION INFO")
info = client.get_collection(COLLECTION)
vec_cfg = info.config.params.vectors   # VectorParams (unnamed vectors)
VEC_SIZE = vec_cfg.size
print(f"  Status       : {info.status}")
print(f"  Points count : {info.points_count}")
print(f"  Vector size  : {VEC_SIZE}")
print(f"  Distance     : {vec_cfg.distance}")

# ── Exact point count ──────────────────────────────────────────────────────────
sep("4. EXACT COUNT")
count = client.count(collection_name=COLLECTION, exact=True).count
print(f"  Exact count: {count}")

# ── Sentinel point ─────────────────────────────────────────────────────────────
sep("5. SENTINEL POINT (model metadata)")
hits = client.retrieve(
    collection_name=COLLECTION,
    ids=[SENTINEL_ID],
    with_payload=True,
    with_vectors=False,
)
if hits:
    print(f"  Sentinel found  : {hits[0].payload}")
else:
    print("  No sentinel found (legacy collection or not yet written).")

# ── Scroll — first 5 real points ──────────────────────────────────────────────
sep("6. SCROLL (first 5 non-sentinel points)")
points, _next = client.scroll(
    collection_name=COLLECTION,
    limit=6,            # fetch 6, skip sentinel if present
    with_payload=True,
    with_vectors=False,
    scroll_filter=Filter(
        must_not=[FieldCondition(key="sentinel", match=MatchValue(value=True))]
    ),
)
for p in points[:5]:
    print(f"  id={p.id}")
    pay = p.payload or {}
    print(f"    norm_id      : {pay.get('norm_id')}")
    print(f"    clause       : {pay.get('clause_number')} — {pay.get('clause_title')}")
    print(f"    content_type : {pay.get('content_type')}")
    print(f"    token_count  : {pay.get('token_count')}")
    print(f"    text (80ch)  : {str(pay.get('text',''))}")

# Save a real point id for retrieve test
sample_id = points[0].id if points else None

# ── Retrieve single point by UUID ──────────────────────────────────────────────
if sample_id:
    sep("7. RETRIEVE BY UUID")
    retrieved = client.retrieve(
        collection_name=COLLECTION,
        ids=[sample_id],
        with_payload=True,
        with_vectors=True,
    )
    r = retrieved[0]
    print(f"  id            : {r.id}")
    print(f"  vector[:5]    : {r.vector[:5]}")
    pay = r.payload or {}
    for key in ("norm_id", "norm_full", "clause_number", "embedding_model",
                "has_requirements", "keywords"):
        print(f"  {key:20s}: {pay.get(key)}")

# ── Filtered scroll — has_requirements = True ──────────────────────────────────
sep("8. FILTER: has_requirements=True  (first 5)")
req_points, _ = client.scroll(
    collection_name=COLLECTION,
    scroll_filter=Filter(
        must=[FieldCondition(key="has_requirements", match=MatchValue(value=True))]
    ),
    limit=5,
    with_payload=True,
    with_vectors=False,
)
print(f"  Found (up to 5): {len(req_points)}")
for p in req_points:
    pay = p.payload or {}
    print(f"  clause {pay.get('clause_number'):>10} | shall_count={pay.get('shall_count')}")

# ── Count with filter ──────────────────────────────────────────────────────────
sep("9. COUNT: has_requirements=True")
req_count = client.count(
    collection_name=COLLECTION,
    count_filter=Filter(
        must=[FieldCondition(key="has_requirements", match=MatchValue(value=True))]
    ),
    exact=True,
).count
print(f"  Points with has_requirements=True: {req_count} / {count}")

# ── Vector similarity search ───────────────────────────────────────────────────
sep("10. VECTOR SEARCH (random query, top 5)")
query_vec = [round(random.uniform(-1, 1), 6) for _ in range(VEC_SIZE)]
results = client.query_points(
    collection_name=COLLECTION,
    query=query_vec,
    limit=5,
    with_payload=True,
).points
for r in results:
    pay = r.payload or {}
    print(f"  score={r.score:.4f} | clause={pay.get('clause_number')} | "
          f"norm={pay.get('norm_id')} | text={str(pay.get('text',''))[:60]}…")

# ── Filtered vector search ─────────────────────────────────────────────────────
sep("11. FILTERED VECTOR SEARCH (has_requirements=True, top 3)")
filtered = client.query_points(
    collection_name=COLLECTION,
    query=query_vec,
    query_filter=Filter(
        must=[FieldCondition(key="has_requirements", match=MatchValue(value=True))]
    ),
    limit=3,
    with_payload=True,
).points
for r in filtered:
    pay = r.payload or {}
    print(f"  score={r.score:.4f} | clause={pay.get('clause_number')} | "
          f"shall={pay.get('shall_count')}")

# ── Upsert + retrieve + delete round-trip ─────────────────────────────────────
sep("12. UPSERT → RETRIEVE → DELETE (round-trip test)")
# Use a deterministic test UUID that won't collide with real data
TEST_CHUNK_ID = "test-chunk-run-py-integration-check"
test_point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, TEST_CHUNK_ID))
test_vec = [round(random.uniform(-1, 1), 6) for _ in range(VEC_SIZE)]
test_payload = {
    "chunk_id": TEST_CHUNK_ID, "norm_id": "TEST-001", "norm_full": "Test Norm",
    "norm_version": "0.0", "clause_number": "0.0", "clause_title": "Test Clause",
    "parent_clause": "", "page_number": 0, "chunk_index": 0, "total_chunks": 1,
    "text": "This is a synthetic test point inserted by run.py.",
    "token_count": 10, "content_type": "normative", "shall_count": 0,
    "should_count": 0, "has_requirements": False, "has_permissions": False,
    "has_recommendations": False, "has_capabilities": False,
    "keywords": "", "related_clauses": "", "embedding_model": "test",
}

op = client.upsert(
    collection_name=COLLECTION,
    wait=True,
    points=[PointStruct(id=test_point_id, vector=test_vec, payload=test_payload)],
)
print(f"  Upsert status : {op.status}")
print(f"  Test point id : {test_point_id}")

verify = client.retrieve(
    collection_name=COLLECTION, ids=[test_point_id], with_payload=True
)
print(f"  Retrieved     : {verify[0].payload.get('chunk_id') if verify else 'NOT FOUND'}")

del_op = client.delete(
    collection_name=COLLECTION,
    points_selector=PointIdsList(points=[test_point_id]),
    wait=True,
)
print(f"  Delete status : {del_op.status}")

after_del = client.retrieve(collection_name=COLLECTION, ids=[test_point_id])
print(f"  After delete  : {'gone ✓' if not after_del else 'STILL EXISTS ✗'}")

# ── Summary ────────────────────────────────────────────────────────────────────
sep("SUMMARY")
print(f"  Collection          : {COLLECTION}")
print(f"  Total points        : {count}")
print(f"  Vector size         : {VEC_SIZE}")
print(f"  has_requirements=T  : {req_count}")
print(f"  Round-trip test     : {'PASS' if not after_del else 'FAIL'}")
print(f"\n  ALL TESTS COMPLETE\n")

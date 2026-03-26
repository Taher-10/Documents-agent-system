# Import & Architecture Review

## 1. Import Root

✅ **FIXED (Step 1)** — `pyproject.toml` added at the project root; `rag-iso` installed with `pip install -e .`. The true import root is now `rag/` for the entire project. All sub-packages are anchored under `rag.*`.

~~The true import root is `rag/ingestion_pipeline/` for the ingestion side and `rag/retrival/` for the retrieval side. Both trees are invoked with their respective directory on `sys.path` (either via `cd rag/ingestion_pipeline && python run.py` or by the `sys.path.insert` hacks in the retrieval layer). There is **no single unified root**; the two sub-trees treat themselves as separate Python projects — `parser`, `segmenter`, `chunker`, `enricher`, `registry`, `embedder`, and `vector_store` are all bare top-level names relative to `rag/ingestion_pipeline/`, while `models`, `query_retrival`, `query_transformer`, and `clients` are bare names relative to `rag/retrival/`. This split is the root cause of every import anti-pattern in the project: there is no package anchoring at `rag/` or project root level, so every import that crosses the `ingestion_pipeline` / `retrival` boundary must resort to hacks.~~

---

## 2. Import Fixes

### Simple Fixes

- File: `rag/ingestion_pipeline/pipeline.py` (line 56) — ✅ **FIXED**
  - ❌ `from parser.document import ParsedDocument`
  - ✅ `from rag.ingestion_pipeline.parser.document import ParsedDocument`
  - Note: `parser` is a Python stdlib module name. Shadowing it with a local package named `parser` is a latent collision bug. The package should be renamed (e.g. `pdf_parser`) or all imports must be root-anchored.

- File: `rag/ingestion_pipeline/pipeline.py` (lines 58–67) — ✅ **FIXED**
  - ❌ `from chunker import NormChunk, assemble_norm_chunks`
  - ✅ `from rag.ingestion_pipeline.chunker import NormChunk, assemble_norm_chunks`
  - ❌ `from enricher import Enricher`
  - ✅ `from rag.ingestion_pipeline.enricher import Enricher`
  - ❌ `from registry import validate_chunks, write_registry`
  - ✅ `from rag.ingestion_pipeline.registry import validate_chunks, write_registry`
  - ❌ `from segmenter import (STANDARD_ID_MAP, ClauseNode, ...)`
  - ✅ `from rag.ingestion_pipeline.segmenter import (STANDARD_ID_MAP, ClauseNode, ...)`

- File: `rag/ingestion_pipeline/run.py` (lines 3–4) — ✅ **FIXED**
  - ❌ `from parser import parse_iso_pdf`
  - ✅ `from rag.ingestion_pipeline.parser import parse_iso_pdf`
  - ❌ `from pipeline import segment, embed_and_store`
  - ✅ `from rag.ingestion_pipeline.pipeline import segment, embed_and_store`

- File: `rag/ingestion_pipeline/segmenter/iso_segmenter.py` (line 27) — ✅ **FIXED**
  - ❌ `from parser.document import ParsedDocument`
  - ✅ `from rag.ingestion_pipeline.parser.document import ParsedDocument`

- File: `rag/ingestion_pipeline/segmenter/pipeline.py` (lines 48, 50) — ⏭️ **SKIPPED** (file is orphaned; will be deleted in Step 4)
  - ❌ `from parser.document import ParsedDocument`
  - ✅ `from rag.ingestion_pipeline.parser.document import ParsedDocument`
  - ❌ `from segmenter import (STANDARD_ID_MAP, ClauseNode, ...)`
  - ✅ `from rag.ingestion_pipeline.segmenter import (...)`

- File: `rag/ingestion_pipeline/chunker/assembler.py` (lines 40–47) — ✅ **FIXED**
  - ❌ `from segmenter.models import (NORM_ID_MAP, NORM_VERSION_MAP, ...)`
  - ✅ `from rag.ingestion_pipeline.segmenter.models import (...)`
  - ❌ `from segmenter.page_tracker import PageTracker`
  - ✅ `from rag.ingestion_pipeline.segmenter.page_tracker import PageTracker`

- File: `rag/ingestion_pipeline/chunker/models.py` (line 27) — ✅ **FIXED**
  - ❌ `from segmenter.models import ContentType`
  - ✅ `from rag.ingestion_pipeline.segmenter.models import ContentType`

- File: `rag/ingestion_pipeline/enricher/enricher.py` (line 29) — ✅ **FIXED**
  - ❌ `from chunker.models import NormChunk`
  - ✅ `from rag.ingestion_pipeline.chunker.models import NormChunk`

- File: `rag/ingestion_pipeline/registry/registry.py` (lines 43–44) — ✅ **FIXED**
  - ❌ `from chunker.models import NormChunk`
  - ✅ `from rag.ingestion_pipeline.chunker.models import NormChunk`
  - ❌ `from segmenter.models import ClauseNode`
  - ✅ `from rag.ingestion_pipeline.segmenter.models import ClauseNode`

- File: `rag/ingestion_pipeline/embedder/embedder.py` (lines 47–60) — ✅ **FIXED**
  - ❌ `from chunker.models import NormChunk`
  - ✅ `from rag.ingestion_pipeline.chunker.models import NormChunk`
  - ❌ `from embedder.bm25_encoder import BM25SparseEncoder`
  - ✅ `from .bm25_encoder import BM25SparseEncoder` (relative — same package)
  - ❌ `from embedder.config import (...)`
  - ✅ `from .config import (...)` (relative — same package)
  - ❌ `from embedder.models import EmbeddedChunk, EmbeddingResult`
  - ✅ `from .models import EmbeddedChunk, EmbeddingResult` (relative — same package)

- File: `rag/ingestion_pipeline/embedder/models.py` (line 17) — ✅ **FIXED**
  - ❌ `from chunker.models import NormChunk`
  - ✅ `from rag.ingestion_pipeline.chunker.models import NormChunk`

- File: `rag/ingestion_pipeline/vector_store/qdrant_store.py` (line 42) — ✅ **FIXED (Step 3)**
  - ~~❌ `from embedder.models import EmbeddedChunk`~~
  - Fix applied: `from rag.ingestion_pipeline.embedder.models import EmbeddedChunk`
  - Deferred imports (lines 109, 184) fixed: `from embedder.config import SPARSE_DIM` → `from rag.shared.bm25.config import SPARSE_DIM`

- File: `rag/retrival/query_transformer/Querytransformer.py` (line 24) — ✅ **FIXED**
  - ❌ `from models import TransformedQuery`
  - ✅ `from rag.retrival.models import TransformedQuery`
  - Also fixed deferred import (line 205): ❌ `from clients.llm_client import chat_complete` → ✅ `from rag.retrival.clients.llm_client import chat_complete`

- File: `rag/retrival/query_retrival/retriever.py` (line 48) — ✅ **FIXED**
  - ❌ `from models import RetrievedChunk, TransformedQuery`
  - ✅ `from rag.retrival.models import RetrievedChunk, TransformedQuery`

- File: `rag/retrival/query_retrival/tests/smoketest/smoke_dense.py` (line 43) — ✅ **FIXED (Step 4)**
  - ~~❌ `from models import TransformedQuery`~~
  - ✅ `from rag.retrival.models import TransformedQuery`
  - Also fixed: `from query_retrival.retriever import DenseRetriever, EmptyCorpusError` → `from rag.retrival.query_retrival.retriever import DenseRetriever, EmptyCorpusError`
  - Also removed `sys.path.insert` hack (line 38)

- File: `rag/retrival/query_retrival/tests/smoketest/smoke_hybrid.py` (line 53) — ✅ **FIXED**
  - ❌ `from models import TransformedQuery`
  - ✅ `from rag.retrival.models import TransformedQuery`
  - Also fixed (line 54): ❌ `from query_retrival.retriever import HybridRetriever, EmptyCorpusError` → ✅ `from rag.retrival.query_retrival.retriever import HybridRetriever, EmptyCorpusError`
  - Also removed `sys.path.insert` hack (line 48)

### Complex Fixes

- File: `rag/ingestion_pipeline/segmenter/iso_segmenter.py` (line 27) — ⏳ **PENDING** (import root-anchored in Step 1; directional decoupling is Step 5)
  - Issue: `segmenter` imports `ParsedDocument` from `parser`. Per the documented dependency rule, `segmenter` should only depend on its own models and the stdlib. Importing from `parser` creates a backwards-direction dependency that couples Phase 2/3 to Phase 1.
  - Recommendation: Replace the `parser.document.ParsedDocument` import with a local protocol or a shared contracts module. `detect_clause_boundaries` only needs `doc.markdown` and `doc.heading_positions` — a `Protocol` or a plain dataclass in a shared `contracts` module avoids the cross-phase import entirely.

- File: `rag/ingestion_pipeline/segmenter/pipeline.py` — ✅ **FIXED (Step 4)** (file deleted)
  - Issue: A second `pipeline.py` exists inside `segmenter/` with functions duplicating the top-level `pipeline.py` (same function names `segment_document`, `segment`, `embed_and_store`). It is incomplete (the file cuts off at line 96 mid-function), imports from `parser` and `segmenter` using bare names, and partially re-implements the orchestrator. This file is orphaned — nothing imports it — but its existence alongside the real orchestrator creates confusion and a maintenance hazard.
  - Recommendation: Delete `rag/ingestion_pipeline/segmenter/pipeline.py`. The only legitimate orchestrator is `rag/ingestion_pipeline/pipeline.py`.

- File: `rag/retrival/query_retrival/retriever.py` (lines 52–57) — ✅ **FIXED (Step 3)**
  - ~~Step 1: Replaced 50-line importlib hack with a 2-line lazy function: `from rag.ingestion_pipeline.embedder.bm25_encoder import BM25SparseEncoder`.~~
  - Fix applied (Step 3): Lazy `_get_bm25_encoder()` wrapper removed entirely. Direct top-level import: `from rag.shared.bm25.bm25_encoder import BM25SparseEncoder`. Cross-tree coupling eliminated.

- File: `rag/retrival/query_retrival/retriever.py` (line 46) — ✅ **FIXED (Step 1)**
  - ~~Issue: `sys.path.insert(0, ...)` mutates the global import path at module import time.~~
  - Fix applied: `sys.path.insert` removed. `sys` and `os` imports also removed since they were only used for path manipulation.

- File: `rag/retrival/query_retrival/tests/smoketest/smoke_dense.py` (line 38), `smoke_dense_multi.py` (line 34) — ✅ **FIXED (Step 4)**
  - ~~Issue: Both smoke tests still use `sys.path.insert` to walk up three directory levels.~~
  - Fix applied: `sys.path.insert` removed from both files; bare-name imports updated to `rag.*`; `[tool.pytest.ini_options] pythonpath = ["."]` added to `pyproject.toml` so no manual path manipulation is ever needed again.
  - `smoke_hybrid.py` (line 48) — ✅ **FIXED (Step 1)**: `sys.path.insert` removed; imports updated to `rag.*`.

- File: `rag/retrival/query_retrival/tests/test_sparse_encoder_query.py` (lines 15–57) — ✅ **FIXED (Step 3)**
  - ~~PARTIALLY FIXED (Step 1): importlib bootstrap updated to use `rag.*` module names.~~
  - Fix applied (Step 3): Entire `importlib` bootstrap (40 lines) replaced with two plain imports: `from rag.shared.bm25.bm25_encoder import BM25SparseEncoder` and `from rag.shared.bm25.config import SPARSE_DIM`. No more `sys.modules` stubs needed.

- File: `rag/ingestion_pipeline/chunker/models.py` (line 27) and `rag/ingestion_pipeline/registry/registry.py` (lines 43–44) — ✅ **FIXED (Step 1)**
  - ~~Issue: expressed as bare names without root anchoring.~~
  - Fix applied: Root-anchored to `rag.ingestion_pipeline.*`. Dependency direction was already correct.

- File: `rag/ingestion_pipeline/pipeline.py` — `parser` name collision — ✅ **FIXED (Step 2)**
  - ~~Issue: `from parser import ...` and `from parser.document import ...` shadow Python's stdlib `parser` module. The local package named `parser/` is a reserved name conflict.~~
  - Fix applied: Renamed `rag/ingestion_pipeline/parser/` → `rag/ingestion_pipeline/pdf_parser/`. Updated four import sites: `pipeline.py` (line 56), `run.py` (line 3), `segmenter/iso_segmenter.py` (line 27), `segmenter/pipeline.py` (line 48). Internal files unchanged (relative imports). No logic changes.

---

## 3. OOP vs Functional Recommendations

- Component: `PageTracker` (`segmenter/page_tracker.py`)
  - Current: class
  - Recommendation: class
  - Reason: Holds sorted offset/page arrays built at construction time. State justifies the class. `page_at` and `page_range` are the natural public API for that state.

- Component: `Enricher` (`enricher/enricher.py`)
  - Current: class
  - Recommendation: class
  - Reason: Pre-computes corpus IDF in `__init__`, then applies it per chunk. The IDF cache is genuine shared state across `enrich()` calls. However, the docstring says "stateless post-processing pass" which contradicts its own `__init__` — the docstring should be corrected.

- Component: `BM25SparseEncoder` (`embedder/bm25_encoder.py`)
  - Current: class
  - Recommendation: class
  - Reason: Corpus statistics (DF, avgdl) are computed in `__init__` and reused per `encode()` call. `encode_query` is a `@staticmethod` and could be a module-level function — but keeping it on the class keeps the BM25 API surface cohesive.

- Component: `EmbedderService` (`embedder/embedder.py`)
  - Current: class
  - Recommendation: class
  - Reason: Manages an `httpx.AsyncClient`, a `Semaphore`, a fallback model, and a `_model_name`. Clear lifecycle (init → use → close). Class is correct.

- Component: `VectorStoreManager` (`vector_store/qdrant_store.py`)
  - Current: class
  - Recommendation: class
  - Reason: Holds a `QdrantClient` connection and a `_created_collections` set across calls. Lifecycle state justifies a class.

- Component: `detect_clause_boundaries`, `construct_clause_tree` (`segmenter/iso_segmenter.py`)
  - Current: functions
  - Recommendation: functions
  - Reason: Pure transformations with no retained state. Correct design. The private helpers are also correctly factored as module-level functions.

- Component: `assemble_norm_chunks` and helpers (`chunker/assembler.py`)
  - Current: functions
  - Recommendation: functions
  - Reason: All transformations are stateless. Module-level regex constants are correctly defined as module-level, not as class attributes.

- Component: `validate_chunks`, `write_registry` (`registry/registry.py`)
  - Current: functions
  - Recommendation: functions
  - Reason: Pure I/O transformations. `_ChunkValidator` is a Pydantic model used as a validation schema — correct; it is not a general-purpose class.

- Component: `HybridRetriever` (`query_retrival/retriever.py`)
  - Current: class
  - Recommendation: class
  - Reason: Holds an injected `embedder` and `qdrant` client. Dependency injection via `__init__` is correct. `DenseRetriever = HybridRetriever` alias is fine for backward compatibility.

- Component: `transform`, `scan_iso_vocabulary`, `augment_bm25_tokens`, `generate_hyde_text`, `build_norm_filter` (`query_transformer/Querytransformer.py`)
  - Current: functions (module-level)
  - Recommendation: functions
  - Reason: All are pure or async I/O functions with no shared state. No class is needed. Note: the module filename `Querytransformer.py` uses PascalCase, which is a Python naming convention violation — module files should be lowercase (`query_transformer.py`). There is already a `query_transformer/` package directory with the same conceptual name; the file inside it should be renamed to match convention.

- Component: `_ChunkValidator` inside `registry/registry.py`
  - Current: class (Pydantic model)
  - Recommendation: class
  - Reason: Schema-validation classes are the correct use of Pydantic. The underscore prefix correctly signals it is private to the module.

---

## 4. Key Global Issues

- ✅ **FIXED (Step 1)** — **No unified package root — two disconnected `sys.path` universes.** ~~`rag/ingestion_pipeline/` and `rag/retrival/` are treated as independent roots. There is no `pyproject.toml` or `setup.py` at the `rag/` or project level that installs either tree as a proper package. This forces every cross-boundary reference to use either `sys.path.insert` hacks or `importlib` surgery, both of which are brittle and invisible to static analysers.~~ → `pyproject.toml` created, `rag-iso` installed with `pip install -e .`.

- ✅ **FIXED (Step 2)** — **`parser` package name shadows the Python stdlib `parser` module.** ~~All files that write `from parser import ...` or `from parser.document import ...` are importing a local package with a reserved stdlib name. While Python 3.12 removed the stdlib `parser`, the pattern is a maintenance trap that confuses linters and any developer unfamiliar with the working directory convention.~~ → `rag/ingestion_pipeline/parser/` renamed to `rag/ingestion_pipeline/pdf_parser/`; all four import sites updated.

- ✅ **FIXED (Step 4)** — **Orphaned duplicate orchestrator `segmenter/pipeline.py`.** ~~A second, incomplete orchestrator exists inside the `segmenter/` package with identical function signatures to the real orchestrator (`segment_document`, `segment`, `embed_and_store`). It is never imported, is cut off mid-function, and documents a data flow that is inconsistent with the real pipeline. It will mislead contributors and could be accidentally wired in.~~ → File deleted.

- ✅ **FIXED (Step 3)** — **`BM25SparseEncoder` is shared across ingestion and retrieval but lives only in the ingestion tree.** ~~The `importlib` hack in `retriever.py` has been replaced with a clean lazy import now that all deps are installed. The `sys.modules` stub in the test has been updated to use correct `rag.*` module names.~~ → `BM25SparseEncoder` and `SPARSE_DIM` moved to `rag/shared/bm25/`. All four consumers updated to import from shared. `importlib` bootstrap in test replaced with 2-line import. Lazy `_get_bm25_encoder()` wrapper removed from `retriever.py`.

- ✅ **FIXED (Step 1)** — **`sys.path.insert` used at module import time in production code.** ~~`rag/retrival/query_retrival/retriever.py` (line 46) mutates `sys.path` when the module is first imported.~~ → `sys.path.insert` removed from `retriever.py` and `smoke_hybrid.py`. Remaining hacks in `smoke_dense.py` and `smoke_dense_multi.py` are addressed in Step 4.

---

## 5. Priority Fix Plan

- ✅ **DONE** — Step 1: **Add `pyproject.toml` at the project root and make `rag` an installable package.** `pyproject.toml` created; `rag-iso` installed with `pip install -e .`; all bare-name imports across 13 files updated to `rag.*`; all `sys.path.insert` hacks removed from `retriever.py` and `smoke_hybrid.py`; 50-line `importlib` hack in `retriever.py` replaced with a 2-line lazy import.

- ✅ **DONE** — Step 2: **Rename `rag/ingestion_pipeline/parser/` to `rag/ingestion_pipeline/pdf_parser/` and update all import sites.** Directory renamed; four import sites updated (`pipeline.py`, `run.py`, `iso_segmenter.py`, `segmenter/pipeline.py`). Parser's own `__init__.py` untouched (uses relative imports). No logic changes.

- ✅ **DONE** — Step 3: **Extract `BM25SparseEncoder` + `SPARSE_DIM` into `rag/shared/bm25/`.** `rag/shared/bm25/bm25_encoder.py` and `rag/shared/bm25/config.py` created. `embedder/bm25_encoder.py` deleted. `embedder/config.py` re-exports `SPARSE_DIM` from shared. Four consumers updated: `embedder/embedder.py`, `vector_store/qdrant_store.py` (3 fixes), `retriever.py` (lazy wrapper removed), `test_sparse_encoder_query.py` (importlib bootstrap removed).

- ✅ **DONE** — Step 4: **Delete `rag/ingestion_pipeline/segmenter/pipeline.py` and remove all `sys.path.insert` calls from retrieval code.** Orphaned `segmenter/pipeline.py` deleted. `sys.path.insert` removed from `smoke_dense.py` and `smoke_dense_multi.py`; bare-name imports updated to `rag.*`. `[tool.pytest.ini_options] pythonpath = ["."]` added to `pyproject.toml` — no more manual path hacks needed anywhere.

- Step 5 (longer-term): **Define a `ParsedDocument`-compatible protocol in `segmenter/` to decouple it from `pdf_parser/`.** `iso_segmenter.py` only reads `doc.markdown` and `doc.heading_positions` — it does not need the full `ParsedDocument` dataclass. Replacing the type annotation with a `typing.Protocol` removes the cross-layer import and makes the segmenter independently testable without constructing a `ParsedDocument`.

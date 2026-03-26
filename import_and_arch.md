# Import & Architecture Review

## 1. Import Root

The true import root is `rag/ingestion_pipeline/` for the ingestion side and `rag/retrival/` for the retrieval side. Both trees are invoked with their respective directory on `sys.path` (either via `cd rag/ingestion_pipeline && python run.py` or by the `sys.path.insert` hacks in the retrieval layer). There is **no single unified root**; the two sub-trees treat themselves as separate Python projects — `parser`, `segmenter`, `chunker`, `enricher`, `registry`, `embedder`, and `vector_store` are all bare top-level names relative to `rag/ingestion_pipeline/`, while `models`, `query_retrival`, `query_transformer`, and `clients` are bare names relative to `rag/retrival/`. This split is the root cause of every import anti-pattern in the project: there is no package anchoring at `rag/` or project root level, so every import that crosses the `ingestion_pipeline` / `retrival` boundary must resort to hacks.

---

## 2. Import Fixes

### Simple Fixes

- File: `rag/ingestion_pipeline/pipeline.py` (line 56)
  - ❌ `from parser.document import ParsedDocument`
  - ✅ `from rag.ingestion_pipeline.parser.document import ParsedDocument`
  - Note: `parser` is a Python stdlib module name. Shadowing it with a local package named `parser` is a latent collision bug. The package should be renamed (e.g. `pdf_parser`) or all imports must be root-anchored.

- File: `rag/ingestion_pipeline/pipeline.py` (lines 58–67)
  - ❌ `from chunker import NormChunk, assemble_norm_chunks`
  - ✅ `from rag.ingestion_pipeline.chunker import NormChunk, assemble_norm_chunks`
  - ❌ `from enricher import Enricher`
  - ✅ `from rag.ingestion_pipeline.enricher import Enricher`
  - ❌ `from registry import validate_chunks, write_registry`
  - ✅ `from rag.ingestion_pipeline.registry import validate_chunks, write_registry`
  - ❌ `from segmenter import (STANDARD_ID_MAP, ClauseNode, ...)`
  - ✅ `from rag.ingestion_pipeline.segmenter import (STANDARD_ID_MAP, ClauseNode, ...)`

- File: `rag/ingestion_pipeline/run.py` (lines 3–4)
  - ❌ `from parser import parse_iso_pdf`
  - ✅ `from rag.ingestion_pipeline.parser import parse_iso_pdf`
  - ❌ `from pipeline import segment, embed_and_store`
  - ✅ `from rag.ingestion_pipeline.pipeline import segment, embed_and_store`

- File: `rag/ingestion_pipeline/segmenter/iso_segmenter.py` (line 27)
  - ❌ `from parser.document import ParsedDocument`
  - ✅ `from rag.ingestion_pipeline.parser.document import ParsedDocument`

- File: `rag/ingestion_pipeline/segmenter/pipeline.py` (lines 48, 50)
  - ❌ `from parser.document import ParsedDocument`
  - ✅ `from rag.ingestion_pipeline.parser.document import ParsedDocument`
  - ❌ `from segmenter import (STANDARD_ID_MAP, ClauseNode, ...)`
  - ✅ `from rag.ingestion_pipeline.segmenter import (...)`

- File: `rag/ingestion_pipeline/chunker/assembler.py` (lines 40–47)
  - ❌ `from segmenter.models import (NORM_ID_MAP, NORM_VERSION_MAP, ...)`
  - ✅ `from rag.ingestion_pipeline.segmenter.models import (...)`
  - ❌ `from segmenter.page_tracker import PageTracker`
  - ✅ `from rag.ingestion_pipeline.segmenter.page_tracker import PageTracker`

- File: `rag/ingestion_pipeline/chunker/models.py` (line 27)
  - ❌ `from segmenter.models import ContentType`
  - ✅ `from rag.ingestion_pipeline.segmenter.models import ContentType`

- File: `rag/ingestion_pipeline/enricher/enricher.py` (line 29)
  - ❌ `from chunker.models import NormChunk`
  - ✅ `from rag.ingestion_pipeline.chunker.models import NormChunk`

- File: `rag/ingestion_pipeline/registry/registry.py` (lines 43–44)
  - ❌ `from chunker.models import NormChunk`
  - ✅ `from rag.ingestion_pipeline.chunker.models import NormChunk`
  - ❌ `from segmenter.models import ClauseNode`
  - ✅ `from rag.ingestion_pipeline.segmenter.models import ClauseNode`

- File: `rag/ingestion_pipeline/embedder/embedder.py` (lines 47–60)
  - ❌ `from chunker.models import NormChunk`
  - ✅ `from rag.ingestion_pipeline.chunker.models import NormChunk`
  - ❌ `from embedder.bm25_encoder import BM25SparseEncoder`
  - ✅ `from rag.ingestion_pipeline.embedder.bm25_encoder import BM25SparseEncoder`
  - ❌ `from embedder.config import (...)`
  - ✅ `from rag.ingestion_pipeline.embedder.config import (...)`
  - ❌ `from embedder.models import EmbeddedChunk, EmbeddingResult`
  - ✅ `from rag.ingestion_pipeline.embedder.models import EmbeddedChunk, EmbeddingResult`

- File: `rag/ingestion_pipeline/embedder/models.py` (line 17)
  - ❌ `from chunker.models import NormChunk`
  - ✅ `from rag.ingestion_pipeline.chunker.models import NormChunk`

- File: `rag/ingestion_pipeline/vector_store/qdrant_store.py` (line 42)
  - ❌ `from embedder.models import EmbeddedChunk`
  - ✅ `from rag.ingestion_pipeline.embedder.models import EmbeddedChunk`
  - Deferred imports inside `_write_sentinel` and `validate_model_consistency` (lines 109, 184): ❌ `from embedder.config import SPARSE_DIM` → ✅ `from rag.ingestion_pipeline.embedder.config import SPARSE_DIM`

- File: `rag/retrival/query_transformer/Querytransformer.py` (line 24)
  - ❌ `from models import TransformedQuery`
  - ✅ `from rag.retrival.models import TransformedQuery`

- File: `rag/retrival/query_retrival/retriever.py` (line 48)
  - ❌ `from models import RetrievedChunk, TransformedQuery`
  - ✅ `from rag.retrival.models import RetrievedChunk, TransformedQuery`

- File: `rag/retrival/query_retrival/tests/smoketest/smoke_dense.py` (line 43)
  - ❌ `from models import TransformedQuery`
  - ✅ `from rag.retrival.models import TransformedQuery`

- File: `rag/retrival/query_retrival/tests/smoketest/smoke_hybrid.py` (line 53)
  - ❌ `from models import TransformedQuery`
  - ✅ `from rag.retrival.models import TransformedQuery`

### Complex Fixes

- File: `rag/ingestion_pipeline/segmenter/iso_segmenter.py` (line 27)
  - Issue: `segmenter` imports `ParsedDocument` from `parser`. Per the documented dependency rule, `segmenter` should only depend on its own models and the stdlib. Importing from `parser` creates a backwards-direction dependency that couples Phase 2/3 to Phase 1.
  - Recommendation: Replace the `parser.document.ParsedDocument` import with a local protocol or a shared contracts module. `detect_clause_boundaries` only needs `doc.markdown` and `doc.heading_positions` — a `Protocol` or a plain dataclass in a shared `contracts` module avoids the cross-phase import entirely.

- File: `rag/ingestion_pipeline/segmenter/pipeline.py`
  - Issue: A second `pipeline.py` exists inside `segmenter/` with functions duplicating the top-level `pipeline.py` (same function names `segment_document`, `segment`, `embed_and_store`). It is incomplete (the file cuts off at line 96 mid-function), imports from `parser` and `segmenter` using bare names, and partially re-implements the orchestrator. This file is orphaned — nothing imports it — but its existence alongside the real orchestrator creates confusion and a maintenance hazard.
  - Recommendation: Delete `rag/ingestion_pipeline/segmenter/pipeline.py`. The only legitimate orchestrator is `rag/ingestion_pipeline/pipeline.py`.

- File: `rag/retrival/query_retrival/retriever.py` (lines 59–115)
  - Issue: `_get_bm25_encoder()` uses `importlib.util.spec_from_file_location` with hardcoded relative path traversal (`../../../ingestion_pipeline/embedder/`) to load `bm25_encoder.py` and `config.py` from the ingestion pipeline. This is a filesystem-path hack that bypasses the package system entirely, is fragile to directory renames, and silently registers fake module stubs into `sys.modules`.
  - Recommendation: Extract `BM25SparseEncoder` and its `config` into a shared library package (e.g. `rag/shared/bm25/`) that both `ingestion_pipeline` and `retrival` can import cleanly. Alternatively, publish it as a proper internal package (`rag.shared`). The core encoder has no ingestion-pipeline dependencies — only `hashlib`, `math`, and `collections` — so extraction is low-risk.

- File: `rag/retrival/query_retrival/retriever.py` (line 46)
  - Issue: `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` mutates the global import path at module import time. This makes the retrieval module non-importable from any other working directory without a side effect.
  - Recommendation: Remove the `sys.path` mutation. Establish `rag/retrival/` as a proper package with a `pyproject.toml` entry point, or run with `PYTHONPATH=rag/retrival` set in the shell / CI environment.

- File: `rag/retrival/query_retrival/tests/smoketest/smoke_dense.py` (line 38), `smoke_hybrid.py` (line 48), `smoke_dense_multi.py` (line 34)
  - Issue: All three smoke tests use `sys.path.insert` to walk up three directory levels to find `models.py`. This is equivalent to runtime sys.path surgery and breaks as soon as the test runner changes working directory.
  - Recommendation: Move smoke tests under a `tests/` folder anchored to the package root and use a `conftest.py` or `pyproject.toml` `[tool.pytest.ini_options] pythonpath` directive. Eliminates all path hacks.

- File: `rag/retrival/query_retrival/tests/test_sparse_encoder_query.py` (lines 27–55)
  - Issue: Uses `importlib.util` + manual `sys.modules` stub registration to load `embedder/bm25_encoder.py` from the ingestion pipeline tree. Same root cause as the `retriever.py` hack — no shared package exists.
  - Recommendation: Same as the `retriever.py` fix — extract `BM25SparseEncoder` into `rag/shared/`. Tests become a one-line import with no path manipulation.

- File: `rag/ingestion_pipeline/chunker/models.py` (line 27) and `rag/ingestion_pipeline/registry/registry.py` (lines 43–44)
  - Issue: `chunker.models` imports `ContentType` from `segmenter.models`. `registry.registry` imports both `NormChunk` from `chunker` and `ClauseNode` from `segmenter`. These are correct directional imports (chunker depends on segmenter, registry depends on both), but they are expressed as bare names without root anchoring, making them execution-directory-dependent.
  - Recommendation: Root-anchor all imports as described above. The dependency direction itself is correct.

- File: `rag/ingestion_pipeline/pipeline.py` — `parser` name collision
  - Issue: `from parser import parse_iso_pdf` and `from parser.document import ParsedDocument` shadow Python's stdlib `parser` module (present in Python 3.8; removed in 3.12 but the shadowing pattern is still a hazard and a readability trap). The local package named `parser/` is a reserved name conflict.
  - Recommendation: Rename `rag/ingestion_pipeline/parser/` to `rag/ingestion_pipeline/pdf_parser/` and update all imports. This is a one-time mechanical rename with zero logic change.

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

- **No unified package root — two disconnected `sys.path` universes.** `rag/ingestion_pipeline/` and `rag/retrival/` are treated as independent roots. There is no `pyproject.toml` or `setup.py` at the `rag/` or project level that installs either tree as a proper package. This forces every cross-boundary reference to use either `sys.path.insert` hacks or `importlib` surgery, both of which are brittle and invisible to static analysers.

- **`parser` package name shadows the Python stdlib `parser` module.** All files that write `from parser import ...` or `from parser.document import ...` are importing a local package with a reserved stdlib name. While Python 3.12 removed the stdlib `parser`, the pattern is a maintenance trap that confuses linters and any developer unfamiliar with the working directory convention.

- **Orphaned duplicate orchestrator `segmenter/pipeline.py`.** A second, incomplete orchestrator exists inside the `segmenter/` package with identical function signatures to the real orchestrator (`segment_document`, `segment`, `embed_and_store`). It is never imported, is cut off mid-function, and documents a data flow that is inconsistent with the real pipeline. It will mislead contributors and could be accidentally wired in.

- **`BM25SparseEncoder` is shared across ingestion and retrieval but lives only in the ingestion tree.** The retrieval layer needs the encoder at query time but cannot import it normally because the ingestion `embedder/__init__.py` cascades into `chunker.models` which is not present in the retrieval environment. This forces two separate workarounds (`importlib` hack in `retriever.py`, `sys.modules` stub in the test). The encoder itself has zero ingestion dependencies — it belongs in a shared package.

- **`sys.path.insert` used at module import time in production code.** `rag/retrival/query_retrival/retriever.py` (line 46) mutates `sys.path` when the module is first imported. This is production code, not a test helper. Any caller that imports `HybridRetriever` inherits a silently mutated path, making the import behaviour dependent on the order modules are loaded — a classic source of hard-to-diagnose `ImportError`s in multi-module applications.

---

## 5. Priority Fix Plan

- Step 1: **Add `pyproject.toml` at the project root and make `rag` an installable package.** Declare `rag/ingestion_pipeline/` and `rag/retrival/` as namespaced sub-packages (or as a single flat package). Once installed with `pip install -e .`, all bare-name imports become root-anchored automatically. This single change unblocks every subsequent fix and makes CI/CD possible. Zero business logic changes required.

- Step 2: **Rename `rag/ingestion_pipeline/parser/` to `rag/ingestion_pipeline/pdf_parser/` and update all import sites.** Eliminates the stdlib name collision. Purely mechanical: five import sites in `pipeline.py`, `run.py`, `iso_segmenter.py`, `segmenter/pipeline.py`, and the parser's own `__init__.py`. No logic changes.

- Step 3: **Extract `BM25SparseEncoder` + `embedder/config.py` into `rag/shared/bm25/`.** Move the encoder and its config constants to a shared location. Update `embedder/embedder.py`, `vector_store/qdrant_store.py`, `retriever.py`, and the test file to import from the shared location. Removes the `importlib` hack in `retriever.py` and the `sys.modules` stub in the test — both become normal imports. High-impact, low-risk: the encoder has no side effects and its public API is stable.

- Step 4: **Delete `rag/ingestion_pipeline/segmenter/pipeline.py` and remove all `sys.path.insert` calls from retrieval code.** The orphaned orchestrator duplicate is a documentation and maintenance hazard. The `sys.path.insert` in `retriever.py` and all three smoke tests should be replaced with proper `PYTHONPATH` configuration (via `pyproject.toml` `[tool.pytest.ini_options] pythonpath` or a `conftest.py`). After Step 1 these hacks are unnecessary.

- Step 5 (longer-term): **Define a `ParsedDocument`-compatible protocol in `segmenter/` to decouple it from `parser/`.** `iso_segmenter.py` only reads `doc.markdown` and `doc.heading_positions` — it does not need the full `ParsedDocument` dataclass. Replacing the type annotation with a `typing.Protocol` removes the cross-layer import and makes the segmenter independently testable without constructing a `ParsedDocument`.

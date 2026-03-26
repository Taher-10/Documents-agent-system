# Project Documentation: Structure and Imports

## Directory Tree

```text
Documents agent system/
    project_structure_and_imports.md
    requirements.txt
    run.py
    rag/
        __init__.py
        retrival/
            models.py
            clients/
                __init__.py
                llm_client.py
                vectorDbtest.py
            query_transformer/
                Querytransformer.py
                __init__.py
                query_transformer_design.md
                vocabulary.py
            query_retrival/
                __init__.py
                retriever.py
                tests/
                    __init__.py
                    test_sparse_encoder_query.py
                    smoketest/
                        smoke_dense.py
                        smoke_dense_multi.py
                        smoke_hybrid.py
        ingestion_pipeline/
            __init__.py
            pipeline.py
            run.py
            enricher/
                __init__.py
                enricher.py
            output/
                ISO-n14001-2015.md
            embedder/
                __init__.py
                bm25_encoder.py
                config.py
                embedder.py
                models.py
            docs/
                01_global_overview.md
                02_components.md
                03_data_flow.md
                04_architecture_insights.md
                05_adrs.md
                06_summary.md
                README.md
            parser/
                __init__.py
                config.py
                document.py
                patterns.py
                pipeline.py
                postprocess.py
                phases/
                    __init__.py
                    phase1_boilerplate.py
                    phase2_font.py
                    phase3_classify.py
                    phase4_format.py
                    phase5_tables.py
            vector_store/
                __init__.py
                qdrant_store.py
            registry/
                __init__.py
                registry.py
            segmenter/
                __init__.py
                iso_segmenter.py
                models.py
                page_tracker.py
                pipeline.py
            chunker/
                __init__.py
                assembler.py
                models.py
```

## Dependencies by Component

### Root Directory

#### `run.py`
- **Imports**: *None*

### Sub-component: `rag`

#### `__init__.py`
- **Imports**: *None*

### Sub-component: `rag/retrival`

#### `models.py`
- **Imports**:
  - `dataclasses.dataclass`
  - `dataclasses.field`
  - `qdrant_client.models.Filter`
  - `typing.List`

### Sub-component: `rag/retrival/clients`

#### `__init__.py`
- **Imports**:
  - `llm_client.chat_complete`

#### `llm_client.py`
- **Imports**:
  - `asyncio`
  - `openai.AsyncOpenAI`
  - `os`
  - `requests`
  - `typing.Any`

#### `vectorDbtest.py`
- **Imports**:
  - `__future__.annotations`
  - `os`
  - `qdrant_client.QdrantClient`
  - `qdrant_client.models.Distance`
  - `qdrant_client.models.FieldCondition`
  - `qdrant_client.models.Filter`
  - `qdrant_client.models.MatchValue`
  - `qdrant_client.models.PointIdsList`
  - `qdrant_client.models.PointStruct`
  - `qdrant_client.models.VectorParams`
  - `random`
  - `uuid`

### Sub-component: `rag/retrival/query_transformer`

#### `Querytransformer.py`
- **Imports**:
  - `asyncio`
  - `clients.llm_client.chat_complete`
  - `models.TransformedQuery`
  - `os`
  - `qdrant_client.models.FieldCondition`
  - `qdrant_client.models.Filter`
  - `qdrant_client.models.MatchAny`
  - `qdrant_client.models.MatchValue`
  - `re`
  - `typing.List`
  - `typing.Optional`
  - `typing.Set`
  - `vocabulary.ISO_VOCABULARY_EN`
  - `vocabulary.ISO_VOCABULARY_FR`

#### `__init__.py`
- **Imports**:
  - `Querytransformer.augment_bm25_tokens`
  - `Querytransformer.build_norm_filter`
  - `Querytransformer.generate_hyde_text`
  - `Querytransformer.scan_iso_vocabulary`
  - `Querytransformer.should_use_hyde`
  - `Querytransformer.transform`

#### `vocabulary.py`
- **Imports**: *None*

### Sub-component: `rag/retrival/query_retrival`

#### `__init__.py`
- **Imports**:
  - `retriever.DenseRetriever`
  - `retriever.EmptyCorpusError`
  - `retriever.HybridRetriever`

#### `retriever.py`
- **Imports**:
  - `__future__.annotations`
  - `importlib.util`
  - `models.RetrievedChunk`
  - `models.TransformedQuery`
  - `os`
  - `qdrant_client.QdrantClient`
  - `qdrant_client.models.Fusion`
  - `qdrant_client.models.FusionQuery`
  - `qdrant_client.models.Prefetch`
  - `qdrant_client.models.ScoredPoint`
  - `qdrant_client.models.SparseVector`
  - `query_retrival.embedder.EmbedderService`
  - `sys`
  - `types`
  - `typing.Any`
  - `typing.List`
  - `typing.TYPE_CHECKING`

### Sub-component: `rag/retrival/query_retrival/tests`

#### `__init__.py`
- **Imports**: *None*

#### `test_sparse_encoder_query.py`
- **Imports**:
  - `embedder.config.SPARSE_DIM`
  - `importlib.util`
  - `os`
  - `sys`
  - `types`
  - `unittest`

### Sub-component: `rag/retrival/query_retrival/tests/smoketest`

#### `smoke_dense.py`
- **Imports**:
  - `__future__.annotations`
  - `asyncio`
  - `models.TransformedQuery`
  - `os`
  - `qdrant_client.QdrantClient`
  - `qdrant_client.models.FieldCondition`
  - `qdrant_client.models.Filter`
  - `qdrant_client.models.MatchValue`
  - `query_retrival.retriever.DenseRetriever`
  - `query_retrival.retriever.EmptyCorpusError`
  - `requests`
  - `sys`

#### `smoke_dense_multi.py`
- **Imports**:
  - `__future__.annotations`
  - `asyncio`
  - `dataclasses.dataclass`
  - `models.RetrievedChunk`
  - `models.TransformedQuery`
  - `os`
  - `qdrant_client.QdrantClient`
  - `qdrant_client.models.FieldCondition`
  - `qdrant_client.models.Filter`
  - `qdrant_client.models.MatchValue`
  - `query_retrival.retriever.DenseRetriever`
  - `query_retrival.retriever.EmptyCorpusError`
  - `requests`
  - `sys`
  - `typing.List`

#### `smoke_hybrid.py`
- **Imports**:
  - `__future__.annotations`
  - `asyncio`
  - `models.TransformedQuery`
  - `os`
  - `qdrant_client.QdrantClient`
  - `qdrant_client.models.FieldCondition`
  - `qdrant_client.models.Filter`
  - `qdrant_client.models.MatchValue`
  - `query_retrival.retriever.EmptyCorpusError`
  - `query_retrival.retriever.HybridRetriever`
  - `requests`
  - `sys`

### Sub-component: `rag/ingestion_pipeline`

#### `__init__.py`
- **Imports**: *None*

#### `pipeline.py`
- **Imports**:
  - `__future__.annotations`
  - `asyncio`
  - `chunker.NormChunk`
  - `chunker.assemble_norm_chunks`
  - `dataclasses.dataclass`
  - `embedder.EmbedderService`
  - `embedder.EmbeddingResult`
  - `embedder.config.EMBED_CRITICAL_THRESHOLD`
  - `embedder.config.EMBED_WARNING_THRESHOLD`
  - `enricher.Enricher`
  - `parser.document.ParsedDocument`
  - `registry.validate_chunks`
  - `registry.write_registry`
  - `segmenter.ClauseNode`
  - `segmenter.PageTracker`
  - `segmenter.STANDARD_ID_MAP`
  - `segmenter.construct_clause_tree`
  - `segmenter.detect_clause_boundaries`
  - `typing.List`
  - `vector_store.VectorStoreManager`
  - `warnings`

#### `run.py`
- **Imports**:
  - `os`
  - `parser.parse_iso_pdf`
  - `pathlib.Path`
  - `pipeline.embed_and_store`
  - `pipeline.segment`

### Sub-component: `rag/ingestion_pipeline/enricher`

#### `__init__.py`
- **Imports**:
  - `enricher.Enricher`

#### `enricher.py`
- **Imports**:
  - `chunker.models.NormChunk`
  - `math`
  - `re`
  - `typing.Dict`
  - `typing.List`

### Sub-component: `rag/ingestion_pipeline/embedder`

#### `__init__.py`
- **Imports**:
  - `embedder.EmbedderService`
  - `models.EmbeddedChunk`
  - `models.EmbeddingResult`

#### `bm25_encoder.py`
- **Imports**:
  - `__future__.annotations`
  - `chunker.models.NormChunk`
  - `collections.Counter`
  - `config.SPARSE_DIM`
  - `hashlib.md5`
  - `math`
  - `typing.Dict`
  - `typing.List`
  - `typing.TYPE_CHECKING`
  - `typing.Tuple`

#### `config.py`
- **Imports**:
  - `os`

#### `embedder.py`
- **Imports**:
  - `__future__.annotations`
  - `asyncio`
  - `chunker.models.NormChunk`
  - `embedder.bm25_encoder.BM25SparseEncoder`
  - `embedder.config.EMBED_BATCH_SIZE`
  - `embedder.config.EMBED_CONTENT_TYPES`
  - `embedder.config.EMBED_MAX_RETRIES`
  - `embedder.config.EMBED_RETRY_BASE_DELAY`
  - `embedder.config.EMBED_RETRY_JITTER`
  - `embedder.config.EMBED_RETRY_MAX_DELAY`
  - `embedder.config.MAX_CONCURRENT_REQUESTS`
  - `embedder.config.OLLAMA_EMBED_ENDPOINT`
  - `embedder.config.OLLAMA_EMBED_MODEL`
  - `embedder.models.EmbeddedChunk`
  - `embedder.models.EmbeddingResult`
  - `httpx`
  - `random`
  - `sentence_transformers.SentenceTransformer`
  - `typing.List`
  - `typing.Optional`
  - `warnings`

#### `models.py`
- **Imports**:
  - `__future__.annotations`
  - `chunker.models.NormChunk`
  - `dataclasses.dataclass`
  - `dataclasses.field`
  - `typing.List`

### Sub-component: `rag/ingestion_pipeline/parser`

#### `__init__.py`
- **Imports**:
  - `document.ParsedDocument`
  - `pipeline.parse_iso_pdf`

#### `config.py`
- **Imports**: *None*

#### `document.py`
- **Imports**:
  - `dataclasses.dataclass`

#### `patterns.py`
- **Imports**:
  - `re`

#### `pipeline.py`
- **Imports**:
  - `collections.Counter`
  - `config._DEBUG_SCORES`
  - `config._score_log`
  - `document.ParsedDocument`
  - `fitz`
  - `pathlib.Path`
  - `patterns.ANNEX_RE`
  - `patterns.CLAUSE_START_RE`
  - `pdfplumber`
  - `phases.phase1_boilerplate.detect_headers_footers`
  - `phases.phase2_font.build_font_hierarchy`
  - `phases.phase2_font.compute_doc_stats`
  - `phases.phase2_font.get_block_dominant_size`
  - `phases.phase2_font.get_block_text`
  - `phases.phase4_format.format_block_as_markdown`
  - `phases.phase5_tables.extract_tables_with_pdfplumber`
  - `postprocess.is_toc_page`
  - `postprocess.normalize_whitespace`
  - `postprocess.remove_page_numbers`
  - `re`

#### `postprocess.py`
- **Imports**:
  - `re`

### Sub-component: `rag/ingestion_pipeline/parser/phases`

#### `__init__.py`
- **Imports**: *None*

#### `phase1_boilerplate.py`
- **Imports**:
  - `config.HEADER_FOOTER_MAX_CHARS`
  - `config.HEADER_FOOTER_THRESHOLD`
  - `config.HEADER_FOOTER_ZONE`
  - `config.SAMPLE_PAGES`
  - `patterns._CONTROL_CHARS_RE`

#### `phase2_font.py`
- **Imports**:
  - `config.FONT_GAP_TOLERANCE`
  - `config.MIN_HEADING_CHARS_FLOOR`
  - `config.MIN_HEADING_CHARS_PCT`
  - `phase1_boilerplate._clean`

#### `phase3_classify.py`
- **Imports**:
  - `config.FONT_GAP_TOLERANCE`
  - `config.HEADING_SCORE_THRESHOLD`
  - `config.HEADING_STRUCTURAL_SCORE_THRESHOLD`
  - `config.SHORT_TEXT_THRESHOLD`
  - `config.UPPERCASE_RATIO_THRESHOLD`
  - `config.VERTICAL_GAP_MULTIPLIER`
  - `config._DEBUG_SCORES`
  - `config._score_log`
  - `patterns.ANNEX_RE`
  - `patterns.ISO_SECTION_RE`
  - `phase2_font.get_block_dominant_size`
  - `phase2_font.get_block_text`

#### `phase4_format.py`
- **Imports**:
  - `patterns._PAGE_NUMBER_RE`
  - `phase2_font.get_block_dominant_size`
  - `phase2_font.get_block_text`
  - `phase3_classify.classify_block`

#### `phase5_tables.py`
- **Imports**: *None*

### Sub-component: `rag/ingestion_pipeline/vector_store`

#### `__init__.py`
- **Imports**:
  - `qdrant_store.VectorStoreManager`

#### `qdrant_store.py`
- **Imports**:
  - `__future__.annotations`
  - `embedder.config.SPARSE_DIM`
  - `embedder.models.EmbeddedChunk`
  - `os`
  - `qdrant_client.QdrantClient`
  - `qdrant_client.models.Distance`
  - `qdrant_client.models.PointStruct`
  - `qdrant_client.models.SparseIndexParams`
  - `qdrant_client.models.SparseVector`
  - `qdrant_client.models.SparseVectorParams`
  - `qdrant_client.models.VectorParams`
  - `typing.List`
  - `typing.Optional`
  - `typing.Set`
  - `uuid`
  - `warnings`

### Sub-component: `rag/ingestion_pipeline/registry`

#### `__init__.py`
- **Imports**:
  - `registry.validate_chunks`
  - `registry.write_registry`

#### `registry.py`
- **Imports**:
  - `chunker.models.NormChunk`
  - `dataclasses`
  - `datetime`
  - `json`
  - `os`
  - `pydantic.BaseModel`
  - `pydantic.ConfigDict`
  - `pydantic.field_validator`
  - `pydantic.model_validator`
  - `re`
  - `segmenter.models.ClauseNode`
  - `typing.List`
  - `warnings`

### Sub-component: `rag/ingestion_pipeline/segmenter`

#### `__init__.py`
- **Imports**:
  - `iso_segmenter.construct_clause_tree`
  - `iso_segmenter.detect_clause_boundaries`
  - `models.ClauseNode`
  - `models.ClauseSpan`
  - `models.ContentType`
  - `models.EXPECTED_LEAF_COUNTS`
  - `models.NORM_ID_MAP`
  - `models.NORM_VERSION_MAP`
  - `models.STANDARD_ID_MAP`
  - `page_tracker.PageTracker`

#### `iso_segmenter.py`
- **Imports**:
  - `models.ClauseNode`
  - `models.ClauseSpan`
  - `models.EXPECTED_LEAF_COUNTS`
  - `parser.document.ParsedDocument`
  - `re`
  - `typing.List`
  - `warnings`

#### `models.py`
- **Imports**:
  - `__future__.annotations`
  - `dataclasses.dataclass`
  - `dataclasses.field`
  - `enum.Enum`
  - `typing.Dict`
  - `typing.List`
  - `typing.Tuple`

#### `page_tracker.py`
- **Imports**:
  - `bisect`
  - `warnings`

#### `pipeline.py`
- **Imports**:
  - `__future__.annotations`
  - `asyncio`
  - `dataclasses.dataclass`
  - `parser.document.ParsedDocument`
  - `segmenter.ClauseNode`
  - `segmenter.PageTracker`
  - `segmenter.STANDARD_ID_MAP`
  - `segmenter.construct_clause_tree`
  - `segmenter.detect_clause_boundaries`
  - `typing.List`
  - `warnings`

### Sub-component: `rag/ingestion_pipeline/chunker`

#### `__init__.py`
- **Imports**:
  - `assembler.assemble_norm_chunks`
  - `assembler.build_chunk_id`
  - `models.NormChunk`

#### `assembler.py`
- **Imports**:
  - `json`
  - `models.NormChunk`
  - `os`
  - `re`
  - `segmenter.models.ClauseSpan`
  - `segmenter.models.ContentType`
  - `segmenter.models.NORM_ID_MAP`
  - `segmenter.models.NORM_VERSION_MAP`
  - `segmenter.models.STANDARD_ID_MAP`
  - `segmenter.page_tracker.PageTracker`
  - `typing.List`
  - `typing.Tuple`
  - `urllib.request`
  - `warnings`

#### `models.py`
- **Imports**:
  - `__future__.annotations`
  - `dataclasses.dataclass`
  - `dataclasses.field`
  - `segmenter.models.ContentType`
  - `typing.List`


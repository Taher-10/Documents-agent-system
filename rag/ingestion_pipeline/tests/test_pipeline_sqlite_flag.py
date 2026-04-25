from __future__ import annotations

from types import SimpleNamespace

from rag.ingestion_pipeline import pipeline


def _stub_core_pipeline(monkeypatch, result):
    monkeypatch.setattr(pipeline, "segment_document", lambda doc, language="": result)
    monkeypatch.setattr(pipeline, "validate_chunks", lambda chunks: 0)
    monkeypatch.setattr(
        pipeline,
        "write_registry",
        lambda result, output_dir="output": f"{output_dir}/registry.json",
    )
    monkeypatch.setattr(
        pipeline,
        "write_normid_clause_keywords_registry",
        lambda result, output_dir="output": f"{output_dir}/keywords.json",
    )
    monkeypatch.setattr(
        pipeline,
        "write_normid_clause_bm25_registry",
        lambda result, output_dir="output": f"{output_dir}/bm25.json",
    )


def test_segment_calls_sqlite_writer_when_explicitly_enabled(monkeypatch, tmp_path) -> None:
    result = SimpleNamespace(standard_id="ISO 9001:2015", tree=SimpleNamespace(children=[]), chunks=[])
    _stub_core_pipeline(monkeypatch, result)

    calls = {}

    def _write_sqlite(result, db_path, if_exists):
        calls["db_path"] = db_path
        calls["if_exists"] = if_exists
        return 0

    monkeypatch.setattr(pipeline, "write_sqlite_clause_registry", _write_sqlite)

    pipeline.segment(
        doc=SimpleNamespace(),
        output_dir=str(tmp_path),
        sqlite_registry_enabled=True,
        sqlite_db_path=str(tmp_path / "custom.db"),
        sqlite_if_exists="upsert",
    )

    assert calls["db_path"] == str(tmp_path / "iso_clauses.db")
    assert calls["if_exists"] == "upsert"


def test_segment_uses_env_defaults_for_sqlite_when_enabled(monkeypatch, tmp_path) -> None:
    result = SimpleNamespace(standard_id="ISO 9001:2015", tree=SimpleNamespace(children=[]), chunks=[])
    _stub_core_pipeline(monkeypatch, result)

    calls = {}

    def _write_sqlite(result, db_path, if_exists):
        calls["db_path"] = db_path
        calls["if_exists"] = if_exists
        return 0

    monkeypatch.setattr(pipeline, "write_sqlite_clause_registry", _write_sqlite)
    monkeypatch.setenv("SQLITE_REGISTRY_ENABLED", "true")
    monkeypatch.delenv("SQLITE_REGISTRY_PATH", raising=False)
    monkeypatch.delenv("SQLITE_REGISTRY_IF_EXISTS", raising=False)

    pipeline.segment(doc=SimpleNamespace(), output_dir=str(tmp_path))

    assert calls["db_path"] == pipeline._default_sqlite_registry_path()
    assert calls["if_exists"] == "skip"


def test_segment_uses_env_sqlite_if_exists(monkeypatch, tmp_path) -> None:
    result = SimpleNamespace(standard_id="ISO 9001:2015", tree=SimpleNamespace(children=[]), chunks=[])
    _stub_core_pipeline(monkeypatch, result)

    calls = {}

    def _write_sqlite(result, db_path, if_exists):
        calls["if_exists"] = if_exists
        return 0

    monkeypatch.setattr(pipeline, "write_sqlite_clause_registry", _write_sqlite)
    monkeypatch.setenv("SQLITE_REGISTRY_ENABLED", "true")
    monkeypatch.setenv("SQLITE_REGISTRY_IF_EXISTS", "error")

    pipeline.segment(doc=SimpleNamespace(), output_dir=str(tmp_path))

    assert calls["if_exists"] == "error"


def test_segment_skips_sqlite_writer_when_disabled(monkeypatch, tmp_path) -> None:
    result = SimpleNamespace(standard_id="ISO 9001:2015", tree=SimpleNamespace(children=[]), chunks=[])
    _stub_core_pipeline(monkeypatch, result)

    called = {"value": False}

    def _write_sqlite(result, db_path, if_exists):
        called["value"] = True
        return 0

    monkeypatch.setattr(pipeline, "write_sqlite_clause_registry", _write_sqlite)
    monkeypatch.setenv("SQLITE_REGISTRY_ENABLED", "false")

    pipeline.segment(doc=SimpleNamespace(), output_dir=str(tmp_path))

    assert called["value"] is False

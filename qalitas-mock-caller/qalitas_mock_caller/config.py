from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    agent_base_url: str
    agent_analyze_path: str
    agent_timeout_seconds: float
    agent_repo_root: Path
    qalitas_db_path: Path
    qalitas_db_init_sql: Path
    qalitas_docs_dir: Path

    @property
    def analyze_url(self) -> str:
        base = self.agent_base_url.rstrip("/")
        path = self.agent_analyze_path
        if not path.startswith("/"):
            path = "/" + path
        return f"{base}{path}"


def load_settings() -> Settings:
    repo_root_default = Path(__file__).resolve().parents[2]
    timeout_raw = os.getenv("AGENT_TIMEOUT_SECONDS", "120")

    try:
        timeout = float(timeout_raw)
    except ValueError:
        timeout = 30.0

    repo_root = Path(os.getenv("AGENT_REPO_ROOT", str(repo_root_default))).expanduser().resolve()
    db_path = Path(os.getenv("QALITAS_DB_PATH", str(repo_root / "qalitas-mock-caller" / "db" / "qalitas_mock.db"))).expanduser().resolve()
    db_init_sql = Path(
        os.getenv(
            "QALITAS_DB_INIT_SQL",
            str(repo_root / "qalitas-mock-caller" / "db" / "init_mock_sqlite.sql"),
        )
    ).expanduser().resolve()
    docs_dir = Path(
        os.getenv(
            "QALITAS_DOCS_DIR",
            str(repo_root / "qalitas-mock-caller" / "storage" / "docs"),
        )
    ).expanduser().resolve()

    return Settings(
        agent_base_url=os.getenv("AGENT_BASE_URL", "http://127.0.0.1:8000"),
        agent_analyze_path=os.getenv("AGENT_ANALYZE_PATH", "/analyze"),
        agent_timeout_seconds=max(timeout, 1.0),
        agent_repo_root=repo_root,
        qalitas_db_path=db_path,
        qalitas_db_init_sql=db_init_sql,
        qalitas_docs_dir=docs_dir,
    )

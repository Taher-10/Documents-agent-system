from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class AnalyzeSession(BaseModel):
    company_id: UUID
    site_id: UUID
    user_id: UUID


class AnalyzeDocument(BaseModel):
    id: UUID
    code: str = Field(min_length=1)
    designation: str = Field(min_length=1)
    version: str = Field(min_length=1)
    type_designation: str = Field(min_length=1)
    Q: bool
    E: bool
    S: bool
    H: bool
    file_path: str = Field(min_length=1)

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, value: str) -> str:
        raw = value.strip()
        if not raw:
            raise ValueError("file_path must not be empty")
        if PurePosixPath(raw).is_absolute() or PureWindowsPath(raw).is_absolute():
            raise ValueError("file_path must be relative")
        parts = PurePosixPath(raw).parts
        if any(part == ".." for part in parts):
            raise ValueError("file_path must not contain '..'")
        return raw


class AnalyzeOptions(BaseModel):
    format: Literal["json", "pdf", "docx"] = "json"


class AnalyzeRequest(BaseModel):
    session: AnalyzeSession
    document: AnalyzeDocument
    options: AnalyzeOptions = Field(default_factory=AnalyzeOptions)


class CoverageItem(BaseModel):
    clause: str
    status: Literal["COVERED", "PARTIAL", "MISSING"]
    evidence: str
    gaps: list[str]
    confidence: float


class ActionItem(BaseModel):
    action: str
    clause: str
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    section: str


class ReportPayload(BaseModel):
    executive_summary: str
    coverage_matrix: list[CoverageItem]
    action_plan: list[ActionItem]
    overall_status: Literal["COVERED", "PARTIAL", "MISSING"]


class AnalyzeSuccessResponse(BaseModel):
    status: Literal["completed"]
    doc_id: str
    doc_code: str
    sections_analyzed: int
    sections_skipped: int
    applicable_norms: list[str]
    report: ReportPayload
    report_url: str | None = None


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    code: str
    detail: str
    errors: list[dict] | None = None

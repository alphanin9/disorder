from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FlagVerification(BaseModel):
    method: Literal["platform_submit", "local_check", "regex_only", "none"]
    verified: bool
    details: str


class DeliverableEntry(BaseModel):
    path: str
    type: Literal["solve_script", "exploit", "binary", "writeup", "other"]
    how_to_run: str


class EvidenceEntry(BaseModel):
    kind: Literal["command", "file", "log", "decompiler"]
    ref: str
    summary: str


class SandboxResult(BaseModel):
    challenge_id: str
    challenge_name: str
    status: Literal["flag_found", "deliverable_produced", "blocked"]
    stop_criterion_met: Literal["primary", "secondary", "none"]
    flag: str | None = None
    flag_verification: FlagVerification
    deliverables: list[DeliverableEntry] = Field(default_factory=list)
    repro_steps: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    evidence: list[EvidenceEntry] = Field(default_factory=list)
    notes: str = ""

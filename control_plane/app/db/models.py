import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from control_plane.app.db.base import Base


class IntegrationConfig(Base):
    __tablename__ = "integration_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CTFIntegrationConfig(Base):
    __tablename__ = "ctf_integration_configs"
    __table_args__ = (
        UniqueConstraint("ctf_id", "provider", name="uq_ctf_integration_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ctf_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ctf_events.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    ctf: Mapped["CTFEvent"] = relationship(back_populates="integration_configs")


class CTFEvent(Base):
    __tablename__ = "ctf_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    default_flag_regex: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    challenges: Mapped[list["ChallengeManifest"]] = relationship(back_populates="ctf")
    integration_configs: Mapped[list["CTFIntegrationConfig"]] = relationship(
        back_populates="ctf",
        cascade="all, delete-orphan",
    )


class ChallengeManifest(Base):
    __tablename__ = "challenge_manifests"
    __table_args__ = (
        UniqueConstraint(
            "ctf_id",
            "platform",
            "platform_challenge_id",
            name="uq_ctf_platform_challenge_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ctf_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ctf_events.id", ondelete="RESTRICT"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_challenge_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description_md: Mapped[str] = mapped_column(Text, nullable=False)
    description_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifacts: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    remote_endpoints: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    local_deploy_hints: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    flag_regex: Mapped[str | None] = mapped_column(String(512), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    ctf: Mapped[CTFEvent] = relationship(back_populates="challenges")
    runs: Mapped[list["Run"]] = relationship(
        back_populates="challenge", cascade="all, delete-orphan"
    )
    flag_submissions: Mapped[list["FlagSubmissionAttempt"]] = relationship(
        back_populates="challenge",
        cascade="all, delete-orphan",
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("challenge_manifests.id", ondelete="CASCADE"), nullable=False
    )
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("runs.id", ondelete="RESTRICT"), nullable=True
    )
    continuation_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    continuation_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    continuation_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    backend: Mapped[str] = mapped_column(String(32), nullable=False)
    budgets: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    stop_criteria: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    agent_invocation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    auto_continuation_policy: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    runner_loop_policy: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    allowed_endpoints: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    paths: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    local_deploy: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    continuation_origin: Mapped[str] = mapped_column(
        String(32), nullable=False, default="operator"
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="queued")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    challenge: Mapped[ChallengeManifest] = relationship(back_populates="runs")
    parent_run: Mapped["Run | None"] = relationship(
        remote_side=[id], back_populates="child_runs", foreign_keys=[parent_run_id]
    )
    child_runs: Mapped[list["Run"]] = relationship(
        back_populates="parent_run", foreign_keys=[parent_run_id]
    )
    result: Mapped["RunResult | None"] = relationship(
        back_populates="run", uselist=False, cascade="all, delete-orphan"
    )
    flag_submissions: Mapped[list["FlagSubmissionAttempt"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class RunResult(Base):
    __tablename__ = "run_results"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json_object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    logs_object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    finalization_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    run: Mapped[Run] = relationship(back_populates="result")


class FlagSubmissionAttempt(Base):
    __tablename__ = "flag_submission_attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("challenge_manifests.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    auth_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    submission_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    verdict_normalized: Mapped[str] = mapped_column(
        String(64), nullable=False, default="unknown"
    )
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_payload_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    response_payload_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    run: Mapped[Run] = relationship(back_populates="flag_submissions")
    challenge: Mapped[ChallengeManifest] = relationship(
        back_populates="flag_submissions"
    )

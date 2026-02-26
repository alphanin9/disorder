"""per-ctf ctfd config, submission audit table, and scoped challenge uniqueness

Revision ID: 0004_ctfd_per_ctf_cfg
Revises: 0003_run_continuation
Create Date: 2026-02-26 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_ctfd_per_ctf_cfg"
down_revision: str | None = "0003_run_continuation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ctf_integration_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ctf_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["ctf_id"], ["ctf_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ctf_id", "provider", name="uq_ctf_integration_provider"),
    )
    op.create_index("ix_ctf_integration_configs_ctf_id", "ctf_integration_configs", ["ctf_id"], unique=False)

    op.create_table(
        "flag_submission_attempts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("challenge_id", sa.UUID(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("auth_mode", sa.String(length=32), nullable=True),
        sa.Column("submission_hash", sa.String(length=64), nullable=False),
        sa.Column("verdict_normalized", sa.String(length=64), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("request_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["challenge_id"], ["challenge_manifests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_flag_submission_attempts_run_id", "flag_submission_attempts", ["run_id"], unique=False)
    op.create_index("ix_flag_submission_attempts_challenge_id", "flag_submission_attempts", ["challenge_id"], unique=False)
    op.create_index("ix_flag_submission_attempts_submitted_at", "flag_submission_attempts", ["submitted_at"], unique=False)

    op.drop_constraint("uq_platform_challenge_id", "challenge_manifests", type_="unique")
    op.create_unique_constraint(
        "uq_ctf_platform_challenge_id",
        "challenge_manifests",
        ["ctf_id", "platform", "platform_challenge_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_ctf_platform_challenge_id", "challenge_manifests", type_="unique")
    op.create_unique_constraint("uq_platform_challenge_id", "challenge_manifests", ["platform", "platform_challenge_id"])

    op.drop_index("ix_flag_submission_attempts_submitted_at", table_name="flag_submission_attempts")
    op.drop_index("ix_flag_submission_attempts_challenge_id", table_name="flag_submission_attempts")
    op.drop_index("ix_flag_submission_attempts_run_id", table_name="flag_submission_attempts")
    op.drop_table("flag_submission_attempts")

    op.drop_index("ix_ctf_integration_configs_ctf_id", table_name="ctf_integration_configs")
    op.drop_table("ctf_integration_configs")

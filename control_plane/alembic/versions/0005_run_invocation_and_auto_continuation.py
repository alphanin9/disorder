"""run invocation and auto continuation metadata

Revision ID: 0005_run_inv_cfg
Revises: 0004_ctfd_per_ctf_cfg
Create Date: 2026-03-12 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_run_inv_cfg"
down_revision: str | None = "0004_ctfd_per_ctf_cfg"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column(
            "agent_invocation",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "runs",
        sa.Column(
            "auto_continuation_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "runs",
        sa.Column(
            "continuation_origin",
            sa.String(length=32),
            nullable=False,
            server_default="operator",
        ),
    )
    op.add_column(
        "run_results",
        sa.Column(
            "finalization_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.alter_column("runs", "agent_invocation", server_default=None)
    op.alter_column("runs", "continuation_origin", server_default=None)


def downgrade() -> None:
    op.drop_column("run_results", "finalization_metadata")
    op.drop_column("runs", "continuation_origin")
    op.drop_column("runs", "auto_continuation_policy")
    op.drop_column("runs", "agent_invocation")

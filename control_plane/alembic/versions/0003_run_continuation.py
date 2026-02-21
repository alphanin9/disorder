"""add run continuation lineage metadata

Revision ID: 0003_run_continuation
Revises: 0002_ctf_events
Create Date: 2026-02-21 06:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_run_continuation"
down_revision: str | None = "0002_ctf_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("parent_run_id", sa.UUID(), nullable=True))
    op.add_column("runs", sa.Column("continuation_depth", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("runs", sa.Column("continuation_input", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("continuation_type", sa.String(length=32), nullable=True))

    op.create_index("ix_runs_parent_run_id", "runs", ["parent_run_id"], unique=False)
    op.create_foreign_key(
        "fk_runs_parent_run_id",
        "runs",
        "runs",
        ["parent_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.alter_column("runs", "continuation_depth", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_runs_parent_run_id", "runs", type_="foreignkey")
    op.drop_index("ix_runs_parent_run_id", table_name="runs")

    op.drop_column("runs", "continuation_type")
    op.drop_column("runs", "continuation_input")
    op.drop_column("runs", "continuation_depth")
    op.drop_column("runs", "parent_run_id")

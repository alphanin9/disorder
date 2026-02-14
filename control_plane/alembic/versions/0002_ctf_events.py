"""add ctf grouping and challenge ownership

Revision ID: 0002_ctf_events
Revises: 0001_initial
Create Date: 2026-02-15 01:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_ctf_events"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_CTF_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "ctf_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=True),
        sa.Column("default_flag_regex", sa.String(length=512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.add_column("challenge_manifests", sa.Column("ctf_id", sa.UUID(), nullable=True))

    op.execute(
        sa.text(
            f"""
            INSERT INTO ctf_events (id, name, slug, platform, default_flag_regex, notes)
            VALUES ('{DEFAULT_CTF_ID}'::uuid, 'Default CTF', 'default-ctf', 'manual', 'flag\\{{.*?\\}}', 'Auto-generated default CTF event')
            ON CONFLICT (slug) DO NOTHING
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE challenge_manifests
            SET ctf_id = (SELECT id FROM ctf_events WHERE slug = 'default-ctf' LIMIT 1)
            WHERE ctf_id IS NULL
            """
        )
    )

    op.alter_column("challenge_manifests", "ctf_id", nullable=False)
    op.create_foreign_key(
        "fk_challenge_manifests_ctf_id",
        "challenge_manifests",
        "ctf_events",
        ["ctf_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_challenge_manifests_ctf_id", "challenge_manifests", type_="foreignkey")
    op.drop_column("challenge_manifests", "ctf_id")
    op.drop_table("ctf_events")

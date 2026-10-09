"""Add concise reference notes.

Revision ID: 0003
Revises: 0002
"""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "subject_id",
            sa.Integer(),
            sa.ForeignKey("subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "section_id",
            sa.Integer(),
            sa.ForeignKey("sections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_document_id",
            sa.Integer(),
            sa.ForeignKey("lecture_sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_page", sa.String(100)),
        sa.Column("note_type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "note_type IN ('formula', 'theorem', 'concept', 'procedure')",
            name="ck_note_type",
        ),
    )
    op.create_index("ix_notes_subject_id", "notes", ["subject_id"])
    op.create_index("ix_notes_section_id", "notes", ["section_id"])
    op.create_index(
        "ix_notes_source_document_id", "notes", ["source_document_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_notes_source_document_id", table_name="notes")
    op.drop_index("ix_notes_section_id", table_name="notes")
    op.drop_index("ix_notes_subject_id", table_name="notes")
    op.drop_table("notes")

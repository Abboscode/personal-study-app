"""Add persistent lecture sources and optional question links.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lecture_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "subject_id",
            sa.Integer(),
            sa.ForeignKey("subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("page_count", sa.Integer()),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "subject_id", "file_hash", name="uq_lecture_source_subject_hash"
        ),
    )
    op.create_index(
        "ix_lecture_sources_subject_id", "lecture_sources", ["subject_id"]
    )
    op.add_column(
        "questions", sa.Column("source_document_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_questions_source_document_id_lecture_sources",
        "questions",
        "lecture_sources",
        ["source_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_questions_source_document_id", "questions", ["source_document_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_questions_source_document_id", table_name="questions")
    op.drop_constraint(
        "fk_questions_source_document_id_lecture_sources",
        "questions",
        type_="foreignkey",
    )
    op.drop_column("questions", "source_document_id")
    op.drop_index("ix_lecture_sources_subject_id", table_name="lecture_sources")
    op.drop_table("lecture_sources")

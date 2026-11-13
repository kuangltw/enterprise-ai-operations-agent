"""建立文件版本的持久索引工作登錄表。"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_document_index_jobs"
down_revision = "0008_document_user_acl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_index_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "document_version_id",
                            name="uq_document_index_jobs_version"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["document_versions.tenant_id", "document_versions.id"],
            name="fk_document_index_jobs_version",
        ),
        sa.CheckConstraint("status IN ('pending','processing','completed','failed')",
                           name="ck_document_index_jobs_status"),
        sa.CheckConstraint("attempt_count >= 0",
                           name="ck_document_index_jobs_attempt_count"),
    )


def downgrade() -> None:
    op.drop_table("document_index_jobs")

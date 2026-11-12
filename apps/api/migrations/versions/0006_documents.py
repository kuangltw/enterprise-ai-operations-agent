"""建立文件中繼資料、版本及租戶隔離的 ACL 基礎。

Revision ID: 0006_documents
Revises: 0005_tenant_warehouses
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_documents"
down_revision = "0005_tenant_warehouses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_documents_tenant_id"),
        sa.CheckConstraint("status IN ('active','deleted')", name="ck_documents_status"),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_documents_title_not_blank"),
        sa.CheckConstraint("current_version IS NULL OR current_version > 0",
                           name="ck_documents_current_version_positive"),
    )
    op.create_table(
        "document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column("indexing_status", sa.String(20), nullable=False,
                  server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_document_versions_tenant_id"),
        sa.UniqueConstraint("tenant_id", "document_id", "version",
                            name="uq_document_versions_number"),
        sa.ForeignKeyConstraint(["tenant_id", "document_id"],
                                ["documents.tenant_id", "documents.id"],
                                name="fk_document_versions_document"),
        sa.CheckConstraint("version > 0", name="ck_document_versions_number"),
        sa.CheckConstraint("length(trim(storage_key)) > 0",
                           name="ck_document_versions_storage_key_not_blank"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'",
                           name="ck_document_versions_sha256"),
        sa.CheckConstraint("indexing_status IN ('pending','processing','ready','failed')",
                           name="ck_document_versions_indexing_status"),
    )
    op.create_foreign_key(
        "fk_documents_current_version", "documents", "document_versions",
        ["tenant_id", "id", "current_version"],
        ["tenant_id", "document_id", "version"],
    )
    op.create_table(
        "document_acl",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "document_id", "role"),
        sa.ForeignKeyConstraint(["tenant_id", "document_id"],
                                ["documents.tenant_id", "documents.id"],
                                name="fk_document_acl_document", ondelete="CASCADE"),
        sa.CheckConstraint("role IN ('admin','manager','staff','viewer')",
                           name="ck_document_acl_role"),
    )


def downgrade() -> None:
    op.drop_table("document_acl")
    op.drop_constraint("fk_documents_current_version", "documents", type_="foreignkey")
    op.drop_table("document_versions")
    op.drop_table("documents")

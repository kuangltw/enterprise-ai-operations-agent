"""建立待對帳的退役文件物件鍵；不回填既有版本。"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_document_retired_keys"
down_revision = "0009_document_index_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_document_versions_tenant_document_id", "document_versions",
        ["tenant_id", "document_id", "id"],
    )
    op.create_table(
        "document_upload_retired_keys",
        sa.Column("storage_key", sa.Text(), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id", "document_version_id"],
            ["document_versions.tenant_id", "document_versions.document_id",
             "document_versions.id"],
            name="fk_retired_keys_version", ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "storage_key ~ ('^' || tenant_id::text || '/' || document_id::text || '/' || "
            "document_version_id::text || '/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            "[0-9a-f]{4}-[0-9a-f]{12}\\.pdf$')",
            name="ck_retired_keys_canonical",
        ),
    )


def downgrade() -> None:
    # 同交易先排除並行寫入，避免檢查後新墓碑被 DROP TABLE 一併刪除。
    # DO 區塊讓 Alembic 離線產生的 SQL 也保有相同的保護。
    op.execute("LOCK TABLE document_upload_retired_keys IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM document_upload_retired_keys) THEN
                RAISE EXCEPTION '退役鍵紀錄非空，禁止降版刪除對帳依據';
            END IF;
        END
        $$
    """)
    op.drop_table("document_upload_retired_keys")
    op.drop_constraint("uq_document_versions_tenant_document_id", "document_versions",
                       type_="unique")

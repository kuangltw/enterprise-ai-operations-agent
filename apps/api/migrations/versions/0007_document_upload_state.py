"""記錄文件版本的原始檔儲存狀態及租戶內冪等識別。"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_document_upload_state"
down_revision = "0006_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column("storage_status", sa.String(20), nullable=False,
                  server_default="pending_upload"),
    )
    op.add_column(
        "document_versions",
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_document_versions_storage_status", "document_versions",
        "storage_status IN ('pending_upload','stored','failed')",
    )
    op.create_unique_constraint(
        "uq_document_versions_idempotency_key", "document_versions",
        ["tenant_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_document_versions_idempotency_key", "document_versions", type_="unique")
    op.drop_constraint("ck_document_versions_storage_status", "document_versions", type_="check")
    op.drop_column("document_versions", "idempotency_key")
    op.drop_column("document_versions", "storage_status")

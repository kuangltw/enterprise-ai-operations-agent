"""新增僅授予指定租戶成員的文件存取權限。"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_document_user_acl"
down_revision = "0007_document_upload_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_user_acl",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "document_id", "user_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"],
            name="fk_document_user_acl_document", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"], ["memberships.tenant_id", "memberships.user_id"],
            name="fk_document_user_acl_membership", ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("document_user_acl")

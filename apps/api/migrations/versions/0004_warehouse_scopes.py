"""將倉庫授權範圍綁定至租戶成員資格。

Revision ID: 0004_warehouse_scopes
Revises: 0003_email_case_unique
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_warehouse_scopes"
down_revision = "0003_email_case_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "membership_warehouse_scopes",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("warehouse_code", sa.String(80), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "user_id", "warehouse_code"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"], ["memberships.tenant_id", "memberships.user_id"],
            ondelete="CASCADE", name="fk_scope_membership",
        ),
        sa.CheckConstraint("length(trim(warehouse_code)) > 0", name="ck_scope_code_not_blank"),
    )


def downgrade() -> None:
    op.drop_table("membership_warehouse_scopes")

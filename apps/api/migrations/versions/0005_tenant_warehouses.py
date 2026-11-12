"""建立租戶倉庫登錄與授權範圍的租戶歸屬約束。

Revision ID: 0005_tenant_warehouses
Revises: 0004_warehouse_scopes
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_tenant_warehouses"
down_revision = "0004_warehouse_scopes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_warehouses",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("warehouse_code", sa.String(80), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "warehouse_code"),
        sa.UniqueConstraint("warehouse_code", name="uq_tenant_warehouses_code"),
        sa.CheckConstraint("length(trim(warehouse_code)) > 0", name="ck_tenant_warehouse_code_not_blank"),
    )
    op.create_foreign_key(
        "fk_scope_tenant_warehouse", "membership_warehouse_scopes", "tenant_warehouses",
        ["tenant_id", "warehouse_code"], ["tenant_id", "warehouse_code"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_scope_tenant_warehouse", "membership_warehouse_scopes", type_="foreignkey")
    op.drop_table("tenant_warehouses")

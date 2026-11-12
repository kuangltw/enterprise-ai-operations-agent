"""新增可撤銷的使用者工作階段。

Revision ID: 0002_sessions
Revises: 0001_identity
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_sessions"
down_revision = "0001_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("expires_at > created_at", name="ck_sessions_expires_after_creation"),
        sa.CheckConstraint("revoked_at IS NULL OR revoked_at >= created_at", name="ck_sessions_revoked_after_creation"),
    )
    op.create_index("ix_sessions_user_expires", "sessions", ["user_id", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_sessions_user_expires", table_name="sessions")
    op.drop_table("sessions")

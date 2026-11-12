"""阻止 Email 只差大小寫的重複使用者。

Revision ID: 0003_email_case_unique
Revises: 0002_sessions
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_email_case_unique"
down_revision = "0002_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ux_users_email_lower", "users", [sa.text("lower(email)")], unique=True)


def downgrade() -> None:
    op.drop_index("ux_users_email_lower", table_name="users")

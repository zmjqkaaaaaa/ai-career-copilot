"""Create users and personal profiles."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

revision = "20261120_0001"
down_revision = None
branch_labels = None
depends_on = None

def timestamps():
    return (
        sa.Column("created_at", DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.Column("updated_at", DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")),
    )

def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254, collation="utf8mb4_bin"), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        *timestamps(),
        sa.UniqueConstraint("email", name="uq_users_email"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("real_name", sa.String(100)),
        sa.Column("undergraduate_school", sa.String(150)),
        sa.Column("undergraduate_major", sa.String(150)),
        sa.Column("undergraduate_degree", sa.String(80)),
        sa.Column("graduate_school", sa.String(150)),
        sa.Column("graduate_major", sa.String(150)),
        sa.Column("graduation_year", sa.Integer()),
        sa.Column("target_position", sa.String(150)),
        sa.Column("interested_industries", sa.JSON(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("internship_experience", sa.JSON(), nullable=False),
        sa.Column("project_experience", sa.JSON(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_profiles_user_id_users", ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_user_profiles_user_id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )

def downgrade():
    op.drop_table("user_profiles")
    op.drop_table("users")

"""link recommendation to project workspace"""
from alembic import op
import sqlalchemy as sa


revision = '20261121_0008'
down_revision = '20261121_0007'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('github_repositories', sa.Column('recommendation_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_github_repositories_recommendation_id'), 'github_repositories', ['recommendation_id'], unique=False)
    op.create_foreign_key('fk_workspace_recommendation', 'github_repositories', 'project_recommendations',
                          ['recommendation_id'], ['id'], ondelete='SET NULL')

def downgrade():
    op.drop_constraint('fk_workspace_recommendation', 'github_repositories', type_='foreignkey')
    op.drop_index(op.f('ix_github_repositories_recommendation_id'), table_name='github_repositories')
    op.drop_column('github_repositories', 'recommendation_id')

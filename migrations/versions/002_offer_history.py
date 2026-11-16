from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('drafts', sa.Column('committed_offers', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('drafts') as batch:
        batch.drop_column('committed_offers')

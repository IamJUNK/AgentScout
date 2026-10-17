"""Persist search budgets across attempts; keys are case sensitive."""
from alembic import op
import sqlalchemy as sa
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('research_tasks', sa.Column('max_search_calls',sa.Integer(),nullable=False,server_default='24'))
    op.add_column('task_attempts', sa.Column('search_usage',sa.Integer(),nullable=False,server_default='0'))
    op.add_column('task_attempts', sa.Column('search_limit',sa.Integer(),nullable=False,server_default='12'))
    op.execute("UPDATE task_attempts SET search_usage = COALESCE(JSON_EXTRACT(snapshot, '$.search_call_count'), 0)")
    op.alter_column('research_tasks','idempotency_key',existing_type=sa.String(128),type_=sa.String(128,collation='utf8mb4_bin'),existing_nullable=False)
    for table,column in [('research_tasks','max_search_calls'),('task_attempts','search_usage'),('task_attempts','search_limit')]:
        op.alter_column(table,column,existing_type=sa.Integer(),server_default=None)

def downgrade():
    op.drop_column('task_attempts','search_limit')
    op.drop_column('task_attempts','search_usage')
    op.drop_column('research_tasks','max_search_calls')

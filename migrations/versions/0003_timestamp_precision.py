"""Preserve subsecond state changes for cursor ordering and UI refresh."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME
revision='0003'
down_revision='0002'
branch_labels=None
depends_on=None

def upgrade():
    op.alter_column('research_tasks','created_at',existing_type=sa.DateTime(),type_=DATETIME(fsp=6),existing_nullable=False)
    for name in ('created_at','updated_at','started_at','ended_at','heartbeat_at','dispatch_after'):
        op.alter_column('task_attempts',name,existing_type=sa.DateTime(),type_=DATETIME(fsp=6),existing_nullable=name in {'started_at','ended_at','heartbeat_at'})

def downgrade():
    op.alter_column('research_tasks','created_at',existing_type=DATETIME(fsp=6),type_=sa.DateTime(),existing_nullable=False)
    for name in ('created_at','updated_at','started_at','ended_at','heartbeat_at','dispatch_after'):
        op.alter_column('task_attempts',name,existing_type=DATETIME(fsp=6),type_=sa.DateTime(),existing_nullable=name in {'started_at','ended_at','heartbeat_at'})

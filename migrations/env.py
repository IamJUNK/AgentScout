from alembic import context
from sqlalchemy import create_engine
from config import load_settings
from storage.orm import Base
url=load_settings().database_url
if not url.startswith('mysql+pymysql://'):
    raise RuntimeError('Set DATABASE_URL to a MySQL database before migration')
if context.is_offline_mode():
    context.configure(url=url,target_metadata=Base.metadata,literal_binds=True)
    with context.begin_transaction(): context.run_migrations()
else:
    engine=create_engine(url,pool_pre_ping=True)
    with engine.connect() as connection:
        context.configure(connection=connection,target_metadata=Base.metadata,compare_type=True)
        with context.begin_transaction(): context.run_migrations()

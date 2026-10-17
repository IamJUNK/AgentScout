from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, JSON, ForeignKey, UniqueConstraint, Index, Boolean, DateTime, Float
from sqlalchemy.dialects.mysql import LONGTEXT, DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Base(DeclarativeBase):
    pass

Timestamp = DateTime().with_variant(DATETIME(fsp=6), 'mysql')

class ResearchTask(Base):
    __tablename__ = 'research_tasks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128, collation='utf8mb4_bin'), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict] = mapped_column(JSON)
    current_attempt_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(Timestamp, default=now, index=True)
    max_tokens: Mapped[int] = mapped_column(Integer)
    max_search_calls: Mapped[int] = mapped_column(Integer, default=24)
    __table_args__ = (Index('ix_task_cursor', 'created_at', 'id'),)

class Attempt(Base):
    __tablename__ = 'task_attempts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('research_tasks.id'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    execution_status: Mapped[str] = mapped_column(String(24), default='pending_dispatch', index=True)
    quality_status: Mapped[str] = mapped_column(String(32), default='unassessed')
    created_at: Mapped[datetime] = mapped_column(Timestamp, default=now)
    updated_at: Mapped[datetime] = mapped_column(Timestamp, default=now, index=True)
    started_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    execution_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    dispatch_count: Mapped[int] = mapped_column(Integer, default=0)
    dispatch_after: Mapped[datetime] = mapped_column(Timestamp, default=now)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    reserved_tokens: Mapped[int] = mapped_column(Integer, default=0)
    token_limit: Mapped[int] = mapped_column(Integer)
    search_usage: Mapped[int] = mapped_column(Integer, default=0)
    search_limit: Mapped[int] = mapped_column(Integer, default=12)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint('task_id', 'number'),)

class Source(Base):
    __tablename__ = 'source_documents'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey('task_attempts.id'), index=True)
    source_id: Mapped[str] = mapped_column(String(80))
    url: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, 'mysql'))
    metadata_json: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('attempt_id','source_id'),)

class Evidence(Base):
    __tablename__ = 'evidence_chunks'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey('task_attempts.id'), index=True)
    evidence_id: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('attempt_id','evidence_id'),)

class Report(Base):
    __tablename__ = 'reports'
    attempt_id: Mapped[str] = mapped_column(ForeignKey('task_attempts.id'), primary_key=True)
    markdown: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, 'mysql'))
    structured: Mapped[dict] = mapped_column(JSON)
    review: Mapped[dict] = mapped_column(JSON)
    quality_status: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer, default=1)

class Event(Base):
    __tablename__ = 'execution_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey('task_attempts.id'), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('attempt_id','sequence'),)

class ExternalCall(Base):
    __tablename__ = 'external_calls'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey('task_attempts.id'), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('attempt_id','sequence'),)

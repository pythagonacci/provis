"""
Database models and configuration for Provis Step 2 infrastructure.
"""
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text, ForeignKey, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from typing import Optional

Base = declarative_base()

class Repo(Base):
    __tablename__ = "repos"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=True)
    owner_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    snapshots = relationship("Snapshot", back_populates="repo")

class Snapshot(Base):
    __tablename__ = "snapshots"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("repos.id"), nullable=False)
    commit_hash = Column(String(64), nullable=False)
    settings_hash = Column(String(64), nullable=False)
    source = Column(String(50), default="upload")
    status = Column(String(50), default="processing")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    repo = relationship("Repo", back_populates="snapshots")
    jobs = relationship("Job", back_populates="snapshot")
    artifacts = relationship("Artifact", back_populates="snapshot")
    warnings = relationship("Warning", back_populates="snapshot")

class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("repos.id"), nullable=False)
    snapshot_id = Column(UUID(as_uuid=True), ForeignKey("snapshots.id"), nullable=False)
    phase = Column(String(50), default="queued")
    pct = Column(Integer, default=0)
    priority = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    snapshot = relationship("Snapshot", back_populates="jobs")
    tasks = relationship("Task", back_populates="job")
    events = relationship("Event", back_populates="job")

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    name = Column(String(100), nullable=False)  # ingest/discover/parse_batch/merge/map/summarize/finalize
    batch_index = Column(Integer, nullable=True)
    state = Column(String(50), default="queued")  # queued/running/done/failed
    attempt = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    
    # Relationships
    job = relationship("Job", back_populates="tasks")

class Artifact(Base):
    __tablename__ = "artifacts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id = Column(UUID(as_uuid=True), ForeignKey("snapshots.id"), nullable=False)
    kind = Column(String(50), nullable=False)  # files/graph/summaries/capabilities/metrics/tree
    version = Column(Integer, nullable=False)
    uri = Column(String(500), nullable=False)
    bytes = Column(Integer, nullable=False)
    schema_version = Column(Integer, default=1)
    generator_version = Column(String(50), default="1.0.0")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    snapshot = relationship("Snapshot", back_populates="artifacts")

class Event(Base):
    __tablename__ = "events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    type = Column(String(100), nullable=False)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    job = relationship("Job", back_populates="events")

class Warning(Base):
    __tablename__ = "warnings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    snapshot_id = Column(UUID(as_uuid=True), ForeignKey("snapshots.id"), nullable=False)
    file_path = Column(String(500), nullable=True)
    code = Column(String(100), nullable=True)  # parse_timeout, unresolved_import, etc.
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    job = relationship("Job")
    snapshot = relationship("Snapshot", back_populates="warnings")

# Database configuration
def get_database_url() -> str:
    """Get database URL from environment or default to local PostgreSQL."""
    import os
    return os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/provis")

def create_engine_instance():
    """Create SQLAlchemy engine with proper configuration."""
    return create_engine(
        get_database_url(),
        pool_pre_ping=True,
        pool_recycle=300,
        echo=False
    )

def get_session():
    """Get database session."""
    engine = create_engine_instance()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()

# Initialize database
def init_db():
    """Initialize database tables."""
    engine = create_engine_instance()
    Base.metadata.create_all(bind=engine)

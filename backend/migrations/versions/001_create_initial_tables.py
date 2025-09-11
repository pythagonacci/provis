"""Create initial tables for Step 2 infrastructure

Revision ID: 001
Revises: 
Create Date: 2025-01-10 19:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create repos table
    op.create_table('repos',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('owner_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create snapshots table
    op.create_table('snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('repo_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('commit_hash', sa.String(length=64), nullable=False),
        sa.Column('settings_hash', sa.String(length=64), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['repo_id'], ['repos.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('repo_id', 'commit_hash', 'settings_hash')
    )
    
    # Create jobs table
    op.create_table('jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('repo_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('snapshot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('phase', sa.String(length=50), nullable=True),
        sa.Column('pct', sa.Integer(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['repo_id'], ['repos.id'], ),
        sa.ForeignKeyConstraint(['snapshot_id'], ['snapshots.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create tasks table
    op.create_table('tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('batch_index', sa.Integer(), nullable=True),
        sa.Column('state', sa.String(length=50), nullable=True),
        sa.Column('attempt', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create artifacts table
    op.create_table('artifacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('snapshot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('kind', sa.String(length=50), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('uri', sa.String(length=500), nullable=False),
        sa.Column('bytes', sa.Integer(), nullable=False),
        sa.Column('schema_version', sa.Integer(), nullable=True),
        sa.Column('generator_version', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['snapshot_id'], ['snapshots.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('snapshot_id', 'kind', 'version')
    )
    
    # Create events table
    op.create_table('events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', sa.String(length=100), nullable=False),
        sa.Column('payload', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create warnings table
    op.create_table('warnings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('snapshot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=True),
        sa.Column('code', sa.String(length=100), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
        sa.ForeignKeyConstraint(['snapshot_id'], ['snapshots.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_snapshots_repo_id', 'snapshots', ['repo_id'])
    op.create_index('ix_jobs_repo_id', 'jobs', ['repo_id'])
    op.create_index('ix_jobs_snapshot_id', 'jobs', ['snapshot_id'])
    op.create_index('ix_tasks_job_id', 'tasks', ['job_id'])
    op.create_index('ix_tasks_state', 'tasks', ['state'])
    op.create_index('ix_artifacts_snapshot_id', 'artifacts', ['snapshot_id'])
    op.create_index('ix_events_job_id', 'events', ['job_id'])
    op.create_index('ix_events_created_at', 'events', ['created_at'])
    op.create_index('ix_warnings_job_id', 'warnings', ['job_id'])


def downgrade() -> None:
    op.drop_index('ix_warnings_job_id', table_name='warnings')
    op.drop_index('ix_events_created_at', table_name='events')
    op.drop_index('ix_events_job_id', table_name='events')
    op.drop_index('ix_artifacts_snapshot_id', table_name='artifacts')
    op.drop_index('ix_tasks_state', table_name='tasks')
    op.drop_index('ix_tasks_job_id', table_name='tasks')
    op.drop_index('ix_jobs_snapshot_id', table_name='jobs')
    op.drop_index('ix_jobs_repo_id', table_name='jobs')
    op.drop_index('ix_snapshots_repo_id', table_name='snapshots')
    
    op.drop_table('warnings')
    op.drop_table('events')
    op.drop_table('artifacts')
    op.drop_table('tasks')
    op.drop_table('jobs')
    op.drop_table('snapshots')
    op.drop_table('repos')

# Provis Step 2 Infrastructure - Runbook

## Overview

This document describes how to run and operate the Provis Step 2 infrastructure upgrade, which transforms Provis from a single-process system to a robust, scalable queue + worker architecture.

## Architecture

### Core Components

1. **Postgres**: Persistent storage for repos, snapshots, jobs, tasks, artifacts, events, and warnings
2. **Redis**: Real-time status overlay, event streaming, and task queues
3. **S3/MinIO**: Versioned artifact storage
4. **FastAPI**: Thin API layer for uploads, status, and artifact serving
5. **RQ Workers**: External processes executing discrete, idempotent tasks

### Data Flow

```
Upload → Ingest Task → Discover Task → Parse Batch Tasks → Merge Task → Map Task → Summarize Task → Finalize Task
```

## Prerequisites

### Required Services

1. **PostgreSQL** (v13+)
2. **Redis** (v6+)
3. **S3-compatible storage** (AWS S3 or MinIO)

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/provis

# Redis
REDIS_URL=redis://localhost:6379/0

# Storage
S3_BUCKET=provis-artifacts
S3_REGION=us-east-1
S3_ENDPOINT_URL=http://localhost:9000  # For MinIO
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin

# Resource Limits
NODE_SUBPROC_CONCURRENCY=2
NODE_FILE_TIMEOUT_S=20
NODE_BATCH_TIMEOUT_S=120
LLM_TPM=10000
LLM_RPM=100
MAX_UPLOAD_BYTES=536870912  # 512MB

# Security
ZIP_MAX_ENTRIES=60000
ZIP_MAX_DEPTH=20
ZIP_MAX_UNCOMPRESSED_BYTES=1073741824  # 1GB
ZIP_MAX_RATIO=200
```

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements-step2.txt
```

### 2. Set Up Database

```bash
# Create database
createdb provis

# Run migrations
cd backend
python -m alembic upgrade head
```

### 3. Set Up Redis

```bash
# Start Redis server
redis-server

# Verify connection
redis-cli ping
```

### 4. Set Up Storage (MinIO)

```bash
# Download and start MinIO
wget https://dl.min.io/server/minio/release/linux-amd64/minio
chmod +x minio
./minio server /tmp/minio --console-address ":9001"

# Create bucket
mc alias set local http://localhost:9000 minioadmin minioadmin
mc mb local/provis-artifacts
```

## Running the System

### 1. Start the API Server

```bash
cd backend
uvicorn app.main_new:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Start Workers

```bash
# Start worker for all queues
cd backend
python workers/worker.py --queues high normal low

# Or start separate workers for different priorities
python workers/worker.py --queues high --name high-priority-worker
python workers/worker.py --queues normal --name normal-priority-worker
python workers/worker.py --queues low --name low-priority-worker
```

### 3. Monitor the System

```bash
# Check Redis queues
redis-cli
> LLEN rq:queue:high
> LLEN rq:queue:normal
> LLEN rq:queue:low

# Check job status
curl http://localhost:8000/status/{job_id}

# Stream job events
curl -N http://localhost:8000/jobs/{job_id}/events
```

## API Endpoints

### Core Endpoints

- `POST /ingest` - Upload repository zip and start processing
- `GET /status/{job_id}` - Get job status with real-time progress
- `GET /jobs/{job_id}/events` - Stream job events as SSE
- `GET /repos/{repo_id}/snapshots/{snapshot_id}/artifacts` - List artifacts

### Artifact Endpoints

- `GET /repo/{repo_id}/graph` - Get dependency graph
- `GET /repo/{repo_id}/files` - Get parsed files
- `GET /repo/{repo_id}/capabilities` - Get capabilities
- `GET /repo/{repo_id}/metrics` - Get processing metrics

### Monitoring

- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics

## Task Types

### 1. Ingest Task
- **Purpose**: Extract zip and compute hashes
- **Queue**: High priority
- **Idempotency**: Check existing snapshots by hash

### 2. Discover Task
- **Purpose**: Find files in snapshot
- **Queue**: Normal priority
- **Output**: File count and list

### 3. Parse Batch Task
- **Purpose**: Parse batch of files (50 files per batch)
- **Queue**: Normal priority
- **Parallelization**: Multiple batches can run concurrently
- **Resource Limits**: Node subprocess concurrency limits

### 4. Merge Files Task
- **Purpose**: Combine parsed results and validate schema
- **Queue**: Normal priority
- **Output**: files.v{n}.json artifact

### 5. Map Task
- **Purpose**: Build dependency graph
- **Queue**: Normal priority
- **Output**: graph.v{n}.json artifact

### 6. Summarize Task
- **Purpose**: Generate LLM summaries and capabilities
- **Queue**: Low priority
- **Resource Limits**: LLM rate limiting
- **Output**: summaries.v{n}.json and capabilities.v{n}.json

### 7. Finalize Task
- **Purpose**: Complete job and write metrics
- **Queue**: High priority
- **Output**: metrics.v{n}.json artifact

## Event Types

### Job Events
- `upload_received` - Upload received and validated
- `cache_hit` - Snapshot already exists (idempotency)
- `phase` - Phase change (discovering, parsing, mapping, summarizing, done)
- `progress` - Progress update with percentage
- `files_total` - Total files discovered
- `batch_parsed` - Parse batch completed
- `artifact_ready` - Artifact written and available
- `imports_metrics` - Import statistics
- `warning` - Warning during processing
- `error` - Error occurred
- `done` - Job completed successfully

## Artifact Storage

### Structure
```
s3://bucket/repos/{repo_id}/snapshots/{commit_hash}/{settings_hash}/{kind}.v{n}.json
```

### Artifact Types
- `tree` - Directory structure (optional early)
- `files` - Parsed file data
- `graph` - Dependency graph
- `summaries` - LLM-generated summaries
- `capabilities` - Discovered capabilities
- `metrics` - Processing metrics

### Versioning
- Artifacts are never overwritten
- Version numbers increment automatically
- Latest version is determined by highest number

## Monitoring and Observability

### Structured Logging
All logs are in JSON format with consistent fields:
```json
{
  "timestamp": "2024-01-10T19:45:00.000Z",
  "level": "INFO",
  "message": "Task completed",
  "job_id": "job_123",
  "task_name": "parse_batch",
  "duration_ms": 1500,
  "success": true
}
```

### Prometheus Metrics
- `provis_jobs_total` - Job counts by phase and status
- `provis_job_duration_ms` - Job duration histograms
- `provis_tasks_total` - Task counts by name and state
- `provis_task_duration_ms` - Task duration histograms
- `provis_files_parsed_total` - File parsing counts
- `provis_node_parse_ms` - Node.js subprocess duration
- `provis_imports_total` - Import processing counts
- `provis_artifacts_created_total` - Artifact creation counts
- `provis_queue_size` - Current queue sizes
- `provis_errors_total` - Error counts by component

### Health Checks
- API health: `GET /health`
- Database connectivity: Check Postgres connection
- Redis connectivity: Check Redis connection
- Storage connectivity: Check S3/MinIO connection

## Troubleshooting

### Common Issues

1. **Jobs stuck in "queued" state**
   - Check if workers are running
   - Check Redis connectivity
   - Check queue sizes: `redis-cli LLEN rq:queue:normal`

2. **Parse tasks failing**
   - Check Node.js subprocess limits
   - Check file permissions
   - Check memory limits

3. **Storage errors**
   - Check S3/MinIO connectivity
   - Check bucket permissions
   - Check disk space

4. **Database errors**
   - Check Postgres connectivity
   - Check migration status
   - Check connection pool limits

### Debugging Commands

```bash
# Check job status in database
psql provis -c "SELECT id, phase, pct, error FROM jobs WHERE id = 'job_id';"

# Check task status
psql provis -c "SELECT name, state, error FROM tasks WHERE job_id = 'job_id';"

# Check Redis keys
redis-cli KEYS "job:*"

# Check queue status
redis-cli LLEN rq:queue:high
redis-cli LLEN rq:queue:normal
redis-cli LLEN rq:queue:low

# Check worker status
ps aux | grep worker.py
```

## Security Considerations

### Zip Extraction
- Maximum entries: 60,000
- Maximum depth: 20 levels
- Maximum uncompressed size: 1GB
- Maximum compression ratio: 200:1
- Path traversal protection
- Reserved name protection (Windows)

### Resource Limits
- Node subprocess concurrency: 2
- Per-file timeout: 20 seconds
- Per-batch timeout: 120 seconds
- Memory limits: 512MB per worker
- CPU time limits: 1 hour per worker

### Network Security
- No network egress for parser processes
- Presigned URLs for artifact access
- CORS configuration for API access

## Performance Tuning

### Queue Configuration
- High priority: Critical tasks (ingest, finalize)
- Normal priority: Core processing (discover, parse, merge, map)
- Low priority: LLM work (summarize)

### Batch Sizes
- Parse batch size: 50 files (configurable)
- Adjust based on file complexity and worker capacity

### Resource Limits
- Node concurrency: Adjust based on CPU cores
- LLM limits: Adjust based on API quotas
- Memory limits: Adjust based on available RAM

## Migration from Step 1

### Backward Compatibility
- Legacy endpoints maintained with fallback to local files
- Gradual migration path available
- Existing artifacts can be imported

### Migration Steps
1. Deploy Step 2 infrastructure
2. Run database migrations
3. Start workers alongside existing system
4. Gradually migrate traffic to new endpoints
5. Remove legacy fallbacks once stable

## Scaling Considerations

### Horizontal Scaling
- Multiple worker processes
- Multiple API instances
- Redis clustering for high availability
- Database read replicas

### Vertical Scaling
- Increase worker memory limits
- Increase Node subprocess concurrency
- Increase LLM rate limits
- Increase storage capacity

### Load Balancing
- API instances behind load balancer
- Worker distribution across machines
- Queue sharding by repository ID
- Artifact storage distribution

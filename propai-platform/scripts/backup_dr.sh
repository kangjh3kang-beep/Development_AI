#!/bin/bash
# Reusable backup script for Disaster Recovery (DR)

set -e

# Default env vars if not set
POSTGRES_USER=${POSTGRES_USER:-propai_user}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-propai_pass_dev}
POSTGRES_HOST=${POSTGRES_HOST:-localhost}
POSTGRES_PORT=${POSTGRES_PORT:-5432}
POSTGRES_DB=${POSTGRES_DB:-propai_db}

S3_BUCKET=${S3_BUCKET:-s3://propai-dr-backup}
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="propai_db_backup_${DATE}.sql.gz"

START_TIME=$(date +%s)

echo "[INFO] Starting database backup at $(date)"
export PGPASSWORD=$POSTGRES_PASSWORD

# Dump and compress
pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip -9 > "$BACKUP_FILE"
echo "[INFO] Backup created: $BACKUP_FILE"

# Upload to S3 if AWS CLI is installed
if command -v aws >/dev/null 2>&1; then
    echo "[INFO] Uploading to AWS S3 ($S3_BUCKET)..."
    aws s3 cp "$BACKUP_FILE" "$S3_BUCKET/$BACKUP_FILE" --storage-class STANDARD_IA
    echo "[INFO] Upload complete."
else
    echo "[WARN] aws-cli not found. Skipping S3 upload."
fi

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Log to DB (Phase 1 Part N table: backup_logs)
echo "[INFO] Logging backup attempt to database..."
psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "INSERT INTO backup_logs (filename, s3_path, duration_seconds, status, created_at) VALUES ('$BACKUP_FILE', '$S3_BUCKET/$BACKUP_FILE', $DURATION, 'SUCCESS', NOW());" || echo "[WARN] Failed to insert log to DB. Note: Make sure backup_logs table is created by alembic."

# Cleanup local file
rm "$BACKUP_FILE"
echo "[INFO] Local backup file removed. DR Backup process finished in ${DURATION}s."

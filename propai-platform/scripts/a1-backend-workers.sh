#!/usr/bin/env bash
# Restart backend A1 Celery worker and Flower with task-aware healthchecks.
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/Development_AI/propai-platform}"
IMAGE="${PROPAI_API_IMAGE:-propai-api:latest}"
DOCKER_BIN="${DOCKER_BIN:-docker}"
CELERY_APP="${CELERY_APP:-app.tasks.celery_app:app}"
WORKER_NAME="${CELERY_WORKER_NAME:-propai-celery-worker}"
FLOWER_NAME="${CELERY_FLOWER_NAME:-propai-celery-flower}"
BEAT_NAME="${CELERY_BEAT_NAME:-propai-celery-beat}"
QUEUES="${CELERY_WORKER_QUEUES:-parcel_batch,celery,rates,auction,growth}"
CONCURRENCY="${CELERY_WORKER_CONCURRENCY:-5}"
FLOWER_PORT="${CELERY_FLOWER_PORT:-5555}"
BEAT_LOGLEVEL="${CELERY_BEAT_LOGLEVEL:-info}"
BEAT_SCHEDULE_DIR="${CELERY_BEAT_SCHEDULE_DIR:-/var/lib/propai/celery}"
BEAT_SCHEDULE_FILE="${CELERY_BEAT_SCHEDULE_FILE:-$BEAT_SCHEDULE_DIR/celerybeat-schedule}"
ENV_FILE="$REPO_DIR/.env"

REQUIRED_TASKS=(
  "app.tasks.parcel_batch_task.run_batch"
  "app.tasks.rate_tasks.check_legal_rates"
  "app.tasks.auction_sync_task.sync_onbid_auctions"
  "app.tasks.growth_tasks.analyze_growth"
)

REQUIRED_QUEUES=(
  "parcel_batch"
  "celery"
  "rates"
  "auction"
  "growth"
)

cd "$REPO_DIR"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: .env not found in $REPO_DIR" >&2
  exit 1
fi

"$DOCKER_BIN" image inspect "$IMAGE" >/dev/null

prepare_beat_state() {
  if command -v sudo >/dev/null; then
    sudo mkdir -p "$BEAT_SCHEDULE_DIR"
    sudo chown -R 1001:1001 "$BEAT_SCHEDULE_DIR"
  else
    mkdir -p "$BEAT_SCHEDULE_DIR"
  fi
}

wait_for_running() {
  local name="$1"
  local status
  for _ in $(seq 1 60); do
    status="$("$DOCKER_BIN" inspect -f '{{.State.Status}}' "$name" 2>/dev/null || true)"
    if [ "$status" = "running" ]; then
      echo "$name status=$status"
      return 0
    fi
    sleep 2
  done
  echo "ERROR: $name did not become running" >&2
  "$DOCKER_BIN" logs --tail 120 "$name" 2>&1 || true
  exit 1
}

install_systemd_units() {
  local docker_path
  docker_path="$(command -v "$DOCKER_BIN")"

  cat >/tmp/propai-celery-worker.service <<UNIT
[Unit]
Description=PropAI Celery Worker (Operational Queues)
After=docker.service
Requires=docker.service

[Service]
Restart=always
RestartSec=10
ExecStartPre=-$docker_path rm -f $WORKER_NAME
ExecStart=$docker_path run --name $WORKER_NAME --rm --network host --env-file $ENV_FILE --no-healthcheck $IMAGE celery -A $CELERY_APP worker -Q $QUEUES --concurrency=$CONCURRENCY
ExecStop=$docker_path stop -t 10 $WORKER_NAME

[Install]
WantedBy=multi-user.target
UNIT

  cat >/tmp/propai-celery-flower.service <<UNIT
[Unit]
Description=PropAI Celery Flower (Monitoring)
After=docker.service propai-celery-worker.service
Requires=docker.service

[Service]
Restart=always
RestartSec=10
ExecStartPre=-$docker_path rm -f $FLOWER_NAME
ExecStart=$docker_path run --name $FLOWER_NAME --rm --network host --env-file $ENV_FILE --no-healthcheck $IMAGE celery -A $CELERY_APP flower --url_prefix=flower --port=$FLOWER_PORT
ExecStop=$docker_path stop -t 10 $FLOWER_NAME

[Install]
WantedBy=multi-user.target
UNIT

  cat >/tmp/propai-celery-beat.service <<UNIT
[Unit]
Description=PropAI Celery Beat Scheduler
After=docker.service propai-celery-worker.service
Requires=docker.service

[Service]
Restart=always
RestartSec=10
ExecStartPre=-$docker_path rm -f $BEAT_NAME
ExecStart=$docker_path run --name $BEAT_NAME --rm --network host --env-file $ENV_FILE --no-healthcheck -v $BEAT_SCHEDULE_DIR:$BEAT_SCHEDULE_DIR $IMAGE celery -A $CELERY_APP beat --loglevel=$BEAT_LOGLEVEL --schedule=$BEAT_SCHEDULE_FILE
ExecStop=$docker_path stop -t 10 $BEAT_NAME

[Install]
WantedBy=multi-user.target
UNIT

  sudo install -m 0644 /tmp/propai-celery-worker.service /etc/systemd/system/propai-celery-worker.service
  sudo install -m 0644 /tmp/propai-celery-flower.service /etc/systemd/system/propai-celery-flower.service
  sudo install -m 0644 /tmp/propai-celery-beat.service /etc/systemd/system/propai-celery-beat.service
  sudo systemctl daemon-reload
  sudo systemctl enable propai-celery-worker.service propai-celery-flower.service propai-celery-beat.service >/dev/null
  sudo systemctl restart propai-celery-worker.service
  sudo systemctl restart propai-celery-flower.service
  sudo systemctl restart propai-celery-beat.service
}

restart_direct_containers() {
  echo "== Restart Celery worker =="
  "$DOCKER_BIN" rm -f "$WORKER_NAME" >/dev/null 2>&1 || true
  "$DOCKER_BIN" run -d \
    --name "$WORKER_NAME" \
    --restart always \
    --network host \
    --env-file "$ENV_FILE" \
    --no-healthcheck \
    "$IMAGE" \
    celery -A "$CELERY_APP" worker -Q "$QUEUES" --concurrency="$CONCURRENCY"

  echo "== Restart Flower =="
  "$DOCKER_BIN" rm -f "$FLOWER_NAME" >/dev/null 2>&1 || true
  "$DOCKER_BIN" run -d \
    --name "$FLOWER_NAME" \
    --restart always \
    --network host \
    --env-file "$ENV_FILE" \
    --no-healthcheck \
    "$IMAGE" \
    celery -A "$CELERY_APP" flower --url_prefix=flower --port="$FLOWER_PORT"

  echo "== Restart Celery Beat =="
  "$DOCKER_BIN" rm -f "$BEAT_NAME" >/dev/null 2>&1 || true
  "$DOCKER_BIN" run -d \
    --name "$BEAT_NAME" \
    --restart always \
    --network host \
    --env-file "$ENV_FILE" \
    --no-healthcheck \
    -v "$BEAT_SCHEDULE_DIR:$BEAT_SCHEDULE_DIR" \
    "$IMAGE" \
    celery -A "$CELERY_APP" beat --loglevel="$BEAT_LOGLEVEL" --schedule="$BEAT_SCHEDULE_FILE"
}

verify_registered_tasks() {
  local tmp
  tmp="$(mktemp)"
  inspect_with_retry "registered" "$tmp"
  for task in "${REQUIRED_TASKS[@]}"; do
    if ! grep -Fq "$task" "$tmp"; then
      echo "ERROR: required Celery task is not registered: $task" >&2
      cat "$tmp" >&2
      rm -f "$tmp"
      exit 1
    fi
  done
  cat "$tmp"
  rm -f "$tmp"
}

inspect_with_retry() {
  local method="$1"
  local outfile="$2"
  local attempt
  for attempt in $(seq 1 12); do
    if "$DOCKER_BIN" exec "$WORKER_NAME" \
      celery -A "$CELERY_APP" inspect "$method" --timeout=10 >"$outfile" 2>&1; then
      if ! grep -Fq "No nodes replied" "$outfile"; then
        return 0
      fi
    fi
    sleep 5
  done
  echo "ERROR: celery inspect $method did not reply" >&2
  cat "$outfile" >&2
  exit 1
}

verify_active_queues() {
  local tmp
  tmp="$(mktemp)"
  inspect_with_retry "active_queues" "$tmp"
  for queue in "${REQUIRED_QUEUES[@]}"; do
    if ! grep -Fq "'name': '$queue'" "$tmp"; then
      echo "ERROR: required Celery queue is not active: $queue" >&2
      cat "$tmp" >&2
      rm -f "$tmp"
      exit 1
    fi
  done
  cat "$tmp"
  rm -f "$tmp"
}

verify_beat() {
  for _ in $(seq 1 12); do
    if "$DOCKER_BIN" logs --tail 80 "$BEAT_NAME" 2>&1 | grep -Eq "beat: Starting|Scheduler"; then
      return 0
    fi
    sleep 2
  done
  echo "ERROR: Celery Beat log smoke failed" >&2
  "$DOCKER_BIN" logs --tail 120 "$BEAT_NAME" 2>&1 || true
  exit 1
}

prepare_beat_state

if command -v systemctl >/dev/null && systemctl show docker.service >/dev/null 2>&1; then
  echo "== Install and restart systemd Celery units =="
  install_systemd_units
else
  restart_direct_containers
fi

wait_for_running "$WORKER_NAME"
wait_for_running "$FLOWER_NAME"
wait_for_running "$BEAT_NAME"

echo "== Verify registered tasks =="
verify_registered_tasks

echo "== Verify active queues =="
verify_active_queues

echo "== Verify Flower =="
curl -fsS "http://localhost:$FLOWER_PORT/flower/" >/dev/null

echo "== Verify Beat =="
verify_beat

echo "DONE worker=$WORKER_NAME flower=$FLOWER_NAME beat=$BEAT_NAME image=$IMAGE app=$CELERY_APP queues=$QUEUES"

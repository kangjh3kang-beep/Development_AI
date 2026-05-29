#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/_workspace/review"
MD_LOG="$LOG_DIR/LIVE_REVIEW_LOG.md"
JSON_LOG="$LOG_DIR/LIVE_REVIEW_LOG.ndjson"

type="update"
severity="INFO"
status="open"
target="-"
action="-"
owner="-"
message=""

usage() {
  cat <<'EOF'
사용법:
  bash scripts/review-live-log.sh -m "로그 내용" [옵션]

옵션:
  -t  타입 (예: finding, update, decision, fix)
  -s  심각도 (예: CRITICAL, HIGH, MEDIUM, LOW, INFO)
  -r  상태 (예: open, in_progress, done, blocked)
  -f  대상 파일/모듈
  -a  조치안
  -o  담당자
  -m  로그 내용 (필수)
  -h  도움말
EOF
}

while getopts ":t:s:r:f:a:o:m:h" opt; do
  case "$opt" in
    t) type="$OPTARG" ;;
    s) severity="$OPTARG" ;;
    r) status="$OPTARG" ;;
    f) target="$OPTARG" ;;
    a) action="$OPTARG" ;;
    o) owner="$OPTARG" ;;
    m) message="$OPTARG" ;;
    h)
      usage
      exit 0
      ;;
    \?)
      echo "알 수 없는 옵션: -$OPTARG" >&2
      usage
      exit 1
      ;;
    :)
      echo "옵션 -$OPTARG 에 값이 필요합니다." >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$message" ]]; then
  echo "오류: -m \"로그 내용\"은 필수입니다." >&2
  usage
  exit 1
fi

mkdir -p "$LOG_DIR"
timestamp="$(date '+%Y-%m-%d %H:%M:%S %Z')"

if [[ ! -f "$MD_LOG" ]]; then
  cat >"$MD_LOG" <<'EOF'
# 코드리뷰 실시간 로그

## 로그

| 시간 | 타입 | 심각도 | 상태 | 대상 | 내용 | 조치안 | 담당 |
|---|---|---|---|---|---|---|---|
EOF
fi

escape_md_cell() {
  local s="$1"
  s="${s//|/\\|}"
  s="${s//$'\n'/ }"
  printf '%s' "$s"
}

message_cell="$(escape_md_cell "$message")"
action_cell="$(escape_md_cell "$action")"
target_cell="$(escape_md_cell "$target")"
owner_cell="$(escape_md_cell "$owner")"

printf '| %s | %s | %s | %s | %s | %s | %s | %s |\n' \
  "$timestamp" "$type" "$severity" "$status" "$target_cell" "$message_cell" "$action_cell" "$owner_cell" >>"$MD_LOG"

json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  printf '%s' "$s"
}

printf '{"timestamp":"%s","type":"%s","severity":"%s","status":"%s","target":"%s","message":"%s","action":"%s","owner":"%s"}\n' \
  "$(json_escape "$timestamp")" \
  "$(json_escape "$type")" \
  "$(json_escape "$severity")" \
  "$(json_escape "$status")" \
  "$(json_escape "$target")" \
  "$(json_escape "$message")" \
  "$(json_escape "$action")" \
  "$(json_escape "$owner")" >>"$JSON_LOG"

echo "기록 완료: $timestamp | $type | $severity | $message"


#!/usr/bin/env bash
# apick(에이픽) 등기부 API 키를 .env에 안전 입력(upsert)하는 헬퍼.
#
# 사용법(서버에서 실행):
#   cd ~/Development_AI/propai-platform
#   bash scripts/set_apick_key.sh
#
# - 키는 화면에 표시되지 않는 숨김 입력으로 받습니다(셸 히스토리에도 안 남음).
# - 기존 키가 있으면 갱신, 없으면 추가(upsert). 변경 전 .env.bak 백업 생성.
# - REGISTRY_PROVIDER=apick 전환은 선택(미선택 시 CODEF 유지).
# - 적용은 백엔드 재배포(컨테이너 .env 재로드) 후 반영됩니다.
set -euo pipefail

ENV_FILE="${ENV_FILE:-$(cd "$(dirname "$0")/.." && pwd)/.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ .env 파일을 찾을 수 없습니다: $ENV_FILE"
  echo "   ENV_FILE=/경로/.env bash scripts/set_apick_key.sh 로 경로를 지정하세요."
  exit 1
fi

# .env의 KEY=값 upsert(값에 / 등이 있어도 안전하도록 구분자 사용 안 함 — 라인 단위 처리)
upsert() {
  local key="$1" val="$2" tmp
  tmp="$(mktemp)"
  local found=0
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ "$line" == "${key}="* ]]; then
      printf '%s=%s\n' "$key" "$val" >> "$tmp"; found=1
    else
      printf '%s\n' "$line" >> "$tmp"
    fi
  done < "$ENV_FILE"
  [ "$found" -eq 0 ] && printf '%s=%s\n' "$key" "$val" >> "$tmp"
  cat "$tmp" > "$ENV_FILE"; rm -f "$tmp"
  echo "  ✓ ${key} 설정됨(길이 ${#val})"
}

echo "== apick 등기부 API 키 입력 =="
echo "대상 .env: $ENV_FILE"
cp "$ENV_FILE" "${ENV_FILE}.bak"
echo "  (백업 생성: ${ENV_FILE}.bak)"

# 숨김 입력으로 키 받기
printf "apick CL_AUTH_KEY 입력(화면 미표시): "
read -rs APICK_KEY
echo
if [ -z "${APICK_KEY// /}" ]; then
  echo "❌ 키가 비어 있어 중단합니다."
  exit 1
fi

upsert "APICK_CL_AUTH_KEY" "$APICK_KEY"

# 공급자 전환 여부(기본: 변경 안 함 = CODEF 유지)
printf "지금 등기 공급자를 apick으로 전환할까요? (y/N): "
read -r SWITCH
if [[ "${SWITCH:-N}" =~ ^[Yy]$ ]]; then
  upsert "REGISTRY_PROVIDER" "apick"
  echo "  → REGISTRY_PROVIDER=apick (apick 사용)"
else
  cur="$(grep -E '^REGISTRY_PROVIDER=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
  echo "  → REGISTRY_PROVIDER 유지(현재: ${cur:-미설정}). 나중에 전환하려면:"
  echo "       bash scripts/set_apick_key.sh 재실행 또는 .env에서 REGISTRY_PROVIDER=apick 로 변경"
fi

echo
echo "✅ 완료. 변경을 반영하려면 백엔드 재배포가 필요합니다:"
echo "   ssh -i ~/.oci.key ubuntu@134.185.104.167 'nohup bash ~/deploy.sh > ~/deploy_\$(date +%s).LOG 2>&1 & echo STARTED'"
echo "   (재배포 후 /api/v1/registry/status 로 provider 확인)"

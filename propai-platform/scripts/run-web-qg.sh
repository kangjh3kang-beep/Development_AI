#!/usr/bin/env bash
set -euo pipefail

repo_root="/home/kangjh3kang/My_Projects/Development_AI/propai-platform"
server_pid=""

cleanup() {
  if [[ -n "${server_pid}" ]]; then
    kill "${server_pid}" >/dev/null 2>&1 || true
    wait "${server_pid}" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

cd "${repo_root}"

corepack pnpm --filter @propai/web exec next start --hostname 127.0.0.1 --port 3000 \
  >/tmp/propai-web-qg.log 2>&1 &
server_pid=$!

ready_code=""
for _ in $(seq 1 30); do
  ready_code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/ko || true)"
  if [[ "${ready_code}" == "200" ]]; then
    break
  fi
  sleep 1
done

if [[ "${ready_code}" != "200" ]]; then
  cat /tmp/propai-web-qg.log
  exit 1
fi

echo "[routes]"
for path in \
  /ko/projects/sample-project/bim \
  /ko/projects/sample-project/drone \
  /ko/projects/sample-project/blockchain \
  /ko/agent
do
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:3000${path}" || true)"
  printf '%s %s\n' "${path}" "${code}"
done

echo "[content]"
while IFS='|' read -r path needle; do
  if curl -s "http://127.0.0.1:3000${path}" | grep -Fq "${needle}"; then
    result="ok"
  else
    result="missing"
  fi
  printf '%s %s [%s]\n' "${path}" "${result}" "${needle}"
done <<'EOF'
/ko/projects/sample-project/bim|BIM 검토 워크스페이스
/ko/projects/sample-project/drone|드론 하자 히트맵
/ko/projects/sample-project/blockchain|에스크로 상태 카드
/ko/agent|AI 에이전트 타임라인
EOF

browser_script="$(wslpath -w "${repo_root}/scripts/run-web-qg-browser.ps1")"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${browser_script}"

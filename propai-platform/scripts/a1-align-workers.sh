#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
# a1-align-workers.sh — 배포한 이미지를 **모든 백그라운드 워커**에 정렬한다.
#
# ★왜 이 파일이 생겼나 (2026-08-12 실측):
#   백엔드 배포는 API 컨테이너만 블루-그린으로 교체한다. 워커는 대상이 아니다.
#   arq 는 2026-08-02 에 이 사실이 발각돼 `a1-arq-worker.sh` 로 정렬이 배선됐는데,
#   **똑같은 처지의 celery 3종(worker·beat·flower)은 스윕되지 않았다.**
#   그 결과 celery 컨테이너가 **2026-07-22 이미지로 3주간** 돌았고, 그 사이의 모든
#   백엔드 수정이 celery 가 실행하는 태스크(parcel_batch·rates·auction·growth·
#   member PII 파기)에는 **한 번도 도달하지 않았다**.
#
#   발각 계기: PR #601(Celery 배치가 매일 DB 연결을 흘리던 근본 봉합)을 배포하려다,
#   "그 수정이 실제로 누수하는 프로세스에 닿는가"를 확인해 보니 닿지 않았다.
#   ★처방이 결함이 사는 곳에 닿지 않는다 — 이 저장소의 고질이 배포 층에서 재현된 것.
#
# ★그래서 여기서 하는 일: "어떤 워커를 정렬해야 하는가"를 **한 곳에만** 둔다.
#   배포 스크립트는 이 파일 하나만 부르면 되고, 워커가 늘어도 배포는 안 고쳐도 된다.
#   (종전처럼 배포 스크립트가 워커를 개별로 알면, 워커가 늘 때마다 조용히 누락된다.)
#
# 사용법: bash scripts/a1-align-workers.sh
# 종료코드: 0=전부 정렬됨 · 1=하나 이상 실패(어느 것이 실패했는지 출력)
#
# ★비치명적으로 부를 것: 호출부(배포)는 이미 트래픽 전환이 끝난 지점이라,
#   실패해도 배포를 되돌리지 말고 경고만 남긴다(운영자가 수동 재실행).
# ════════════════════════════════════════════════════════════════
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

failed=""

echo "== 워커 정렬 ① arq =="
if ! bash "$SCRIPT_DIR/a1-arq-worker.sh"; then
  failed="$failed arq"
fi

echo "== 워커 정렬 ② celery(worker·beat·flower) =="
# a1-backend-workers.sh 는 systemd 유닛을 재설치·재시작하고 **등록 태스크·활성 큐·beat**
# 까지 검증한다(멱등). 컨테이너가 Up 인 것만으로는 신 이미지라는 뜻이 아니므로,
# "돌고 있다"가 아니라 "무엇을 등록했다"까지 확인하는 그 검증을 그대로 쓴다.
if ! bash "$SCRIPT_DIR/a1-backend-workers.sh"; then
  failed="$failed celery"
fi

if [ -n "$failed" ]; then
  echo "⚠️ 워커 정렬 실패:$failed — 해당 워커가 구 이미지일 수 있습니다."
  echo "   수동 재실행: bash $SCRIPT_DIR/a1-align-workers.sh"
  exit 1
fi

echo "✅ 워커 정렬 완료 (arq · celery)"
exit 0

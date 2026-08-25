#!/usr/bin/env bash
# 통합자 계기판 — 여러 세션이 같은 계기판을 보게 하는 **공용 측정기**.
#
# ★설계 원칙(전부 이 스크립트를 만들다 실제로 데인 것):
#   ① **빈 절을 만들지 않는다.** 프로브가 죽으면 "이상 없음"이 아니라 "★프로브 실패"를 찍는다.
#      (첫 판에서 컨테이너가 블루-그린으로 갈리며 복사해 둔 프로브가 사라졌는데,
#       그 절이 **조용히 비어** 정상처럼 보였다.)
#   ② **대조군은 같은 술어를 태운다.** DB 연결만 확인하는 대조군은 문자열 리터럴이 깨졌을 때
#      0 을 '깨끗함'으로 읽게 만든다 — 실제로 `0건/0건`이라는 **거짓 안전신호**를 냈다.
#      지금은 `insight_type='latency_regression'` 전체 수를 같이 세서 술어 생존을 증명한다.
#   ③ **음성 대조군을 함께 찍는다**(`/zzz-nope` 가 404 여야 HTTP 프로브가 살아 있다).
#   ④ **배포 판정은 커밋 수가 아니라 두 런타임 값의 일치**로 한다.
#
# 사용: bash propai-platform/scripts/monitor/integrator_dashboard.sh
# 각 항목에 대조군을 붙인다(0/없음이 "조회 결과"인지 "부재"인지 가르기 위해).
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # ★cd 이전에 확정한다
REPO="$(cd "$SELF_DIR/../../.." && pwd)"
cd "$REPO" || { echo "★저장소 루트를 못 찾음: $REPO"; exit 1; }
K="ssh -i $HOME/.oci.key -o StrictHostKeyChecking=no -o ConnectTimeout=15"
echo "════ 통합자 계기판  $(date '+%Y-%m-%d %H:%M:%S %Z')  (UTC $(date -u '+%H:%M')) ════"

git fetch origin main -q 2>/dev/null
MAIN=$(git rev-parse --short origin/main)
SW=$($K ubuntu@158.179.174.207 'curl -s --max-time 10 http://localhost/sw.js | grep -m1 "^const CACHE_NAME"' 2>/dev/null | grep -oE 'propai-v[0-9]+-[0-9a-f]+')
SWPUB=$(curl -s --max-time 12 https://4t8t.net/sw.js | grep -m1 '^const CACHE_NAME' | grep -oE 'propai-v[0-9]+-[0-9a-f]+')
API=$($K ubuntu@168.110.125.89 'for c in $(docker ps --filter name=propai-api- --format "{{.Names}}"); do docker exec $c printenv APP_BUILD_ID 2>/dev/null; done | head -1' 2>/dev/null)

echo "── ① 배포 수렴 (판정 = 런타임 값 일치, 커밋 수 아님)"
printf "   origin/main %s │ 158 web %s │ 168 api %s\n" "$MAIN" "${SWPUB:-★조회실패}" "${API:-★조회실패}"
w=$(echo "$SWPUB" | grep -c "$MAIN"); a=$(echo "$API" | grep -c "$MAIN")
if [ "$w" -ge 1 ] && [ "$a" -ge 1 ]; then echo "   ✅ 양쪽 수렴"
elif [ "$a" -ge 1 ]; then echo "   ⏳ 168 만 최신 (158 빌드 중이거나 미배포)"
else echo "   ⏳ 미수렴"; fi

echo "── ② 라이브 표면 (음성 대조군 포함)"
for r in /ko /ko/projects /ko/settings /sw.js; do
  printf "   %-14s %s\n" "$r" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 12 "https://4t8t.net$r")"
done
printf "   %-14s %s  ← 404 여야 프로브 정상\n" "/zzz-nope" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://4t8t.net/zzz-nope)"
printf "   %-14s %s\n" "api/health" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 12 https://api.4t8t.net/health)"

echo "── ③ 성장루프 (낡은 생산자 재발 감시 · 정지 2026-08-24T23:00:37Z)"
PROBE="$SELF_DIR/growth_stale_producer_probe.py"
[ -f "$PROBE" ] || { echo "   ★프로브 파일 없음: $PROBE"; }
if ! scp -i "$HOME/.oci.key" -o StrictHostKeyChecking=no -o ConnectTimeout=15 "$PROBE" ubuntu@168.110.125.89:/tmp/growth_probe.py >/dev/null 2>&1; then
     echo "   ★프로브 전송 실패 — 아래 숫자는 **컨테이너에 남은 옛 사본**의 결과일 수 있다."
   fi
G=$($K ubuntu@168.110.125.89 'c=$(docker ps --filter name=propai-api- --format "{{.Names}}"|head -1); docker cp /tmp/growth_probe.py $c:/tmp/ >/dev/null 2>&1 && docker exec $c python /tmp/growth_probe.py' 2>&1 | grep -m1 '^PROBE ')
if [ -z "$G" ]; then
  echo "   ★프로브 실패 — 이 절은 '이상 없음'이 **아니다**. 컨테이너 교체/DB/구문을 확인하라."
else
  ctrl=$(echo "$G" | grep -oE 'ctrl_type_total=[0-9]+' | cut -d= -f2)
  post=$(echo "$G" | grep -oE 'impossible_post=[0-9]+' | cut -d= -f2)
  pre=$(echo  "$G" | grep -oE 'impossible_pre=[0-9]+'  | cut -d= -f2)
  live=$(echo "$G" | grep -oE 'engine_alive=[0-9]+' | cut -d= -f2)
  if [ "${ctrl:-0}" -eq 0 ]; then
    echo "   ★대조군 0 — **같은 술어가 아무것도 못 집었다**. 아래 숫자를 믿지 마라(리터럴/스키마 확인)."
  else
    echo "   불가능 행: 정지 이후 ${post}건 / 정지 이전 ${pre}건   [대조군 latency_regression 24h ${ctrl}건 = 술어 생존]"
    echo "   엔진 생존: 정지 이후 인사이트 ${live}건 기록"
    [ "${post:-0}" -gt 0 ] && echo "   ★★재발 — 낡은 생산자가 또 있다. 기각한 가설(워커 옛이미지·severity UPDATE·다른 INSERT 경로)은 재생성 말 것."
  fi
fi
echo "── ④ 정지시킨 옛 스택 (부활 감시 · compose 에 아직 정의돼 있음)"
$K ubuntu@158.179.174.207 'docker inspect -f "   propai-platform_api_1 = {{.State.Status}} restart={{.HostConfig.RestartPolicy.Name}}" propai-platform_api_1 2>/dev/null || echo "   ★컨테이너 없음(삭제됨)"' 2>&1

echo "── ⑤ 열린 PR (라벨은 분 단위로 바뀐다 — 이건 스냅샷)"
gh pr list --state open --limit 20 --json number,mergeStateStatus,autoMergeRequest,headRefName \
 --jq '.[] | "   #\(.number) \(.mergeStateStatus) AM=\(if .autoMergeRequest then "ON" else "off" end) \(.headRefName)"' 2>/dev/null | head -14

echo "── ⑥ 보드 최신 3항목"
grep -oE '^- \[(NOTE|CLAIM|RELEASE)\][^|]{0,110}' .git/coordination/BOARD.md | tail -3 | sed 's/^/   /'
echo "════ 끝 ════"

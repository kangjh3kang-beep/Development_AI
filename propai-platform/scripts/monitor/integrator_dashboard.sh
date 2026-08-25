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
#   ⑤ ★**"검사기가 죽었다"와 "깨끗하다"를 다른 종료코드로 가른다.**
#      (`propai-platform/tests/_scan_guard.py` 가 `ScannerDeadError` 와 `AssertionError` 를
#       나눈 것과 같은 규율 — 뭉치면 죽은 검사기가 초록으로 읽힌다.)
#
# 종료코드 계약:
#   0 = 이상 없음(모든 프로브 생존 · 위반 0)
#   2 = **진짜 위반** — 낡은 생산자 재발 / 정지한 옛 스택 부활
#   3 = **검사기 사망** — 프로브 실패 또는 대조군 파괴. ★0 과 절대 뭉치지 않는다.
#       (3 을 0 으로 읽으면 "안 재 봤다"가 "깨끗하다"가 된다)
#
# 사용: bash propai-platform/scripts/monitor/integrator_dashboard.sh
# 각 항목에 대조군을 붙인다(0/없음이 "조회 결과"인지 "부재"인지 가르기 위해).
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # ★cd 이전에 확정한다
REPO="$(cd "$SELF_DIR/../../.." && pwd)"
cd "$REPO" || { echo "★저장소 루트를 못 찾음: $REPO"; exit 1; }
K="ssh -i $HOME/.oci.key -o StrictHostKeyChecking=no -o ConnectTimeout=15"
DEAD=0   # 검사기 사망
VIOL=0   # 진짜 위반

echo "════ 통합자 계기판  $(date '+%Y-%m-%d %H:%M:%S %Z')  (UTC $(date -u '+%H:%M')) ════"

git fetch origin main -q 2>/dev/null
MAIN=$(git rev-parse --short origin/main)
SW=$($K ubuntu@158.179.174.207 'curl -s --max-time 10 http://localhost/sw.js | grep -m1 "^const CACHE_NAME"' 2>/dev/null | grep -oE 'propai-v[0-9]+-[0-9a-f]+')
SWPUB=$(curl -s --max-time 12 https://4t8t.net/sw.js | grep -m1 '^const CACHE_NAME' | grep -oE 'propai-v[0-9]+-[0-9a-f]+')
API=$($K ubuntu@168.110.125.89 'for c in $(docker ps --filter name=propai-api- --format "{{.Names}}"); do docker exec $c printenv APP_BUILD_ID 2>/dev/null; done | head -1' 2>/dev/null)

echo "── ① 배포 수렴 (판정 = 런타임 값 일치, 커밋 수 아님)"
printf "   origin/main %s │ 158 web %s │ 168 api %s\n" "$MAIN" "${SWPUB:-★조회실패}" "${API:-★조회실패}"
# ★판정은 sha 일치가 아니라 **런타임 델타**로 한다.
#   api 만 바뀐 주기에는 web 을 굽지 않는 것이 **정답**인데(sw 재채번 = 전 사용자
#   앱셸 캐시 무효화), sha 만 비교하면 그 정상 상태를 매번 "미수렴"으로 신고한다.
#   ★가드의 위양성도 결함이다 — 정상 운영을 실패로 찍으면 곧 무시당한다.
WSHA=$(echo "$SWPUB" | grep -oE '[0-9a-f]{8}$')
ASHA=$(echo "$API"   | grep -oE '[0-9a-f]{8}$')
runtime_delta() {  # $1=배포된 sha, $2..=경로들 → 런타임 변경 파일 수
  local base="$1"; shift
  [ -z "$base" ] && { echo "?"; return; }
  git diff --name-only "$base..origin/main" -- "$@" 2>/dev/null \
    | grep -vcE '(__tests__|\.test\.|\.spec\.|vitest\.config|/tests/|test_)'
}
WD=$(runtime_delta "$WSHA" propai-platform/apps/web/ propai-platform/packages/)
AD=$(runtime_delta "$ASHA" propai-platform/apps/api/ propai-platform/apps/worker/)
CD=$(git diff --name-only "${ASHA:-HEAD}..origin/main" 2>/dev/null | grep -cE 'Dockerfile|docker-compose|requirements.*\.txt')
printf "   런타임 델타 — web %s파일 · api %s파일 · 컨테이너입력 %s파일\n" "$WD" "$AD" "$CD"
if [ "$WD" = "?" ] || [ "$AD" = "?" ]; then
  echo "   ★배포 sha 조회 실패 — 수렴 여부를 **모른다**."; DEAD=1
elif [ "$WD" -eq 0 ] && [ "$AD" -eq 0 ] && [ "$CD" -eq 0 ]; then
  echo "   ✅ 수렴 — 굽지 않아도 되는 상태(sha 가 달라도 런타임은 최신)"
else
  [ "$AD" -gt 0 ] || [ "$CD" -gt 0 ] && echo "   ⏳ **168 먼저** 구울 것(api 계약이 화면보다 앞서야 한다)"
  [ "$WD" -gt 0 ] && echo "   ⏳ 158 굽기 필요"
fi

echo "── ② 라이브 표면 (음성 대조군 포함)"
for r in /ko /ko/projects /ko/settings /sw.js; do
  printf "   %-14s %s\n" "$r" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 12 "https://4t8t.net$r")"
done
NEG=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://4t8t.net/zzz-nope)
printf "   %-14s %s  ← 404 여야 HTTP 프로브 정상\n" "/zzz-nope" "$NEG"
[ "$NEG" != "404" ] && { DEAD=1; echo "   ★음성 대조군 파괴($NEG) — 위 200 들을 '정상'으로 읽지 마라."; }
printf "   %-14s %s\n" "api/health" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 12 https://api.4t8t.net/health)"

echo "── ③ 성장루프 (낡은 생산자 재발 감시 · 정지 2026-08-24T23:00:37Z)"
PROBE="$SELF_DIR/growth_stale_producer_probe.py"
[ -f "$PROBE" ] || { echo "   ★프로브 파일 없음: $PROBE"; }
if ! scp -i "$HOME/.oci.key" -o StrictHostKeyChecking=no -o ConnectTimeout=15 "$PROBE" ubuntu@168.110.125.89:/tmp/growth_probe.py >/dev/null 2>&1; then
     echo "   ★프로브 전송 실패 — 아래 숫자는 **컨테이너에 남은 옛 사본**의 결과일 수 있다."
     DEAD=1
   fi
G=$($K ubuntu@168.110.125.89 'c=$(docker ps --filter name=propai-api- --format "{{.Names}}"|head -1); docker cp /tmp/growth_probe.py $c:/tmp/ >/dev/null 2>&1 && docker exec $c python /tmp/growth_probe.py' 2>&1 | grep -m1 '^PROBE ')
if [ -z "$G" ]; then
  echo "   ★프로브 실패 — 이 절은 '이상 없음'이 **아니다**. 컨테이너 교체/DB/구문을 확인하라."
  DEAD=1
else
  ctrl=$(echo "$G" | grep -oE 'ctrl_type_total=[0-9]+' | cut -d= -f2)
  post=$(echo "$G" | grep -oE 'impossible_post=[0-9]+' | cut -d= -f2)
  pre=$(echo  "$G" | grep -oE 'impossible_pre=[0-9]+'  | cut -d= -f2)
  live=$(echo "$G" | grep -oE 'engine_alive=[0-9]+' | cut -d= -f2)
  if [ "${ctrl:-0}" -eq 0 ]; then
    echo "   ★대조군 0 — **같은 술어가 아무것도 못 집었다**. 아래 숫자를 믿지 마라(리터럴/스키마 확인)."
    DEAD=1
  else
    echo "   불가능 행: 정지 이후 ${post}건 / 정지 이전 ${pre}건   [대조군 latency_regression 24h ${ctrl}건 = 술어 생존]"
    echo "   엔진 생존: 정지 이후 인사이트 ${live}건 기록"
    # ★★"이 단언이 참이 되는 다른 경로" — post=0 은 **그 서명을 가진** 생산자가 없다는 뜻뿐이다.
    #   다른 빌드의 잔재 스택은 이 검사를 그냥 통과한다. 생산자 표식으로 직접 센다.
    BUILDS=$(echo "$G" | sed -n 's/.*builds=//p')
    NB=$(echo "$BUILDS" | tr ',' '\n' | grep -c '=')
    echo "   생산자 빌드: $BUILDS"
    case "$BUILDS" in
      *"(표식없음)"*) echo "   ★표식 미배포(PR #826 미머지) — **빌드 기반 판별은 아직 불가**. 위 0 은 '그 서명이 없다'까지만 말한다." ;;
      *) [ "${NB:-1}" -gt 1 ] && { VIOL=1; echo "   ★★생산자 빌드가 ${NB}종 — 잔재 스택이 또 있다."; } ;;
    esac
    [ "${post:-0}" -gt 0 ] && { VIOL=1; echo "   ★★재발 — 낡은 생산자가 또 있다. 기각한 가설(워커 옛이미지·severity UPDATE·다른 INSERT 경로)은 재생성 말 것."; }
  fi
fi
echo "── ④ 정지시킨 옛 스택 (부활 감시 · compose 에 아직 정의돼 있음)"
OLD=$($K ubuntu@158.179.174.207 'docker inspect -f "{{.State.Status}} restart={{.HostConfig.RestartPolicy.Name}}" propai-platform_api_1 2>/dev/null || echo "absent"' 2>&1)
echo "   propai-platform_api_1 = $OLD"
case "$OLD" in
  running*|restarting*) VIOL=1; echo "   ★★부활 — 낡은 스택이 다시 돌고 있다. 즉시 정지 판단 필요." ;;
  exited*|absent)      : ;;
  *) DEAD=1; echo "   ★상태 조회 실패 — 부활 여부를 **모른다**(정상 아님)." ;;
esac

echo "── ④-2 디스크 추세 (★단일 값이 아니라 **직전 대비 감소폭**)"
# ★2026-08-25 실패에서 배운 것: 여유가 79G→76→65→61→58→54G 로 줄고 있었는데
#   매 주기 df 를 찍으면서도 **추세로 보지 않았다**. 값은 있었고 판단이 없었다.
#   빌드 실패(`failed to export layer: CreateDiff`)로 드러났고, 정리 후 재시도는 성공했다.
HIST="${TMPDIR:-/tmp}/propai_disk_history.tsv"
for host in 158.179.174.207 168.110.125.89; do
  free=$($K ubuntu@$host 'df -BG / | tail -1 | awk "{print \$4}" | tr -d G' 2>/dev/null)
  pct=$($K ubuntu@$host 'df -h / | tail -1 | awk "{print \$5}"' 2>/dev/null)
  if [ -z "$free" ]; then echo "   ★$host 디스크 조회 실패 — 추세를 **모른다**"; DEAD=1; continue; fi
  prev=$(grep -E "^$host	" "$HIST" 2>/dev/null | tail -1 | cut -f3)
  printf '%s\t%s\t%s\n' "$host" "$(date +%s)" "$free" >> "$HIST"
  if [ -z "$prev" ]; then
    printf "   %-16s %s (%sG 여유)  — 이전 기록 없음(다음 실행부터 추세 판정)\n" "$host" "$pct" "$free"
  else
    d=$((prev - free))
    msg=""
    [ "$free" -lt 30 ] && { msg="★★여유 ${free}G — 빌드 실패 임계(54G에서 실패한 전례)"; VIOL=1; }
    [ -z "$msg" ] && [ "$d" -ge 15 ] && { msg="★직전 대비 ${d}G 감소 — 추세 경보"; VIOL=1; }
    [ -z "$msg" ] && msg="직전 대비 $([ "$d" -ge 0 ] && echo "-${d}" || echo "+$((-d))")G"
    printf "   %-16s %s (%sG 여유)  %s\n" "$host" "$pct" "$free" "$msg"
  fi
done

echo "── ⑤ 열린 PR (라벨은 분 단위로 바뀐다 — 이건 스냅샷)"
gh pr list --state open --limit 20 --json number,mergeStateStatus,autoMergeRequest,headRefName \
 --jq '.[] | "   #\(.number) \(.mergeStateStatus) AM=\(if .autoMergeRequest then "ON" else "off" end) \(.headRefName)"' 2>/dev/null | head -14

echo "── ⑥ 보드 최신 3항목"
# ★워크트리에서 .git 은 **파일**(gitdir 포인터)이다 — 보드는 공용 git 디렉토리에 있다.
#   종전엔 여기서 "Not a directory" 가 나고 이 절이 **조용히 비었다**(이 저장소는 워크트리가 규약이다).
BOARD="$(git rev-parse --git-common-dir 2>/dev/null)/coordination/BOARD.md"
if [ -f "$BOARD" ]; then
  grep -oE '^- \[(NOTE|CLAIM|RELEASE)\][^|]{0,110}' "$BOARD" | tail -3 | sed 's/^/   /'
else
  echo "   ★보드를 못 읽음: $BOARD"; DEAD=1
fi
echo "════ 끝 ════"

# ── 종료코드 (★사망과 청결을 뭉치지 않는다) ──
if [ "$DEAD" -eq 1 ]; then echo "판정: ★검사기 사망 — 결과를 신뢰하지 마라 (exit 3)"; exit 3; fi
if [ "$VIOL" -eq 1 ]; then echo "판정: ★★위반 발견 (exit 2)"; exit 2; fi
echo "판정: 이상 없음 — 모든 프로브 생존 (exit 0)"
exit 0

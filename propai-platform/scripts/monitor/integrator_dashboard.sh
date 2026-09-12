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
#   4 = **관측 이상 / 판정 불가** — 위반도 사망도 아니나 **「이상 없음」도 아니다**.
#       ★2026-09-02 — ③ 대조군 0 을 「술어 사망」과 「시스템 유휴」로 갈랐는데, 유휴를 `DEAD=0` 으로
#         두자 **마지막 줄의 `exit 0`("모든 프로브 생존")로 떨어졌다.** 이 파일이 `3` 을 `0` 에서
#         가른 이유와 **같은 형태의 재발**이다 — *"경보를 안 냄"* 과 *"「이상 없음」이라 말함"* 은 다른 명제다.
#       ★`#910` 이 같은 코드(4)를 버스트 관측용으로 도입한다. **의도적으로 같은 번호**를 쓴다 —
#         둘 다 *"위반은 아니나 이상 없음도 아니다"* 이고, **텍스트 충돌은 보이는 편이 낫다**.
#       (3 을 0 으로 읽으면 "안 재 봤다"가 "깨끗하다"가 된다)
#   4 = **관측 이상** — 위반은 아니나 **「이상 없음」도 아니다**. 판정은 사람이 한다.
#       ★왜 4 가 따로 있나(2026-08-28 · 독립 리뷰가 짚었다):
#         이 파일이 ⑤에서 *"사망과 청결을 뭉치면 죽은 검사기가 초록으로 읽힌다"* 고 적어 놓고
#         **관측된 버스트는 0 에 뭉쳐 두고 있었다** — 처방을 적용한 범위가 결함이 사는 범위보다
#         좁았다(§D-20). 92,238ms 짜리 동시다발 버스트가 도는 중에도 `exit 0` 이었다.
#         ★가설이 아니다: 이 계기판을 읽는 **통합자 세션이 실제로 `EXIT=0` 을 35회
#           완료신호로 인용했다**(전사 실측). 사람이 소비자였고, 그 사람이 오독했다.
#       ★그런데 `2` 로 올리지는 않는다 — 원인이 외부(DB·풀러)라 상시 빨개지면 그 신호는
#         무시되고(#868 이 값을 치렀다) 그때 **진짜 위반이 묻힌다.** `4` 는 `2` 의 희소성을
#         보존하면서 「이상 없음이 아님」을 기계에도 전한다.
#       ★굳지 않는다는 근거(리뷰 실측 · 48h 를 6h 슬라이스 8개로): 동시다발이 있는 창 6/8.
#         최근 12시간은 조용했다 — 즉 `4` 는 **켜진 채 굳지 않는다**(항상 4면 3과 같은 문제다).
#
# 사용: bash propai-platform/scripts/monitor/integrator_dashboard.sh
# 각 항목에 대조군을 붙인다(0/없음이 "조회 결과"인지 "부재"인지 가르기 위해).
# ── 판정(★락이 이 함수를 **네 모집단**으로 태운다) ──
#   함수로 꺼낸 이유: 종료코드 결정이 스크립트 끝에 인라인으로 있으면 그것을 태우려면
#   DB·SSH·네트워크가 전부 살아 있어야 한다 → 실제로는 **아무도 안 태운다.**
verdict_exit() {
  if [ "${DEAD:-0}" -eq 1 ]; then echo "판정: ★검사기 사망 — 결과를 신뢰하지 마라 (exit 3)"; exit 3; fi
  if [ "${VIOL:-0}" -eq 1 ]; then echo "판정: ★★위반 발견 (exit 2)"; exit 2; fi
  if [ "${OBS:-0}" -eq 1 ]; then echo "판정: ★관측 이상 — 위반은 아니나 **이상 없음도 아니다** (exit 4)"; exit 4; fi
  echo "판정: 이상 없음 — 모든 프로브 생존 (exit 0)"; exit 0
}
# ── 델타 축(★락이 실물로 태운다 — 그래서 `--verdict-lib` 게이트 **위**에 둔다) ──
#   ★2026-09-09: 종전 `runtime_delta` 는 게이트 **아래**에 있어 테스트가 꺼낼 수 없었다.
#     그러면 사람은 파이프라인을 테스트에 **복사**하게 되고, 형제 락이 그것을 명문으로 금지한다
#     (*"사본을 태우지 않는다 — 프로덕션 분기를 통째로 되돌려도 락이 초록"*, #905 실측).
runtime_delta() {  # $1=배포된 sha, $2..=경로들 → 런타임 변경 파일 수
  local base="$1"; shift
  [ -z "$base" ] && { echo "?"; return; }
  # ★거짓 초록 봉합(2026-09-09 실측): base 가 로컬에 없으면 `git diff` 가 fatal 이고
  #   `2>/dev/null` 이 그것을 삼켜 grep 입력이 0줄 → **`0` → "✅ 수렴"** 으로 읽혔다.
  #   실측: `deadbeef..origin/main` → 0 / 대조군 유효 sha → 2. 「배포 안 됨」이 「수렴」으로 뒤집힌다.
  git cat-file -e "${base}^{commit}" 2>/dev/null || { echo "?"; return; }
  git diff --name-only "$base..origin/main" -- "$@" 2>/dev/null \
    | grep -vcE '(__tests__|\.test\.|\.spec\.|vitest\.config|/tests/|test_)'
}

# 델타가 **주석·독스트링만**인지 판정한다 → `yes` / `no` / `unknown`
#   ★줄 접두 필터(`^[-+]\s*#`)를 쓰지 않는다 — 실측으로 틀렸다: 파이썬 **독스트링 본문**을
#     코드로 세고(정답 1 ↔ 측정 3), 반대로 `*) …;;`·`//`·셔뱅 같은 **실행 줄을 주석으로 버린다**.
#     그래서 **AST** 로 판정한다(주석은 AST 에 없고, 독스트링은 명시적으로 제거한다).
#   ★`.py` 가 아닌 변경이 하나라도 있거나, 수정(M) 이외 상태(추가·삭제·이름변경·모드)가 있거나,
#     python3 가 없거나 파싱이 실패하면 **`unknown`** 이다 — 그때는 **강등하지 않는다**(안전한 쪽).
comment_only_delta() {  # $1=배포된 sha, $2..=경로들
  local base="$1"; shift
  [ -z "$base" ] && { echo "unknown"; return; }
  git cat-file -e "${base}^{commit}" 2>/dev/null || { echo "unknown"; return; }
  command -v python3 >/dev/null 2>&1 || { echo "unknown"; return; }
  local files
  files=$(git diff --name-only --diff-filter=M "$base..origin/main" -- "$@" 2>/dev/null \
          | grep -vE '(__tests__|\.test\.|\.spec\.|vitest\.config|/tests/|test_)')
  local all
  all=$(git diff --name-only "$base..origin/main" -- "$@" 2>/dev/null \
        | grep -vE '(__tests__|\.test\.|\.spec\.|vitest\.config|/tests/|test_)')
  [ -z "$all" ] && { echo "unknown"; return; }              # 변경 없음은 이 함수가 답할 질문이 아니다
  [ "$files" != "$all" ] && { echo "unknown"; return; }     # 추가·삭제·rename·모드가 섞였다
  echo "$all" | grep -qvE '\.py$' && { echo "unknown"; return; }   # .py 아닌 것이 있다
  BASE_REV="$base" python3 - $all <<'PYEOF' 2>/dev/null || echo unknown
import ast, os, subprocess, sys
base = os.environ["BASE_REV"]
def blob(rev, path):
    r = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True)
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None
def norm(src):
    if src is None:
        return None
    tree = ast.parse(src)                      # SyntaxError 면 밖에서 unknown 이 된다
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body:
            first = body[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(getattr(first, "value", None), ast.Constant)
                    and isinstance(first.value.value, str)):
                body.pop(0)                    # 독스트링 제거
    return ast.dump(tree, include_attributes=False)
for path in sys.argv[1:]:
    if norm(blob(base, path)) != norm(blob("origin/main", path)):
        print("no"); break
else:
    print("yes")
PYEOF
}
# 델타 판정을 **순수 함수**로 꺼낸다 → `converged` / `obs` / `viol`
#   ★왜 꺼냈나: ⑤-2 블록 안에 인라인으로 두면 그것을 태우려면 보드·SSH·네트워크가 전부 살아야 해서
#     **아무도 안 태운다.** 그러면 락은 «소스에 `OBS=1` 이라는 문자열이 있는가» 로 내려앉고,
#     그건 이 저장소가 «존재를 잠그면 행위는 안 잠긴다» 로 이미 값을 치른 형태다.
#   인자: $1=web델타 $2=api델타 $3=컨테이너입력델타 $4=web주석만(yes/no/unknown) $5=api주석만
delta_verdict() {
  local wd="$1" ad="$2" cd_="$3" cow="$4" coa="$5"
  if [ "$wd" = "0" ] && [ "$ad" = "0" ] && [ "$cd_" = "0" ]; then echo "converged"; return; fi
  # 컨테이너 입력(Dockerfile·requirements)이 바뀌면 강등하지 않는다 — 재빌드가 필요하다
  if [ "$cd_" != "0" ]; then echo "viol"; return; fi
  if { [ "$ad" = "0" ] || [ "$coa" = "yes" ]; } && { [ "$wd" = "0" ] || [ "$cow" = "yes" ]; }; then
    echo "obs"; return
  fi
  echo "viol"
}
# ── ③ 분석 상태 판정 ──
#   ★**규칙을 셸에 다시 구현하지 않는다.** 프로브의 순수 함수 `analysis_verdict` 를
#     **그대로** 태운다. 2026-08-26 에 이 저장소는 큐 정렬을 *산문*으로 주고 받는 쪽이
#     다르게 구현해 **없는 결함을 신고**했다 — 산문은 여러 구현을 허용한다.
#     여기서 `case "$ASTATE" in starved) …` 를 쓰면 정확히 그 재발이다.
#   ★락이 이 함수를 태울 수 있도록 `--verdict-lib` 게이트 **위**에 둔다(형제 `delta_verdict` 와 같은 이유).
analysis_verdict_of() {   # $1=astate  $2=insights_24h  → stdout "kind|사유"
  local d
  d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  python3 -c '
import sys
sys.path.insert(0, sys.argv[1])
from growth_stale_producer_probe import analysis_verdict
kind, why = analysis_verdict(sys.argv[2], sys.argv[3])
print(kind + "|" + why)
' "$d" "$1" "$2" 2>/dev/null || echo "unknown|판정 함수를 태우지 못했다(python3 또는 프로브 경로 확인)"
}

if [ "${1:-}" = "--verdict-lib" ]; then return 0 2>/dev/null || exit 0; fi

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # ★cd 이전에 확정한다
REPO="$(cd "$SELF_DIR/../../.." && pwd)"
cd "$REPO" || { echo "★저장소 루트를 못 찾음: $REPO"; exit 1; }
K="ssh -i $HOME/.oci.key -o StrictHostKeyChecking=no -o ConnectTimeout=15"
DEAD=0   # 검사기 사망
VIOL=0   # 진짜 위반
OBS=0    # ★관측 이상(위반은 아니나 「이상 없음」도 아니다) — exit 4

echo "════ 통합자 계기판  $(date '+%Y-%m-%d %H:%M:%S %Z')  (UTC $(date -u '+%H:%M')) ════"

git fetch origin main -q 2>/dev/null
MAIN=$(git rev-parse --short origin/main)
SW=$($K ubuntu@158.179.174.207 'curl -s --max-time 10 http://localhost/sw.js | grep -m1 "^const CACHE_NAME"' 2>/dev/null | grep -oE 'propai-v[0-9]+-[0-9a-f]+')
SWPUB=$(curl -s --max-time 12 https://4t8t.net/sw.js | grep -m1 '^const CACHE_NAME' | grep -oE 'propai-v[0-9]+-[0-9a-f]+')
# ★활성 스택 판정 — **caddy 가 실제로 서비스하는 것**을 본다.
#   종전엔 `docker ps ... | head -1` 이었는데, 블루그린 전환 중에는 두 컨테이너가 동시에
#   살아 있어 **정렬상 앞선 유휴 스택**을 집는다. 실측(2026-08-26): head -1 이 8000(유휴·구버전)을
#   집었고 caddy 활성은 8001(신버전)이었다 — 그 오독으로 한 세션이 **이미 배포된 PR 을
#   "미배포"로 읽고 주기를 중복 CLAIM** 했다. 그리고 같은 날 활성 포트가 8001→8000→8001 로
#   두 번 뒤집혔다(우연히 맞는 회차가 섞이면 더 위험하다).
#   ★주석 배제 + `reverse_proxy` 앵커 + **유일성**까지 본다. 비면 **반드시 죽어야** 한다 —
#     빈 값이면 `docker exec propai-api- …` 라는 **문법상 유효한 다른 명령**이 된다(조용한 오답).
ACTIVE_SNIPPET='PORTS=$(grep -vE "^[[:space:]]*#" $HOME/caddy/Caddyfile | grep -oE "reverse_proxy[[:space:]]+localhost:80[0-9]+" | grep -oE "80[0-9]+" | sort -u); [ "$(printf %s "$PORTS" | grep -c .)" -eq 1 ] || exit 3; C=propai-api-$PORTS'
API=$($K ubuntu@168.110.125.89 "$ACTIVE_SNIPPET"'; docker exec $C printenv APP_BUILD_ID 2>/dev/null' 2>/dev/null)

echo "── ① 배포 수렴 (판정 = 런타임 값 일치, 커밋 수 아님)"
printf "   origin/main %s │ 158 web %s │ 168 api %s\n" "$MAIN" "${SWPUB:-★조회실패}" "${API:-★조회실패}"
# ★판정은 sha 일치가 아니라 **런타임 델타**로 한다.
#   api 만 바뀐 주기에는 web 을 굽지 않는 것이 **정답**인데(sw 재채번 = 전 사용자
#   앱셸 캐시 무효화), sha 만 비교하면 그 정상 상태를 매번 "미수렴"으로 신고한다.
#   ★가드의 위양성도 결함이다 — 정상 운영을 실패로 찍으면 곧 무시당한다.
WSHA=$(echo "$SWPUB" | grep -oE '[0-9a-f]{8}$')
ASHA=$(echo "$API"   | grep -oE '[0-9a-f]{8}$')
# (runtime_delta 는 위 판정 구역으로 옮겼다 — 락이 실물을 태울 수 있도록)
WD=$(runtime_delta "$WSHA" propai-platform/apps/web/ propai-platform/packages/)
AD=$(runtime_delta "$ASHA" propai-platform/apps/api/ propai-platform/apps/worker/)
# ★CD 도 같은 거짓 초록을 갖는다 — base 가 로컬에 없으면 grep 입력이 0줄이라 **0** 이 나온다.
if [ -n "${ASHA:-}" ] && ! git cat-file -e "${ASHA}^{commit}" 2>/dev/null; then
  CD="?"
else
  CD=$(git diff --name-only "${ASHA:-HEAD}..origin/main" 2>/dev/null | grep -cE 'Dockerfile|docker-compose|requirements.*\.txt')
fi
printf "   런타임 델타 — web %s파일 · api %s파일 · 컨테이너입력 %s파일\n" "$WD" "$AD" "$CD"
if [ "$WD" = "?" ] || [ "$AD" = "?" ] || [ "$CD" = "?" ]; then
  # ★`3` 의 희소성을 지킨다(c8 리뷰 2026-09-09): 이제 **fetch 지연만으로도** 여기 올 수 있다.
  #   상시 3 이 되면 3 이 무시되고 그때 진짜 검사기 사망이 묻힌다 — 그래서 **어느 3 인지 말한다.**
  for _sha in "$WSHA" "$ASHA"; do
    [ -n "$_sha" ] && ! git cat-file -e "${_sha}^{commit}" 2>/dev/null \
      && echo "   ★배포 sha ${_sha} 가 **로컬 저장소에 없다** — `git fetch origin` 후 다시 보라(fetch 지연·스쿼시·미머지 빌드)."
  done
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
G=$($K ubuntu@168.110.125.89 "$ACTIVE_SNIPPET"'; docker cp /tmp/growth_probe.py $C:/tmp/ >/dev/null 2>&1 && docker exec $C python /tmp/growth_probe.py' 2>&1 | grep -m1 '^PROBE ')
if [ -z "$G" ]; then
  echo "   ★프로브 실패 — 이 절은 '이상 없음'이 **아니다**. 컨테이너 교체/DB/구문을 확인하라."
  DEAD=1
else
  ctrl=$(echo "$G" | grep -oE 'ctrl_type_total=[0-9]+' | cut -d= -f2)
  # ★대조군 0 의 **이유를 가른다**(2026-09-02). 종전엔 "술어 사망"으로만 읽어 DEAD=1 이었는데,
  #   시스템이 유휴여도 24h 창은 0 이다 — 실측: 술어 전체 2,348건·최신 08-28 인데 24h **0**.
  #   그대로 두면 유휴가 지속되는 동안 **매 실행 exit 3** 이고, 상시 3 은 곧 무시된다
  #   (`#868` 이 상시 빨강으로 치른 값과 같은 형태 — 이 파일 ③ 주석이 그것을 적어 뒀다).
  ctrl_all=$(echo "$G" | grep -oE 'ctrl_type_alltime=[0-9]+' | cut -d= -f2)
  post=$(echo "$G" | grep -oE 'impossible_post=[0-9]+' | cut -d= -f2)
  pre=$(echo  "$G" | grep -oE 'impossible_pre=[0-9]+'  | cut -d= -f2)
  live=$(echo "$G" | grep -oE 'engine_alive=[0-9]+' | cut -d= -f2)
  if [ "${ctrl:-0}" -eq 0 ] && [ "${ctrl_all:-0}" -eq 0 ]; then
    # 창에서도 0 이고 **전 역사에서도 0** → 술어가 아무것도 못 집는다 = 검사기 사망.
    echo "   ★대조군 0 — **같은 술어가 전 역사에서 아무것도 못 집었다**. 아래 숫자를 믿지 마라(리터럴/스키마 확인)."
    DEAD=1
  elif [ "${ctrl:-0}" -eq 0 ]; then
    # ★창에서만 0 → **술어는 살아 있고 시스템이 유휴**다. 이건 검사기 사망이 **아니다**.
    #   ★그렇다고 "이상 없음"도 아니다 — 판정을 **못 한** 것이므로 그렇게 적는다.
    #   ★`exit 2` 도 내지 않는다: 유휴는 위반이 아니고, `#868` 의 기각(상시 빨강)을 존중한다.
    # ★★종전엔 여기서 «판정 불가» 를 찍고 끝냈다 — **정직하지만 답이 아니었다.**
    #   답은 `analyzer.py` 가 **이미 발행하고 있었다**(`growth_analysis` 설정키 · TTL 180분).
    #   빠진 것은 기능이 아니라 **이 레인의 소비처**였다(실측 2026-09-12 08:2xZ:
    #   state=starved · axes="fal 0/0 lat 0/19 pay 0/1 qua 0/0" · at=08:05:05Z).
    #   ★내가 그 사실을 **소스 grep 으로 못 찾고 라이브 응답으로 알았다** —
    #     «매체»(`INSERT INTO platform_events`)로 찾으면 «목적»(분석기가 실행을 어디 남기나)을 놓친다.
    ASTATE=$(echo "$G" | grep -oE 'astate=[^ ]+' | cut -d= -f2)
    AAT=$(echo   "$G" | grep -oE 'aat=[^ ]+'    | cut -d= -f2)
    AAXES=$(echo "$G" | grep -oE 'aaxes=[^ ]+'  | cut -d= -f2)
    AINS=$(echo  "$G" | grep -oE 'ains=[^ ]+'   | cut -d= -f2)
    ALAST=$(echo "$G" | grep -oE 'alast=[^ ]+'  | cut -d= -f2)
    # ★필드가 비면 «(필드없음)» 으로 **명시**한다 — 빈 문자열을 그냥 넘기면
    #   «옛 프로브 사본» 이 «축이 없다(idle)» 로 조용히 둔갑한다(형제 `overlap` 과 같은 규율).
    [ -z "$ASTATE" ] && ASTATE="(필드없음)"
    AV=$(analysis_verdict_of "$ASTATE" "${ctrl:-0}" 2>/dev/null)
    AK=${AV%%|*}; AR=${AV#*|}
    # ★★판정기 자체가 없으면(함수 미정의·python3 부재) `AV` 가 **빈 문자열**이고
    #   그러면 사유 칸이 통째로 **비어서 출력된다** — 이 파일이 금지하는 바로 그 침묵이다.
    #   실측: 형제 락(`test_dashboard_idle_vs_dead_scanner.py`)이 블록만 떼어 돌렸더니
    #   «★ — **0 으로 읽지 마라**» 라는 **사유 없는 경보**가 나왔다. 그 락이 잡아 줬다.
    #   ⇒ 빈 값은 «모른다» 로 승격하되 **사유를 반드시 채운다.**
    if [ -z "$AK" ] || [ "$AK" = "$AR" ]; then
      AK="unknown"
      AR="분석상태 판정기를 태우지 못했다(함수 미정의 또는 python3 부재) — 이 줄은 '유휴'가 아니다"
    fi
    echo "   인사이트 24h 창 0 (전 역사 ${ctrl_all}건 = 술어 생존)"
    echo "   분석기 상태: state=${ASTATE} · 축 ${AAXES:--} · 인사이트 ${AINS:--} · 발행 ${AAT:--} · 워터마크 ${ALAST:--}"
    case "$AK" in
      ok)      echo "   ✅ ${AR}" ;;
      obs)     OBS=1; echo "   ★${AR}" ;;
      *)       DEAD=1; echo "   ★${AR} — **0 으로 읽지 마라**" ;;
    esac
  else
    echo "   불가능 행: 정지 이후 ${post}건 / 정지 이전 ${pre}건   [대조군 latency_regression 24h ${ctrl}건 = 술어 생존]"
    echo "   엔진 생존: 정지 이후 인사이트 ${live}건 기록"
    # ★★"이 단언이 참이 되는 다른 경로" — post=0 은 **그 서명을 가진** 생산자가 없다는 뜻뿐이다.
    #   다른 빌드의 잔재 스택은 이 검사를 그냥 통과한다. 생산자 표식으로 직접 센다.
    BUILDS=$(echo "$G" | sed -n 's/.*builds=//p')
    # ★★**무표식 행과 표식 있는 빌드를 갈라서 센다.**
    #   종전엔 `NB` 가 둘을 함께 세고, 아래 case 가 `(표식없음)` 이 **하나라도 있으면**
    #   첫 분기로 빠져 **위반 검사(NB>1)가 도달 불가**였다. 즉 표식 배포 직후처럼
    #   옛 무표식 행이 남아 있는 동안에는 **진짜 잔재 스택이 있어도 조용했다.**
    #   실측 2026-08-26: `(표식없음)=242,propai-v002797-881b0b50=26` 에서 NB=2 인데
    #   위반 검사가 건너뛰어졌다(이번엔 무해했지만 그것은 운이다).
    MARKED=$(echo "$BUILDS" | tr ',' '\n' | grep '=' | grep -v '(표식없음)')
    NB=$(printf '%s' "$MARKED" | grep -c '=')            # ★표식 있는 빌드만 센다
    UNMARKED=$(echo "$BUILDS" | tr ',' '\n' | grep -c '(표식없음)')
    echo "   생산자 빌드: $BUILDS"
    # ★★표식이 없을 때 **이유를 셋으로 가른다** — 종전엔 *"PR #826 미머지"* 하나로 찍었는데,
    #   #826 이 머지·배포된 뒤에도 그 문구가 나와 **능동적으로 거짓**이 됐다(2026-08-26 실측).
    #   머지·배포·데이터반영은 **다른 사건**이다. 한 단어로 부르면 다음 사람이 엉뚱한 곳을 판다
    #   (실제로 나는 `(표식없음)` 을 보고 머지 여부부터 확인하러 갔다).
    # ★판정은 **표식 있는 빌드**로 한다. 무표식은 "표식 이전 생성분"이라 별도로 말한다.
    case "$MARKED" in
      "")
        MARK=$($K ubuntu@168.110.125.89 "$ACTIVE_SNIPPET"'; docker exec -w /app/apps/api $C python -c "from app.services.growth import stale_build_guard as g; print(g.running_build_id() or \"\")" 2>/dev/null' 2>/dev/null)
        MRC=$?
        if [ "$MRC" -ne 0 ]; then
          echo "   ★표식 프로브 실패 — **배포 여부를 모른다**(이 줄은 '미배포'가 아니다). 활성 스택/모듈 확인 필요."
          DEAD=1
        elif [ -z "$MARK" ]; then
          echo "   ★표식 **미배포** — 실행 중인 빌드에 생산자 표식이 없다. 빌드 기반 판별 불가."
        else
          echo "   표식은 **배포됨**($MARK) — 다만 **그 이후 생성분이 아직 없다**(analyze 배치는 매시 :05)."
          echo "   → 이 줄은 '미배포'가 아니라 '대기'다. 다음 배치 뒤 다시 보라."
        fi ;;
      *)
        [ "${UNMARKED:-0}" -gt 0 ] && echo "   (무표식 행이 함께 있음 — **표식 배포 이전 생성분**이다. 판정에서 제외한다.)"
        # ★★판정은 **종류 수가 아니라 시간 겹침**이다 — 프로브의 `overlap=` 을 읽는다.
        #   2026-08-26 회귀: 종전 `NB > 1` 은 STOP(2일 전) 이후 창에서 **배포마다 표식이
        #   바뀌므로 두 번째 배포 이후 영원히 위반**이었다. 실측으로 확인한 형태 —
        #     v002797 04:04~04:05 · v002799 08:05 · v002809 12:05~12:08  (교차 0건)
        #   완전한 순차 승계인데 "잔재 스택 3종"으로 신고했다. 상시 빨간 계기판은
        #   곧 무시되고, 그때 **진짜 잔재가 묻힌다**. 판정은 probe 의 순수 함수
        #   `is_stale_stack()` 이 하고(테스트가 잠근다), 셸은 그 결과만 읽는다.
        OV=$(echo "$G" | sed -n 's/.*overlap=//p' | awk '{print $1}')
        if [ -z "$OV" ]; then
          # ★프로브가 이 필드를 안 준다 = **옛 사본**이 돌고 있다. 0 으로 읽지 않는다.
          DEAD=1; echo "   ★프로브에 overlap 필드가 없다 — 컨테이너의 프로브가 옛 사본이다(판정 불가)."
        elif [ "$OV" != "none" ]; then
          VIOL=1; echo "   ★★잔재 스택 — 서로 다른 표식이 **동시에** 기록했다: $OV"
        elif [ "${NB:-1}" -gt 1 ]; then
          echo "   ✅ 표식 ${NB}종이지만 **시간이 겹치지 않는다** — 배포마다 표식이 바뀐 정상 승계."
        else
          echo "   ✅ 표식 있는 생산자 빌드 **1종** — 잔재 스택 없음(추론이 아니라 조회로 확인)."
        fi ;;
    esac
    [ "${post:-0}" -gt 0 ] && { VIOL=1; echo "   ★★재발 — 낡은 생산자가 또 있다. 기각한 가설(워커 옛이미지·severity UPDATE·다른 INSERT 경로)은 재생성 말 것."; }
  fi
fi
echo "── ③-2 지연 버스트 (★사후 판정 — /health 는 그 순간만 말한다)"
# ★왜 이 절이 있나: 2026-08-27 하루에 ~10분짜리 지연 버스트가 **최소 5회** 났고
#   **두 세션이 라이브로 못 봤다.** 가장 심한 것(parcel-boundaries **69,503ms** @07:05Z)은
#   아무도 안 보고 지나갔다 — 우연히 로그인을 시도한 시각에만 알아챘기 때문이다.
#   `/health` 폴링은 구조적으로 못 잡는다(그 순간만 말한다). `platform_events` 는
#   **지나간 버스트를 되짚을 수 있다.**
# ★판정은 개수가 아니라 **동시성**이다 — 여러 라우트가 같은 5분에 걸리면 공통 경로(DB) 의심.
BPROBE="$SELF_DIR/latency_burst_probe.py"
[ -f "$BPROBE" ] || { echo "   ★프로브 파일 없음: $BPROBE"; DEAD=1; }
if ! scp -i "$HOME/.oci.key" -o StrictHostKeyChecking=no -o ConnectTimeout=15 "$BPROBE" ubuntu@168.110.125.89:/tmp/burst_probe.py >/dev/null 2>&1; then
     echo "   ★프로브 전송 실패 — 아래 숫자는 **컨테이너에 남은 옛 사본**의 결과일 수 있다."
     DEAD=1
   fi
B=$($K ubuntu@168.110.125.89 "$ACTIVE_SNIPPET"'; docker cp /tmp/burst_probe.py $C:/tmp/ >/dev/null 2>&1 && docker exec $C python /tmp/burst_probe.py' 2>&1 | grep -m1 '^PROBE ')
if [ -z "$B" ]; then
  echo "   ★프로브 실패 — 이 절은 '버스트 없음'이 **아니다**. 컨테이너 교체/DB/구문을 확인하라."
  DEAD=1
else
  SCAN=$(echo "$B" | grep -oE 'scanned_buckets=[0-9]+' | cut -d= -f2)
  NB2=$(echo  "$B" | grep -oE 'burst_buckets=[0-9]+'   | cut -d= -f2)
  MR=$(echo   "$B" | grep -oE 'multi_route=[0-9]+'     | cut -d= -f2)
  WORST=$(echo "$B" | grep -oE 'worst_p95_ms=[0-9]+'   | cut -d= -f2)
  TOP=$(echo  "$B" | sed -n 's/.*top=//p')
  if [ "${SCAN:-0}" -eq 0 ]; then
    # ★대조군 — 스캔한 버킷이 0이면 「버스트 0」은 청결이 아니라 **조회 실패**다
    echo "   ★대조군 0 — 스캔한 버킷이 없다. 수집이 멈췄거나 컬럼이 바뀌었다(버스트 0 을 청결로 읽지 마라)."
    DEAD=1
  else
    echo "   최근 6시간: 스캔 ${SCAN}버킷 · 버스트 ${NB2} · **동시다발 ${MR}** · 최대 ${WORST}ms"
    [ "$TOP" != "none" ] && echo "   동시다발 버킷: $TOP"
    # ★여기서 exit 2 를 내지 **않는다.** 원인이 외부(DB·풀러)라 상시 빨개지면
    #   그 신호는 곧 무시되고(#868 이 배운 것), 그때 진짜 위반이 묻힌다.
    #   버스트는 **관측**으로 싣고, 판정은 사람이 한다.
    if [ "${MR:-0}" -gt 0 ]; then
      OBS=1
      echo "   ⚠ 동시다발 버스트는 **공통 경로(DB·풀러) 의심**이다 — 라우트별 문제가 아니다."
      echo "     (exit 2 가 아니라 **exit 4(관측 이상)** 이다 — 외부 원인이라 2 로 올리면 상시 빨강이 된다)"
    fi
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

echo "── ⑤-2 ★미처리 배포 요청 (보드는 다른 세션이 읽는 **유일한 지속 채널**)"
# ★2026-08-26 실측: SESSION-F 가 "배포 요청 — 168 필요" 를 올렸는데, 나는 ①수렴 줄만 보고
#   사용자에게 "대기 상태, 배포할 것 없음" 이라고 답했다. 약 30분 지연됐다.
#   인계서에 *"쓰기만 하고 읽지 마라"* · *"NOTE 줄에 배포요청이 숨는다"* 가 **적혀 있었다.**
#   → 산문으로 남기지 않고 계기판이 직접 찾게 한다. 요청이 있는데 런타임 델타가 남아 있으면 **위반**.
BOARD2="$(git rev-parse --git-common-dir 2>/dev/null)/coordination/BOARD.md"
if [ ! -f "$BOARD2" ]; then
  echo "   ★보드를 못 읽음 — 배포 요청 유무를 **모른다**"; DEAD=1
else
  REQ=$(grep -oE '^- \[NOTE\][^|]*(배포 요청|→ 통합자)[^|]{0,90}' "$BOARD2" | tail -3)
  if [ -z "$REQ" ]; then
    echo "   미처리 배포 요청 없음 (대조군: 보드 $(wc -l < "$BOARD2")줄 읽힘)"
  else
    echo "$REQ" | sed 's/^/   /' | cut -c1-150
    # 요청이 있는데 아직 구울 것이 남아 있으면 미처리로 본다
    if [ "${WD:-0}" != "0" ] || [ "${AD:-0}" != "0" ] || [ "${CD:-0}" != "0" ]; then
      # ★2026-09-09: 「파일이 바뀌었다」와 「런타임이 바뀐다」는 다른 명제다. 주석·독스트링만 바뀐
      #   델타를 **위반(2)** 으로 내면 상시 빨강이 되고, 상시 빨강은 곧 무시된다(#868 이 이미 치른 값).
      #   그렇다고 **0(이상 없음)** 으로 내리지 않는다 — 컨테이너 소스는 여전히 git 과 갈려 있고
      #   이 저장소는 컨테이너 소스를 표식으로 grep 한다(이 파일 자신이 그렇게 한다).
      #   ⇒ 있는 칸을 쓴다: **관측 이상(4)**. 「위반은 아니나 이상 없음도 아니다」.
      CO_API=$(comment_only_delta "$ASHA" propai-platform/apps/api/ propai-platform/apps/worker/)
      CO_WEB=$(comment_only_delta "$WSHA" propai-platform/apps/web/ propai-platform/packages/)
      if [ "$(delta_verdict "${WD:-0}" "${AD:-0}" "${CD:-0}" "$CO_WEB" "$CO_API")" = "obs" ]; then
        echo "   ★관측 이상 — 위 요청의 델타는 **주석·독스트링만**이다(web ${WD} · api ${AD} · AST 판정)"
        echo "     런타임 동작 변화 0. 다만 **컨테이너 소스는 git 과 갈려 있다** — 다음 배포가 해소한다."
        OBS=1
      else
        echo "   ★★미처리 — 위 요청이 있는데 **런타임 델타가 남아 있다**(web ${WD} · api ${AD} · 주석만? api=${CO_API} web=${CO_WEB})"
        VIOL=1
      fi
    else
      echo "   → 런타임 델타 0 이므로 위 요청은 **처리됨**으로 본다"
    fi
  fi
fi

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

# ── 종료코드 (★사망·위반·관측이상·청결을 뭉치지 않는다) ──
verdict_exit

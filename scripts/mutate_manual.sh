#!/usr/bin/env bash
# 손으로 고른 변이(semantic mutation)를 **안전하게** 돌린다.
#
# ★왜 이 스크립트가 필요한가 (2026-08-21 실사고)
#   `scripts/mutate_changed.py` 는 diff 에서 **기계적으로** 변이를 뽑고, 스냅샷 복원이라 안전하다.
#   그런데 배선·계약처럼 **의미를 아는 사람만 만들 수 있는 변이**는 손으로 넣게 된다
#   (예: "Dockerfile 이 다른 파일을 가리키게" · "가드를 화이트리스트에서 블랙리스트로").
#   그 손 경로에는 **안전장치가 하나도 없었고**, 실제로 사고가 났다:
#
#     · 미커밋 상태에서 `git checkout -- <파일>` 로 변이를 되돌리다 **내 편집을 통째로 날렸다**
#       (테스트 13 passed → 10 passed. CLAUDE.md §B7 이 명시한 그 함정을 알면서 밟았다)
#     · `grep -c` 로 주입을 확인하다 **동명의 다른 줄**을 세어 주입 실패를 못 봤다(§B8)
#
#   규율이 문서에만 있으면 지켜지지 않는다. **안전한 길을 더 쉽게** 만들어야 한다.
#
# 사용법:
#   scripts/mutate_manual.sh <파일> <sed표현식> <테스트명령…>
#
# 예:
#   scripts/mutate_manual.sh propai-platform/Dockerfile.oracle \
#     's|requirements.oracle.txt|reqs-prod.txt|' \
#     python3 -m pytest tests/test_no_unused_jwt_dependency.py -q
#
# 이 스크립트가 강제하는 것:
#   ①§B7 — 대상 파일에 **미커밋 변경이 있으면 거부**한다(커밋 먼저).
#   ②§B8 — 변이가 **실제로 주입됐는지** 파일 내용 비교로 확인한다(`grep -c` 를 안 믿는다).
#   ③원복은 **git 이 아니라 스냅샷**에서 한다 — git 은 내 다른 편집까지 되돌린다.
#   ④원복 후 **바이트 동일**을 단언한다. 다르면 시끄럽게 실패한다.
#   ⑤★**기준선이 초록인지 먼저 잰다**(2026-08-27 실증). 빨간 기준선에서는 **모든 변이가
#     거짓 CAUGHT** 다 — 변이와 무관하게 rc≠0 이기 때문이다. 실증: 일부러 실패하는
#     테스트를 두고 **의미가 완전히 동일한 변이**(`5000` → `5_000`)를 넣었더니 **CAUGHT**
#     가 나왔다. ★그리고 **rc=5(수집 0건)** 는 따로 가른다(exit 14) — `-k` 오타 하나로
#     테스트가 **한 건도 안 돌았는데** CAUGHT 가 나온다. 처방이 다르다(러너 vs 코드).
#     이 도구는 파이프 오염(12)·미커밋(10)·주입실패(11)는 막고 있었는데
#     **이 축만 비어 있었다** — 그리고 그것이 가장 조용하다(초록 로그가 안 나오므로).
set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "사용법: $0 <파일> <sed표현식> <테스트명령…>" >&2
  exit 64
fi

FILE="$1"; SED_EXPR="$2"; shift 2

[ -f "$FILE" ] || { echo "★대상 파일이 없다: $FILE" >&2; exit 65; }

# ── ①§B7 커밋 먼저 ──────────────────────────────────────────────────────────
#   미커밋 변경이 있으면 거부한다. 스냅샷 복원이라 원리적으로는 안전하지만,
#   **변이 결과 자체가 오염**된다 — 내 미커밋 편집이 섞인 상태를 재는 것이기 때문이다.
if ! git diff --quiet -- "$FILE" || ! git diff --cached --quiet -- "$FILE"; then
  echo "★중단: '$FILE' 에 미커밋 변경이 있다(CLAUDE.md §B7)." >&2
  echo "  변이 결과가 오염된다 — **커밋 먼저** 하고 다시 실행할 것." >&2
  git --no-pager diff --stat -- "$FILE" | sed 's/^/    /' >&2
  exit 10
fi

# ── ⑤★기준선 rc 측정 ───────────────────────────────────────────────────────
#   ★변이를 넣기 **전에** 같은 명령을 돌려 초록인지 본다. 빨간 기준선에서 나온
#     CAUGHT 는 **변이를 잡은 것이 아니라 원래 빨간 것**이다.
#   ★비용: 테스트를 한 번 더 돈다. 그 값이 아까우면 `MUTATE_SKIP_BASELINE="사유"` 로
#     건너뛸 수 있다 — **다만 그때 나온 CAUGHT 는 근거로 쓰지 마라.**
if [ -n "${MUTATE_SKIP_BASELINE:-}" ]; then
  echo "== 기준선 측정 건너뜀 =="
  echo "  사유: $MUTATE_SKIP_BASELINE"
  echo "  ★이 실행의 CAUGHT 는 **기준선이 초록이라는 보장이 없다.** 근거로 인용하지 말 것."
else
  echo "== 기준선(변이 없음) =="
  BASE_LOG="$(mktemp)"
  set +e
  "$@" >"$BASE_LOG" 2>&1
  BASE_RC=$?
  set -e
  if [ "$BASE_RC" -eq 5 ]; then
    # ★★rc=5 는 pytest 의 **「수집 0건」**이다 — 빨간 기준선과 **처방이 다르다**.
    #   전자는 **러너**를 고치고(-k·경로), 후자는 **코드/환경**을 고친다.
    #   뭉치면 *"기준선이 빨갛다"* 를 보고 **있지도 않은 실패를 찾으러 간다.**
    #   ★동료 세션 development-ai-ca 실측(2026-08-27): `-k` 오타 하나로 테스트가
    #     **한 건도 안 돌았는데** rc≠0 이라 CAUGHT 로 보고됐다.
    echo "판정 불가(무효) — 테스트가 **0건 수집**됐다(pytest rc=5)." >&2
    echo "  변이와 무관하게 rc≠0 이므로 **거짓 CAUGHT** 가 된다." >&2
    echo "  ★이건 기준선이 빨간 것이 아니라 **러너가 아무것도 안 고른 것**이다." >&2
    echo "  확인할 것: -k 표현식 오타 · 테스트 파일 경로 · 이름 변경 · working-directory" >&2
    exit 14
  fi
  if [ "$BASE_RC" -ne 0 ]; then
    # ★판정을 발행하지 않는다 — 파이프 축(12)과 같은 규율이다.
    #   못 믿는 값으로 CAUGHT 를 찍으면 그것이 증거로 인용된다.
    echo "판정 불가(무효) — **기준선이 이미 빨갛다**(rc=$BASE_RC)." >&2
    echo "  이 상태에서는 어떤 변이를 넣어도 rc≠0 이라 **전부 거짓 CAUGHT** 가 된다." >&2
    # ★백틱을 쓰지 않는다 — 종전 판은 안내문의 백틱이 **셸에서 명령 치환**돼
    #   "command not found" 가 찍히고 **문구가 소실**됐다(내가 이 도구를 돌려서 발견했다).
    echo "  (실증 2026-08-27: 값이 동일한 5000 → 5_000 변이가 CAUGHT 로 나왔다)" >&2
    echo "  다음 중 하나를 하라:" >&2
    echo "    · 기준선을 초록으로 만들어라(권장) — 무엇이 빨간지부터 보라" >&2
    echo "    · 테스트 범위를 좁혀라(그 변이가 실제로 태우는 파일만)" >&2
    echo "    · 정말 의도한 것이면  MUTATE_SKIP_BASELINE=\"사유\"  로 다시 실행하라" >&2
    rm -f "$BASE_LOG"
    exit 13
  fi

  # ── ⑤-2 ★★개수 축 — rc 만으로는 **원리적으로 한 칸이 샌다** ──────────────
  #
  #   실측 2026-08-28(내 손으로 재확인 · 동료 development-ai-ca 가 먼저 짚고
  #   development-ai-32 가 vitest 축을 보탰다):
  #
  #     러너    오타 종류   기준선 rc   rc축   틀리는 방향
  #     pytest  -k 이름         5       걸림   거짓 CAUGHT
  #     pytest  파일 경로       4       걸림   거짓 CAUGHT
  #     vitest  파일 경로       1       걸림   거짓 CAUGHT
  #     vitest  -t 이름       ★0     ★통과   ★거짓 SURVIVED
  #
  #   ★vitest 는 -t 가 아무것도 안 골라도 rc=0 이다(요약: Tests 15 skipped (15)).
  #     기준선도 rc=0 이라 **어떤 rc 기반 게이트도 통과한다.** 개수를 봐야만 갈린다.
  #
  #   ★추출 함정 — 여기가 이 함정의 **새 서식지**다:
  #     첫 매치를 집으면 요약이 아니라 본문 줄을 읽는다(vitest 는 Test Files 줄이 먼저).
  #     그래서 **모든 매치의 최대값**을 쓴다 — 줄 위치를 가정하지 않는다.
  #   ★|| true 가 필수다 — grep 은 **0건일 때 exit 1** 이고, 명령치환 대입의 종료코드는
  #     파이프 마지막 명령의 것이라 set -e 가 **판정 대신 스크립트를 죽인다**(rc=1).
  #     실측 2026-08-28: 이 줄이 없어서 vitest 빈 선택이 exit 15 가 아니라 rc=1 로 나왔다 —
  #     ★그러면 「테스트 실패(1)」와 **구별되지 않는다.** 무성 실패보다 나쁘다: 그럴듯하다.
  #   ★가드는 **파이프 끝에 하나만** 둔다. 명령치환 대입의 종료코드는 파이프
  #     **마지막** 명령의 것이므로 중간 grep 에 || true 를 또 달아도 판정에 영향이 없다
  #     (실측: 안쪽만 지운 변이는 **생존** · 바깥을 지우면 CAUGHT).
  #     도달 불가 방어를 남겨 두면 변이 점수만 부풀린다.
  BASE_PASSED=$(grep -oE '[0-9]+ passed' "$BASE_LOG" 2>/dev/null \
                  | grep -oE '^[0-9]+' | sort -rn | head -1 || true)
  BASE_PASSED=${BASE_PASSED:-0}
  if [ "$BASE_PASSED" -eq 0 ]; then
    echo "판정 불가(무효) — 기준선에서 **통과한 케이스가 0건**이다(rc=$BASE_RC)." >&2
    echo "  rc 는 초록인데 실제로는 **아무것도 실행되지 않았다.**" >&2
    echo "  ★이 상태에서는 변이를 넣어도 rc 가 안 변해 **전부 거짓 SURVIVED** 가 된다." >&2
    echo "  가장 흔한 원인: vitest -t / pytest -k 표현식이 **아무것도 고르지 않았다**" >&2
    echo "                 (vitest 는 전부 skip 이어도 rc=0 이라 조용하다)" >&2
    echo "  기준선 요약:" >&2
    grep -aE 'Tests |Test Files |[0-9]+ (passed|skipped|failed|xfailed|deselected)' "$BASE_LOG" \
      | tail -3 | sed 's/^/    /' >&2 || true
    echo "  대상이 정말 전부 xfail/skip 이면  MUTATE_SKIP_BASELINE=\"사유\"  로 다시 실행하라" >&2
    rm -f "$BASE_LOG"
    exit 15
  fi
  rm -f "$BASE_LOG"
  # ★"rc=0" 이라고 쓰지 않는다 — rc=0 은 유효성의 근거가 **아니었다**(위 표 4행).
  echo "  기준선 초록 · **통과 $BASE_PASSED 건** — 판정이 유효하다."
fi

SNAP="$(mktemp)"
cp "$FILE" "$SNAP"

# ── ③원복은 git 이 아니라 스냅샷에서 · ④바이트 동일 단언 ────────────────────
restore() {
  cp "$SNAP" "$FILE"
  if ! cmp -s "$SNAP" "$FILE"; then
    echo "★★원복 실패 — '$FILE' 이 스냅샷과 다르다. 손으로 확인할 것: $SNAP" >&2
    exit 70
  fi
  rm -f "$SNAP"
}
trap restore EXIT   # 중간에 끊겨도 반드시 원복(Ctrl-C·오류 포함)

# ── ②§B8 주입 확인 — grep 이 아니라 내용 비교 ────────────────────────────────
sed -i "$SED_EXPR" "$FILE"
if cmp -s "$SNAP" "$FILE"; then
  echo "★중단: 변이가 **주입되지 않았다**(파일 내용 무변화 · CLAUDE.md §B8)." >&2
  echo "  sed 표현식이 대상을 못 찾았다. 이 상태로 테스트를 돌리면 '통과'가 무의미하다." >&2
  echo "  표현식: $SED_EXPR" >&2
  exit 11
fi
echo "== 주입 확인(내용이 실제로 바뀜) =="
git --no-pager diff --no-index --stat "$SNAP" "$FILE" 2>/dev/null | tail -1 | sed 's/^/  /' || true

# ── ⑥파이프 경고 — 이 저장소가 반복해서 데인 함정 ──────────────────────────
#   `cmd | tail -1` 은 **파이프 끝의 종료코드**를 준다. 그러면 테스트가 실패해도 rc=0 이 되어
#   이 하네스가 **CAUGHT 를 SURVIVED 로 보고**한다.
#   ★실제로 이 도구의 **첫 실사용에서 그 일이 났다**(2026-08-21): 테스트는 `1 failed` 인데
#     `| tail -1` 때문에 SURVIVED 로 찍혔다. 도구는 정확했고 **호출이 틀렸다.**
#   도구가 호출자의 셸 문자열까지 알 수는 없으니, 보이면 **시끄럽게 경고**한다.
#
# ★★2026-08-27 정정 — **경고만으로는 못 막았다.** 종전엔 위 사실을 알면서도
#   `stderr` 로 세 줄 찍고 **오염된 `RC` 로 판정을 그대로 발행**했다. 즉 도구가
#   *"이 값은 못 믿는다"* 를 알면서 **그 값으로 SURVIVED/CAUGHT 를 찍었다.**
#   다음 사람은 경고가 아니라 **마지막 줄**을 읽는다(동료 세션 실측: 실제로 오보를 읽었다).
#   **경고는 산문이고 판정이 산출물이다** — 이 저장소 §검증규율 9 가 도구 안에서 재발했다.
#   → 파이프가 보이면 **판정을 발행하지 않는다.** `판정 불가(무효)` + 비정상 종료(12).
#
# ★차단하되 길을 준다(이 저장소 관행 — `REVIEW_EXEMPT` 동형):
#   · 명령에 `set -o pipefail` 이 있으면 `RC` 를 신뢰할 수 있으므로 **정상 판정**한다.
#   · 인자 안의 **리터럴 `|`**(예: `-k 'a|b'` 정규식)는 파이프가 아니다 — 위양성도 결함이므로
#     `MUTATE_ALLOW_PIPE="사유"` 로 통과시키되 **사유를 출력에 남긴다.**
# ★★2026-09-02 재설계 — **탐지가 거꾸로였다**(실증).
#
#   이 도구는 `"$@"` 로 **execvp 직접 실행**한다 — **셸을 거치지 않는다.**
#   그래서 rc 를 못 믿는 경우는 **호출자가 셸 래퍼로 감쌌을 때뿐**이고,
#   직접 argv 호출에서 인자 안의 `|` 는 **리터럴**이다(파이프가 아니다).
#
#   종전엔 **인자열 전체에서 문자 `|` 하나만** 봤다. 그래서 층이 섞였다:
#
#       bash -c "pytest | tail"     → 잡힘        (맞다)
#       bash -c "pytest; tail"      → **못 잡음**  ← 거짓 SURVIVED (격리 저장소에서 실증)
#       bash -c "pytest && tail"    → **못 잡음**
#       pytest -k 'a|b' (직접argv)  → 잡힘        ← **리터럴인데 차단**(위양성)
#
#   ★한 문장: **같은 문자 하나로 성질이 다른 두 층을 판정하고 있었다.**
#
#   ★그리고 면제가 **탐지를 통째로 껐다** — `case *"pipefail"*` 이 무조건 0 으로 되돌려
#     `set -o pipefail; pytest; tail`(`;` 위험 잔존)까지 면제했고, `pipefail` 이
#     **변수명·주석·경로에 문자열로만** 있어도 면제됐다(단어 경계 없음).
#
# ★★왜 형태를 더 넓히지 않는가(`*[";|&"]*`):
#   `set -o pipefail; pytest | tail` 은 **안전**하고(`;` 가 설정만 분리 · rc 는 파이프라인 것)
#   `pytest; tail` 은 **위험**하다. **같은 `;` 인데 성질이 다르다** — 문자열로는 못 가른다.
#   못 가르는 것을 가르는 척하면 위양성과 위음성을 **동시에** 낸다(종전이 그랬다).
#   → **추측하지 않는다.** 셸 스크립트 문자열은 **불투명**하다고 인정하고,
#     그 층이면 **판정을 발행하지 않는다**(호출자가 사유를 대고 통과시킬 수 있다).
#   ★★그리고 **셸 래퍼라고 다 위험한 것도 아니다.** `bash -c 'pytest tests/x.py -q'` 처럼
#     **단일 단순 명령**이면 rc 는 그 명령의 것이다(이 저장소의 기존 락이 그 형태로 부른다).
#     그래서 래퍼면 **스크립트 문자열을 본다** — 위험한 것은 **명령을 잇는 연산자**다.
#   ★`set -o pipefail` 은 **접두 설정**이므로 걷어내고 본다. 그러면
#       set -o pipefail; cmd | tail   → 나머지에 `;` 없음 · `|` 는 pipefail 이 고침 → **안전**
#       set -o pipefail; cmd; tail    → 나머지에 `;` 있음                          → **위험**
#     같은 `;` 를 위치로 가른다 — 문자 하나로는 못 하던 것을 **구조로** 한다.
#   ★★fail-closed 가 이 판정의 뼈대다. 구판은 **두 겹으로 fail-open** 이었다:
#     ①`env bash -c` · `timeout 60 bash -c` 는 argv[0] 이 셸이 아니라 **case 에 걸리지도 않았고**
#     ②`bash -lc` · `bash -c --` 는 `-c` 를 못 찾아 `_script` 가 비면 **그냥 신뢰**했다.
#     그 결과 **파이프를 실은 5형태가 「차단」에서 「거짓 SURVIVED」로** 열렸다(적대 리뷰 실측).
#     → 무엇이 실행되는지 **특정하지 못하면 판정하지 않는다.**
#   ★`&&` 를 위험에 넣는 이유는 「실패를 가린다」가 **아니다**(가리지 못한다 — `a && b` 의 rc 는
#     어느 쪽이 실패해도 0 이 아니다). 위험한 방향이 **반대**다: `cd 없는디렉토리 && pytest` 는
#     **테스트가 돌지도 않았는데 rc≠0** 이라 **거짓 CAUGHT** 를 만든다. 변이 점수를 부풀리는
#     그 방향도 똑같이 결함이다(`sh -c 'set -o pipefail'` 이 dash 에서 내는 것과 같은 클래스).
#   ★★★2026-09-02 3차 — **위험을 열거하는 방식을 버린다.**
#     1차는 문자 `|` 하나, 2차는 `; & && || 개행` 목록이었다. 매번 **빠뜨린 형태가 거짓
#     SURVIVED 로 새어** 나갔다(적대 리뷰 2회가 각각 8형태·8형태를 찾아냈다).
#     **목록은 곧 상한이 된다** — 이 저장소가 반복해서 적은 그것이다.
#     → **뒤집는다: 위험을 세지 않고 「단일 단순 명령의 모양」만 신뢰한다.**
#       메타문자가 하나라도 있으면 **그 의미를 따지지 않고** 판정을 발행하지 않는다.
#       (`2>&1` 처럼 실제로는 안전한 것도 막힌다 — 그것이 이 설계가 치르는 값이고,
#        탈출구 `MUTATE_ALLOW_SHELL` 이 사유를 남기고 통과시킨다.)
#   ★rc 를 **바꿀 수 있는** 접두 래퍼(`timeout`)는 셸을 끼워도 신뢰하지 않는다 —
#     시간초과 rc(124)가 **거짓 CAUGHT** 가 된다. `&&` 를 막은 것과 같은 자다.
RC_UNTRUSTED=0
RC_WHY=""
_NL='
'
# ★셸 판정을 **파생**시킨다 — 이름만 보면 `rbash`(→bash 심링크)·`ash`·`mksh` 가 새어 나가
#   **셸인데 직접 명령으로 신뢰**된다(적대 리뷰 3차 실측: `rbash -c 'a; true'` → 거짓 SURVIVED).
#   세 축: ①이름 ②심링크를 따라간 **실체** ③시스템 자신의 목록 `/etc/shells`.
_resolved_shell=""
# ★rc 를 **바꾸거나 버리는** 프로그램. **argv 층과 스크립트 문자열 층이 이 함수를 공유**한다 —
#   3차에서 argv 층만 닫았더니 `bash -c 'script -qc …'` 한 겹으로 전부 우회됐다(4차 CRITICAL-2).
#   ★`setsid` 는 실측상 rc 를 버린다(`setsid false` → **0**). 중립 목록에 두면 안 된다.
#   ★이 목록은 **완전하지 않다** — 임의 실행파일은 원리적으로 알 수 없다(§부채·xfail).
# ★rc **중립** 접두 — rc 가 그대로 통과한다. argv 층과 스크립트 문자열 층이 **같은 목록**을
#   보게 함수로 뺀다(5차 리뷰 CRITICAL-1: 함수는 공유했는데 **먹이는 입력이 두 층에서 달랐다**).
_rc_neutral_prefix() {
  case "$(basename -- "${1:-}")" in
    env|nohup|stdbuf|command|exec|nice|ionice) return 0 ;;
  esac
  return 1
}
_rc_destroying() {
  case "$(basename -- "${1:-}")" in
    timeout|script|flock|xargs|retry|setsid) return 0 ;;
  esac
  return 1
}
_is_shell() {
  _n="$(basename -- "$1")"
  # ★**항상 실체까지 푼다.** 이름이 목록에 있다고 거기서 멈추면 `rbash`(→bash)의
  #   pipefail 지원 여부를 **이름으로** 판정하게 되어 정상 사용을 막는다(실측: rbash 는
  #   pipefail 을 실제로 지원한다 — 직접 실행 rc=1 확인).
  _r="$(command -v -- "$1" 2>/dev/null)" || _r=""
  if [ -n "$_r" ]; then
    _rr="$(readlink -f -- "$_r" 2>/dev/null)" || _rr="$_r"
  else
    _rr=""
  fi
  _rn="${_rr:+$(basename -- "$_rr")}"
  for _cand in "$_rn" "$_n"; do
    [ -n "$_cand" ] || continue
    case "$_cand" in
      sh|bash|zsh|dash|ksh|ash|mksh|rbash|busybox|yash|posh)
        _resolved_shell="$_cand"; return 0 ;;
    esac
  done
  if [ -n "$_r" ] && [ -r /etc/shells ]; then
    if grep -qxF -- "$_r" /etc/shells 2>/dev/null || grep -qxF -- "$_rr" /etc/shells 2>/dev/null; then
      _resolved_shell="${_rn:-$_n}"; return 0
    fi
  fi
  return 1
}
_wrapper=""; _script=""; _scriptfile=0
_saw_prefix=0; _rc_altering=0; _state=scan; _skipnext=0; _had_pipefail=0
for _a in "$@"; do
  if [ "$_skipnext" != 0 ]; then
    # ★부호를 본다 — `+o pipefail` 은 **끄는 것**인데 종전엔 켜는 것으로 셌다(리뷰 HIGH-4).
    #   그리고 **부분문자열이 아니라 정확한 낱말**이어야 한다(`pipefailZZ` 가 통과했다 · HIGH-5).
    if [ "$_a" = "pipefail" ]; then
      [ "$_skipnext" = on ] && _had_pipefail=1 || _had_pipefail=0
    fi
    _skipnext=0
    continue
  fi
  case "$_state" in
    scan)
      if _rc_destroying "$_a"; then
        _saw_prefix=1; _rc_altering=1; continue
      fi
      # ★rc **중립** 접두는 **투명**하다(신뢰 판정을 바꾸지 않는다) — 막으면
      #   `env FOO=1 pytest` 같은 가장 흔한 정당 형태를 막는다(4차 HIGH-2).
      if _rc_neutral_prefix "$_a"; then
        _saw_prefix=1; continue
      fi
      if _is_shell "$_a"; then
        _wrapper="$_resolved_shell"; _state=shellargs; continue
      fi
      if [ "$_saw_prefix" -eq 1 ]; then
        case "$_a" in -*|*=*|[0-9]*) continue ;; esac
      fi
      break
      ;;
    shellargs)
      case "$_a" in
        # ★`--` 를 여기서 만났다면 **`-c` 를 본 적이 없다** — 다음 인자는 스크립트 **파일**이다
        #   (`bash -- runner.sh`). 종전엔 그것을 `-c` 문자열로 받아 **파일명을 검사**했고,
        #   파일명엔 메타문자가 없으니 그대로 신뢰됐다(적대 리뷰 3차 CRITICAL-1).
        --)     _scriptfile=1; break ;;
        -o)     _skipnext=on;  continue ;;
        +o)     _skipnext=off; continue ;;
        --*)    continue ;;          # ★`-*c*` 보다 **먼저** 봐야 한다(--norc/--rcfile 이 c 를 품는다)
        -*c*)   _state=wantscript; continue ;;
        -*)     continue ;;
        *)      _scriptfile=1; break ;;
      esac
      ;;
    wantscript)
      case "$_a" in
        --) continue ;;
        *)  _script="$_a"; _state=done; break ;;
      esac
      ;;
  esac
done
if [ "$_rc_altering" -eq 1 ]; then
  RC_UNTRUSTED=1
  RC_WHY="rc 를 바꿀 수 있는 접두 래퍼(timeout 등)를 거친다 — 시간초과 rc(124)가 **거짓 CAUGHT** 가 된다"
elif [ -n "$_wrapper" ] && [ "$_state" != done ]; then
  RC_UNTRUSTED=1
  if [ "$_scriptfile" -eq 1 ]; then
    RC_WHY="셸 래퍼가 **스크립트 파일**을 받는다 — 내용을 볼 수 없어 rc 가 테스트의 것인지 판정하지 않는다"
  else
    RC_WHY="셸 래퍼인데 '-c' 스크립트를 특정하지 못했다 — 무엇이 실행되는지 모르므로 판정하지 않는다"
  fi
elif [ -n "$_wrapper" ]; then
  _rest="$_script"
  # ★접두 `set …` 을 **반복해서** 걷는다. 단 그 절에 주석·명령치환이 있으면 **걷지 않는다**
  #   (걷어내면 그 안의 테스트까지 시야에서 사라져 위음성이 된다 — 적대 리뷰 M1 실측).
  while :; do
    while :; do
      case "$_rest" in
        " "*) _rest="${_rest# }" ;;
        "	"*) _rest="${_rest#	}" ;;
        *) break ;;
      esac
    done
    case "$_rest" in "set -"*) ;; *) break ;; esac
    _segA="${_rest%%;*}"; _segB="${_rest%%"$_NL"*}"
    if [ "$_segA" = "$_rest" ] && [ "$_segB" = "$_rest" ]; then break; fi
    if [ ${#_segA} -le ${#_segB} ]; then
      _seg="$_segA"; _tail="${_rest#*;}"
    else
      _seg="$_segB"; _tail="${_rest#*"$_NL"}"
    fi
    # ★스트립 가드는 **화이트리스트와 같은 집합**이어야 한다 — 약하면 위험이 스트립으로
    #   시야에서 사라진다(`set -e | grep …; true` 가 통과했다 · 적대 리뷰 3차 HIGH-6).
    case "$_seg" in
      *"&"*|*"("*|*")"*|*"<"*|*">"*|*'`'*|*'$'*|*"!"*|*"#"*|*"|"*) break ;;
    esac
    # ★부분문자열이 아니라 **낱말**로, 그리고 **부호**를 본다.
    _pf_prev=""
    set -f          # ★비인용 순회라 `*`·`?` 가 cwd 에 글롭된다 — 판정이 작업디렉토리에 의존하면 안 된다
    for _w in $_seg; do
      if [ "$_w" = "pipefail" ]; then
        case "$_pf_prev" in -*o) _had_pipefail=1 ;; +*o) _had_pipefail=0 ;; esac
      fi
      _pf_prev="$_w"
    done
    set +f
    _rest="$_tail"
  done
  # ★`sh`/`dash` 에는 `set -o pipefail` 이 없다 — 인정하면 「명령이 깨져서 CAUGHT」가 된다.
  case "$_wrapper" in bash|zsh|ksh|mksh|rbash) ;; *) _had_pipefail=0 ;; esac
  # ★화이트리스트 — 위험을 세지 않고 **단일 단순 명령의 모양**만 신뢰한다.
  case "$_rest" in
    ""|" "*|"	"*)
      # ★리터럴 빈 문자열만 막으면 `bash -c $'\t'` 가 샌다(리뷰 LOW).
      #   선행 공백은 위에서 이미 걷었으므로, 여기 남았다면 **공백뿐**이라는 뜻이다.
      RC_UNTRUSTED=1
      RC_WHY="래퍼 스크립트가 비어 있다(공백뿐) — 테스트가 실행되지 않았는데 rc=0 이 나온다"
      ;;
    *"||"*|*";"*|*"&"*|*"("*|*")"*|*"<"*|*">"*|*'`'*|*'$'*|*"!"*|*"#"*|*"$_NL"*)
      RC_UNTRUSTED=1
      RC_WHY="래퍼 스크립트가 **단일 단순 명령이 아니다**('||' ';' '&' '(' ')' '<' '>' 백틱 '\$' '!' '#' 개행 중 하나가 있다) — rc 가 테스트의 것이라고 보증할 수 없다"
      ;;
    *"|"*)
      if [ "$_had_pipefail" -eq 0 ]; then
        RC_UNTRUSTED=1
        RC_WHY="래퍼 스크립트에 파이프가 있는데 'set -o pipefail' 이 없다(또는 그 셸이 지원하지 않는다) — rc 는 **끝 명령**의 것이다"
      fi
      ;;
  esac
  # ★화이트리스트는 **모양만** 본다 — **명령 이름**도 봐야 한다(4차 CRITICAL-2).
  #   `bash -c 'script -qc "…" /dev/null'` 은 메타문자가 없어 통과하는데 **rc 가 버려진다.**
  #   argv 층과 **같은 함수**(`_rc_destroying`)를 쓴다 — 한 곳을 고치면 두 층이 따라온다.
  #   ★`set --` 로 낱말을 뽑으면 `"$@"` 가 파괴되어 **테스트 실행 자체가 깨진다** — 쓰지 않는다.
  if [ "$RC_UNTRUSTED" -eq 0 ]; then
    _scan="$_rest"
    while :; do
      _one="${_scan%%|*}"
      # ★argv 층과 **같은 규칙**으로 명령 낱말을 찾는다 — 종전엔 «공백으로 자른 첫 낱말» 하나만
      #   봐서 `env script …` · `nice timeout …` · 탭 구분이 전부 검사를 비껴갔다(5차 CRITICAL-1).
      #   `for` 는 IFS 로 쪼개므로 **탭·개행도 구분자**다.
      _cmd=""
      set -f
      for _w in $_one; do
        case "$_w" in *=*) continue ;; esac        # VAR=값 대입은 명령이 아니다
        if _rc_neutral_prefix "$_w"; then continue; fi
        _cmd="$_w"; break
      done
      set +f
      if [ -n "$_cmd" ]; then
        # ★**해석하지 못하면 신뢰하지 않는다**(fail-closed). 종전엔 이름을 못 알아보면
        #   그냥 신뢰해서 `"script"` · `sc""ript` 가 통과했다 — 이 도구가 스스로 선언한
        #   *"무엇이 실행되는지 특정하지 못하면 판정하지 않는다"* 와 **정반대**였다.
        #   ★**명령 낱말만** 본다 — 인자의 따옴표(`grep -q "alpha" f`)는 정상이다.
        case "$_cmd" in
          *\'*|*\"*|*\\*)
            RC_UNTRUSTED=1
            RC_WHY="래퍼 스크립트의 **명령 이름에 인용부호/이스케이프**가 있어 무엇을 부르는지 특정할 수 없다 — 판정하지 않는다"
            break
            ;;
        esac
        if _rc_destroying "$_cmd"; then
          RC_UNTRUSTED=1
          RC_WHY="래퍼 스크립트가 **rc 를 바꾸거나 버리는 명령**($_cmd)을 부른다 — rc 가 테스트의 것이 아니다"
          break
        fi
      fi
      case "$_scan" in
        *"|"*) _scan="${_scan#*|}" ;;
        *) break ;;
      esac
    done
  fi
fi
if [ "$RC_UNTRUSTED" -eq 1 ] && [ -n "${MUTATE_ALLOW_SHELL:-}${MUTATE_ALLOW_PIPE:-}" ]; then
  echo "== 셸 래퍼 예외: ${MUTATE_ALLOW_SHELL:-${MUTATE_ALLOW_PIPE:-}} (호출자가 rc 보존을 선언) =="
  RC_UNTRUSTED=0
fi
PIPE_SEEN="$RC_UNTRUSTED"

# ── 테스트 실행 ─────────────────────────────────────────────────────────────
echo "== 변이 상태에서 테스트 =="
set +e
"$@"
RC=$?
set -e

if [ "$PIPE_SEEN" -eq 1 ]; then
  # ★판정을 발행하지 않는다 — 못 믿는 값으로 SURVIVED/CAUGHT 를 찍으면 그것이 증거로 인용된다.
  echo "판정 불가(무효) — rc=$RC 를 신뢰할 수 없다: ${RC_WHY}"
  echo "  셸 스크립트의 rc 는 **마지막 명령의 것**이다: 'pytest ...; tail -1' 처럼 쓰면"
  echo "  테스트가 실패해도 rc=0 이 되어 **CAUGHT 가 SURVIVED 로 보고**된다."
  echo "  (파이프도 같은 형태다 — 이 도구의 첫 실사용에서 실제로 났다 · 2026-08-21)"
  echo "  ★이 도구는 셸을 거치지 않고 execvp 로 직접 실행하므로, 래퍼를 빼면 rc 가 정확하다."
  echo "  다음 중 하나를 하라:"
  echo "    · 셸 래퍼를 빼라(권장) — 예:  mutate_manual.sh <파일> <sed> pytest tests/x.py -q"
  echo "      ★인자 안의 리터럴 '|'(예: -k 'a|b')는 **파이프가 아니다** — 그대로 써도 된다."
  echo "    · 래퍼가 꼭 필요하고 rc 를 보존했다면(마지막 명령이 테스트이거나 RC 를 명시 보존)"
  echo "      MUTATE_ALLOW_SHELL=\"사유\" 로 다시 실행하라(사유가 출력에 남는다)."
  PIPE_INVALID=1
elif [ "$RC" -eq 0 ]; then
  echo "SURVIVED — 변이를 넣었는데 테스트가 통과했다. 그 자리는 잠겨 있지 않다."
else
  echo "CAUGHT — 변이가 잡혔다(rc=$RC)."
fi

# trap 이 원복한다. 원복 결과는 아래에서 다시 확인한다.
restore
trap - EXIT
if ! git diff --quiet -- "$FILE"; then
  echo "★★원복 후에도 작업트리가 더럽다: $FILE" >&2
  exit 71
fi
echo "== 원복 확인(작업트리 깨끗) =="

# ★판정 불가는 **성공도 실패도 아니다.** 오염된 RC 를 그대로 돌려주면 호출 스크립트가
#   그것을 CAUGHT/SURVIVED 로 해석한다 — 이 도구가 막으려는 그 일이다.
if [ "${PIPE_INVALID:-0}" -eq 1 ]; then
  exit 12
fi
# ★테스트가 **진짜로 12** 를 내면 stdout 은 CAUGHT 인데 종료코드는 「판정 불가」와 같아진다.
#   CLAUDE.md 가 *"12 를 실패로 읽지 마라"* 라고 선언했으므로, 종료코드만 읽는 호출자는
#   **진짜 CAUGHT 를 판정 불가로 오독**한다 — 이 도구가 막으려는 그 일이다(리뷰 3차 MEDIUM).
#   판정은 이미 stdout 에 있으므로 **충돌하는 값만** 1 로 옮긴다.
if [ "$RC" -eq 12 ]; then
  echo "  (참고: 테스트가 낸 rc=12 는 이 도구의 「판정 불가」와 겹치므로 종료코드를 1 로 옮긴다)"
  exit 1
fi
exit "$RC"

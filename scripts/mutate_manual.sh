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
RC_UNTRUSTED=0
RC_WHY=""
case "$(basename -- "${1:-}")" in
  sh|bash|zsh|dash|ksh)
    # `-c` 다음 인자가 스크립트다.
    _script=""; _next=0
    for _a in "$@"; do
      if [ "$_next" -eq 1 ]; then _script="$_a"; break; fi
      [ "$_a" = "-c" ] && _next=1
    done
    if [ -n "$_script" ]; then
      # ★접두 `set -o pipefail`(및 -e/-u 조합)을 걷어낸다 — 그것은 명령 연결이 아니다.
      _rest="$_script"
      _had_pipefail=0
      case "$_rest" in
        "set -"*"pipefail"*";"*)
          _had_pipefail=1
          _rest="${_rest#*;}"
          ;;
      esac
      case "$_rest" in
        *";"*|*"&&"*|*"||"*)
          RC_UNTRUSTED=1
          RC_WHY="래퍼 스크립트가 명령을 이어 붙인다(';' 또는 '&&'/'||') — rc 는 **마지막 명령**의 것이다"
          ;;
        *"|"*)
          if [ "$_had_pipefail" -eq 0 ]; then
            RC_UNTRUSTED=1
            RC_WHY="래퍼 스크립트에 파이프가 있는데 'set -o pipefail' 이 없다 — rc 는 **끝 명령**의 것이다"
          fi
          ;;
      esac
    fi
    ;;
esac
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
exit "$RC"

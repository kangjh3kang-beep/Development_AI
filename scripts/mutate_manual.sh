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
#     가 나왔다. 이 도구는 파이프 오염(12)·미커밋(10)·주입실패(11)는 막고 있었는데
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
  set +e
  "$@" >/dev/null 2>&1
  BASE_RC=$?
  set -e
  if [ "$BASE_RC" -ne 0 ]; then
    # ★판정을 발행하지 않는다 — 파이프 축(12)과 같은 규율이다.
    #   못 믿는 값으로 CAUGHT 를 찍으면 그것이 증거로 인용된다.
    echo "판정 불가(무효) — **기준선이 이미 빨갛다**(rc=$BASE_RC)." >&2
    echo "  이 상태에서는 어떤 변이를 넣어도 rc≠0 이라 **전부 거짓 CAUGHT** 가 된다." >&2
    echo "  (실증 2026-08-27: 의미가 동일한 `5000`→`5_000` 변이가 CAUGHT 로 나왔다)" >&2
    echo "  다음 중 하나를 하라:" >&2
    echo "    · 기준선을 초록으로 만들어라(권장) — 무엇이 빨간지부터 보라" >&2
    echo "    · 테스트 범위를 좁혀라(그 변이가 실제로 태우는 파일만)" >&2
    echo "    · 정말 의도한 것이면  MUTATE_SKIP_BASELINE=\"사유\"  로 다시 실행하라" >&2
    exit 13
  fi
  echo "  기준선 초록(rc=0) — 판정이 유효하다."
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
PIPE_SEEN=0
case " $* " in *"|"*) PIPE_SEEN=1 ;; esac
case " $* " in *"pipefail"*) PIPE_SEEN=0 ;; esac   # 호출자가 이미 막았다
if [ "$PIPE_SEEN" -eq 1 ] && [ -n "${MUTATE_ALLOW_PIPE:-}" ]; then
  echo "== 파이프 예외: ${MUTATE_ALLOW_PIPE} (호출자가 리터럴이라고 선언) =="
  PIPE_SEEN=0
fi

# ── 테스트 실행 ─────────────────────────────────────────────────────────────
echo "== 변이 상태에서 테스트 =="
set +e
"$@"
RC=$?
set -e

if [ "$PIPE_SEEN" -eq 1 ]; then
  # ★판정을 발행하지 않는다 — 못 믿는 값으로 SURVIVED/CAUGHT 를 찍으면 그것이 증거로 인용된다.
  echo "판정 불가(무효) — 테스트 명령에 파이프(|)가 있어 rc=$RC 를 신뢰할 수 없다."
  echo "  파이프는 **끝 명령의 종료코드**를 준다: 테스트가 실패해도 rc=0 이 되어"
  echo "  CAUGHT 가 SURVIVED 로 보고된다(이 도구의 첫 실사용에서 실제로 났다 · 2026-08-21)."
  echo "  다음 중 하나를 하라:"
  echo "    · 파이프를 빼라(권장)"
  echo "    · 명령 안에 'set -o pipefail' 을 넣어라"
  echo "    · 리터럴 '|' 라면  MUTATE_ALLOW_PIPE=\"사유\" 로 다시 실행하라"
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

# shellcheck shell=bash
# ════════════════════════════════════════════════════════════════
# assert_a1_host — **「기계가 틀렸다」와 「경로가 틀렸다」를 가른다.**
#
# 왜(실증 2026-09-12): `safe-deploy.sh` 가 `cd "$REPO" || { status "FAIL cd-repo"; exit 1; }`
#   **한 문구**로 두 사건을 같은 모양으로 냈다. 동료 세션이 개발 워크트리에서 돌려
#   ㉡(기계가 틀렸다)를 만났고 그것을 ㉠(경로가 틀렸다)으로 읽어
#   *"Hardcoded $HOME/Development_AI vs Actual My_Projects Nested Path"* 를 **결함으로 인계**했다.
#   그 수정을 적용했다면 A1 에서 배포가 **영구히** 막혔을 것이다
#   (A1 실측: `$HOME/Development_AI` 실재 · `$HOME/My_Projects/...` 없음).
#
# ★**함수로 뺀 이유** — 형제가 셋이다(`safe-deploy.sh`·`rollback-web.sh`·`a1-*`).
#   블록을 복붙하면 한쪽만 고쳐지는 발산이 생긴다(이 저장소의 반복 결함).
#   ***한 곳을 고치면 전역이 따라오게 한다.***
#
# 사용: assert_a1_host "$REPO" "<상태를 적는 함수 이름 또는 빈 문자열>"
#   · A1 이 아니면  → 안내를 stderr 로 내고 **exit 8**
#   · A1 인데 경로 없음 → **exit 1**(다른 이름의 사건)
#   · 경로가 있으면 → **아무것도 하지 않는다**(정상 경로에서는 한 줄도 안 돈다)
# ════════════════════════════════════════════════════════════════
assert_a1_host() {
  local repo="${1:?assert_a1_host: repo 경로가 필요하다}"
  local status_fn="${2:-}"
  [ -d "$repo" ] && return 0

  # 여기가 A1 인지 아닌지를 **실제로 가른다** — 개발 워크트리에는 중첩 경로가 있다.
  if [ -d "$HOME/My_Projects/Development_AI" ] || [ -d "$PWD/propai-platform" ]; then
    [ -n "$status_fn" ] && "$status_fn" "ABORT wrong-host(A1 아님)"
    cat >&2 <<'WRONGHOST'
★중단 — 여기는 배포 서버(A1)가 아닙니다. **경로 상수를 고치지 마십시오.**

이 스크립트는 A1 에서 돌도록 만들어졌고, A1 에는 $HOME/Development_AI 가 실재합니다.
지금 보이는 중첩 경로($HOME/My_Projects/Development_AI)는 **개발 워크트리 쪽 사실**입니다.

  ✘ REPO 를 My_Projects 경로로 바꾸면  → A1 에서 cd 실패 · 배포/롤백 영구 차단
  ◎ A1 에서 실행하십시오:
      ssh -i ~/.oci.key ubuntu@<A1> 'bash $HOME/Development_AI/propai-platform/scripts/<이 스크립트>'
    (★A1 주소는 기억에서 적지 말고 저장소에서 파생하십시오)
WRONGHOST
    exit 8
  fi

  # A1 로 보이는데 경로가 없다 = **진짜 경로/체크아웃 문제**(다른 사건이다).
  [ -n "$status_fn" ] && "$status_fn" "FAIL repo-missing($repo)"
  echo "★중단 — A1 로 보이는데 $repo 가 없습니다. 이건 실제 경로/체크아웃 문제입니다." >&2
  exit 1
}

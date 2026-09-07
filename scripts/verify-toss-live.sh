#!/usr/bin/env bash
# 토스페이먼츠 연동 **라이브 검증** — ★돈을 한 푼도 쓰지 않는다.
#
# ## 왜 이 형태인가
#
# 이 저장소의 규율: *"검증 비용이 보호 대상과 같으면 자기모순이다."*
# 결제가 되는지 확인하려고 **결제를 하지 않는다.** 대신 결함 경로를 쪼갠다:
#
#   ① 우리 서버가 키를 **쓸 수 있다고 판정하는가**  → /admin/payments/health
#   ② 그 키로 **벤더가 우리를 인증하는가**          → 존재하지 않는 주문 조회
#      (NOT_FOUND_PAYMENT = 인증 성공 · 무과금 · 부작용 0)
#   ③ 브라우저에 나가는 키가 **공개키가 맞는가**     → /payments/toss/config
#   ④ 반영이 **모든 워커에 미치는가**               → health 연속 폴링
#
# ★②가 핵심이다. ①만 보면 "우리 판정"이지 "벤더 판정"이 아니다 —
#   내가 잰 것이 사용자가 실제로 쓰는 그것인지 갈리는 자리다.
#
# ## 쓰는 법
#
#   export TOSS_SECRET_KEY='test_gsk_…'      # ★②를 하려면 필요. 저장되지 않는다.
#   export PROPAI_ADMIN_PW='…'               # 관리자 로그인
#   scripts/verify-toss-live.sh
#
# 시크릿 키 없이 돌리면 ②를 **건너뛴다고 말하고** 나머지를 검사한다(조용히 넘기지 않는다).
set -uo pipefail

API="${PROPAI_API:-https://api.4t8t.net}"
ADMIN_EMAIL="${PROPAI_ADMIN_EMAIL:-admin@4t8t.net}"
FAIL=0
note() { printf '%s\n' "$*"; }
bad()  { printf '✘ %s\n' "$*"; FAIL=1; }
ok()   { printf '✔ %s\n' "$*"; }

# ── 0) 대조군 먼저 — 조회기가 살아 있음을 증명한 뒤에 판정한다 ────────────────
#    ★이 순서를 바꾸면 사람이 먼저 결론을 낸다. 죽은 조회기는 본판정과 대조군을
#      **똑같이** 비우므로, 그 「같음」이 유일한 신호다.
ctl=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$API/api/v1/billing/zzz-no-such-route")
if [ "$ctl" = "404" ]; then ok "대조군: 없는 경로 → 404 (프로브 생존)"
else bad "대조군이 404가 아니다($ctl) — 아래 결과를 신뢰하지 마라"; exit 2; fi

if [ -z "${PROPAI_ADMIN_PW:-}" ]; then bad "PROPAI_ADMIN_PW 미설정"; exit 2; fi
TOK=$(curl -s --max-time 25 -X POST "$API/api/v1/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$PROPAI_ADMIN_PW\"}" \
      | python3 -c 'import json,sys;print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)
[ -n "$TOK" ] || { bad "관리자 로그인 실패"; exit 2; }
ok "관리자 로그인(토큰 ${#TOK}자)"

# ── ① 우리 판정 ──────────────────────────────────────────────────────────────
H=$(curl -s --max-time 25 -H "Authorization: Bearer $TOK" "$API/api/v1/billing/admin/payments/health")
note "── health ──"; printf '%s\n' "$H" | python3 -m json.tool 2>/dev/null || printf '%s\n' "$H"
python3 - "$H" <<'PY' || FAIL=1
import json, sys
h = json.loads(sys.argv[1])
d = h.get("key_diagnosis") or {}
if not h.get("configured"):
    print("✘ configured=false — 키가 아직 등록되지 않았다"); raise SystemExit(1)
if not d.get("ok"):
    print(f"✘ 키 진단 실패 [{d.get('code')}] {d.get('message')}")
    print(f"  → 할 일: {d.get('action')}"); raise SystemExit(1)
if h.get("payment_mode") != "toss":
    print(f"✘ payment_mode={h.get('payment_mode')} — 결제창이 켜지지 않는다"); raise SystemExit(1)
print(f"✔ 우리 판정: 사용 가능 (test_mode={h.get('test_mode')})")
if h.get("test_mode") is False:
    print("  ⚠ 라이브 키다 — 토스 상점 계약이 완료되지 않았으면 결제가 실패한다")
PY

# ── ③ 브라우저로 나가는 값이 **공개키**인가 ──────────────────────────────────
CFG=$(curl -s --max-time 25 -H "Authorization: Bearer $TOK" "$API/api/v1/billing/payments/toss/config")
python3 - "$CFG" <<'PY' || FAIL=1
import json, re, sys
c = json.loads(sys.argv[1])
ck = c.get("client_key") or ""
if not re.match(r"^(test|live)_gck_", ck):
    print(f"✘ 브라우저로 나가는 키가 gck 가 아니다: {ck[:12]}… — v2 위젯이 이것을 못 받는다")
    raise SystemExit(1)
print(f"✔ config 가 내보내는 키는 공개 클라이언트 키({ck[:13]}…)")
PY

# ── ② ★벤더 판정 — 무과금 인증 확인 ─────────────────────────────────────────
if [ -z "${TOSS_SECRET_KEY:-}" ]; then
  note "⊘ ② 벤더 인증 확인 **건너뜀** — TOSS_SECRET_KEY 미설정."
  note "   (조용히 넘기지 않는다: 이 실행은 「우리 판정」만 확인한 것이다)"
else
  # 존재하지 않는 주문번호 — 조회는 **무과금**이고 부작용이 없다.
  PROBE="PROPAI-VERIFY-$(date +%s)"
  BODY=$(curl -s --max-time 25 -u "$TOSS_SECRET_KEY:" \
           "https://api.tosspayments.com/v1/payments/orders/$PROBE")
  CODE=$(printf '%s' "$BODY" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("code",""))' 2>/dev/null)
  case "$CODE" in
    NOT_FOUND_PAYMENT)
      ok "② 벤더가 우리를 **인증했다**(없는 주문 → NOT_FOUND_PAYMENT · 무과금)" ;;
    UNAUTHORIZED_KEY|INVALID_API_KEY|INCORRECT_BASIC_AUTH_FORMAT)
      bad "② 벤더가 키를 거부했다: $CODE — 클라이언트 키와 **짝인** 시크릿 키인지 확인하라" ;;
    "")
      bad "② 응답을 해석하지 못했다(네트워크·방화벽?): $(printf '%s' "$BODY" | head -c 200)" ;;
    *)
      bad "② 예상 밖 코드: $CODE" ;;
  esac
fi

# ── ④ 반영이 모든 워커에 미치는가(무료) ─────────────────────────────────────
#    `set_secret` 은 `os.environ` 에 쓰는데 그것은 **프로세스 단위**다.
#    컨테이너가 여럿이면 응답이 폴링마다 흔들린다.
SEEN=$(for _ in 1 2 3 4 5 6 7 8; do
  curl -s --max-time 15 -H "Authorization: Bearer $TOK" \
    "$API/api/v1/billing/admin/payments/health" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin).get("payment_mode"))' 2>/dev/null
done | sort -u | tr '\n' ' ')
if [ "$(printf '%s' "$SEEN" | wc -w)" -eq 1 ]; then
  ok "④ 8회 폴링 모두 같은 판정($SEEN) — 워커 간 드리프트 없음"
else
  bad "④ ★폴링마다 판정이 다르다($SEEN) — 키가 일부 워커/컨테이너에만 반영됐다. 재배포가 필요하다"
fi

echo; [ "$FAIL" -eq 0 ] && { echo "== 전부 통과 =="; exit 0; } || { echo "== 실패 있음 =="; exit 1; }

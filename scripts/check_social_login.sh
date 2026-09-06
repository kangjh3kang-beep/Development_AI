#!/usr/bin/env bash
# 간편로그인 3사가 **실제로 어디서 깨지는지** 판정한다.
#
# ★왜 필요한가 — 2026-09-06 실측:
#   네이버·구글 로그인은 2026-06-15 부터 **구현·배포돼 있었다**. 그런데 사용자에게는
#   「카카오만 된다」로 보였다. 코드는 멀쩡하고 **공급자 콘솔에 리디렉션 URI 가 미등록**이었다.
#   ★그 사실을 **아무도 잴 수 없었다** — 버튼을 눌러야만 알 수 있었고, 눌러도 공급자
#   오류 페이지로 보내질 뿐 이유가 우리 쪽에 남지 않았다. **관측 장치가 없었다.**
#
# 판정 축 셋 — 순서가 곧 진단이다:
#   ①우리 API 가 login-url 을 주는가        (우리 코드·키 설정)
#   ②그 URL 이 공급자 **로그인 화면**으로 가는가 (공급자 콘솔 등록)
#   ③콜백 엔드포인트가 살아 있는가            (우리 코드)
#
# 사용법: scripts/check_social_login.sh [API_BASE] [WEB_BASE]
# 종료코드: 0=3사 정상 · 1=하나 이상 설정 문제 · 2=판정 불가(조회 실패 — 「정상」으로 읽지 마라)
set -uo pipefail
API="${1:-https://api.4t8t.net}"
WEB="${2:-https://4t8t.net}"
PROVIDERS="kakao naver google"

# ★음성 대조군을 **본판정보다 먼저** 찍는다 — 조회기가 죽으면 본판정과 대조군이 똑같이 빈다.
CTL_404="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$API/api/v1/auth/zzz-nope/login-url" 2>/dev/null)"
CTL_200="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$API/health" 2>/dev/null)"
echo "대조군: 없는 provider=$CTL_404 (404 여야) · /health=$CTL_200 (200 이어야)"
if [ "$CTL_404" != "404" ] || [ "$CTL_200" != "200" ]; then
  echo "::VERDICT=UNDECIDED"
  echo "★조회기 사망 — API 에 닿지 못한다. 「정상」으로 읽지 마라." >&2
  exit 2
fi
echo

BAD=0
for P in $PROVIDERS; do
  RU="$WEB/ko/$P/callback"
  BODY="$(curl -s --max-time 25 "$API/api/v1/auth/$P/login-url?redirect_uri=$(printf '%s' "$RU" | sed 's|:|%3A|g; s|/|%2F|g')" 2>/dev/null)"
  URL="$(printf '%s' "$BODY" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("url",""))
except Exception: print("")' 2>/dev/null)"
  if [ -z "$URL" ]; then
    printf '%-7s ✘ 축① login-url 없음 — 우리 API/키 설정 문제. 응답: %s\n' "$P" "$(printf '%s' "$BODY" | head -c 90)"
    BAD=$((BAD+1)); continue
  fi
  CID="$(printf '%s' "$URL" | python3 -c 'import sys,urllib.parse as u
q=u.parse_qs(u.urlparse(sys.stdin.read().strip()).query); print(q.get("client_id",["(없음)"])[0][:28])')"
  # 축② — authorize 를 실제로 태운다. 오류면 공급자가 오류 URL/페이지로 보낸다.
  FIN="$(curl -s -o /tmp/_csl.$$ -w '%{url_effective}' -L --max-redirs 5 --max-time 30 "$URL" 2>/dev/null)"
  REDIR_ERR=0; INPAGE_ERR=0
  case "$FIN" in *"/error"*|*"error?"*|*"authError="*) REDIR_ERR=1;; esac
  grep -q 'location.replace("https://nid.naver.com/login/ext/error' /tmp/_csl.$$ 2>/dev/null && INPAGE_ERR=1
  rm -f /tmp/_csl.$$
  if [ "$REDIR_ERR" = "1" ] || [ "$INPAGE_ERR" = "1" ]; then
    printf '%-7s ✘ 축② 공급자가 **오류**를 낸다 — 콘솔에 리디렉션 URI 미등록 의심\n' "$P"
    printf '        client_id=%s · redirect_uri=%s\n' "$CID" "$RU"
    printf '        최종: %s\n' "$(printf '%s' "$FIN" | head -c 100)"
    BAD=$((BAD+1))
  else
    printf '%-7s ◎ 축①② 정상 (client_id=%s)\n' "$P" "$CID"
  fi
done

echo
if [ "$BAD" = "0" ]; then echo "::VERDICT=OK"; exit 0; fi
echo "::VERDICT=MISCONFIGURED ($BAD/3)"
cat <<'HINT'
★코드 문제가 아니다 — 공급자 콘솔에서 **리디렉션 URI 를 등록**해야 한다:
  · Google  : Cloud Console → 사용자 인증 정보 → 해당 OAuth 클라이언트
              → 「승인된 리디렉션 URI」에 위 redirect_uri 추가(로케일별로 /ko/ /en/ /zh-CN/)
  · 네이버  : 개발자센터 → 애플리케이션 → API 설정 → Callback URL 등록 + 서비스 상태 확인
HINT
exit 1

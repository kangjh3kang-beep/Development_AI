#!/usr/bin/env bash
# 번들 전수 수집: eager 청크 → 그 안의 static/chunks/ 문자열까지 추적(next/dynamic 지연 청크)
set -u
OUT="$1"; shift
rm -rf "$OUT"; mkdir -p "$OUT"
BASE=https://4t8t.net
# ★상세/동적 라우트를 반드시 포함한다 — 목록 라우트만 훑으면 그쪽 청크를 못 본다.
#   실측: /ko/projects/<id> 에 목록 라우트에 없는 청크가 3개 있었고, 그 때문에
#   "정밀도 미표기" 지표가 0 으로 나와 미배포로 오보할 뻔했다(이 저장소 7회 오판 지점).
ROUTES=("/ko" "/ko/precheck" "/ko/analysis" "/ko/projects" "/ko/projects/new"
        "/ko/projects/probe-id" "/ko/projects/probe-id/site-analysis"
        "/ko/projects/probe-id/feasibility" "/ko/projects/probe-id/design"
        "/ko/design-audit" "/ko/registry-analysis" "/ko/regulations" "/ko/permits"
        "/ko/settings" "/ko/analytics/investment" "/ko/design-studio")
: > "$OUT/urls.txt"
for r in "${ROUTES[@]}"; do
  curl -s "$BASE$r" | grep -oE '/_next/static/chunks/[A-Za-z0-9._/-]+\.js' >> "$OUT/urls.txt"
done
sort -u "$OUT/urls.txt" -o "$OUT/urls.txt"
echo "eager 청크 $(wc -l < "$OUT/urls.txt")개"
# 1차 다운로드
dl() {
  while read -r u; do
    f="$OUT/$(echo "$u" | tr '/' '_')"
    [ -s "$f" ] && continue
    curl -s "$BASE$u" -o "$f"
  done < "$1"
}
dl "$OUT/urls.txt"
# 2차: 청크 내부가 참조하는 static/chunks 경로 추적(지연 청크)
for pass in 1 2; do
  cat "$OUT"/*next_static_chunks*.js 2>/dev/null \
    | grep -oE 'static/chunks/[A-Za-z0-9._/-]+\.js' | sed 's|^|/_next/|' | sort -u > "$OUT/more.txt"
  comm -23 "$OUT/more.txt" "$OUT/urls.txt" > "$OUT/new.txt"
  n=$(wc -l < "$OUT/new.txt")
  echo "pass$pass 신규 지연청크 ${n}개"
  [ "$n" -eq 0 ] && break
  dl "$OUT/new.txt"
  cat "$OUT/urls.txt" "$OUT/new.txt" | sort -u -o "$OUT/urls.txt"
done
echo "총 청크 파일 $(ls "$OUT"/*next_static_chunks*.js 2>/dev/null | wc -l)개 · $(cat "$OUT"/*next_static_chunks*.js 2>/dev/null | wc -c) 바이트"

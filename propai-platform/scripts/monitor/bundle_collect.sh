#!/usr/bin/env bash
# 번들 전수 수집: eager 청크 → 그 안의 static/chunks/ 문자열까지 추적(next/dynamic 지연 청크)
set -u
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SELF_DIR/../../.." && pwd)"
OUT="$1"; shift
rm -rf "$OUT"; mkdir -p "$OUT"
BASE=https://4t8t.net
# ★ROUTES 를 **손으로 세지 않는다** — app 디렉토리에서 파생한다.
#   실측: 목록형으로 뒀다가 **세 번** 오판했다(precision · 혼재/미상 · …). 손으로 센 목록은
#   곧 상한이 되고, 새 라우트가 생기면 그 청크는 영원히 안 모인다.
#   ★동적 세그먼트([id] 등)는 프로브용 더미 값으로 치환한다 — 서버는 셸을 그려 주므로
#     존재하지 않는 id 여도 그 라우트의 청크 목록은 나온다.
APP_DIR="$REPO/propai-platform/apps/web/app/[locale]/(dashboard)"
if [ -d "$APP_DIR" ]; then
  mapfile -t ROUTES < <(
    find "$APP_DIR" -name 'page.tsx' -printf '%P\n' 2>/dev/null \
      | sed 's|/page.tsx$||; s|^page.tsx$||' \
      | sed 's|\[[^]]*\]|probe-id|g' \
      | sed 's|^|/ko/|; s|/ko/$|/ko|' \
      | sort -u
  )
fi
if [ "${#ROUTES[@]}" -lt 5 ]; then
  # ★파생이 실패하면 **조용히 적게 모으지 않는다** — 시끄럽게 알린다.
  echo "★라우트 파생 실패(${#ROUTES[@]}개) — app 디렉토리 경로를 확인하라: $APP_DIR" >&2
  echo "  (수집 범위가 좁으면 지표 0 이 '미배포'로 오보된다 — 이 저장소가 3회 겪은 함정)" >&2
  [ "${#ROUTES[@]}" -eq 0 ] && exit 3
fi
echo "라우트 ${#ROUTES[@]}개(파생형 — app/**/page.tsx 에서 추출)"
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

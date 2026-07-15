#!/usr/bin/env bash
# 무중단(블루-그린) 배포: Caddy(80) 뒤에서 앱을 8000↔8001 교대 기동 + graceful reload.
set -e
cd ~/Development_AI/propai-platform
git pull origin main 2>&1 | tail -1
echo "== build =="
sudo docker build -f Dockerfile.oracle -t propai-api:latest . 2>&1 | tail -2
CUR=$(grep -oE 'localhost:[0-9]+' ~/caddy/Caddyfile | grep -oE '[0-9]+' | tail -1)
[ -z "$CUR" ] && CUR=8000
NEW=$([ "$CUR" = "8000" ] && echo 8001 || echo 8000)
NAME=propai-api-$NEW
echo "현재 활성 포트=$CUR → 신규 포트=$NEW ($NAME)"
sudo docker rm -f "$NAME" 2>/dev/null || true
sudo docker run -d --name "$NAME" --restart always --env-file .env -p ${NEW}:8000 propai-api:latest >/dev/null
echo "== 신앱 health 대기(8000 내부) =="
ok=0; for i in $(seq 1 60); do if curl -sf -o /dev/null "http://localhost:${NEW}/health"; then ok=1; break; fi; sleep 3; done
if [ "$ok" != "1" ]; then echo "!! 신앱 health 실패 — 배포중단(기존 유지)"; sudo docker rm -f "$NAME"; exit 1; fi
# ★DB 마이그레이션(신 컨테이너 내부 alembic upgrade head) — 트래픽 전환 '전'에 수행.
#  새 코드가 요구하는 스키마(신규 컬럼/테이블)를 트래픽 받기 전에 반영해, 코드-스키마 불일치로
#  로그인 등이 500 나던 사고(2026-07-15 042)를 원천 차단한다. additive 마이그레이션 전제라
#  구 컨테이너는 마이그레이션 중에도 정상 서빙(하위호환). 실패 시 트래픽 전환 없이 배포중단.
#  ★프로덕션 DB는 alembic 관리(alembic_version=042 stamp 완료) — 이후 신규 리비전만 자동 적용.
echo "== DB 마이그레이션(alembic upgrade head, 신 컨테이너 내부) =="
if ! sudo docker exec "$NAME" sh -c "cd /app/apps/api && PYTHONPATH=/app alembic upgrade head"; then
  echo "!! 마이그레이션 실패 — 배포중단(기존 유지·트래픽 전환 안 함)"; sudo docker rm -f "$NAME"; exit 1
fi
echo "== Caddy 전환(graceful reload) → $NEW =="
printf ":80 {\n  reverse_proxy localhost:%s\n}\n" "$NEW" > ~/caddy/Caddyfile
sudo docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
sleep 2
code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:80/health)
echo "전환 후 80 -> $code"
if [ "$code" != "200" ]; then echo "!! 전환 실패 — 롤백(Caddy를 $CUR로)"; printf ":80 {\n  reverse_proxy localhost:%s\n}\n" "$CUR" > ~/caddy/Caddyfile; sudo docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; sudo docker rm -f "$NAME"; exit 1; fi
echo "== 구앱 제거 =="
for c in $(sudo docker ps -a --format '{{.Names}}' | grep -E '^propai-api'); do [ "$c" = "$NAME" ] || sudo docker rm -f "$c" 2>/dev/null || true; done
echo "✅ 무중단 배포 완료 (활성=$NEW)"

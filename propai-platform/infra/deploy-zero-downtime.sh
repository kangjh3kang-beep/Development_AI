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

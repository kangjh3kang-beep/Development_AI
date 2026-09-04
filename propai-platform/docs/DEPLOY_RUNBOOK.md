# PropAI A1 배포 런북 (안전배포 + 장애복구)

작성: 2026-06-09 · 대상: A1 오리진(158.179.174.207, Docker Compose v1 + cloudflared)

## -1. 배포 대상 SSOT (반복 실수 방지)

- **프론트/UI 배포 대상**: `ubuntu@158.179.174.207`, key `~/.oci.key`, hostname `4t8t`, repo `/home/ubuntu/Development_AI`.
- **백엔드/API 대상**: `ubuntu@168.110.125.89`, hostname `4t8tpropai-backend-a1`.
- `4t8t.net/ko`, `/ko/precheck`, `/ko/design-studio` 같은 화면 변경은 프론트 A1에서 `web` target으로 배포한다.
- 프론트 화면 변경 확인에 `168.110.125.89`를 사용하지 않는다. 이 호스트의 SSH 실패를 프론트 배포 차단으로 해석하지 않는다.

## 0. 배포 단일 소유 원칙 (★가장 중요)
**A1 배포는 한 세션만 전담한다.** 두 클로드/제미나이 창이 동시에 `git pull + docker system prune -af + build` 를 돌리면 서로의 빌드 레이어를 prune이 날려 **반드시 실패**한다(이번 세션 다발 장애의 1순위 원인). 다른 창은 **코드 작업 + 커밋/푸시만**. 배포자는 `scripts/safe-deploy.sh`의 락으로 동시실행을 한 번 더 차단한다.

## 1. 표준 배포 (권장)
```bash
ssh -i ~/.oci.key ubuntu@158.179.174.207
# 분리 실행(ssh 끊겨도 완주) — both | web | api
setsid bash ~/Development_AI/propai-platform/scripts/safe-deploy.sh both </dev/null >/dev/null 2>&1 &
# 진행 폴링
watch -n5 cat /tmp/deploy_status.txt    # PREFLIGHT→SYNC→BUILD→RECREATE→NGINX-RELOAD→VERIFY→DONE
```
safe-deploy.sh가 보장하는 것: 동시배포 락 · prune 안 함 · git을 origin과 정확히 동기화 · legacy builder(ContainerConfig 보장) · 옛 컨테이너 선제거(compose 버그 우회) · **헬스 실패 시 옛 이미지로 자동 롤백** · api/web 네트워크 멤버십 강제 · nginx 재시작(새 IP 재인식) · 공개 200 검증.

- **프론트만 변경** → `web`. **백엔드(api) 변경 포함** → `both`(또는 `api`). 백엔드 라우트 신설은 `both` 필수(web만 하면 새 엔드포인트 미반영).

## 2. 알려진 함정 (이번 세션에서 실제 겪음)
| 증상 | 원인 | 안전배포의 대응 |
|------|------|----------------|
| 빌드가 `failed to export layer / CreateDiff` 로 실패 | 다른 창의 `docker system prune -af` 가 빌드 레이어 삭제 | 락 + 단일소유 + prune 미사용 |
| `docker-compose up -d` 가 `KeyError: 'ContainerConfig'` | compose v1 + buildkit 이미지의 볼륨복사 비호환 | 옛 컨테이너 **선제거** 후 생성(마이그레이션 경로 회피) |
| 재생성 후 nginx `host not found in upstream "api"` → 전체 502 | api 컨테이너가 네트워크에서 빠짐 / nginx가 옛 IP 캐시 | 재생성 후 네트워크 강제연결 + nginx 재시작 |
| `docker start` 로 살린 컨테이너가 네트워크 없음 | start는 compose 네트워크 alias 재부여 안 함 | 복구는 항상 `docker-compose up -d --no-deps <svc>` 사용 |
| 새 web 컨테이너가 502(Next는 Ready) | nginx upstream IP 캐시 | nginx 재시작 |

## 3. 긴급 복구 (배포 중 502/다운 시)
```bash
# (a) 컨테이너 상태 — 누가 떠있고 누가 사라졌나
docker ps -a --format "{{.Names}} | {{.Status}}" | grep -E "web|api|nginx|qdrant"
# (b) 네트워크 멤버십 — 셋 다 같은 네트워크여야 함
for c in web api nginx; do echo "$c:"; docker inspect propai-platform_${c}_1 \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' 2>/dev/null; done
# (c) 사라진 컨테이너 재생성(옛 컨테이너 없으면 ContainerConfig 버그 안 남)
cd ~/Development_AI/propai-platform
docker-compose up -d --no-deps --no-build api   # 또는 web
# (d) 네트워크 빠졌으면 강제연결
docker network connect --alias api propai-platform_propai-network propai-platform_api_1
# (e) nginx 재시작으로 upstream 재인식
docker restart propai-platform_nginx_1
# (f) 검증
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:80/ko
curl -s https://www.4t8t.net/ko -o /dev/null -w "%{http_code}\n"
```
- nginx upstream(`api`,`web`)은 **시작 시 1회 해석**된다 → 컨테이너 재생성 후엔 nginx 재시작 필수.
- **api는 절대 단독으로 `docker stop` 후 방치 금지** — nginx가 즉시 502. 항상 stop→up 한 호흡.

## 4. 배포 후 체크리스트
- [ ] `/tmp/deploy_status.txt` 가 `DONE web=200 api=200`
- [ ] `https://www.4t8t.net/ko` 200, `https://api.4t8t.net/health` 200
- [ ] 백엔드 라우트 변경 시: `curl localhost/openapi.json | grep <새경로>` 로 등록 확인
- [ ] 핵심 화면 1개 콜드로드(대시보드/프로젝트 상세) 무오류

## 5. 심의엔진 shadow 관측 켜기 (선택·기본 off)
- **Shadow ON 절차(한 줄)**: api 컨테이너 env에 `DELIBERATION_SHADOW_ENABLED=true` + 엔진 연결(`DELIBERATION_ENGINE_URL`·`DELIBERATION_ENGINE_API_TOKEN`) 설정 후 재배포 → 도메인 분석이 플랫폼 vs 엔진 판정을 대조 적재(관측 전용·판정 무변경, 실패는 무전파). 승격 게이트는 `docs/CENTRAL_ENGINE_STAGE3_PROMOTION.md`.

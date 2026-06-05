# 프런트엔드 Oracle A1 이전 — 컷오버 런북 (Cloudflare Tunnel)

작성: 2026-06-05 · 결정: **A1 단일 코로케이션 + Cloudflare Tunnel** · 소유: Claude 전담

## 목표 아키텍처 (시너지: Cloudflare 엣지 + Oracle A1 오리진)
```
사용자 → Cloudflare 엣지(CDN/SSL/WAF/DDoS)
        ⇅ cloudflared 아웃바운드 터널(오리진 IP 비노출·인바운드 포트 0)
     A1(158.179.174.207, 6GB, aarch64)
        nginx:80
          ├─ /            → web:3000 (Next.js standalone, Node)
          ├─ /api/*       → api:8000 (FastAPI)
          └─ /docs,/openapi.json → api:8000
        + qdrant(벡터DB)  ← 모두 동일 박스 코로케이션(지연↓)
```
- 백엔드도 A1로 통합 → 프런트↔백엔드 동일호스트(저지연), 6GB 여유. Micro(1GB)는 예비/은퇴.
- Cloudflare는 **제거가 아니라 엣지로 유지**(SSL·CDN·WAF 그대로).

## Phase 1 (프로덕션 무영향, Claude 완료/진행)
- [x] `docker-compose.yml` api `environment: PYTHONPATH=/app:/app/apps/api` 고정 → A1 api 크래시(No module named 'app') 해소(커밋 abd197d).
- [x] A1 `.env` 교정: `NEXT_PUBLIC_API_BASE_URL=https://api.4t8t.net/api/v1`, `NEXT_PUBLIC_API_URL=https://api.4t8t.net` (백업 .env.bak.*).
- [x] A1 git → 최신 main(abd197d): precheck 할루시네이션 수정·opencv 포함.
- [~] A1 `docker compose build api web && up -d` 재빌드·recreate(진행).
- [ ] 내부검증: api `/health` 200, web 200, nginx `/api` 라우팅, qdrant.
- nginx.conf(레포)는 이미 `/api→api:8000`, `/→web:3000` 리버스 프록시 — 추가 하드닝(gzip/server_name)은 선택.

## Phase 2 (Cloudflare 자격증명 필요 — 사용자와 함께)
> 모두 A1에서 실행. cloudflared가 Cloudflare 계정과 아웃바운드 터널을 맺으므로 인바운드 포트 개방 불필요.

### 2-1. cloudflared 설치(A1, aarch64)
```bash
ssh -i ~/.oci.key ubuntu@158.179.174.207
ARCH=arm64
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH} -o cloudflared
sudo install -m755 cloudflared /usr/local/bin/cloudflared
cloudflared --version
```
### 2-2. 로그인·터널 생성 (★Cloudflare 계정 인증)
```bash
cloudflared tunnel login          # 브라우저 인증 URL 출력 → 사용자가 4t8t.net 존 선택·승인
cloudflared tunnel create propai-a1
# → 터널 UUID + ~/.cloudflared/<UUID>.json 자격증명 생성
```
### 2-3. 터널 라우팅 설정 `~/.cloudflared/config.yml`
```yaml
tunnel: <UUID>
credentials-file: /home/ubuntu/.cloudflared/<UUID>.json
ingress:
  - hostname: www.4t8t.net
    service: http://localhost:80      # A1 nginx
  - hostname: 4t8t.net
    service: http://localhost:80
  - hostname: api.4t8t.net
    service: http://localhost:80      # nginx가 /api→api:8000 라우팅
  - service: http_status:404
```
### 2-4. DNS 연결(터널이 자동 CNAME 생성)
```bash
cloudflared tunnel route dns propai-a1 www.4t8t.net
cloudflared tunnel route dns propai-a1 4t8t.net
cloudflared tunnel route dns propai-a1 api.4t8t.net   # ★기존 api는 Micro→A1로 전환
```
> ★주의: `api.4t8t.net`을 A1로 돌리기 전, A1 api가 모든 공공데이터 키·DB로 정상(/health 200·실호출)인지 확인. 전환=프로덕션 백엔드 이동.

### 2-5. Worker 라우트 해제(Cloudflare 대시보드)
- 현재 www는 `opennextjs-cloudflare`가 Worker로 서빙 → **Workers Routes에서 www.4t8t.net/* 라우트 비활성화**(또는 삭제). 그래야 터널 오리진이 우선.
- `deploy-cloudflare.yml`(GitHub Actions) 비활성화/제거 — 더는 Cloudflare로 프런트 배포 안 함.

### 2-6. 서비스 상시화
```bash
sudo cloudflared service install      # systemd 등록(부팅 자동기동)
sudo systemctl status cloudflared
```
### 2-7. 검증
```bash
curl -sI https://www.4t8t.net | grep -i "cf-ray\|server"     # Cloudflare 엣지 경유 확인
curl -s https://api.4t8t.net/health                          # A1 백엔드 200
# 브라우저: 대시보드/프로젝트상세/BIM(1102 재현 페이지) 콜드·웜 로드 무오류 확인
```

## 롤백 (즉시)
- **프런트만 원복**: `cloudflared tunnel route dns` 되돌리거나 터널 중지(`sudo systemctl stop cloudflared`) → Cloudflare Worker 라우트 재활성화 → www가 다시 Workers로.
- **백엔드 원복**: `api.4t8t.net` DNS를 Micro(134.185.104.167) 오리진으로 환원. Micro 스택은 보존(은퇴 전까지 유지).
- Phase 1은 A1 내부 변경뿐이라 프로덕션 영향 없음(롤백 불필요).

## 잔여/주의
- web NEXT_PUBLIC은 빌드 ARG 미주입 → 클라이언트는 api-client `resolveApiOrigin` 폴백으로 `api.4t8t.net` 호출(4t8t.net 호스트 화이트리스트). 결정적 동작 원하면 Dockerfile.web에 `ARG NEXT_PUBLIC_API_BASE_URL` 추가 후 compose build args 전달.
- web 컨테이너에 백엔드 시크릿(env_file 공유)이 주입됨 — 인터넷 비노출이나, 장기적으로 web용 `.env.web`(NEXT_PUBLIC_*만)로 분리 권장.
- Micro 은퇴: api.4t8t.net 전환·안정 확인 후. 그 전까지 백업 오리진으로 보존.

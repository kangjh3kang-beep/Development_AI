# 백엔드 Micro(x86·1GB) → Ampere A1(ARM·12~18GB) 이관 런북

작성: 2026-06-16 · 작성자: 배포 코디네이터 세션 · 대상: 인프라(제미나이) + 배포 코디네이터
용도: 백엔드 VM 선제 증설(유저·데이터 증가 대비). **무중단 블루그린 이관.**

> 결론 한 줄: **제자리 리사이즈 불가**(Micro=x86, A1=ARM) → **새 A1 인스턴스 생성 후 이관**. OCI 콘솔 작업은 인프라(제미나이), 앱 이관·컷오버·검증은 배포 코디네이터.

---

## 0. 왜 디스크가 아니라 VM 업그레이드인가 (실측 2026-06-16)

| 자원 | 백엔드 Micro(현재) | 비고 |
|------|--------------------|------|
| arch | **x86_64** | A1은 aarch64 → 리사이즈 불가, 신규생성 필요 |
| RAM | **956MB(≈1GB)** · 유휴에도 **swap 504MB 사용** | ★실제 병목 |
| CPU | 2 vCPU (load 0.02 유휴) | 여유 |
| 디스크 | 45G/15G여유 · **DB 37MB뿐** | 압박은 Docker 빌드캐시(15G prune 가능), 데이터 아님 |

→ 디스크 확장은 안 터지는 곳을 늘리는 것. **RAM이 천장**이므로 VM 자체를 키운다.

### A1 무료 한도 잔여(실측)
| | arch | OCPU | RAM | 디스크 |
|---|---|---|---|---|
| 프론트 A1(158.179.174.207, 사용중) | aarch64 | 1 | 5.8GB | 193G/140G여유 |
| **Always Free A1 한도(테넌시 총)** | ARM | **4** | **24GB** | — |
| **→ 신규 백엔드 A1 가용 잔여** | ARM | **~3** | **~18GB** | 충분 |

→ 신규 백엔드 A1을 **2~3 OCPU / 12~18GB**로 무료 한도 내 생성 가능(현 1GB의 12~18배).

---

## 1. 역할 분담

- **인프라(제미나이) — OCI 콘솔**: A1 인스턴스 생성·네트워크·공인IP·SSH키·capacity 확보. (배포 코디는 콘솔 권한 없음)
- **배포 코디네이터 — 앱 이관**: Docker/compose 설치, repo, env, ARM 빌드, DB 이관, Caddy, 컷오버, 검증, Micro 폐기.

---

## 2. 사전 점검 결과 — ARM(aarch64) 휠 가용성

운영 백엔드는 **`apps/api/requirements.oracle.txt`**(슬림셋)을 사용 — `torch·torchvision·gdal·geopandas·faiss·mlflow`는 이미 제거됨.

| 패키지 | aarch64 휠 | 판정 |
|--------|-----------|------|
| asyncpg·psycopg2-binary·numpy·pandas·scipy·shapely·pyproj·Pillow·lxml·cryptography·python-jose·reportlab | 존재(manylinux aarch64) | ✅ 무위험 |
| opencv-python-headless 4.10 | 존재 | ✅ |
| **ifcopenshell==0.8.4** | **검증 필요** | ⚠️ A1에서 `pip install ifcopenshell==0.8.4` 단독 선검증. 실패 시 (a)소스빌드 (b)BIM/IFC 기능 일시 비활성 플래그 |

→ **단 하나의 실위험 = ifcopenshell**. Phase B-3에서 단독 설치로 먼저 검증한다.

---

## 3. Phase A — OCI 인스턴스 생성 (인프라/제미나이)

1. **Compute → Create Instance**
   - Shape: **VM.Standard.A1.Flex**, **2~3 OCPU / 12~18GB**(잔여 한도 내).
   - Image: **Ubuntu 22.04 (aarch64)** — 현 Micro와 동일 계열.
   - **★Region: 한국 리전(현 인프라와 동일 리전 유지)** — 공공데이터포털 국외IP 차단 회피(메모리: 국외IP시 차단). 프론트 A1과 같은 VCN/서브넷 권장(내부통신·일관성).
   - Boot volume: 100GB+ (넉넉히).
   - 공인 IP 할당. SSH 공개키 = 기존 `~/.oci.key` 의 공개키 등록.
   - VCN Security List / NSG: 인바운드 **TCP 80·443**(Caddy), 22(SSH, 본인IP 한정 권장).
2. **★Capacity 함정**: Always Free A1은 인기 리전에서 "Out of host capacity" 빈발 → 콘솔 재시도 또는 OCI CLI 재시도 루프. 안 되면 시간대 바꿔 재시도/유료 소액 전환 검토.
3. 생성 후 **공인 IP를 배포 코디에 전달** → Phase B 시작.

---

## 4. Phase B — 앱 이관 (배포 코디네이터, A1 준비 후)

> Micro는 계속 가동(블루그린). 아래는 신규 A1에서 수행.

1. **기반 설치**: Docker·docker-compose-plugin, git. repo 클론(현 Micro의 배포 경로 구조 동일하게).
2. **env 복사 — ★최우선 주의**:
   - `apps/api/.env` + 루트 `.env`를 Micro에서 복사.
   - **★`SECRET_STORE_KEY`를 Micro와 100% 동일하게 고정**. 다르면 `platform_secrets` 복호화 24/24 전부 실패(메모리 교훈: 서버별 휘발 파생키로 복호화붕괴 발생했었음). `DATABASE_URL`·`MOLIT_API_KEY`·`ONBID`·`LIVEKIT`·`SUPABASE`·`KAKAO` 등 전 비밀 동일.
   - `DATABASE_URL` 비밀번호의 `%21`(URL인코딩 `!`) 등 특수문자 그대로 유지(alembic CLI는 이 때문에 깨지므로 마이그레이션은 raw SQL/asyncpg로, 메모리 교훈).
   - 백엔드 A1의 기본 bridge API 컨테이너는 host gateway로 Redis/Qdrant를 본다. `REDIS_URL=redis://172.17.0.1:6379/0`, `REDIS_CACHE_URL=redis://172.17.0.1:6379/1`, `CELERY_BROKER_URL=redis://172.17.0.1:6379/2`, `CELERY_RESULT_BACKEND=redis://172.17.0.1:6379/3`, `QDRANT_HOST=172.17.0.1`을 유지한다.
3. **ifcopenshell 선검증**: `python3.12 -m venv /tmp/t && /tmp/t/bin/pip install ifcopenshell==0.8.4` 단독 실행.
   - 성공 → 그대로 진행.
   - 실패 → (a) 소스빌드 시도, 또는 (b) 컨테이너 빌드에서 BIM/IFC 모듈만 옵션화(IfcGeneratorService 경로는 이미 폴백 구조이므로 기능 degrade로 우선 가동 후 후속 해결).
4. **ARM 빌드**: A1에서 `docker build`(또는 deploy.sh) 실행 → **aarch64 네이티브 이미지 자동 생성**(프론트 A1이 이미 ARM 빌드 중이라 파이프라인 검증됨). 크로스컴파일 불필요.
5. **DB 이관**(소량 37MB):
   - Micro에서 `pg_dump`(Custom format) → A1 Postgres로 `pg_restore`.
   - 또는 A1에 동일 Postgres(postgis16) 컨테이너 기동 후 덤프 복원.
   - 복원 후 **테이블 수·주요 행수 대조**(analysis_ledger·projects·g2b_bids·platform_secrets 등). `platform_secrets`는 SECRET_STORE_KEY 동일해야 복호화됨 — 복원 후 `reencrypt_all` 불필요(키 동일 시).
   - prod는 alembic 미관리 → 신규 마이그레이션은 raw SQL/asyncpg로(메모리 교훈). 031까지 이미 적용된 스키마가 덤프에 포함됨.
6. **Caddy**: 현 Caddyfile 복제(api.4t8t.net → 백엔드 8000/8001 블루그린, **포트 80** 기준 — 메모리: Micro 라이브호출은 Caddy 포트80). 무중단 reload 구조 유지.
7. **deploy.sh 이식**: 현 Micro의 `~/deploy.sh`(블루그린: 활성포트 토글·health 대기·Caddy graceful reload·구앱 제거) 그대로 A1에 배치.
8. **Celery worker/Flower 재기동**: API 이미지 빌드/전환 후 `bash scripts/a1-backend-workers.sh`를 실행한다. Backend A1은 systemd가 worker/Flower 컨테이너를 소유하므로 이 스크립트로 unit 파일까지 갱신한다. API 이미지 기본 `/health` healthcheck는 worker에 재사용하지 않고, Celery registry에 `app.tasks.parcel_batch_task.run_batch` 등 필수 업무 태스크가 등록됐는지 직접 확인한다.

---

## 5. Phase C — 블루그린 컷오버 (배포 코디네이터)

1. A1에서 백엔드 기동 → **A1 IP로 직접** `/health`·핵심 엔드포인트 검증(아래 §7). Micro는 여전히 라이브.
2. **DNS/프록시 전환**: `api.4t8t.net`(및 Cloudflare 터널·라우팅)을 **A1 신규 IP**로. (Cloudflare는 엣지/터널만, 호스팅X — 메모리.)
3. **★IP 허용목록 갱신(외부 콘솔)**:
   - **Kakao 로그인**: 카카오 개발자콘솔 앱의 **허용 IP에 새 백엔드 A1 IP 등록**(누락 시 kapi "ip mismatched" -401, 메모리 교훈). redirect_uri는 도메인 기반이라 무관.
   - 기타 IP 화이트리스트(있으면) 갱신.
4. 전환 후 라이브 재검증(§7). 안정 확인되면 **Micro 폐기(또는 1~2일 대기 후 종료)**.

---

## 6. 함정 체크리스트 (메모리 기반·반드시 확인)

- [ ] **SECRET_STORE_KEY 두 서버 동일** — 미동일 시 비밀 24/24 복호화 실패.
- [ ] **한국 리전** — 공공데이터포털 국외IP 차단 회피.
- [ ] **Kakao 콘솔 허용IP에 새 IP 등록** — 로그인 -401 방지.
- [ ] **ifcopenshell 0.8.4 aarch64 설치** 선검증 — 유일 ARM 위험.
- [ ] **A1 capacity** 재시도 대비.
- [ ] **DATABASE_URL 특수문자(%21)** 보존 — alembic CLI 회피(raw SQL 유지).
- [ ] **Caddy 포트 80** 기준 라이브호출.
- [ ] `/health`는 `postgres`·`redis`·`qdrant` 모두 `healthy`여야 한다. Redis는 host gateway `172.17.0.1:6379` 기준으로 확인하고, degraded를 정상 범위로 취급하지 않는다.
- [ ] Celery worker/Flower는 `scripts/a1-backend-workers.sh`로 재기동한다. Docker status의 healthy만 보지 말고 `celery inspect registered`에서 업무 태스크가 보이는지 확인한다.
- [ ] **realtx(국토부 실거래) 502는 이 이관으로 안 고쳐짐** — data.go.kr 백엔드 장애(별개). 한국 리전 유지로 공공데이터 접근성만 보존.

## 7. 검증 항목 (컷오버 전/후 동일 수행)

- `GET https://api.4t8t.net/health` → status 200, postgres/redis/qdrant healthy.
- `docker exec propai-celery-worker celery -A app.tasks.celery_app:app inspect registered` → `app.tasks.parcel_batch_task.run_batch`, `app.tasks.auction_sync_task.sync_onbid_auctions`, `app.tasks.growth_tasks.analyze_growth` 등록.
- 로그인(`/api/v1/auth/login`, admin@4t8t.net) → access_token 발급.
- `GET /api/v1/auction/ranking?by=views` → 200 + items(ONBID 한국IP 접근 확인).
- `GET /api/v1/analysis-ledger/verify-all` → verified:true(DB 이관 무결성).
- 관리자 시크릿 복호화 정상(`platform_secrets` 24/24) — SECRET_STORE_KEY 동일 확인.
- Kakao 로그인 1회 실제 시도(허용IP 등록 확인).
- 공공데이터 1건(건축HUB 등) 호출 200(한국IP 확인).

## 8. 롤백

- 컷오버는 **DNS 전환만**이므로, 문제 시 `api.4t8t.net`을 **Micro IP로 즉시 되돌림**(Micro는 폐기 전까지 살아있음). 앱·DB 원본이 Micro에 그대로라 무손실.

---

## 부록 — 현재 실측값(이관 기준선)
- 백엔드 Micro: x86_64, 2 vCPU, 956MB RAM(swap 504MB 사용), 45G/15G여유, DB 37MB.
- 프론트 A1: aarch64, 1 OCPU, 5.8GB RAM, 193G/140G여유.
- DB 큰 테이블: spatial_ref_sys 7MB·platform_events 1.4MB·g2b_bids 1.2MB·analysis_ledger 0.44MB.
- 관련 계획: [SCALING_OPTIMIZATION_PLAN_2026-06.md](SCALING_OPTIMIZATION_PLAN_2026-06.md)(P0=A1 업그레이드·비동기 큐·Redis 복구).

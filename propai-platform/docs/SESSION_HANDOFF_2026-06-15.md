# 세션 인수인계 — 2026-06-15 (살아 성장하는 에이전트 플랫폼 진화 + F3 회의방 완료)

작성: 2026-06-15 · 브랜치 `feature/trust-infra-2026-06-11` · HEAD `f594d2b` · alembic head `030_livekit_recordings` · origin 동기(0/0) · 워킹트리 클린

> 다음 세션은 **이 문서 → [진화 마스터 spec](superpowers/specs/2026-06-15-living-agent-knowledge-platform-design.md) → [F3 인계](SESSION_HANDOFF_2026-06-14.md) → [배포 인계](DEPLOY_HANDOFF_SP2_COLLAB_2026-06-14.md)** 순으로 읽으면 된다. 작업환경·불변규칙·교훈·파일지도의 상세는 2026-06-14 문서 §1·2·7·8에 있다(여기서는 핵심만 재기술).

## 0. 한 줄 요약
두 트랙이 병행 상태다. **트랙 A(F3 회의방)** = 회의방/자료교환/8엔진/뷰어/scope/의견교환/화상회의(LiveKit)/보안하드닝/배포검증까지 **코드 완성·미배포**. **트랙 B(플랫폼 진화)** = '분야별 전문에이전트·프로젝트 지식저장소·공동경영 멀티에이전트' 비전으로의 additive 리팩토링 **마스터 spec 작성·커밋 완료, 사용자 spec 리뷰 게이트 대기**. 다음 작업은 트랙 B의 Phase 0 구현 plan 분해다.

## 1. 정확한 경로·위치·접속 (실측 2026-06-15 — 추측 아님)

플랫폼은 **개발=WSL2 Linux, 운영=Oracle Cloud Linux 서버** 두 환경이다. 구분 정확히.

### 1.1 개발 환경 (WSL2 — 여기서 편집·커밋·테스트)
- **WSL 배포판**: `Ubuntu`(WSL2, Running). Linux 사용자 `kangjh3kang` · 호스트 `JHHOLDINGS` · **WSL IP `172.24.194.254`**.
- **툴체인**: Python **3.12.3**(`apps/api/.venv/bin/python`) · Node **v20.20.0** · pnpm **9.0.0**.
- **git 워크트리 루트(잠금, 브랜치 `feature/trust-infra-2026-06-11`)**: `/home/kangjh3kang/My_Projects/Development_AI_trust_infra`
- **작업 디렉터리(앱 모노레포 — 거의 모든 `cd` 대상)**: `/home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform` (← `propai-platform`은 git 루트의 하위 디렉터리. `apps/api`·`apps/web`·`docs`가 이 아래).
- **공유 .git(common-dir)**: `/home/kangjh3kang/My_Projects/Development_AI/.git` — 8개 워크트리가 **단일 repo를 공유**. ⚠️ `Development_AI`(main) 등 **다른 워크트리에서 작업 절대 금지**(더블 체크아웃→커밋이 엉뚱한 브랜치로). trust_infra 워크트리는 `locked`.
- **GitHub remote(SSH)**: `git@github.com:kangjh3kang-beep/Development_AI.git`.
- **마이그레이션 실경로**: `apps/api/database/migrations/versions/`(alembic.ini `script_location=database/migrations`). `apps/api/alembic/versions/` 아님.

### 1.2 Windows → WSL 접속 방법
- **파일(Read/Edit/Grep)**: UNC `\\wsl.localhost\Ubuntu\home\kangjh3kang\My_Projects\Development_AI_trust_infra\propai-platform\...`. `[id]`·`(dashboard)`·`[locale]`는 glob 메타문자.
- **명령**: `wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform; ...'`.
- **커밋 메시지**: wsl.exe inline에서 중첩 `$(...)`·내부 작은따옴표 금지 → `printf "%s\n" ...`로 `/tmp/x.txt`에 쓰고 `git commit -q -F /tmp/x.txt`.

### 1.3 로컬 실행·접속 (dev, WSL — Windows 브라우저는 WSL2 포워딩으로 `localhost:PORT` 그대로 접속, 또는 `172.24.194.254:PORT`)
- **백엔드(FastAPI)**: `cd apps/api && uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000` → **http://localhost:8000** (APP_PORT=8000).
- **프론트(Next 16)**: `cd apps/web && pnpm dev` → **http://localhost:3000**.
- **인프라 서비스**: `docker compose -f infra/docker-compose.yml up -d` — Postgres(postgis16) **host 5444→5432**(container `propai-postgres`) · Redis **6379** · Qdrant **6333** · MinIO(S3) **9000**(콘솔 9001) · Elasticsearch 9200 · Kafka 9092 · MLflow 5000 · Jaeger UI 16686/OTLP 4318 · Prometheus 9090 · Grafana 3001.
- **DB 연결**: 권위는 `apps/api/.env`의 `DATABASE_URL`. 코드 기본값은 위치별 상이(core/database.py=5432, config.py=5444/5445) — 실제는 .env 따름. infra compose는 host **5444** 노출.
- **테스트**: 백엔드 `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest <파일목록> -q`(협업/livekit은 **파일 명시**, `-k` 금지). 프론트 `npx vitest run <file>` · `npx tsc --noEmit` · `npx next build`.

### 1.4 운영(프로덕션) 접속위치
- **공개 도메인**: https://propai.kr · https://www.propai.kr · https://4t8t.net · https://www.4t8t.net (CORS allow-list, `apps/api/config.py:164`).
- **프론트 배포**: Cloudflare Pages(`propai-web.pages.dev`, opennextjs-cloudflare + wrangler).
- **서버 배포**: **Oracle Cloud Linux 서버** — 루트 `docker-compose.yml`(images `propai-web:oracle`·`propai-api:oracle` + qdrant + **nginx 리버스프록시**), `docker-compose.prod.yml`. ⚠️ 실제 서버 IP·SSH 접속정보는 **repo에 없음**(배포 담당·비공개 .env 관리, 추측 금지).
- ⚠️ **배포(머지·alembic 적용·재빌드·prod 반영)는 별도 배포 담당** — 이 워크트리 세션은 커밋·푸시까지.

## 2. 불변규칙 (항상 적용)
1. `feature/trust-infra-2026-06-11`에서만 작업. **main 직푸시·머지 금지**. 배포(머지·alembic 적용·prod)는 **별도 배포 담당** — 이 세션은 커밋·푸시까지.
2. **additive·하위호환** — 기존 키/엔드포인트/스토어/테스트계약/8엔진/DesignReviewResult/원장 스키마 불변, 신규만.
3. **결정론 코어 불변 + LLM 수치 비생성**(해석·종합·토론만, citation_gate 강제). **정직 표기**(data_source/confidence/skipped, silent failure 금지).
4. **무결성=내부 SHA256 해시체인+verify_chain으로 한정**(블록체인 미도입 — 사용자 결정 D4).
5. **갭 판단은 실코드 file:line 인용**. 커밋 푸터 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## 3. 트랙 B — 플랫폼 진화 (★ 다음 작업의 주축)
**상태**: 마스터 spec [`docs/superpowers/specs/2026-06-15-living-agent-knowledge-platform-design.md`](superpowers/specs/2026-06-15-living-agent-knowledge-platform-design.md) 커밋(`f594d2b`). **사용자 spec 리뷰 게이트 대기** — 승인 전 구현 착수 금지(브레인스토밍 HARD-GATE).

**핵심 진단(코드 실측, file:line)**: 그린필드 아님. 계층1(8엔진 `design_audit_orchestrator.py:54`·18 도메인·룰예측 `design_change_predictor.py:95`) 견고, 계층2 절반 구현 — **`apps/api/app/services/ledger/analysis_ledger_service.py`**(SHA256 해시체인·verify_chain·get_latest/get_history, `pipeline.py:425` 자동 append 가동), 계층3(멀티에이전트) 미성숙(`expert_panel_service.py:21`이 레버리지, `core/coordinator.py:9` 스텁, `app/services/agents/` 빈 폴더). **단일 최대 갭 = 성장 피드백 루프 부재**(원장 write만, 읽는 분석 서비스 0건). audit_service in-memory(비영속 결함).

**확정 결정(2026-06-15)**: D1 전체 0~4 마스터 먼저 / D2 전체 cross-project 학습(§6 프라이버시 가드 필수: feature_vector·집계만·익명·opt-out·격리테스트) / D3 Phase3 전 도메인 동시 / D4 내부 해시체인.

**로드맵**: P0 무결성 단일화(1~2주,위험0) → **P1 ★성장루프 read 경로(2~3주,최고가치)** → P2 Lineage DAG·모순감지 → P3 SpecialistAgent+토론(coordinator 실구현) → P4 실시간 이벤트·능동 위험감지. 밖: ML 위험예측층.

**다음 단계(정확히)**: ① 사용자가 spec 리뷰·승인 → ② writing-plans 스킬로 **Phase 0(무결성 단일화)** 구현 plan을 `docs/superpowers/plans/2026-XX-XX-phase0-*.md`로 분해 → ③ TDD 구현 → 검증(코드리뷰·테스트·tsc/build) → 커밋·푸시. 각 Phase는 독립 additive 단위, 0→1→2→3→4 의존 순.

## 4. 트랙 A — F3 회의방 (완료·미배포)
SP2 멤버·초대 / SP3 자료교환+8엔진 정직 type-routing / SP4 purpose 구분+문서뷰어(이미지/PDF react-pdf/DXF 경량 CAD) / SP5 협력업체 scope / SP6 의견교환 스레드 / **LiveKit Phase3 화상회의**(룸·토큰·녹화 alembic 030, 키+스테이징 미검증) / 보안하드닝(악성파일 1차차단·PDF워커 env폴백) / **배포검증 audit→GO**(결함 A~E 수정 `8baac86`~`8213ef2`). 협업+livekit 회귀 **140 passed**. 상세: [SESSION_HANDOFF_2026-06-14](SESSION_HANDOFF_2026-06-14.md) + [DEPLOY_HANDOFF](DEPLOY_HANDOFF_SP2_COLLAB_2026-06-14.md).

## 5. 배포 담당(다른 Claude) 몫 — 이 세션 범위 밖
- main 머지 + **alembic 025~030 적용**(경로 `apps/api/database/migrations/versions/`, 체인 024→030 선형) + `pip install`(livekit-api) · `pnpm install`(react-pdf·livekit-client) + 재빌드.
- 사용자: **LiveKit 키**(LIVEKIT_URL/API_KEY/API_SECRET + Egress S3) → 스테이징 실연결 검증.

## 6. 교훈 (반복 방지)
- 갭은 실코드 file:line 검증(audit가 EXISTS를 MISSING으로 반복 오판 — analysis_ledger도 한 에이전트가 '코드 열람 불가'로 과소평가했으나 실재). 멀티에이전트 review 에이전트가 WSL UNC 미사용 시 'codebase not found' 거짓-critical.
- 협업 테스트는 파일 명시(‑k 금지). wsl.exe 커밋은 printf+`-F`.
- 멀티에이전트 워크플로 병렬 fan-out이 일시 레이트리밋 가능 — 웹조사 등은 실패 시 main 스레드에서 순차 재수행.

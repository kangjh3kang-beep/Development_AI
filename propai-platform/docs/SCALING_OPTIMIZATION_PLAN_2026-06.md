# PropAI 프로덕션·확장 최적화 계획 (핸드오프)

작성일: 2026-06-05 · 용도: 프로덕션 배포·다수 사용자 대비 확장 최적화 (후속 작업 핸드오프)

---

## 0. 현재 아키텍처 실측(2026-06-05)
- **프런트엔드**: Next.js(pnpm 모노레포 `apps/web`, turbo) → **Cloudflare Workers**(`@opennextjs/cloudflare`). 도메인 `4t8t.net`.
  - 문제: **오류 1102(Worker 요청당 CPU/메모리 128MB 한도 초과)** — 무거운 SSR.
- **백엔드**: **Oracle VM 1대** (134.185.104.167) — **RAM 956MB(가용 ~385MB)·2 vCPU·swap 4GB**.
  - `Dockerfile.oracle`로 빌드, **Caddy(:80) 뒤 blue-green**(8000↔8001 단일 컨테이너 교대), qdrant 컨테이너. node 미설치.
  - 도메인 `api.4t8t.net`(Cloudflare → Oracle:80). 공공데이터 국외IP 차단 회피용 국내 서버.
  - **uvicorn 단일 워커**(동시성 한계).
- **DB**: Supabase(원격 pooler). **Redis**: degraded(미가동). **Qdrant**: 일부 unhealthy(정상 범주).
- **부하 특성**: LLM(Claude) 인터프리터 다수, 공공데이터 외부 API(VWorld·MOLIT·R-ONE·G2B 공유키), 3D/CAD 무거움, 동기 장시간 요청(파이프라인·등기 ~50s).

## 1. 확장 병목(우선순위)
1. **백엔드 단일 956MB VM·단일 워커** — 가장 큰 리스크. 동시접속/동시분석 즉시 한계.
2. **장시간 동기 요청**(파이프라인·등기·LLM 10~50s) — 워커 점유 → 소수 동시요청에 큐 막힘·타임아웃.
3. **프런트 Cloudflare 1102** — SSR CPU 한도.
4. **Redis 미가동** — 재계산·외부API 반복(비용·지연).
5. **외부 API 레이트리밋**(공유키), **Supabase 커넥션 한도**.

## 2. 가장 효과적인 단일 전략
**긴 작업은 큐로 분리(비동기) + 무상태 백엔드 수평 확장 + Redis 캐시 정상화 + 인프라 적정화.**
보유 자산 활용: `apps/worker`(arq)·Redis·Supabase·기구축 캐시(`interpretation_cache`·`registry_analysis_cache`·등기 비동기 잡 폴링 패턴).

## 3. 우선순위 로드맵

### P0 — 인프라 적정화
- **Oracle Ampere A1 무료 한도(최대 4 OCPU/24GB)로 VM 업그레이드** — 같은 Oracle, 비용 0~저렴.
  - 효과: 멀티워커 수용 + **프런트 빌드 가능**(현재 956MB는 Next 빌드 OOM — 빌드 2~4GB 필요).
- 백엔드 **uvicorn `--workers N`** 또는 컨테이너 N개 + **Caddy 로드밸런싱**.

### P0 — 장시간 작업 비동기화(최대 효과)
- 파이프라인(`/api/v2/pipeline/run`)·등기·LLM 해석을 **arq 큐 제출 → jobId 폴링**으로 전환(등기는 이미 이 패턴: `/registry/analyze/jobs`).
- 웹 워커가 50s씩 안 묶임 → 동시 처리량 급증, 100s 프록시/1102 회피.

### P1 — 캐시 일원화(Redis 복구)
- LLM 해석·공공데이터(VWorld/MOLIT/R-ONE)·분석결과·세션을 Redis 캐시(현재 일부 DB캐시 → Redis 승격).
- 공공데이터 TTL 캐시로 외부 레이트리밋·지연 회피.

### P1 — 프런트 1102 근본 해결
- **(B) Vercel**(자동확장·운영 최소·즉효) 또는 **(C-1) CI(GitHub Actions) 빌드 → Oracle(업그레이드 후) Node 런타임**(무료 유지·일원화).
- 상세: `docs/FRONTEND_RUNTIME_MIGRATION_2026-06.md`.

### P2 — DB·외부 API
- Supabase pgbouncer 풀링 한도·인덱스 점검, 필요 시 읽기복제. 외부 API 키 다중화·지수 백오프.

### P3 — 관측성(필수)
- Sentry(에러)·APM·요청 지연/큐 길이 모니터링 → 데이터 기반 증설. 부하테스트(k6/locust).

## 4. 권고 실행 순서
1. Oracle VM → Ampere A1(4OCPU/24GB) 업그레이드 (OCI 콘솔).
2. 장시간 작업 arq 큐 전환 + 프런트 폴링.
3. Redis 복구 후 캐시 일원화.
4. 프런트 Vercel 또는 Oracle Node 이전(1102 종결).
5. 부하테스트로 검증하며 단계 증설.

## 5. 이미 적용된 토대(2026-06-05 세션)
- AI 해석 **온디맨드 + 캐시(`interpretation_cache`) + 프리페치** (동기 파이프라인 미블로킹).
- 무거운 패널 **`dynamic ssr:false`**(대시보드·프로젝트 상세·BIM) → 1102 완화.
- 분석 원장(해시체인) + 용량 쿼터 + 관리자 감사로그.
- blue-green 무중단 배포, 멱등 처리(원장·등기).

## 6. 참고 파일/경로
- 배포: Oracle `~/deploy.sh`(blue-green), `Dockerfile.oracle`, Caddy `~/caddy/Caddyfile`.
- 워커: `apps/worker/main.py`(arq `WorkerSettings.functions`/`cron_jobs`).
- 파이프라인: `apps/api/app/services/pipeline/project_pipeline.py`, 라우터 `app/routers/pipeline.py`.
- 캐시: `app/services/ai/interpretation_cache.py`, `app/services/registry/registry_analysis_service.py`.
- 프런트 빌드: `apps/web` `next build`(Node)·`opennextjs-cloudflare build`(현행). `next.config.mjs` `outputFileTracingRoot` 설정됨.

# PropAI 플랫폼 전체 코드리뷰 보고서 (2026-06-11)

> 리뷰 범위: 백엔드 API(보안/계산정확성/아키텍처·성능), 프론트엔드(Next.js), 스마트컨트랙트(Solidity 5종), 인프라/DevOps/저장소 위생.
> 6개 병렬 리뷰 에이전트가 실제 코드를 정독·검증한 결과만 수록. 추측성 항목 없음.

---

## 🚨 즉시 조치 (오늘 안에)

### 1. GitHub에 푸시된 운영 JWT 서명키 — 키 로테이션 최우선
- `propai-platform/.env.example` 이 **git에 추적되어 원격(github.com:kangjh3kang-beep/Development_AI)에 푸시됨**.
- 이 파일의 `JWT_SECRET_KEY=da4c1647...` 값이 실제 운영 `.env`의 JWT 서명키와 동일. `HASURA_GRAPHQL_ADMIN_SECRET`(56자 실값)도 포함.
- 이 키로 누구나 임의 사용자/권한의 위조 JWT 발급 가능.
- **조치**: ① JWT 키 즉시 교체 ② Hasura admin secret 교체 ③ `.env.example`을 플레이스홀더로 정리 ④ `git filter-repo`로 히스토리 제거 검토.

### 2. 블록체인 배포자 프라이빗키 평문 노출
- `contracts/.env:5` — `DEPLOYER_PRIVATE_KEY="bece1e97...f5fbee"` 평문 저장 (git 미추적이지만 파일에 실키 존재).
- 이 키는 Amoy 테스트넷 배포 `PropAIEscrow`(0x961cba4A...82E6)의 **owner 전권 키** (pause, 분쟁해결, 수수료 수취). 메인넷 재사용 시 즉시 자금 탈취 가능.
- Alchemy/Polygonscan API 키도 함께 노출. `setup-env.sh`가 실키를 .env에 기록하는 구조 자체가 문제.
- **조치**: 키 폐기·로테이션, 잔액 이전, 하드웨어 지갑/KMS 전환, setup-env.sh 수정.

### 3. 운영 Supabase DB 비밀번호 평문
- `apps/api/.env:9-10` — 운영 Supabase 호스트+비밀번호(`postgres.kpzextnpunlbpydzbpef:k3j3h3g3f3!@...`) 평문 저장.
- **조치**: DB 비밀번호 회전, 로컬 .env에서 운영 자격증명 제거, secret manager로 이전.

### 4. ANTHROPIC_API_KEY 등 실키 일괄 점검
- `propai-platform/.env` — `sk-ant-` 실키, KAKAO_CLIENT_SECRET, MOLIT_API_KEY 등 평문. `.dockerignore` 한 줄에만 의존해 이미지 유입을 막고 있는 구조.

---

## 🔴 Critical — 비즈니스 로직 (수지분석 결과를 왜곡)

### C-1. 양도세: 장기보유특별공제 이중 차감 → 세액 왜곡(음수 가능)
- `apps/api/app/services/tax/disposal_stage_engine.py:45,124,236-240,252`
- D01이 이미 공제 반영(`taxable = gain × (1−rate)`)했는데, D04가 **과세표준 감소액**(세액 아님)을 음수 항목으로 `total_won`에 또 합산.
- 검증례: 양도차익 10억·5년 보유 → 합계 2.76억 (정답 3.76억). 공제율 크면 합계가 음수까지 감.
- 수정: D04를 정보성 항목으로 분리(합산 제외)하거나 단일 차감 구조로 통일.

### C-2. 취득세·전용부담금 이중계상 — 토지비 엔진과 세금 엔진이 각각 합산
- `app/services/feasibility/modules/common/cost_blocks.py:14-24 vs 81-100` + `generic_module.py:53-66`
- `land_cost_engine`이 취득세(~4.6%)+전용부담금을 토지비에 포함, `calculate_all_taxes()`가 동일 항목을 또 `grand_total_won`에 포함, `aggregate_feasibility()`가 둘 다 비용으로 합산 → **토지가액의 ~4.6%+부담금이 정확히 2번** 계상. 수백억 토지면 수십억 과대.

### C-3. 현금흐름 net_profit에 자기자본이 이익으로 합산
- `app/services/feasibility/cashflow_generator.py:100-103,126-131,188-232`
- 자기자본 투입을 inflow로 기록하나 회수 outflow가 없음 → `net_profit = 실제이익 + equity`. equity 30%면 이익이 총사업비의 30%만큼 부풀려짐. `profit_rate_pct`도 왜곡.

### C-4. 토큰 배당 회계 버그 — burn/transfer 후 배당·토큰 이동 영구 잠김 (DoS)
- `contracts/src/PropAIToken.sol:202-206` (`_updateDividend`)
- mint/burn/transfer 시 `dividendDebit` 재계산 누락. mint 후 과다 적립(배당 풀 지급불능), burn/전송 후 언더플로 revert로 해당 계정의 claim/transfer/burn 영구 실패.
- 재현: mint 1000 → distribute → burn 200 → claim ⇒ revert.
- 수정: 잔액 변경 직전 정산 + 직후 debit 재설정(MasterChef 패턴). burn→claim, transfer→claim 회귀 테스트 추가.

---

## 🟠 High

### 백엔드 보안
| # | 위치 | 문제 | 수정 |
|---|------|------|------|
| H1 | `routers/ai_assistant.py:70-102` | `/api/v1/ai/chat` **무인증** — 비로그인으로 서버 과금 LLM 무제한 호출 가능 | `get_current_user` + ai rate limit(정의된 `ai_limiter` 적용) |
| H2 | `routers/webhooks.py:86`, `services/webhook_service.py:89-90` | SSRF — 사용자 웹훅 URL 무검증 호출(169.254.169.254, localhost 등 내부 자원 접근 가능) | https 강제, 사설/링크로컬/루프백 차단, `follow_redirects=False` |
| H3 | `app/routers/land_price.py:22-48` 등 | 도메인 라우터 다수 무인증 (공공 API 키 소비) | `app/routers/*` 인증 일괄 점검 |
| H4 | `auth/jwt_handler.py:91` + `app/services/auth/auth_service.py:40-49` | JWT aud/iss 미검증 + 토큰 발급/검증 모듈 2개 공존(클레임 구조 불일치) | 단일 모듈 통일, aud/iss 추가 |
| H5 | `app/routers/uploads.py:19-38` | 업로드 무인증 + 매직바이트 미검증 + public 버킷 자동 생성 | 인증 추가, 이미지 검증, 버킷 사전 프로비저닝 |

### 세금/금융 계산
| # | 위치 | 문제 |
|---|------|------|
| H6 | `disposal_stage_engine.py:128-167` | 재건축초과이익환수 — 2024.3.27 개정법(면제 8천만, 구간 5천만, 최고 50%) 미반영. 구법 기준 + 50% 구간 누락 |
| H7 | `acquisition_stage_engine.py:94-101,215` | 등록면허세(A05) 2% 무조건 부과 — 2011년 취득세 통합으로 이중과세. 취득세금 매입가 2%p 과대 |
| H8 | `disposal_stage_engine.py:24-68` | 단기보유 중과세율(1년 미만 70%/50%, 1~2년 60%/40%) 미적용 — 단기 전매형 사업 세금 절반 이하 과소계상 |
| H9 | `cashflow_generator.py:169-179` | 정산월 잔금 계산이 대출금·자기자본까지 분양수입으로 집계 가능. 분양기간이 정산 이후로 넘어가면 수입 이중계상 |
| H10 | `unit_mix_optimizer.py:77-100`, `feasibility_service_v2.py:134-143` | 전용/공급면적 혼용 — GFA÷전용면적으로 세대수 산정(공용면적 무시) → 세대수·매출 ~30% 과대. 전용률 계수 필요 |

### 백엔드 아키텍처
| # | 위치 | 문제 |
|---|------|------|
| H11 | `services/bim_ifc_service.py:150-153`, `app/routers/pipeline.py:493-499` | async 핸들러에서 동기 IFC 파싱·PDF 빌드·전체 파이프라인 실행 → **이벤트 루프 정지**. 워커 태스크(`parse_large_ifc`, `generate_report_pdf`)가 이미 있는데 미사용 | 
| H12 | `routers`+`services` vs `app/routers`+`app/services` **이중 패키지 트리** | `main.py:580-584` 주석 스스로 "중복 등록 시 RBAC 우회 위험" 인정. ImportError 폴백으로 silent 미마운트(런타임 404) 가능 |
| H13 | 10개 파일 | 요청 경로 런타임 DDL(`CREATE TABLE IF NOT EXISTS`) — Alembic 이관 필요 |
| H14 | `database/session.py:97-112` | RLS 테넌트 격리 `get_tenant_db` **호출처 0건** — 격리가 수동 WHERE에만 의존 |
| H15 | `app/api/endpoints/sales/social.py:434-440` 등 | N+1 쿼리 (친구검색 1+20, 멤버별 개별 INSERT 등) |

### 프론트엔드
| # | 위치 | 문제 |
|---|------|------|
| H16 | `components/map/NearbyTransactionsMap.tsx:255-261` | **XSS** — 외부 API 응답(name/address/url)을 이스케이프 없이 카카오맵 오버레이 HTML에 주입. `javascript:` URL 실행 가능 |
| H17 | `lib/api-client.ts:91-152` | 액세스+리프레시 토큰 모두 localStorage 저장 — XSS와 결합 시 세션 영구 하이재킹 (TODO 주석만 있고 미이행) |
| H18 | 8개+ 파일 (`LandScheduleClient.tsx:108` 등) | api-client 우회 직접 fetch + 토큰 직접 조회 → 401 자동갱신·타임아웃·에러 정규화 누락. 토큰 만료 후 해당 화면만 조용히 깨짐 |
| H19 | i18n 전역 | dictionary 사용 27개 파일뿐. AuctionWorkspace 한국어 리터럴 271줄 등. **ProjectDesignWorkspaceClient.tsx:128에 중국어 간체 문자열이 한국어 UI에 잘못 커밋됨** |

### 인프라/CI
| # | 위치 | 문제 |
|---|------|------|
| H20 | `.github/workflows/` 위치 오류 | propai-platform 하위 8개 워크플로(테스트·보안·e2e)는 **git 루트가 Development_AI라 절대 실행 안 됨**. 실제 실행은 루트 `deploy-cloudflare.yml` 1개 — main 푸시마다 **테스트 없이 프로덕션 배포** |
| H21 | `Dockerfile.web` | 최종 스테이지 `USER` 미지정 → root 실행. HEALTHCHECK 없음 |
| H22 | `docker-compose.yml:42-44` | qdrant 6333 포트 호스트 직접 노출, 무인증 |
| H23 | `nginx.conf` | 보안 헤더 전무, `client_max_body_size` 미설정(기본 1MB → 업로드 413 실패) |
| H24 | `docker-compose.prod.yml:12,42` | DB 비밀번호 `secret` 하드코딩 |

---

## 🟡 Medium (요약)

**계산**: SLSQP 수렴실패 무시+선언된 제약(용적률/층수/주차) 미사용(`unit_mix_optimizer.py:131-143`) · 몬테카를로 수렴판정 오류(CV를 수렴지표로 사용 — 표준오차 `std/(|mean|·√N)`로 교체)(`monte_carlo_engine.py:65`) · IRR 표본 선택편향+가짜 민감도분석(`finance/monte_carlo_service.py:35-72`) · 중도금/PF 이자 전액·전기간 가정(~2배 과대)(`finance_cost_engine.py:114-204`) · 주택 취득세 1~3% 슬라이딩 미반영(`regional_tax_data.py:28-31`) · 분양자 부담 세금(C04-C06)을 시행사 사업비에 합산(`sale_stage_engine.py:82-123`) · 관리/농림/자연환경보전지역 법규검증 자체 불가(ZONE_LIMITS 키 누락 → 빈 리스트 = 통과로 보임)(`zoning/legal_zone_limits.py:30-52`)

**보안**: TimescaleDB DDL 헬퍼 f-string SQL(식별자 인젝션 잠재)(`app/core/db_utils.py:92-126`) · 로그인 에러에 내부 예외 노출(`routers/auth.py:121,132`) · CORS allow_credentials+localhost 기본 오리진 · CSP unsafe-inline/eval

**컨트랙트**: 단일 단계 Ownable(→`Ownable2Step`) · 거버넌스 투표 스냅샷 부재(제안 진행 중 멤버 변경으로 결과 조작 가능)(`PropAIGovernance.sol:162-202`) · SubcontractPayment 복수 Pending 청구 합계가 totalAmount 초과 가능(`SubcontractPayment.sol:130-182`)

**프론트**: SVG `dangerouslySetInnerHTML` 무 sanitize(`CadBimIntegrationPanel.tsx:1042`) · 게스트 무료쿼터 클라이언트 전용(localStorage 우회로 LLM 비용 어뷰징)(`ProjectPipelinePanel.tsx:108-123`) · zod 등 응답 런타임 검증 부재 · loading.tsx 0개/error.tsx 9/59 · 836라인 zustand persist 스토어에 서버 상태 영속(서버 상태 관리 3패턴 분열) · 'use client' 299/375 파일(~80%) · 1,000라인+ 컴포넌트 12개 · 죽은 중복 API 클라이언트(`packages/utils/src/api-client.ts` — import 0건)

**인프라**: infra/ vs infrastructure/ 중복(infrastructure/는 참조 0건 — 정리 대상) · 베이스 이미지 digest 미고정 · `/docs`/`openapi.json` 운영 무인증 공개 · compose dev/prod 완전 분기로 진짜 프로덕션 판별 불가

---

## 🧹 저장소 정리 대상 (git rm)

- docker build 출력 사고 파일 15개: `=`, `CACHED`, `CANCELED`, `ERROR`, `[internal]`, `[propai-api`, `[propai-web`, `extracting`, `next`, `reading`, `resolve`, `transferring`, `sha256:*` 3개 (모두 0바이트, git 추적·푸시됨)
- 임시 스크립트: `_gen_phase8.py`, `_phase8_runner*.py` 3개, `_phase8_final.py`, `_phase8_data_1.json`, `design_base64.txt`, `cleanup_safe.py`, `.coverage.JHHOLDINGS.*`
- `apps/web/test-results/` 19개 파일
- 검토 후: `_workspace/`(22), `.build-journal/`(95) — 내부 작업로그 원격 공개 여부 판단
- 디스크만: `로컬`, `로컬+몬테카를로`, `step1~3.png`, `screenshot.js`, `kakao_review_template.html`
- `propai-platform/.gitignore` 보강: `.venv/`, `__pycache__/`, `test-results/`, `.coverage*`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `uploads/`, `qdrant_storage/`

---

## ✅ 양호한 부분

- **보안 기본기**: bcrypt 해싱, 리프레시 토큰 SHA-256 저장+로테이션, `os.system`/`pickle.load`/`eval`/`verify=False` 0건, 라우터 SQL은 바인드 파라미터+화이트리스트 일관, 시크릿 금고(Fernet+DENYLIST+감사로그)
- **계산 일부 정확**: 정북일조 사선(시행령 86조) 정확 구현, 종부세·양도세 누진 브래킷 현행 기준, IRR 이분법의 신중한 근 선택, 몬테카를로 시드 고정(재현성)
- **아키텍처**: `integrations/base_client.py`(타임아웃 세분화+tenacity+Circuit Breaker+Redis 캐시+Prometheus) 모범적, 동기 requests 0건, CPU 작업 일부 `to_thread` 정석 처리
- **컨트랙트**: Escrow 재진입 방어(CEI+nonReentrant+공격 mock 테스트 실증), call 반환값 전수 체크, 메인넷 미배포(Amoy만)
- **프론트**: api-client 401 refresh 설계 정석(중복 refresh 방지), three.js dynamic import, mock 모드 명시적(NEXT_PUBLIC_USE_MOCKS)
- **테스트**: 961개 테스트 수집 성공(unit 78파일/integration/load/benchmarks). 단, 계산 테스트가 "키 존재·양수" 스모크 수준이라 Critical 3건을 통과시킴 — 정답값 고정 수치 회귀 테스트 필요

---

## 📋 권장 로드맵

**Phase 0 — 시크릿 (즉시)**
1. JWT 키·Hasura secret 로테이션 (.env.example 유출분)
2. 배포자 프라이빗키 폐기·이전
3. Supabase DB 비밀번호 회전
4. .env 정리 + secret manager 이전

**Phase 1 — Critical 버그 (1주)**
5. 양도세 D04 이중차감 수정 + 수치 회귀 테스트
6. 취득세/부담금 이중계상 수정 (land_cost vs tax 엔진 역할 분리)
7. equity 이익 합산 수정
8. PropAIToken 배당 회계 수정 (메인넷 배포 전 필수)
9. 무인증 엔드포인트(ai/chat, uploads, land-price 등) 인증 적용
10. 웹훅 SSRF 차단
11. NearbyTransactionsMap XSS 수정

**Phase 2 — 구조 (2~4주)**
12. CI 워크플로 루트 이관 → 배포 전 테스트 게이트 연결
13. 이중 패키지 트리(routers/app.routers) 통합
14. 런타임 DDL → Alembic 이관
15. 무거운 작업(IFC/PDF/파이프라인) arq 워커 위임
16. api-client 우회 fetch 8곳 통일, 리프레시 토큰 HttpOnly 쿠키 전환
17. 저장소 정리(git rm + .gitignore 보강) + infrastructure/ 삭제

**Phase 3 — 품질 (지속)**
18. 세법 업데이트(재건축환수 개정법, 단기 중과, 주택 취득세 슬라이딩)
19. 유닛믹스 전용률 도입 + SLSQP 제약 구현
20. 몬테카를로 수렴판정 교정
21. i18n 이관 + 한글 리터럴 lint
22. 계산 엔진 정답값 회귀 테스트 체계 구축

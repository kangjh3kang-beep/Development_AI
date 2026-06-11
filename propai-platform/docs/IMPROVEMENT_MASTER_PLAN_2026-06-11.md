# PropAI 개선·고도화 마스터플랜 (2026-06-11)

> 근거 자료: ①기획안 분석(모세혈관 Phase00-15, v49/v58/v62, 수지분석 PartA) ②구축현황 실사 ③전체 코드리뷰(docs/CODE_REVIEW_2026-06-11.md)
> 목표: "광범위하게 구현됐으나 신뢰도가 깎인 상태(완성도 ~55-60%)" → "숫자가 맞고, 테스트로 보호되고, 보안이 잠긴 신뢰 가능한 플랫폼" → 기획의 혁신 포인트 완성

---

## 1. 진단 요약

### 기획 대비 현황
| 영역 | 기획 | 현황 | 갭 |
|---|---|---|---|
| 전주기 8단계 통합 | 부지발굴→운영 단일 SaaS | 라우터 110+, 페이지 60, 골격 ~85% | 롱테일 30+ 도메인은 mock 게이트 |
| 수지분석 엔진 | 15유형×38세금×229시군구 + MC 10,000회 + Git 버전관리 | 모듈 엔진 실구현 | ~~Critical 계산버그 4건~~(수정완료), 면적기준 혼용 |
| 법규 AI | RAG + 법령 변경 자동 재검증 | RAG 구현 | 관리/농림지역 ZONE_LIMITS 누락, 변경감지 데몬 미검증 |
| AVM | XGBoost+MLflow MAPE<7% | 폴백(면적 휴리스틱) 의존 | **ml/ 학습 파이프라인 자체가 부재** |
| 멀티테넌트 | RLS 격리 | get_tenant_db 호출 0건 | RLS 미작동, 수동 WHERE 의존 |
| 품질 게이트 | CI E2E+부하테스트 | 워크플로 8개가 루트 불일치로 **전부 미실행** | 무테스트 prod 배포 |
| 보안 | JWT+RLS+PQC | 기본기 양호 | ~~시크릿 유출·무인증 엔드포인트~~(조치중) |

### 신뢰도를 깎는 3대 구조 문제
1. **이중 패키지 트리**: `routers/`+`services/` vs `app/routers/`+`app/services/` — 인증 모듈 2벌, RBAC 우회 위험, silent 미마운트
2. **프론트 서버상태 3분열**: react-query(39) vs zustand persist(836줄 스토어) vs 수동 useEffect(71) + api-client 우회 fetch 8곳
3. **mock 게이트 이중구조**: 56개 컴포넌트 199곳의 canUseLiveApi — 데모와 실기능 경계 불투명

---

## 2. 완료된 작업 (2026-06-11 세션)

### Phase 0 — 시크릿 (코드레벨 완료, 키 로테이션은 사용자 액션: docs/SECURITY_KEY_ROTATION.md)
- [x] `.env.example` 실 JWT 키 제거 → 플레이스홀더
- [x] `docker-compose.prod.yml` 하드코딩 비밀번호 → `${VAR:?}` 필수 주입 가드
- [x] `app/core/config.py` 운영환경 약한/유출 시크릿 시작 차단 (`_KNOWN_WEAK_SECRETS`)
- [x] `setup-contracts-env.sh` 프라이빗키 입력 화면 노출(read → read -s) 수정
- [x] `.gitignore` 보강 (.venv, test-results, .coverage 등 11종)

### Phase 1 — Critical 계산 버그 (수정 + 수치 회귀 테스트 51개 통과)
- [x] **C-1** 양도세 D04 이중차감 → 정보성 항목화. 10억·5년 = 376,266,000원 검증
- [x] **C-2** 취득세·전용부담금 이중계상 → `include_taxes_and_fees` 플래그, 모듈 경로는 세금엔진 단일 계상
- [x] **C-3** 현금흐름 equity 이익 합산 → equity_in_total 분리, net_profit = 수입−실사업비. 이익률 분모도 실사업비로 교정
- [x] **C-4** PropAIToken 배당 회계 → settle/sync 2단계 패턴. burn→claim DoS, transfer 비율, mint 소급적립 회귀 테스트 3건
- [x] **H-4** 정산 잔금 대출금 오염·분양수입 이중계상 → revenue_received 전용 추적
- [x] **H-6** 재건축초과이익환수 2024.3.27 개정법 (면제 8천만, 5천만 단위 10~50%)
- [x] **H-8** 단기보유 중과세율 (1년 미만 70%/50%, 1~2년 60%/40%)

### Phase 1·2 — 진행 중 (병렬 에이전트)
- [ ] 백엔드 보안: ai/chat 인증, 웹훅 SSRF 가드, 업로드 인증+매직바이트, 로그인 에러 정보 노출
- [ ] 프론트 보안: 카카오맵 XSS, SVG sanitize, 중국어 문자열 핫픽스, rel noopener
- [ ] 저장소 정리(git rm 30+파일) + CI 게이트 복구(루트 ci.yml + 배포 전 테스트 필수화)

---

## 3. 남은 로드맵

### Phase 2 — 계산 엔진 완성 (1주, 수지분석 신뢰도 = 플랫폼 핵심가치)
| # | 항목 | 위치 | 효과 |
|---|---|---|---|
| 2-1 | 등록면허세 A05 이중과세 제거 (2011 취득세 통합 반영) | acquisition_stage_engine.py | 취득단계 −2%p 과대 해소 |
| 2-2 | 주택 취득세 1~3% 슬라이딩 + 인지세 하위구간 | regional_tax_data.py | 고가주택 정확도 |
| 2-3 | 유닛믹스 전용률 계수 도입 (GFA÷전용 → 공급면적 기준) | unit_mix_optimizer.py, feasibility_service_v2.py | 세대수·매출 ~30% 과대 해소 |
| 2-4 | SLSQP 수렴실패 처리 + 용적률·층수·주차 제약 실구현 | unit_mix_optimizer.py | 최적화 신뢰성 |
| 2-5 | 몬테카를로 수렴판정 교정 (CV → 표준오차 std/(μ√N)) | monte_carlo_engine.py, monte_carlo_service.py | converged 의미 회복 |
| 2-6 | 중도금·PF 이자 평균잔액 기준 (전액·전기간 → 분할실행 반영) | finance_cost_engine.py | 금융비 ~2배 과대 해소 |
| 2-7 | 분양자 부담 세금(C04-C06) 시행사 사업비에서 분리 | sale_stage_engine.py | 사업비 −1.55%p 과대 해소 |
| 2-8 | 관리/농림/자연환경보전 ZONE_LIMITS 보완 + 제1종전용 건폐율 50 교정 | legal_zone_limits.py | 법규검증 커버리지 |
| 2-9 | IRR 표본 선택편향 제거 + 가짜 민감도분석 실구현 | finance/monte_carlo_service.py | 투자분석 신뢰성 |
| 2-10 | 위 전부에 정답값 고정 회귀 테스트 | tests/ | 재발 방지 |

### Phase 3 — 구조 리팩토링 (2~4주)
| # | 항목 | 비고 |
|---|---|---|
| 3-1 | 이중 패키지 트리 통합 (`routers`→`app/routers`, `services`→`app/services`) | main.py ImportError 폴백 제거, 라우터 등록 명시화. **최대 리스크 작업 — 별도 브랜치+전체 테스트** |
| 3-2 | JWT 발급/검증 단일 모듈 + aud/iss 클레임 | 이중 인증체계 해소 |
| 3-3 | 런타임 DDL 10개 파일 → Alembic 이관 | 레이턴시·락 경합 제거 |
| 3-4 | IFC 파싱·PDF 생성·전체 파이프라인 → arq 워커 위임 (202+폴링) | 이벤트 루프 정지 해소. 워커 태스크 이미 존재 |
| 3-5 | RLS `get_tenant_db` 실적용 또는 명시적 폐기 결정 | 멀티테넌트 격리 |
| 3-6 | 외부 API 호출 `BaseAPIClient` 단일 관문화 (vworld 11곳 우회 해소) | 캐시·Circuit Breaker 일괄 |
| 3-7 | 프론트 api-client 우회 fetch 8곳 통일 + 토큰 키 캡슐화 | 토큰 만료 시 조용한 실패 해소 |
| 3-8 | 리프레시 토큰 HttpOnly 쿠키 전환 | XSS 내성 |
| 3-9 | N+1 쿼리 수정 (social 친구검색, 알림 등) | |
| 3-10 | infrastructure/ 삭제 (infra/로 단일화), compose dev/prod 통합 | |

### Phase 4 — 기획 갭 해소·고도화 (지속)
| # | 항목 | 기획 근거 |
|---|---|---|
| 4-1 | **AVM 실모델 구축**: ml/ 학습 파이프라인 신설(MOLIT 실거래 수집→XGBoost 학습→MLflow 등록→폴백 탈출) | Ph04, MAPE<7% 목표 |
| 4-2 | 게스트 쿼터 서버사이드 검증 (LLM 비용 어뷰징 차단) | 수익모델 보호 |
| 4-3 | 수지분석 Git 버전관리 (commit/branch/diff/rollback) 완성도 점검·E2E | 수지분석 PartA 핵심 차별화 |
| 4-4 | 법령 변경 감지 데몬 실동작 검증 + 기존 프로젝트 자동 재검증 연결 | G190/G215 혁신 포인트 |
| 4-5 | 프론트 서버상태 react-query 일원화 (점진: 신규/수정 화면부터) | 3분열 해소 |
| 4-6 | i18n 이관 (대형 워크스페이스부터) + 한글 리터럴 CI lint | en/zh 사용자 |
| 4-7 | mock 게이트 정리: 도메인별 "실연동 완료" 선언 후 mock 제거 | 데모/실기능 경계 |
| 4-8 | loading.tsx/error.tsx 보강, 'use client' 페이지 셸 서버컴포넌트화 | UX·성능 |
| 4-9 | 컨트랙트: Ownable2Step, 거버넌스 스냅샷, SubcontractPayment 상한 검증 | 메인넷 전 필수 |
| 4-10 | nginx 보안헤더+client_max_body_size, qdrant 포트 비노출, Dockerfile.web 비루트 | 운영 강화 |

### 혁신 업그레이드 후보 (Phase 5 — 기획의 차별화 완성)
1. **Top3 자동추천 파이프라인 고도화**: 주소입력→15모델 시뮬→Top3가 이미 있음 → 계산엔진 신뢰도 확보(Phase 2) 후 "근거 추적 가능한 추천"(calculation_metadata 연결)으로 격상
2. **수지분석 버전관리 UI**: diff 시각화 + 시나리오 브랜치 비교 — 경쟁사(Feasibly 등) 미보유 기능
3. **법령 변경 → 영향받는 프로젝트 자동 알림**: 데몬+웹훅+알림톡 연결 시 "살아있는 인허가 검증" 완성
4. **은행제출용 보고서(PF 심사 10섹션)**: 계산 정확도 확보가 선행조건 — Phase 2 완료 시 실전 투입 가능
5. **G2B 입찰 6엔진**: 적정투찰가 모델 백테스트(과거 낙찰 데이터 대비 정확도 검증) 추가

---

## 4. 실행 원칙
1. **계산 정확성 > 기능 추가**: 수지분석 숫자가 틀리면 플랫폼 전체가 무가치 — Phase 2를 신규 기능보다 우선
2. **모든 수정에 정답값 회귀 테스트**: "키 존재" 스모크 테스트 금지
3. **CI 게이트 먼저, 리팩토링 나중**: 3-1(트리 통합)은 CI 복구 후 착수
4. **키 로테이션은 즉시**: docs/SECURITY_KEY_ROTATION.md 참조 (사용자 액션)

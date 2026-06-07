# PropAI 혁신 리팩토링 업그레이드 계획 (2026-06-07, 다각도 라이브 검증 종합)

검증 방법: 코드 정적분석 + **라이브 E2E**(www.4t8t.net 로그인 test@4t8t.net, agent-browser localStorage/네트워크 격리) + 디자인/워크플로우 전문 감사 2종(130/131) + 8단계 감사(113).

## ★라이브로 확정한 핵심 결함(근본원인)

### A. baseline 0원 → 금융 0 전파 (3중 결함 연쇄, 라이브 422 재현)
- **A1(SPOF·최근본)**: 부지분석이 **수치 면적/PNU를 컨텍스트에 영속 안 함**(주소만 시드). 복원 시 `siteAnalysis.landAreaSqm=null`. → 모든 다운스트림(설계GFA역산·수지·공사비·금융) 연쇄 0. (`useProjectContextStore.ts:411-419`, `ProjectSiteAnalysisWorkspaceClient` 영속 보강 필요)
- **A2**: 백엔드 baseline이 **`zone_code` 무시**(`zone_type`만 읽음) — 프론트 용도지역 정보 항상 폐기. (`v2_feasibility.py:133,139,158,177`) → `zone_type = req.zone_type or req.zone_code` 폴백.
- **A3**: 면적 0 + 약식주소("서울"≠"서울특별시"+번지누락) 지오코딩 실패 → 백엔드 422 → `runBaseline` catch가 **사일런트**(result=null). (`use-feasibility-v2-store.ts:228-234`) → 422를 "면적/정확주소 입력" 게이트로 승격.
- 라이브 대조: 약식주소 land_area 0 → **422**; 완전주소("서울특별시 강남구 역삼동 736") → **200, total_cost 579억**. 차단 아님(서버=한국IP), 주소정규화 문제.
- 금융 0은 수지 0의 종속 — 수지 고치면 동반 해소(`DevelopmentFinancePanel` totalCostWon 게이트).

### B. 가이디드 UX 죽음 (디자인 P0)
- **진행레일(LifecycleProgressRail)·NextStageCta가 라이브에서 미렌더** — `propai-project-context.projectId=null`에 게이트되는데 바인딩 타이밍/일부 진입경로서 null. (LifecycleNavigator는 props라 정상) → 레일/CTA에 **props projectId 폴백** + ProjectContextBinder 바인딩 레이스 점검.

### C. 완성도 모델 거짓 신뢰도
- `siteDone = address 존재`만으로 true → 면적0·baseline0인데 "부지 30% 반영" 표시(모순). (`useProjectContextStore.ts:585`) → 결과/수치 연동 기준으로. 법규·인허가·ESG 미포함(4단계만) → 6단계 확장.

## ★다각도 발견 종합

### 디자인 일관성 (130)
- 토큰체계·다크보정은 견고하나 **토큰 우회 하드코딩 수백건**(text-slate-900 30건 등 다크대비 붕괴), ModulePlaceholder 인디고 하드코딩, 페이지별 모션/여백 편차(cost 10줄 표준이탈, feasibility 과한 Hero).

### 버튼명/용어 (130)
- "분석 실행" 4종 혼재(부지분석실행/AI심층분석실행/가상준공생성/환경분석), 상단탭"입지 분석"↔진행레일"부지분석" 불일치, 단계수 6/8/10 혼재, 개발자용어 노출(raw UUID·PROP/ko/실연동·INTELLIGENCE INPUT 영문). → 용어 표준사전 수립.

### 워크플로우/연결성 (131)
- 강점: stale 자동재계산 인프라(MODULE_UPSTREAM·isStale·stamp)·입력 자동시드·프로젝트별 스냅샷 — 코드상 완결.
- 약점: ①시드 원천(부지 수치) 비면 전구간 0(SPOF) ②isStale "최초1회 제외"가 늦게 채워진 업스트림의 자동 캐스케이드 차단 ③수지(FeasibilityEditorV2) vs ROI(InvestmentFeasibilityClient) **두 수지화면 병존**(둘 다 /v2/feasibility/calculate) ④완성도에 법규/인허가/ESG 누락.

## ★혁신 리팩토링 로드맵 (우선순위)

### Phase 0 — 출혈차단 (즉시·저리스크·최고임팩트)
1. **부지분석 수치(면적/PNU/공시지가/용도) 컨텍스트 영속**(A1) — baseline·전 단계 0 근본해소.
2. **baseline zone_code/zone_type 폴백**(A2) + **약식주소 시도명 정규화**(서울→서울특별시) 지오코딩 성공률↑.
3. **422 graceful 게이트**(A3) — 빈 0 대신 "부지면적/정확주소 입력" 액션 카드, 입력탭 포커스.
4. **진행레일·NextStageCta projectId props 폴백**(B) — 가이디드 UX 복구.
5. **완성도 모델 결과연동**(C) — 거짓 30% 제거.
6. **라벨 표준화** — 분석실행 용어통일·입지/부지 통일·개발자용어 숨김.

### Phase 1 — 단일 데이터 척추(Spine)
- 부지 수치를 워크플로우 SSOT 단일출처로 승격(모든 단계 입력은 spine 역산). 면적 없으면 단일 입력게이트(무목업).
- 완성도 6단계 확장(부지/법규/설계/공사비/금융/인허가·ESG 반영).
- 디자인 하드코딩 토큰화(다크대비), 페이지 모션/여백 표준화.

### Phase 2 — 자동 캐스케이드 완결
- isStale "최초1회 제외"를 업스트림 신규충족시 다운스트림 최초 자동산출 허용으로 보강(값-동일성 가드). baseline 면적변경시 재시도(baselineTriedRef 리셋).

### Phase 3 — 구조 통합·혁신 UX
- 수지/ROI 단일엔진·단일스토어 통합(analytics=읽기뷰). 기기간 동기화에 면적 포함.
- 혁신 UX: 단계별 완성도 게이지·프로젝트 헬스보드(대시보드 요약)·AI 인사이트 인라인 노출·컨텍스트 칩바(주소/용도/면적 상단 고정)·가이디드 next-action.

## 비고
- Phase 0가 "수지/금융 자동 정교화가 라이브에서 실제로 숫자를 채우게" 만드는 핵심(현재 UI는 떠도 값 0). 저리스크·반나절급 다수.
- 무목업 원칙: 면적 없으면 추정생성 금지(입력 게이트), baseline 추정은 "시장표준" 라벨 유지.
- 산출 근거: 130(디자인/UX), 131(워크플로우/근본원인), 113(8단계), 라이브 E2E.

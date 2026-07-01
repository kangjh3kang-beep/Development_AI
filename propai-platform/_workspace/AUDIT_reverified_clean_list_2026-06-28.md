# 발굴 감사 재정밀화 — 실행 정본 리스트(코드정독 재검증·2026-06-28)

4축 재검증이 실코드와 일치함을 확인했다(c2r/mass-templates GET 프론트 호출 0건, asset-ops 주석 블록 명시, 브랜치 diff 일치). 다음은 정본 종합 리스트다.

---

# PropAI 4축 재검증 종합 — 실행 정본 리스트

읽기전용 코드정독 재검증 결과. 앞선 grep 추정 감사를 정정한 **다음 실행의 정본**.

## 1. 정정 요약 — 앞선 감사 대비 뒤집힌 판정

| 항목 | 앞선(grep) 판정 | 재검증(정독) 판정 | 정정 사유 (실코드 근거) |
|------|----------------|------------------|------------------------|
| **UnitMixOptimizerPanel** | "S노력 배선 가능" | **MOCK-차단** | line 155-180 하드코딩 평형·가격, line 154 setTimeout 가짜지연, apiClient 호출 0줄 → 백엔드 미존재 |
| **design-audit** | "고아" | **이미배선** | `/design-audit` 전용 워크스페이스 + extract-brief/run-upload/pdf 동적 호출 확인 |
| **ConversationalMarketPanel** | 미배선 의심 | **이미배선** | line 344 `apiClient.post(/zoning/nearby-map)`, `useMock:false` 명시 |
| **CarbonEmissionsWorkspaceClient** | 미배선 의심 | **이미배선** | line 166/209 `/esg/epd/*` 실호출, EPD Korea DB 실값만 |
| **ParkingLogView** | 고아 의심 | **이미배선** | line 19 `/parking/dashboard` 실호출 + 15초 폴링 |
| **/guide 라우트** | 고아라우트 | **거짓양성** | dashboard/page.tsx 2곳 하드링크 진입, nav 미등록은 IA 정상 |
| **/cost·/boq-auto·/g2b·/analysis-ledger·/deliberation** | 소비처불명/고아 | **이미배선** | 동적 URL(`${projectId}`,`${id}`) 호출이 grep 정적검색에 누락됐던 것 |
| **mass-templates** | 전체 고아 | **부분배선** | seed-design은 호출, GET 조회만 미사용 |

**핵심 교훈**: grep 오판의 주범은 (a) **동적 템플릿 URL**(`/cost/${projectId}/...`) 정적 미탐, (b) **로컬 계산을 "배선"으로 오인**(UnitMix). 동적 URL은 "이미배선"으로 구제됐고, 로컬 목업은 "차단"으로 강등됐다.

---

## 2. ★실행 리스트 — [CLEAN-무목업-즉효] 최종 확정

가치(高/中/低) × 노력(S/M/L) 랭크. **여기 오른 항목만** 다음 실행 후보다.

| # | 항목 | 가치×노력 | 무엇을·어디에 | 어떻게 반영 | 왜 클린(근거) |
|---|------|-----------|---------------|-------------|---------------|
| **C1** | **feat/mass-template-db 머지** | **高 × S** | 브랜치(3파일 234+), `mass_templates` 라우터 + schema_guard 부팅배선 | main에 머지. 부팅 DDL 멱등이므로 별도 마이그레이션 불요 | 순수 신규 라우터·기존코드 미터치·제로 충돌·테스트 5건 완결·정직성(무자료=null) |
| **C2** | **fix/multiparcel-ordinance-legallink 머지** | **中 × S** | 브랜치(2파일 34+), `llm_provider.py` + `requirements.txt` | main에 머지. Gemini 프로바이더 추가만 | 순수 확장·anthropic/openai 무손상·`_provider_package_available` 가드로 반쪽출하 방지 |
| **C3** | **PermitsWorkspaceClient 삭제** | **中 × S** | `apps/web/components/operations/PermitsWorkspaceClient.tsx`(396줄) | 파일 삭제 | permits/page.tsx 주석에 "레거시…제거" 명시 + 대체재 PermitAiWorkspaceClient 운영중 + 소비처 0 |
| **C4** | **ApprovalsWorkspaceClient 삭제** | **中 × S** | `apps/web/components/operations/ApprovalsWorkspaceClient.tsx`(509줄) | 파일 삭제 | 소비처 0·approval 기능은 OperationsIntelligence가 처리. (단, C3보다 명시성 약함 — 잔여불확실 참조) |
| **C5** | **EscrowCard 정리** | **低 × S** | `apps/web/components/.../EscrowCard.tsx`(145줄), import `@/mocks/module-data` | 삭제 또는 실 백엔드 연결 후 재배선 | type만 import·`<EscrowCard` 사용처 0·목업 데이터 의존 → 무목업 위반 |
| **C6** | **JeonseRiskCard 정리** | **低 × S** | `apps/web/components/.../JeonseRiskCard.tsx`(87줄), import `@/mocks/module-data` | 삭제 또는 실 백엔드 연결 후 재배선 | type만 import·사용처 0·목업 의존 → 무목업 위반 |
| **C7** | **mass-templates GET 조회 배선** | **中 × M** | 백엔드 `GET /mass-templates` 존재, 프론트 호출 0 | SeedDesign 흐름에 마스터 조회 추가 또는 관리자 뷰 신설 | 실 백엔드 멀쩡·프론트만 미배선(진짜 미배선)·C1 머지 후 데이터 채워지면 가치 상승 |

**랭킹 결론**: 즉효 1순위는 **C1·C2(머지)** — 제로 충돌·테스트 완결로 ROI 최고. 정리(C3~C6)는 무목업 위반 청산으로 코드 위생 ↑. C7은 신규 배선 작업(M)이라 후순위.

---

## 3. 차단/보류 목록 — ★반영 금지/주의 (되살리거나 배선 금지)

### [MOCK-차단] — 배선하지 말 것 (백엔드 부재, 순수 로컬 목업)
| 항목 | 근거 | 처리 원칙 |
|------|------|-----------|
| **UnitMixOptimizerPanel** | line 154 setTimeout 가짜지연, line 155-180 하드코딩 평형/가격/그리디, apiClient 0줄 | 실 백엔드 엔드포인트 **정의·구현 선행** 없이는 배선 금지. 현 상태 배선=목업 출하 |
| **SafetyWorkspaceClient** | line 235-299 전부 로컬계산, line 240/271 가짜지연, apiClient 0줄 | 동일. 안전/재해 평가는 백엔드 공식 필요 |
| **GenerativePanel** | line 47-58 setTimeout 가짜생성, "IFC 매스"는 텍스트 표기만, AI 호출 0 | 명칭과 달리 AI 무. 실 생성엔진 연결 전 배선 금지 |
| **EscrowCard / JeonseRiskCard** | `@/mocks/module-data` 타입 의존 | C5/C6에서 삭제 우선. **목업 데이터로 살리지 말 것** |

### [의도적보류] — ★건드리지 말 것 (의도적 숨김, 복원 금지)
| 항목 | 근거 |
|------|------|
| **asset-ops 4라우트** (digital-twin/maintenance/tenant/operations-lease) | nav-config.tsx **line 117-130 주석 블록 명시**: "준공 후 운영 단계…코어와 단절·미성숙해 숨긴다. 라우트·컴포넌트 보존, assetOpsOnly 게이팅 유지." 복원=의도 위반 |
| **TenantWorkspaceClient / LeaseOpsWorkspace / OperationsIntelligenceWorkspaceClient** | 위 4라우트가 실제 마운트·렌더 중. asset-ops 세트와 일관. nav 주석 해제 시 자동 복원됨 |

### [충돌위험] — ★직렬 머지·조율 필수 (단독 머지 금지)
| 브랜치 쌍 | 충돌 파일 | 주의 |
|-----------|----------|------|
| **feat/memory-hub-loop**(214파일) ↔ **fix/land-tools-multiparcel-responsive**(9파일) | `registry.py`(_map_permit_response 양쪽 재설계), `test_deliberation.py` | 둘 다 실작업·비목업이나 **동일파일 깊은 겹침**. 한쪽 rebase 또는 3-way merge 협의 후에만 머지. **C1/C2와 별개 트랙** |

### [삭제대상] — C3/C4에서 처리 (되살리기 금지)
PermitsWorkspaceClient, ApprovalsWorkspaceClient (위 실행리스트 C3/C4 = 동일 항목)

---

## 4. 권고 실행순서 — 확정 CLEAN 톱5

각 단계 게이트: **리뷰≥9.5 · tsc/eslint/lint · 라이브검증 · 무목업 확인**

1. **C1 feat/mass-template-db 머지** — 무의존·최단경로·제로충돌. 게이트: 머지 후 부팅 schema_guard DDL 멱등 라이브확인 + GET 응답 검증.
2. **C2 fix/multiparcel-ordinance-legallink 머지** — 독립·경량. 게이트: `langchain-google-genai` 설치 후 드롭다운 노출/미설치 시 드롭 가드 라이브확인.
3. **C3 PermitsWorkspaceClient 삭제** — 명시적 삭제대상. 게이트: 삭제 후 `tsc`/빌드 그린 + permits 페이지 라이브 정상(PermitAiWorkspaceClient 동작).
4. **C5+C6 EscrowCard·JeonseRiskCard 삭제** — 무목업 청산. 게이트: 삭제 후 빌드 그린 + `@/mocks/module-data` 잔여 참조 0 확인.
5. **C7 mass-templates GET 조회 배선** — C1 머지 후 데이터 존재 시 착수. 게이트: 실 데이터 렌더 라이브검증 + 무자료=정직표기 확인.

> C4(ApprovalsWorkspaceClient)는 명시성 부족으로 톱5 대신 잔여불확실로 강등(아래 참조).

---

## 5. 잔여 불확실 — ★착수 전 개별 확인

| 항목 | 불확실 이유 | 착수 전 확인할 것 |
|------|-------------|-------------------|
| **C4 ApprovalsWorkspaceClient 삭제** | C3와 달리 코드 내 "삭제·중복" **명시 주석 없음**. "쌍이므로 삭제" 추론. approval 기능을 OperationsIntelligence가 **완전 대체하는지** 미확정 | OperationsIntelligenceWorkspaceClient가 approval 워크플로우를 실제 커버하는지 grep+정독 후 삭제 |
| **ParkingLogView 소비처** | 실 엔드포인트 호출 확정이나 **타 화면 import는 테스트 mock만** 존재. 어느 페이지가 렌더하는지 미확정 | `<ParkingLogView` 렌더 페이지 추적. 없으면 "이미배선이나 미마운트"로 재분류 |
| **mass-templates GET 활성화 여부** | 조회 엔드포인트 가치가 마스터 데이터 적재량에 의존. 빈 테이블이면 배선 무의미 | C1 머지 후 `GET /mass-templates` 실 응답 건수 확인 → 0건이면 C7 보류 |
| **충돌위험 2브랜치 의도 중복** | 양쪽 `_map_permit_response` 재설계가 **의도적 중복인지 분기인지** 미확정 | 두 브랜치 `registry.py` diff 라인단위 비교 → 동일의도면 한쪽 폐기, 분기면 3-way |

---

**참조 (실코드 근거)**:
- `propai-platform/apps/web/components/layout/nav-config.tsx:117-130` — asset-ops 의도적 숨김 주석 블록 (재검증 확인)
- `apps/web` 전역 grep — `c2r/*` 프론트 호출 **0건**, `mass-templates` GET **0건** (재검증 확인)
- 브랜치 diff — `mass-template-db`=3파일 신규, `ordinance-legallink`=2파일 확장 (재검증 확인)
- UnitMixOptimizerPanel line 154-180 / SafetyWorkspaceClient line 235-299 / GenerativePanel line 47-58 — 로컬 목업 확정 (verify:components 정독)

이 리스트가 다음 실행의 정본이다. CLEAN 7항목 중 **C1·C2 머지가 최고 ROI 즉효**, 차단/보류 항목은 절대 배선·복원 금지.
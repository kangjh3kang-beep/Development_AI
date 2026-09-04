# 적산관리시스템 구현계획 — 국토부 고시 기본참조·시니어 배치·절감/예측 분석

작성: 2026-07-10 · 기준: origin/main e30acb9f · 3원 병렬 실측(자산배선·공공데이터·시니어/예측) 근거 기반
원칙: 그린필드 금지(전 부품 기존자산 재사용·부재는 "조립·배선") · 무목업 · 정직강등 · use_llm 옵트인(미설정 무료)

---

## 0. 진단 요약 (실측 확정)

### 0-1. "적산 메뉴 소실" 전제 정정
- 메뉴는 삭제가 아니라 **IA 리팩토링(800e7477)에서 `lib/navigation/route-registry.ts`로 이관**됨. 현존 진입점 2개:
  - `route-registry.ts:192-201` 프로젝트>사업성 분석>**공사비 분석**(/analytics/cost)
  - `route-registry.ts:356-365` 설계 센터>**3D 모델·공사물량**(/bim-studio) — 구 라벨의 "(BIM·적산)" 접미 탈락
- 체감 소실의 진짜 원인: ①내비 어디에도 "적산" 워딩 부재 ②**가장 완성된 공내역서 워크플로우 UI 2페이지가 완전 orphan**:
  - `/projects/[id]/boq`(BoqAutoWorkspace — 마스터→드래프트→단가결합→XLSX→costData) + 백엔드 `/boq-auto/*` 8엔드포인트 동반 매몰
  - `/projects/[id]/cost`(BimCostDashboard 단독·링크 0)

### 0-2. 4대 구조 결함 (file:line 실측)
| # | 결함 | 증거 |
|---|---|---|
| D1 | **BIM 실측물량 기록경로 미배선**: bim_quantities 기록은 `/bim/analyze`(routers/bim.py:36)뿐인데 프론트 호출 0. `/bim/generate-ifc`(프론트 호출 O)는 Design 테이블만 기록(bim_ifc_service.py:421-440) → D3 origin-cost(cost.py:319)·N2 BIM병합이 라이브에서 항상 no_bim_quantities | dead-path |
| D2 | **BOQ UI 2페이지 완전 orphan** + `/cost/estimate/{id}·/estimates` 조회 소비 0(영속 BOQ 재열람 불가) + cost-intelligence↔ConstructionCostWorkspaceClient 이중 orphan + quantity_takeoffs dead 테이블 | 배선단선 |
| D3 | **단가 전원 내장 상수/시드 — 외부 실단가 소스 0**: ₩/㎡ 하드코딩(construction_cost_engine.py:19-27), material_unit_prices 시드 42(라벨만 '표준품셈2025'), KCCI '시장가'는 `from math import sin` 결정론 시뮬(kcci_material_price_service.py — 실 API 아님), actual=null | 데이터층 부재 |
| D4 | **공종분류 4중 파편**: A 숫자8공종(01~08) / B IFC코드(A01~C01) / C 실적공내역서 5공종·414섹션 / D 화면분해(지상/지하/조경/간접) — 브리지는 수작업 부분매핑 3곳뿐, 정합 SSOT 없음 | 표준 부재 |

### 0-3. 잔존 오점(전파방지 대상)
- `routers/cost.py:551(calculate)`·`:774(boq)` — **use_llm 게이트·quota 없이 CostInterpreter 무조건 호출**(무과금 원칙 위배 잔존 패턴)
- `/cost/{pid}/export-excel`(cost.py:925) — 고정 샘플 3항목 하드코딩(목업성)
- BimCostDashboard.tsx:73-88 — 프론트 근사 역산 물량+하드코딩 단가 2항목

### 0-4. 강점(재사용 코어 — 재구현 금지)
- 공용 코어 3종: `standard_quantity_estimator`(유형별 원단위×연면적→8공종) · `origin_cost_calculator`(12단계 법정요율 체인) · `unit_price_repository`(DB→폴백 SSOT·price_source 출처표기)
- **설계변경 delta 정답 기준선**: `POST /cost/{id}/alternatives`(cost.py:850) — base vs variants BOQ 재산정→delta·delta_pct·affected_work_types
- `cost_monte_carlo.RISK["design_chg"]=(0,0.05,0.15)` 설계변경 밴드 · EVM 기성(D2) · `boq_master`(실적 3,997항목·n=1) · `boq_parametric_engine`
- VE 서술 전담 `CostInterpreter`(ve_suggestions·material_advice·schedule_impact) · 시공 페르소나 `_run_constructor` 골격
- 시나리오 일괄전개 선례 `deliberation/scenario_matrix.py`(PR#200) · 유휴 `SeniorNarratorInterpreter`(호출처 0 — 소생 후보)
- ★시니어 9종에 **시공/적산 도메인 없음**(orchestrator DOMAIN_ROUTES에 cost 키 부재) · cost SpecialistAgent는 고아+상수×면적+interpreter=None

---

## 1. 공공 단가 데이터층 실사 결론 (국토부 고시 기본참조)

| 소스 | 판정 | 연동법 |
|---|---|---|
| **조달청 표준시장단가·가격정보**(data.go.kr API 15129415, 반기갱신, 무료) | ★즉시 API 연동 | `g2b_client.py` serviceKey 패턴 복제(루트 .env·더미키 shadowing 주의) |
| **KOSIS 건설공사비지수**(orgId=397, tblId=DT_39701_A003, 월별) | ★즉시 API 연동 | KOSIS_API_KEY 기존 보유·`ecos_service.py` refresh→캐시→graceful 패턴 이식. 전 단가의 **시점보정 계수** |
| **기본형건축비 고시**(연2회 3/1·9/15, 최신 2026.3 ㎡당 222만원[16~25층·60~85㎡ 지상층]) | 수동 시드+DRF 개정감지 | 층수×면적 매트릭스 시드(연2회) + `gosi_search_service.py` DRF admrul 패턴으로 개정 자동감지 → `seeds/sales_dev_profiles.py:4`의 regulation_change_log 계약 재사용. **주택 적산총액의 법정 기준선**(분양가상한제 sanity check) |
| 조달청 유형별공사비(공공건축 15유형 ㎡당·연1회)·행안부 건물신축가격기준액 | 수동 시드 | 비주택 ㎡당 총액 기준선 |
| 표준품셈(CODIL PDF)·LH 적산기준 | 후순위(파서 ROI 낮음·품→단가 변환에 노임 결합 필요) | 핵심 공종만 시드 유지(현행 42종 확장) |
| 한국부동산원 건물신축단가표 | 부적합(유료·저작권) | 대안: 행안부 기준액 |

**단가 4계층 리졸버(신설 대상)**: T1 공공고시(조달청 API+지수보정+고시시드) → T2 material_unit_prices(품셈 시드) → T3 내장 fallback(UNIT_PRICES_2026) → actual(실적, null 정직). 전 항목 `{value, price_source, basis_date, legal_link, confidence}` evidence 계약. **스키마 신설 불필요 — material_unit_prices에 price_source 라벨로 행 주입**이 정답.

---

## 2. 목표 아키텍처 — 적산관리 파이프라인 (설계·BIM 없이도 완주)

★사용자 요구 핵심: "3D BIM·설계와 관계없이 통상 공사비(국토부 고시) 세부내역을 적산리스트로 산정"

```
S0 기준정보     프로젝트 컨텍스트(용도·연면적·층수·구조) — 설계 없으면 수동입력/컨텍스트 프리필
      │
S1 물량(QTO)    3계층 정직배지(기존 qto_source 계약 확장):
      │           L1 표준원단위(standard_quantity_estimator) ← 설계 무관·항상 가능(±12%)
      │           L2 기하 직산(geometry_qto) ← 매스 있으면(±8%)
      │           L3 BIM 실측(bim_quantities) ← IFC 있으면(±5%) ※D1 배선 소생 후
      │
S2 단가         4계층 리졸버(T1 공공고시→T2 품셈시드→T3 내장→actual) + KOSIS 지수 시점보정
      │           전 항목 evidence{value·source·date·link·confidence}
      │
S3 적산리스트    표준 공종분류 SSOT(대공종 12: 가설/토공/지정·기초/골조/조적·미장/방수/창호·유리/
      │           마감/지붕/설비(기계·전기·통신)/부대·조경/간접) + 기존 4체계 브리지 매핑
      │           → boq_builder(3중단가)+origin_cost_calculator(12단계 법정요율)
      │           + 기본형건축비 ㎡당 기준선 대비 편차 sanity check(주택)
      │
S4 시니어 분석   (신설) 적산 시니어(QS): 정량 evaluator — ㎡당 vs 고시기준선 편차·간접비율·
      │           contingency·단가출처 신뢰도·공종구성비 이상 → PASS/WARN/BLOCK+basis+tradeoff
      │           절감방안: 변형후보(구조/층수/마감 프리셋×massing_strategy) × /cost/alternatives
      │                     delta 결정론 랭킹 → Top-N 절감액(원) + CostInterpreter VE 서술(옵트인)
      │           예측공사비: design_change_predictor(변경원인 룰) → 시나리오 일괄 전개
      │                     (scenario_matrix 패턴·≤12) → 항목별 추가/삭제 delta + MC design_chg 밴드(p10/50/90)
      │
S5 산출·연동     costData→수지(v2 feasibility)·통합보고서 엔진(PDF/PPTX/DOCX 어댑터)·원장 cite·G2B 정합
```

### UI 워크플로우 (가독성·직관 — 기존 단계형 셸 재사용)
- **적산관리 허브 = /analytics/cost 확장**(신규 페이지 아님): 5-스텝 스텝퍼 ①기준정보 ②물량(3계층 배지) ③적산리스트(공종 트리+단가출처 칩) ④AI 분석(시니어 verdict 카드·절감 Top-N·변경 시나리오 비교표) ⑤보고서·수지반영
- 내비: "공사비 분석"→**"적산·공사비 관리"** 개칭(적산 워딩 복원). `/projects/[id]/boq`(BoqAutoWorkspace)를 허브 3스텝 "상세 공내역서(실적기반)" 탭으로 흡수 + route-registry 등록. `/projects/[id]/cost`는 허브로 리다이렉트 후 폐기(중복 제거)
- 표준 컴포넌트 재사용: UseLlmToggle·SeniorVerdictCard·EvidencePanel(단가 출처)·QtoBreakdown

---

## 3. 구현 로드맵 (P0~P5 · 각 단계 9.5게이트+라이브검증)

### P0 — 배선 소생·오점 수선 (1~2일 · 코드 소규모)
1. `/bim/generate-ifc` 성공 시 `_persist_bim_quantities` 호출 배선 → D3(origin-cost)·N2(BIM병합) 소생 [D1]
2. route-registry에 boq 항목 등록+내비 개칭("적산·공사비 관리") · `/projects/[id]/cost` 리다이렉트 [D2]
3. CostInterpreter 무게이트 2경로(cost.py:551·:774)에 use_llm 옵트인+quota 게이트(personas.py 선례) — ★전역스윕 포함 [오점]
4. export-excel 샘플 하드코딩→실 BOQ 데이터(cost_estimate_repository) [오점]
5. BimCostDashboard 프론트 근사물량→estimate-overview 소비로 교체 [오점]
6. `/cost/{pid}/estimates` 조회 UI(허브 3스텝 "저장된 적산" 목록) [D2]
- 검증: bim-quantities/origin-cost 200(no_bim_quantities 소멸)·boq 페이지 내비 도달·use_llm=false 시 LLM 0호출

### P1 — 국토부 기본참조 데이터층 (2~3일)
1. `public_cost_client.py` 신설(조달청 가격정보 API·g2b_client 패턴) → material_unit_prices 행 주입 잡(price_source="표준시장단가 2026상"+링크)
2. KOSIS 공사비지수 서비스(ecos_service 패턴·월별 캐시) → 단가 시점보정 계수 `escalate(base_date→today)`
3. 기본형건축비 매트릭스 시드(층수×면적·2026.3 고시)+DRF admrul 개정감지 잡 → regulation_change_log 계약
4. 단가 4계층 리졸버 `unit_price_repository` 확장(T1 우선순위+evidence 계약) — 소비처(estimator·boq_builder·estimate-overview) 자동 추종
5. kcci sin-시뮬 정직화: KOSIS 지수 기반으로 대체, 잔존 시 "시뮬레이션" 라벨 명기
- 검증: 조달청 API 실키 커버리지 확인(★미확인 리스크)·지수보정 전후 단가 diff·기본형건축비 ㎡당 편차 카드 라이브

### P2 — 공종분류 SSOT + 적산리스트 완결 (2~3일)
1. `cost/work_breakdown.py` 신설: 대공종 12 SSOT + A(8공종)/B(IFC)/C(실적414섹션)/D(화면) 4체계 브리지 매핑 딕셔너리(누락 코드 정직 unmapped)
2. estimate-overview·boq_builder·BimCostDashboard·QtoBreakdown이 SSOT 경유 표시(기존 응답 계약 additive)
3. BoqAutoWorkspace를 허브 탭 흡수+마스터 n=1 한계 정직 배지("실적 1건 기반 참고치")
- 검증: 4체계 왕복 매핑 테스트·미가격 공종(기계/전기/마감) 단가 커버리지 확대 확인

### P3 — 적산 시니어 에이전트 (2~3일)
1. `senior_agents/specs/quantity_surveyor.py` + `evaluators/qs.py` 신설: 정량 룰(㎡당 vs 기본형건축비/유형별공사비 편차 ±15% WARN·간접비율 역전·contingency 부재·단가 T3폴백 비중>50% WARN·공종구성비 이상치) — DecisionRule 계약(basis verified 링크·tradeoff 필수), 골든<50 junior_assist 정직
2. EVALUATORS+DOMAIN_ROUTES에 '적산/시공/cost' 등록 → `attach_senior_consultation("cost")` 활성
3. 허브 4스텝+수지 플로우에 consultation_hook 배선(무LLM 0원·SeniorVerdictCard)
4. cost SpecialistAgent 고도화: 도구 상수×면적→boq_builder 경유+CostInterpreter 주입(PR#200 market 선례)+allow_llm — decision_brief cost 게이트 경로 활성
- 검증: consult 0.00s 결정론·verdict 실산출(편차 케이스 매트릭스)·quota 0청구

### P4 — 절감·예측 조립 (3~4일)
1. **절감방안**: 변형후보 자동생성기(구조 RC↔철골·층수 ±N·마감등급 3단·지하층수 — massing_strategy·기존 프리셋 재사용) × `/cost/alternatives` 일괄 전개(scenario_matrix 패턴·Semaphore·예산가드) → 절감액(원) Top-N 랭킹+affected_work_types. LLM은 CostInterpreter ve_suggestions 옵트인 서술만
2. **설계변경 예측공사비**: design_change_predictor(원인 룰)→해당 공종 delta 시나리오 자동 구성→alternatives delta(정량 원)+cost_monte_carlo design_chg 밴드(p10/50/90) → "향후 변경 시 추가/삭제 가능 예측공사비" 카드
3. UI: 절감 Top-N 카드(각 항목: 절감액·영향공종·tradeoff)·변경 시나리오 비교표(scenario-matrix FE 패턴)
- 검증: 다경우수 매트릭스(구조2×층수3×마감3=18케이스 캡 12)·delta 부호/합계 정합·무과금 기본

### P5 — 보고서·연동 완결 (1~2일)
1. 통합 보고서 엔진 적산 어댑터(ReportModel — 공종트리 DataTable·단가 evidence·시니어 verdict·절감/예측 섹션) → PDF/PPTX/DOCX
2. costData 스키마에 qto_source·price_tier·기준선편차 additive → 수지·G2B 소비 강화
- 검증: 3포맷 스모크·수지 왕복

**총 규모**: 약 11~17일(레인 병렬 시 단축). P0·P1이 독립 선행 가능(P0는 즉시 착수 권장).

---

## 4. 계약·게이트 준수 체크리스트 (구현 시 필수)
1. 수치는 계층1 결정론 도구에서만 생성(LLM 수치 생성 금지) — specialist/시니어 불변식
2. LLM = use_llm 옵트인(기본 false·무과금)+enforce_llm_quota, 내부 자동플로우 allow_llm=False(PR#200 A5 선례)
3. 시니어 consult = 무LLM 0원·절대 raise 금지·unavailable 정직 강등(consultation_hook 단일 진입)
4. 단가·기준선 전 항목 evidence{value,basis,source,legal_link,confidence} — verified 링크만 클릭화
5. 무날조: 미확보 단가는 T3 폴백 라벨 명기·actual null·boq_master n=1 배지·측정불가 rule 생략
6. 과금 신규 billing_key는 기본 0(미설정 무료)
7. 신규 브랜치는 origin/main 분기+전용 워크트리+coord claim(멀티세션 규약) — 로컬 main 34커밋 stale 주의
8. 캐시 키에 결과를 바꾸는 전 입력 포함(PR#200 zone_name 캐시오염 교훈)

## 5. 리스크·미확인(정직 표기)
- 조달청 가격정보 API의 **건축 공종 실커버리지 미검증**(활용신청 후 실데이터 확인 필요 — P1 첫 게이트)
- 법제처 DRF admrul이 기본형건축비 **별표 수치표**를 반환하는지 미확인(본문만 가능성 높음 → 시드가 안전, 감지는 개정 트리거로만)
- boq_master 실적 1건(의정부동 424 주상복합) — 용도 다양화 전까지 "참고치" 배지 유지
- 표준품셈 PDF 파서는 ROI 낮아 명시적 보류(품→단가 변환에 노임단가 결합 필요)

## 6. 검증 계획(요지)
- 단위: 4계층 리졸버 폴백 매트릭스·공종 브리지 왕복·evaluator 룰 경계
- 시뮬레이션: 용도 5(아파트/오피스텔/상가/물류/오피스)×규모 3×구조 2 = 30케이스 적산 완주(설계 無 조건 포함)·기본형건축비 편차 분포 확인
- 라이브: 허브 5스텝 E2E·절감 Top-N 실델타·예측 밴드·보고서 3포맷·수지 반영 왕복

## 7. 산출물 목록(구현 시)
- BE 신설: public_cost_client.py·kosis_cost_index_service.py·work_breakdown.py·specs/quantity_surveyor.py·evaluators/qs.py·절감/예측 조립 서비스(cost/saving_scenarios.py)
- BE 수정: bim_ifc_service(물량 영속)·unit_price_repository(T1)·registry(_build_cost)·orchestrator(DOMAIN_ROUTES)·cost.py(게이트·export-excel)
- FE: 허브 5스텝 셸·절감/예측 카드·내비 개칭·boq 흡수
- 데이터: material_unit_prices 행 주입·기본형건축비 시드·지수 캐시

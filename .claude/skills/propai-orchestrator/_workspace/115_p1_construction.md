# P1 시공단계 목업→실엔진 재결선 (115)

작업일: 2026-06-07 / 담당 executor: P1 시공
원칙: 무목업·실데이터·라이브검증 / push·배포 금지 / 명시경로만 / import 트랩 git diff 확인

## 대상 파일
- `propai-platform/apps/web/components/construction/CostAndQuantityDashboard.tsx`
- `propai-platform/apps/web/components/construction/ScheduleSupervisionPanel.tsx`
- `propai-platform/apps/api/app/routers/project_dashboard.py`

---

## 1. 물량(CostAndQuantityDashboard) — 실 QTO 엔진 재결선

### 문제(확정)
- 기존: `GET /projects/{id}/bim-takeoff` → 백엔드 project_dashboard.py가 **프로젝트 무관 하드코딩 고정배열**(콘크리트 4520m³, 철골 1200ton 등) 반환. 완전 목업.

### 조치
- 프론트를 **`POST /cost/estimate-overview`(실 QTO 엔진)**으로 재결선. CostEstimationClient(이미 estimate-overview 사용)의 검증된 패턴 그대로 차용.
- 요청을 **useProjectContextStore**(designData·siteAnalysis)로 구성:
  - `building_type`: designData.buildingType → 코드 매핑(mapBuildingType, 한글/임의 대응)
  - `total_gfa_sqm`: designData.totalGfaSqm 우선, 없으면 **부지면적×용적률**(getZoningSpec.floorAreaRatioMax) 폴백
  - `floor_count_above`: designData.floorCount (없으면 15 기본)
  - `floor_count_below`: 2, `structure_type`: "RC", `project_id`: 라우트 id(설계 매스 자동 흡수용)
- 컨텍스트 projectId ≠ 라우트 projectId(미동기) 또는 GFA 0이면 **산출 보류 + 정직 빈상태 안내**(무목업).

### estimate-overview 요청/응답 매핑 (cost.py 정합)
요청(OverviewCostRequest): `{building_type, total_gfa_sqm, floor_count_above, floor_count_below, structure_type, project_id}`
응답 사용 필드:
- `items[]` (= items_qto): `{name, spec, unit, quantity, unit_cost_won, cost_won}` → 표 행에 직접 매핑
  - 표 컬럼: 공종(name) / 규격(spec) / 단위(unit) / 수량(quantity) / 단가(unit_cost_won) / 합계(cost_won)
  - 합계 = Σ cost_won
- `qto_source` ("bim"|"derived") → 배지: BIM 매스 실치수 vs 건축개요 역산(추정) 정직 표기

---

## 2. 공정(ScheduleSupervisionPanel) — 실엔진 부재 → 결정론적 추정

### 실 공정엔진 조사 결과 (grep schedule/공정/gantt)
- **건설 공정(Gantt) 엔진 없음.** 존재하는 것:
  - `supervision_service.py`: EVM(PMBOK, SV/CV/SPI/CPI)·사진진척 — 공정관리 지표일 뿐 Gantt 생성 아님
  - `lifecycle.py /lifecycle-opt/replacement-schedule`: 유지보수 교체주기(LCC) — 시공공정 무관
- 기존 백엔드: 4개 **고정 task**(Site Preparation/Earthworks/Core Structure/MEP) 반환. 목업.

### 조치 — 결정론적 공정 추정(`_estimate_schedule`, project_dashboard.py)
실데이터(연면적·지상/지하층수)로 표준공기 산정:
- 총공기(월) = 6 + 지상층×0.55 + 지하층×1.0 + (연면적 30,000㎡ 초과분 / 10,000㎡)당 +1, clamp 6~60개월
- 공종 비중(총공기 대비, 합 100%): 착공·가설8 / 토공·흙막이14 / 기초·지하18 / 지상골조32 / 외장·창호12 / MEP10 / 마감·준공6
- **지하 0층이면** 공종 순서·비중 변동(흙막이→토공·정지, 기초·지하→기초공사, 골조 비중↑38)
- 각 task: `{task, start("Month N"), dur_months, dur(% 막대폭), complete}`
- 응답에 `estimated: true`, `total_months`, `method`("결정론적 표준공기 추정…") 포함
- 프론트: **"추정(표준공기 기반)" 배지 + 총 예상 공기 + 공종별 start/개월** 정직 표기. 간트 막대는 누적시작%로 순차 배치.
- **제거**: 가짜 감리 로그(기초 철근 배근/콘크리트 타설/안전망 — 고정 상태·시간), 가짜 AI 지시사항("C동 4층 슬라브…"). → 공종별 공기 분배(실 추정값)·산출 방식 표기로 대체.

---

## 3. bim-takeoff 목업 정리
- 사용처(grep): `CostAndQuantityDashboard.tsx`(재결선으로 더 이상 미사용), `mocks/handlers.ts`(MSW dev 목업, GET).
- 백엔드 `GET /projects/{id}/bim-takeoff`도 **목업 제거** → 실 엔진으로 재구현:
  - 프로젝트(연면적·유형) + 최신 design_versions(매스·층수)에서 건축개요 구성(`_resolve_overview`) → `estimate_overview()` 직접 호출 → items_qto 반환.
  - 건축개요 미확정 시 `status:"no_data"` + 빈 items(무목업 정직).
- MSW handlers.ts의 bim-takeoff GET 목업은 dev 전용·프론트는 `useMock:false`로 항상 라이브 → 무해, 미수정(다른 컴포넌트 영향 회피).

---

## 라이브 검증 (apps/api/.venv)
실엔진 직접 호출로 비-0·프로젝트별 변별 확인(백엔드 컨테이너 부재, 순수 엔진 검증):

**QTO(StandardQuantityEstimator, estimate-overview items 원천)**
- Project A(GFA 10,000/15F/2B): 레미콘 4,687m³ … 합계 **50.2억** (8개 항목 전부 비-0)
- Project B(GFA 30,000/25F/3B): 레미콘 15,812m³ … 합계 **161.9억**
- non-zero ✔ / 변별(A≠B) ✔

**공정(_estimate_schedule)**
- A(10000/15F/2B)=**16.2개월**, B(30000/25F/3B)=**22.8개월**, C(5000/5F/0B)=**8.8개월** → 3개 모두 상이 ✔
- 비중 합 100%(A·C) ✔ / 지하없음(C) 공종순서 변동(토공·정지) ✔ / building_type 매핑(오피스텔/아파트/지식산업) ✔

## 정적 검증
- 백엔드: `python -m py_compile` OK, AST OK
- 프론트: `npx tsc --noEmit` — 내 2개 파일 **에러 0**(전체 EXIT 2는 permit/page.tsx, 인허가 담당 executor 파일로 본 작업 무관)
- import 보존(git diff 확인): apiClient·useProjectContextStore·getZoningSpec·formatCurrencyKRW·motion 전부 사용 ✔
- 신규 의존성 0 ✔ / 디버그코드(TODO/HACK/debugger/console.log) 없음(console.error만, 의도적 에러로깅)

## 미진/후속
- 실 공정관리(Gantt) 엔진 미존재 → 결정론 추정으로 대체(정직 라벨). 향후 CPM/공정 DB 도입 시 `_estimate_schedule`을 실엔진으로 교체 가능(인터페이스 동일: tasks/total_months/method/estimated).
- estimate-overview의 `floor_count_below`는 프론트·백엔드 모두 기본 2(프론트)/0(백엔드 design_versions 미보유 시) — 설계에 지하층수 필드 생기면 연동 강화 여지.
- MSW bim-takeoff GET 목업(dev 전용) 잔존 — 라이브 모드 무영향이라 미정리.

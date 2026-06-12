# BOQ 자동화(공내역서 마스터 기반 적산) — 아키텍처·연동 설계

작성: 2026-06-12 (WP B4) · 상태: B4(파이프라인 hint 배선) 완료, B1~B3·B5는 병렬 작업분(본 문서 작성 시점 워크트리 미병합 — 계약 기준으로 기술)

근거 데이터: 실무 공내역서 1건 — 의정부동 424 주상복합 신축공사, 연면적 238,504㎡,
5공종(건축/기계소방/전기통신소방/조경/토목), 3,997 고유항목 · 414 섹션
(`apps/api/app/services/cost/data/boq_master/_meta.json`: 건축 961 · 기계소방 1,741 ·
전기통신소방 1,029 · 조경 58 · 토목 208 항목, 섹션 126+99+114+4+71=414).

---

## (a) 아키텍처 — 데이터 흐름

```
[실무 공내역서 .xls/.xlsx (D:\…\적산_공내역서, 단가 빈칸·물량 채움)]
        │  ① 추출(오프라인 1회, 결정론·원본 수치 무가공)
        ▼
scripts/extract_boq_master.py            … apps/api/scripts/extract_boq_master.py:1-29
        │  (품명,규격,단위) 중복 합산 → 결정론 정렬 JSON
        ▼
마스터 JSON (정적 자산, 레포 내장)
  app/services/cost/data/boq_master/{architecture,mechanical,electrical,
  landscape,civil}.json + _meta.json
  item = {id, section_code, section_name, name, spec, unit, qty_sample,
          row_count, ref_mat_price?(전기만)} / project = {gfa_sqm:238504, sample_count:1, provenance}
        │  ② 로드·인덱싱
        ▼
[B1] 레지스트리 — 마스터 JSON 단일출처 로더(분야·섹션·항목 조회)
        │  ③ 파라메트릭 스케일링(결정론: qty_sample × target_gfa/238,504 원단위)
        ▼
[B2] 파라메트릭 엔진 boq_parametric_engine.generate_draft(gfa_sqm=…)
        │                                  │
        │ ④ REST 노출                      │ ⑦ 파이프라인 힌트(B4, 본 WP)
        ▼                                  ▼
[B3] API /api/v1/boq-auto/draft     ProjectPipeline._run_cost 말미
        │  ⑤ 프론트 렌더                    _attach_boq_draft_hint(...)
        ▼                                  … app/services/pipeline/project_pipeline.py:1529,1532-1594
[B5] 프론트 BOQ 초안 화면                   → stage data에 additive 키 "boq_draft_hint"
        │  ⑥ 수지 연동(apply-cost)            {disciplines: {분야: item_count}, item_total,
        ▼                                      badges[], detail: "상세는 /api/v1/boq-auto/draft"}
SSOT costData(source:"boq") 1방향 주입
  … apps/web/components/cost/BoqDetailTable.tsx:115-133 (updateCostData, source:"boq" — :130)
  … apps/web/store/useProjectContextStore.ts:117 (CostData.source: overview | bim | boq)
        ▼
수지분석(feasibility) 재계산 — 스테일니스 규칙이 자동 전파 (아래 (b))
```

기존 적산 자산과의 관계(무수정 재사용): `_run_cost`는 종전대로
`StandardQuantityEstimator.estimate`(project_pipeline.py:1419-1428) →
`OriginCostCalculator.calculate`(:1432-1435) 법정요율 체인으로 공사비를 산출하고,
BOQ 자동초안은 **요약 힌트로만 가산**된다(공사비 수치 비변경). 상세 항목 목록은
스냅샷 비대를 막기 위해 stage data에 싣지 않고 `/api/v1/boq-auto/draft`를 단일
상세 출처로 둔다. `boq_builder` / `unit_price_repository`는 (d) 로드맵의
단가 결합 단계에서 같은 패턴으로 재사용한다.

### B4 배선 상세 (이번 변경분)

- 파이프라인 단계 실코드: `PipelineStage` enum 7단계
  `site_analysis → design → cost → feasibility → tax → esg → report`
  (project_pipeline.py:19-27). **cost 단계 존재 확인** → 배선 수행(생략 사유 없음).
  ※ 과거 기획서의 "site→legal→design→bim→cost→…" 표기 중 legal·bim은 파이프라인
  enum 단계가 아니라 별도 모듈(설계심사·BIM 서비스)로 존재한다 — 정직 표기.
- 단계 결과 저장 형태: 각 단계는 `StageResult.data: dict`(project_pipeline.py:37-44)
  스냅샷에 기록되고, cost 단계의 기존 키는
  `{total_construction_cost, direct_cost, cost_per_pyeong, total_gfa_pyeong,
  construction_months, cost_breakdown, material_item_count}`
  (project_pipeline.py:1500-1508). 라우터는 이를
  `_build_stages_response`(app/routers/pipeline.py:81-94)로 직렬화하고, 재실행은
  `previous_stage_data`(list[{stage,data}] / {stage:{data}} 양형 수용 —
  app/routers/pipeline.py:56)로 복원한다.
- 가산 지점: `_run_cost` 말미 `self._attach_boq_draft_hint(state, design)`
  (project_pipeline.py:1529). 헬퍼 `_attach_boq_draft_hint`(:1532-1594)가
  `app.services.cost.boq_parametric_engine`을 **try/except 안에서 임포트·호출**한다.
  - 성공 시: `state.stages["cost"].data["boq_draft_hint"] =
    {disciplines: {분야: item_count}, item_total, badges[], detail}` (:1586-1591).
  - 엔진 부재(B2 미병합)·시그니처 불일치(TypeError 1회 위치인자 재시도)·반환형
    이상·GFA≤0 — 어느 경우든 **키 자체를 생략**하고 단계 동작·기존 응답 키 불변.
  - 항목수는 엔진 반환값에서만 집계(dict/list 양형 수용), 여기서 수치 생성 금지.
- 하위호환 검증: 기존 `tests/test_project_pipeline_rerun.py` 13건 전부 통과
  (엔진 부재 상태 = 키 생략 경로). 모의 엔진 주입 4시나리오(부착/list형·배지폴백/
  GFA 0 생략/임포트 실패 생략) 인라인 검증 통과.

## (b) 각분야 에이전트 협업 설계

기존 파이프라인 단계를 "분야 에이전트"로 본다. 각 에이전트는 입력 페이로드를 받아
결정론 계산을 수행하고, 결과를 stage data 스냅샷 + 단계간 페이로드로 다음 에이전트에
전달한다(오케스트레이터: `ProjectPipeline.run`, project_pipeline.py:143-218).

| 분야 에이전트 | 단계(enum) | 입력 → 출력 페이로드 (실코드) |
|---|---|---|
| 부지분석 | site_analysis | 주소 → `SiteToDesignPayload`(:47-59) |
| 설계 | design | SiteToDesign → `DesignToCostPayload`(:62-72) |
| **적산(BOQ 에이전트)** | cost | DesignToCost → `CostToFeasibilityPayload`(:74-81) + `boq_draft_hint` |
| 수지 | feasibility | CostToFeasibility → feasibility data |
| 세금/ESG/보고서 | tax·esg·report | 상류 stage data 참조 |

### 적산 에이전트의 계약

- **입력(설계 파라미터)**: 프론트 SSOT `designData`
  (`useProjectContextStore.ts:81-92` — totalGfaSqm·floorCount·buildingType·bcr·far·
  unitCount…)가 파이프라인에서는 `DesignToCostPayload`(project_pipeline.py:62-72 —
  total_gfa_sqm·floor_count_above/below·structure_type·building_type)로 환원된다.
  ※ "massing"은 SSOT의 독립 필드가 아니다 — 매스 결과는 위 평탄 필드
  (연면적·층수·BCR/FAR)로 환원돼 전달된다(정직 표기: store에 massing 키 부재 확인).
  파라메트릭 엔진의 1차 구동변수는 `total_gfa_sqm`(마스터 기준 238,504㎡ 대비 비율).
- **출력**: ① 파이프라인 — cost stage data의 `boq_draft_hint`(요약·additive).
  ② 프론트 — BOQ 초안 합계를 사용자가 명시적으로 "수지반영" 클릭 시
  `updateCostData({...,source:"boq"})` 1방향 주입(BoqDetailTable.tsx:115-133).
  CostData는 full-replace 계약이므로 BOQ가 제공하지 않는 분해 항목은 가짜값 대신
  null 유지(BoqDetailTable.tsx:112-114 주석 — 기존 원칙 동일 적용).
- **스테일니스(재계산 전파)**: 기존 규칙 그대로 사용, 신규 규칙 추가 없음.
  `MODULE_UPSTREAM = { …, cost: ["siteAnalysis","design"],
  feasibility: ["siteAnalysis","design","cost"], finance: ["feasibility","cost"], … }`
  (`useProjectContextStore.ts:226-235`). 설계(연면적 등)가 갱신되면 cost가 stale로
  판정되고(:1109-1119), 마운트된 다운스트림이 1회 자동재계산하거나 CTA를 띄운다
  (`apps/web/hooks/useStageAutoRecalc.ts`). BOQ 초안도 cost 모듈 산하이므로 동일
  규칙으로 자동 무효화된다 — 적산 에이전트에 별도 의존성 선언이 필요 없다.
- **사용자 수동값 보호**: store의 `manualFields` provenance 병행 맵
  (useProjectContextStore.ts:133-140)에 의해 source:"user" 필드는 BOQ 자동 주입이
  덮어쓰지 못한다(기존 merge 가드 재사용).

## (c) 정직성 원칙

1. **실적 n=1 명시**: 마스터의 모든 산출물은 실적 공내역서 1건에서 나온 참고치다.
   `_meta.json project.sample_count=1`,
   `provenance: "실적 공내역서 1건(공개 단가 없음) — 원단위 계수는 n=1 참고치"`를
   레지스트리→엔진→API→프론트가 그대로 전파한다.
2. **전문검토 필수 배지**: BOQ 초안·`boq_draft_hint.badges`에는 "실적 1건 기반
   표준항목(n=1)" · "전문가 검토 필수" 배지를 항상 동반한다. 엔진이 배지를 반환하면
   그 값을 우선하고, 부재 시에만 마스터 출처 **사실**에 근거한 고정 문구로 폴백한다
   (project_pipeline.py:1582-1585 — 수치 폴백 아님, 가짜값 금지).
3. **가짜 단가 금지**: 공내역서는 단가 빈칸이 표준이다. 마스터에 단가는 없으며
   (전기 공종의 비고 단가 `ref_mat_price`만 참고 보존), 금액 산출은 (d)의 단가DB
   결합 전까지 하지 않는다. 힌트도 금액이 아닌 **항목수만** 담는다.
4. **결정론(LLM 0)**: 추출 스크립트·레지스트리·엔진·힌트 모두 결정론 코드 경로다.
   동일 입력(gfa_sqm) → 동일 초안. LLM은 어떤 수치도 생성하지 않는다.
5. **additive·하위호환**: 기존 응답 키·테스트 무파손. `boq_draft_hint`는 가산 키이며
   실패 시 생략된다(스테일 힌트가 새 결과로 오인되지 않음 — `_restore_previous`의
   "재실행 단계 미복원" 원칙(project_pipeline.py:381-386)과 일관).

## (d) 확장 로드맵

1. **실적 N건 축적 → 계수 회귀**: 마스터를 프로젝트별 JSON으로 누적
   (`data/boq_master/<project>/…`)하고, 항목별 원단위(qty/㎡)를 N건 표본으로 회귀·
   신뢰구간 추정. `sample_count`가 배지 문구를 자동 갱신("실적 N건 기반·CV xx%").
   n≥3 전까지는 현 n=1 배지 유지.
2. **BIM 물량 우선 병합**: 모델 `BimQuantity`(app/models/v61_cost.py:54,
   database/models/v61_cost.py:93-96, 테이블 `bim_quantities`)가 존재하는 항목은
   파라메트릭 추정치 대신 BIM 실측 물량을 우선 채택(merge 우선순위:
   user > bim > parametric), 항목별 출처 플래그(`qty_source`)로 정직 표기.
   IFC 매핑은 기존 `ifc_work_map.py`·`geometry_qto.py` 재사용.
3. **단가DB 결합 → 완전 내역서**: `unit_price_repository.py`(표준/시장 KCCI/실적
   3중 단가)와 결합해 단가 빈칸을 채우고, `boq_builder.py`→`origin_cost_calculator.py`
   법정요율 체인으로 원가계산서까지 자동 생성. 이 시점에 `boq_draft_hint`에 금액
   요약을 추가(역시 additive)하고 costData source:"boq" 주입을 항목 단위로 정밀화.
4. **파이프라인 단계 승격(선택)**: BOQ 초안이 금액을 갖게 되면 cost 단계의 폴백
   체인(estimator → 평당 개산, project_pipeline.py:1456-1473)에 "boq_parametric"
   경로를 추가하는 것을 검토 — 단, 기존 키 계약과 `cost_source` 정직 표기 규칙
   (:1519-1521)을 그대로 따른다.

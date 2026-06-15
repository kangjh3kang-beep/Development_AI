# 시장·시세 분석 페이지 전문화 리팩토링 — 상세 구현계획서

> 작성: PropAI 시스템 아키텍트 · 대상 워크트리(읽기): `/home/kangjh3kang/My_Projects/Development_AI_feature/propai-platform`
> 본 문서는 **구현계획서**다. 코드 구현은 본 워크트리가 아닌 실행 lane에서 수행한다(여기서는 설계만).
> 핵심 원칙: **무목업·라이브검증**, **선택형 분석이 기본**, **실데이터 우선 나열 → 분석은 그 다음**, **provider명(SGIS/KOSIS) 비노출**, **가짜값 금지(정직 표기)**.

---

## 0. 현황 진단 (코드 근거)

### 0.1 프론트 — `apps/web/components/operations/MarketInsightsWorkspaceClient.tsx`
- 분석항목 선택: 공용 `AnalysisModuleSelector`에 4개 모듈 평면 카탈로그 주입(L252–257).
  - `base`(필수) / `sgis`("인구/가구 분석 (SGIS)") / `kosis`("거시 소득 지표 (KOSIS)") / `katlas`("마이크로 타겟팅", 프리미엄 잠금).
  - **요구1 위반 지점**: 라벨에 `(SGIS)`·`(KOSIS)` 그대로 노출(L254–255).
- 선택 상태: `analysisOptions = {sgis, kosis, katlas}` 단일 평면 boolean 맵(L221–225). **계층(분류→상세항목) 없음(요구2 미충족).**
- options 전달: `/market/report` POST body의 `options: analysisOptions`(L299). PDF/PPTX 다운로드(`downloadReport`)는 **options를 아예 안 보냄**(L323) → 다운로드 보고서엔 인구/소득 데이터 누락(요구5 결함).
- 렌더 순서(L499~): AI 시세 추정 → 주변 실거래 현황 → 실거래 상세표 → Feasibility → PricingBand → **DemographicPanel(L638)**. 실거래 raw 표는 존재하나, 인구/소득은 `DemographicPanel`(차트) 한 곳에 뭉쳐 있고 **raw 표 우선 나열 구조가 아님(요구3 미충족).**
- 보고서 미리보기는 `narrative`(요약/기회/리스크/가격동향/타겟)만 텍스트로 노출(L447~). raw 통계표는 화면에 표 형태로 거의 없음(실거래 상세표 제외).

### 0.2 백엔드 서비스 — `apps/api/app/services/market/market_report_service.py`
- `build_report(address, lawd_cd, pnu, use_llm, options)`(L242): `options.sgis`/`options.kosis`로 demographics 분기 호출(L268~). **항목별(상세) 분기 없음 — 분류 단위 ON/OFF만.**
- 실거래(MOLIT): `_category_stats`(L109)가 매매(아파트/연립/오피스텔/단독)·전월세·아파트 월별 평당가 추이를 이미 산출(raw 풍부). → **요구4의 실거래 측은 상당부분 확보됨.**
- demographics: `SgisClient`+`KosisClient` 병렬 호출(L297) → `DemographicProfile.model_dump()`. raw + 산출이 한 dict에 혼재.
- export: `to_pdf`(reportlab, L487)·`to_pptx`(python-pptx, L617) 존재. **DOCX 없음(요구5).** 두 export 모두 `demographics` 섹션을 보고서에 거의 안 그림(시장요약/시세표/추이/기회/리스크/가격동향 위주).

### 0.3 provider가 실제로 줄 수 있는 raw 항목 (코드에서 추출 — 실현가능성 근거)
| provider | 메서드 | 실제 산출 raw (data_source) | 비고 |
|---|---|---|---|
| SGIS `get_population_stats` | searchpopulation/household | **총인구·총가구수·평균가구원수**(live), **10세 단위 연령분포 0-9~90+**(live, 실측) | sgis_client.py L256~ / `_AGE_TYPE_LABELS` L168 |
| SGIS(가구원수 분포) | `_estimate_household_sizes` | 1·2·3·4인+ 비율 — **평균가구원수 기반 추정(fallback)** | L229; SGIS 미제공 → 정직 "추정" |
| SGIS `get_migration_stats` | — | **OD 미제공 → unavailable**(가짜 금지) | L119 주석; OD는 KOSIS로 대체 |
| KOSIS `get_migration_od` | DT_1B26001_A01 | **총전입·총전출·순이동**(live) — 단, **출발지 OD 분해는 없음**(top_inflow_regions=[]) | kosis_client.py L279 |
| KOSIS `get_macro_income_stats` | DT_133001N_4215(국세청) | **시군구 평균 연소득**(live), 중위=평균×0.85 추정, **인원 수**, **총급여 금액** | L160; income_bracket_ratio는 표에 없음(빈값) |
| MOLIT `_category_stats` | 실거래 | 유형별 건수/평균/최저/최고/평균면적/**평당가(만원/평)**, **아파트 월별 평당가 추이** | service L109 |
| LandInfoService `collect_comprehensive` | — | 용도지역·공시지가·인프라(지하철 등) | service L251 |
| K-Atlas(마이크로) | — | **미연동(unavailable)** — 표본 비표시 유지 | client L50 model만 존재 |

> **결론**: 요구4 "전문 raw 확대"는 (a)실거래 측은 기존 산출을 화면에 **표로 펼치기만** 하면 되고, (b)인구/가구/소득은 provider live 항목(연령분포·가구수·평균가구원수·전입전출순이동·평균소득)을 **상세항목 단위로 분리 노출**하면 된다. OD 출발지·소득구간비율·K-Atlas는 provider가 안 주므로 **정직 미제공 표기 유지**(가짜 생성 금지).

---

## 1. 분석 분류·항목 트리 설계 (요구1·2·4)

provider명을 숨긴 **사용자 친화 분류 → 상세항목** 2단 트리. 각 항목에 **데이터 출처(어느 provider/raw)**를 매핑(구현 가능성 근거).

```
[기본 부동산 분석]  (base · 필수 · 항상 포함)
 ├─ 주변 실거래 현황       ← MOLIT _category_stats(trade)         [live]
 ├─ AI 시세 추정(평당가)    ← 실거래 평당가 가중평균                 [live]
 ├─ 전월세 보증금 시세      ← MOLIT rent                          [live]
 ├─ 시세 추이(월별 평당가)  ← MOLIT apt_trend                     [live]
 └─ 입지/인프라             ← LandInfoService(지하철·공시지가·용도지역) [live]

[인구/가구 분석]  (population · 분류 토글)   ※ (SGIS) 라벨 제거
 ├─ 인구 규모·가구          ← SGIS 총인구/총가구수/평균가구원수      [live]
 ├─ 연령대 분포            ← SGIS 10세 단위(0-9~90+)              [live]
 ├─ 가구원수 분포          ← SGIS 평균 기반 추정                   [fallback·"추정"배지]
 └─ 인구 이동(전입·전출·순이동) ← KOSIS DT_1B26001_A01            [live·출발지OD 미제공 정직]

[거시 소득 지표]  (income · 분류 토글)        ※ (KOSIS) 라벨 제거
 ├─ 평균 연소득            ← KOSIS DT_133001N_4215(국세청)       [live]
 ├─ 중위 연소득(추정)       ← 평균×0.85                          [fallback·"추정"배지]
 ├─ 소득 산출 근거(인원·총급여) ← KOSIS 원자료                     [live·신규 노출]
 └─ 소득 구간 분포          ← 미제공                              [unavailable·정직표기]

[마이크로 타겟팅]  (katlas · 프리미엄 잠금)
 └─ 금융·소비·신용 지표     ← K-Atlas(미연동)                     [unavailable·표본 비표시]
```

라벨 매핑(요구1): `sgis → "인구/가구 분석"`, `kosis → "거시 소득 지표"`. provider명은 코드 주석·내부 키에만 남기고 **UI 텍스트·보고서 본문에서 전면 제거**(출처는 "통계청 인구주택총조사", "국세청 근로소득" 등 **통계 출처명**으로만 표기 — 신뢰성↑ + provider 직접노출 회피).

---

## 2. 계층형 선택 UI 설계 (요구2)

### 2.1 옵션 페이로드 구조 (프론트 → 백엔드 단일 계약)
하위호환 위해 **평면 boolean(분류) + 항목 맵(상세)** 동시 전송. 백엔드는 항목 맵이 있으면 우선, 없으면 분류 boolean으로 폴백(기존 호출 안 깨짐).

```jsonc
{
  "options": {
    "sgis": true,            // 분류 ON/OFF (하위호환 — 기존 build_report 분기 유지)
    "kosis": true,
    "katlas": false,
    "items": {               // ★신규: 상세항목 선택(있으면 우선)
      "population": { "scale": true, "age": true, "household": true, "migration": true },
      "income":     { "avg": true, "median": true, "basis": true }
    }
  }
}
```
- `sgis` = `items.population` 중 하나라도 true. `kosis` = `items.income` 중 하나라도 true(프론트가 파생 계산 후 전송 → 백엔드 분기 무변경 가능).

### 2.2 선택 상태머신 (전체선택 + 분류별 + 항목별)
신규 공용 컴포넌트 `HierarchicalAnalysisSelector`(또는 기존 `AnalysisModuleSelector` 확장). 상태:
- 분류 체크박스: **tri-state**(전체 선택 / 일부 / 미선택). 분류 ON → 하위 항목 펼침(아코디언).
- 항목 체크박스: 개별 토글. 항목이 모두 켜지면 분류=checked, 일부면 indeterminate, 전무면 unchecked.
- 분류 토글 → 하위 전체 일괄 on/off. 항목 토글 → 분류 상태 자동 재계산(올림).
- **전체선택** 버튼: 모든 분류·항목 on(잠금 모듈은 프리미엄일 때만).
- 과금/시간 표기: 선택된 **항목 수** 기준 합산(`AnalysisModuleSelector`의 coinCost/estimatedSeconds 패턴을 항목 단위로 확장). 미선택 항목은 호출 생략 — 메모리 원칙(선택분만 과금) 준수.

### 2.3 컴포넌트 선택지
- **권장**: `AnalysisModuleSelector`에 `children?: AnalysisSubItem[]` + tri-state 로직을 **하위호환 추가**(다른 모듈은 children 미전달 시 기존 동작 그대로). 단일 공용 컴포넌트 유지 → 전 시스템 확산 용이.
- 대안: 신규 `HierarchicalAnalysisSelector` 분리(시장분석 전용 시작 후 일반화). 회귀 위험 ↓, 중복 ↑.

---

## 3. 응답·렌더 구조 — "실데이터 우선" (요구3)

### 3.1 백엔드 응답 스키마: raw / analysis 분리
`build_report` 반환에 **`raw_data` 블록**을 명시 신설(기존 키 유지 = 하위호환). 프론트는 raw 먼저, analysis 나중 렌더.

```jsonc
{
  // ── 기존 키(유지) ──
  "trade": {...}, "rent": {...}, "apt_trend": [...], "demographics": {...},
  "narrative": {...}, "feasibility_analysis": {...}, "pricing_band": {...},

  // ── ★신규: 화면 "실데이터 우선 나열"용 표준 묶음 ──
  "raw_data": {
    "real_estate": {                      // 분류: 기본 부동산
      "trade_table": [...], "rent_table": [...], "trend_series": [...],
      "source": "국토교통부 실거래가", "data_source": "live"
    },
    "population": {                       // 분류: 인구/가구
      "summary": { "total_population": n, "household_count": n, "avg_household_size": n },
      "age_distribution": [{label, count}...],
      "household_types": [{label, ratio}...],
      "migration": { total_inflow, total_outflow, net_migration },
      "source": "통계청 인구주택총조사 / 국내인구이동통계",
      "data_source": "live|fallback|unavailable"   // 항목별 배지
    },
    "income": {                          // 분류: 거시 소득
      "avg_income_10k": n, "median_income_10k": n,
      "basis": { persons, total_salary }, "bracket_ratio": null,
      "source": "국세청 근로소득", "data_source": "live"
    }
  },
  "analysis": {                          // raw 다음에 제시할 해석/인사이트
    "narrative": {...}, "feasibility": {...}, "pricing_band": {...},
    "unit_mix": {...}, "target_persona": "..."
  }
}
```
> 핵심: **demographics를 항목 단위로 평탄화한 표(row 배열)** 를 백엔드가 만들어 내려준다(프론트가 dict를 가공하지 않게 → 표 우선 노출 단순화 + DOCX/PDF/PPTX 재사용).

### 3.2 프론트 섹션 순서(위 → 아래)
1. **[실데이터 — RAW]** 헤더 구분선
   - 주변 실거래 현황(요약 통계) → **유형별 매매 시세 표(평당가)** → **전월세 표** → **시세 추이 표/스파크라인** → **실거래 상세 내역 표(기존 유지)**
   - 선택 시: **인구 규모·가구 표** → **연령대 분포 표+막대** → **가구원수 분포 표** → **전입/전출/순이동 표**
   - 선택 시: **평균/중위 연소득 표** → **소득 산출 근거 표(인원·총급여)**
   - 각 표 상단 우측 `DataSourceBadge`(live/추정/데이터없음) — 기존 `DataSourceBadge.tsx` 재사용.
2. **[분석 — ANALYSIS]** 헤더 구분선
   - AI 시세 추정 → Feasibility → 적정 분양가 밴드 → 평형 MD 추천 → 시장 요약/기회/리스크/가격동향/타겟 페르소나 → 검증 배지 + 전문가 패널
3. **[보고서 다운로드]** PDF / DOCX / PPTX

기존 `DemographicPanel`(차트)은 **analysis 영역의 보조 시각화**로 위치 이동(raw 표가 1차, 차트는 보강).

---

## 4. 전문화 데이터 확대 (요구4)

신규 raw 생성은 **provider가 실제 주는 값만** 확대(가짜 금지). 추가 가공:
- **실거래 교차분석**: 유형별 평당가 × 면적대 분포(기존 area 데이터 활용), 반경별(500m/1km/3km/5km) 거래량·평균가(프론트 `deriveResults` 이미 산출 — 보고서로도 내려보내기).
- **시세 추이**: 월별 평당가 + 전월 대비 증감률(%) 컬럼 추가(apt_trend에서 계산, 결정론).
- **연소득 산출 근거**: 인원·총급여를 노출해 "평균 = 총급여×100/인원" 투명화(신뢰성).
- **벤치마크**: 평균 연소득을 전국 근사(4,200만원, kosis fallback 상수)와 비교한 "전국 대비 %" 1줄(참고용·결정론).
- **신뢰/출처**: 모든 표에 출처명 + `data_source` 배지. unavailable 항목은 표를 비우고 "○○ 연동 예정" 정직 표기(기존 패턴 L660~ 계승).

> 비-목표(가짜 방지): OD 출발지 Top, 소득 구간비율, K-Atlas 금융지표는 **생성 금지**(provider 미제공). "데이터 없음/연동 예정"으로만 노출.

---

## 5. PDF / DOCX / PPTX Export 설계 (요구5)

### 5.1 공통 — 보고서 데이터 일원화
`build_report`의 `raw_data`+`analysis`를 export 3종이 **공유**(중복 산출 제거). 보고서 표준 구성:
1. 표지(주소·생성일·기간·면책 일부) 2. 핵심 요약(KPI) 3. **실데이터 섹션**(실거래 표·시세추이 차트·인구/가구 표·연령분포 차트·소득 표) 4. **분석 섹션**(AI 요약·기회·리스크·가격동향·타겟·적정분양가) 5. 출처·면책.

### 5.2 PDF (`to_pdf`, reportlab — 기존 확장)
- 현재 매매/전월세/추이까지만. **인구·가구·소득 raw 표 + 연령분포 막대차트 섹션 추가**(reportlab Table/VerticalBarChart 기존 패턴 재사용).
- 데이터 출처/추정 표기를 표 캡션에 삽입.

### 5.3 PPTX (`to_pptx`, python-pptx — 기존 확장)
- `table_slide`/`chart_slide` 헬퍼 재사용해 **인구/가구 슬라이드 + 연령분포 차트 슬라이드 + 소득 슬라이드** 추가.

### 5.4 DOCX (신규 — python-docx)
- **의존성 이미 충족**: `pyproject.toml`(python-docx>=1.1.0)·`requirements.txt`/`requirements.oracle.txt`(==1.1.2)에 선언됨 → **신규 설치 불필요**.
- `to_docx(rep) -> bytes` 신규 메서드: `python-docx`로 표지(Heading)·표(add_table)·연령분포는 표 또는 임베드 PNG(기존 `static_map_png` 패턴의 matplotlib/PIL 차트 생성 1개 추가)·면책 문단. reportlab과 동일 raw_data 소비.

### 5.5 엔드포인트 (`apps/api/routers/market_report.py`)
- 신규: `POST /api/v1/market/report/docx`(pdf/pptx와 동형, media_type `application/vnd.openxmlformats-officedocument.wordprocessingml.document`).
- **버그 수정(중요)**: 기존 `report/pdf`·`report/pptx`가 `build_report(... )` 호출 시 **`options`를 누락**(L60·L75) → 다운로드 보고서에 인구/소득 데이터가 안 들어감. **3종 모두 `options=req.options` 전달하도록 수정**. 프론트 `downloadReport`도 body에 `options: analysisOptions` 추가(현재 L323 누락).

---

## 6. Phased 로드맵

각 Phase는 독립 검증 가능 단위. **DoD = 라이브검증(실주소) + 빌드/린트 통과**.

### P1 — 라벨 정리 + 계층 선택 UI + options 계약 (프론트 중심)
- 산출물: provider명 제거된 라벨, 계층형 선택기(전체/분류/항목), 확장 options 페이로드.
- 수정: `apps/web/components/operations/MarketInsightsWorkspaceClient.tsx`(라벨·analysisOptions 구조·onModulesChange·onSelectAll·downloadReport body에 options 추가).
- 수정/신규: `apps/web/components/common/AnalysisModuleSelector.tsx`(children tri-state 하위호환 확장) 또는 신규 `HierarchicalAnalysisSelector.tsx`.
- 검증: 분류 토글→항목 펼침, tri-state 전이, 선택 코인 합산, 기존 `/market/report` 호출 무회귀.
- DoD: 라벨에 SGIS/KOSIS 0건(grep), 항목별 선택 동작, `pnpm build` 통과.

### P2 — 백엔드 항목 선택 반영 + raw/analysis 응답 분리
- 산출물: `build_report`가 `options.items` 수용, `raw_data`(평탄 표 배열) + `analysis` 신설(기존 키 유지).
- 수정: `apps/api/app/services/market/market_report_service.py`(build_report 분기·raw_data 빌더 함수 신설), 필요 시 `market_models.py`(raw 표 row 스키마 — 선택).
- 검증: 라이브 주소(강남구·파주시 등 메모리 검증지)로 demographics live/fallback/unavailable 분기 정확, 항목 미선택 시 해당 provider 호출 생략(로그 확인).
- DoD: 항목 단위 ON/OFF가 응답 raw_data에 반영, 가짜값 0(unavailable 정직).

### P3 — 프론트 실데이터 우선 렌더(표 → 분석)
- 산출물: RAW 섹션(실거래·인구·가구·소득 표 + DataSourceBadge) 우선, ANALYSIS 섹션 후행. `DemographicPanel`은 분석 보조로 재배치.
- 수정: `MarketInsightsWorkspaceClient.tsx`, 신규 표 컴포넌트(예: `market/RawDataTables.tsx`), `DemographicPanel.tsx` 위치/역할 조정.
- 검증: 표 우선 노출, 추정/데이터없음 배지 정직, 빈데이터 graceful.
- DoD: 화면 상단=raw 표, 하단=분석. 모바일 반응형/AA 대비 유지.

### P4 — DOCX export 신규 + 3종 보고서 통합(인구/소득 섹션 포함) + options 버그 수정
- 산출물: `to_docx`, `/market/report/docx`, PDF/PPTX에 인구·가구·소득 섹션 추가, 3종 모두 options 전달.
- 수정: `market_report_service.py`(to_docx + to_pdf/to_pptx 섹션 확장), `routers/market_report.py`(docx 라우트 + pdf/pptx options 전달), 프론트 다운로드 버튼 3종(DOCX 추가)·`downloadReport`에 options.
- 검증: 3종 다운로드 실파일 열림, 인구/소득 표가 실제로 채워짐(라이브).
- DoD: pdf/docx/pptx 모두 raw+analysis 포함, 파일 정상 오픈.

### P5 — 통합 라이브검증 + 정직성/회귀 감사
- 산출물: 다주소 E2E(강남구·파주시·평창·신봉동 등), 선택형 과금 게이트 회귀, 검증배지/전문가패널 동작.
- 검증: `propai-qa` 정합성(Pydantic↔TS, 라우트↔파일경로), 빌드/린트/타입.
- DoD: 7/7 시뮬레이션 통과 형태의 리포트 + 핸드오프 메모리 갱신.

---

## 7. 위험 · 완화

| 위험 | 영향 | 완화 |
|---|---|---|
| SGIS/KOSIS 키 의존(미설정 시 fallback/unavailable) | 인구·소득 빈값 | 기존 정직 배지(live/fallback/unavailable) 계승, 가짜 생성 금지. 관리자 키 등록 시 즉시 live(os.environ 우선 — 기존 보장). |
| 다중 provider 병렬 호출 지연 | 보고서 응답 지연 | 항목 미선택 시 호출 생략(선택형). 기존 하드타임아웃(5~6s) 유지. raw/analysis 분리로 raw 먼저 표시 가능(점진 렌더 여지). |
| options 페이로드 변경으로 기존 호출 깨짐 | 회귀 | `items` 미전달 시 기존 분류 boolean 폴백(하위호환 계약). PDF/PPTX는 options 누락이 **현재도 버그** → 수정이 곧 개선. |
| 과금 이중 계산(항목 단위 합산) | 과·소 과금 | 실차감은 백엔드 BaseInterpreter LLM 계측이 단일경유(메모리). 프론트 합산은 **안내용 추정치**임을 표기(기존 패턴 유지). |
| tri-state 상태머신 복잡도 | UI 버그 | 단위 로직 분리 + 기존 `AnalysisModuleSelector` 하위호환(children 없으면 무변경)으로 회귀 차단. |
| 한글 폰트(reportlab/docx) | 깨짐 | reportlab은 기존 `HYSMyeongJo-Medium` 등록 패턴 유지. DOCX는 시스템 기본 한글 폰트(맑은 고딕/Noto) 명시 설정. |

---

## 8. market-intel lane 조율 (claim 대상 파일)

동시 작업 충돌 방지를 위해 아래 파일을 lane claim 대상으로 명시(공유보드 claim/release 규약):
- 프론트: `apps/web/components/operations/MarketInsightsWorkspaceClient.tsx`, `apps/web/components/common/AnalysisModuleSelector.tsx`, `apps/web/components/operations/market/DemographicPanel.tsx`, 신규 `market/RawDataTables.tsx`(또는 유사).
- 백엔드: `apps/api/app/services/market/market_report_service.py`, `apps/api/routers/market_report.py`, (선택) `apps/api/app/services/market/market_models.py`.
- 비-claim(읽기만): `sgis_client.py`·`kosis_client.py`(provider 계약은 변경하지 않음 — raw는 호출측에서 재구성).

> 권장: P1(프론트)·P2(백엔드)를 **분리 브랜치=워크트리 1:1**로 진행, P3는 P2 머지 후. main 직푸시 금지(메모리 규약).

---

## 부록 A — 미결정 질문 (실행 전/중 확정 필요)
- [ ] 계층 선택기를 **기존 `AnalysisModuleSelector` 확장** vs **신규 `HierarchicalAnalysisSelector`** 중 무엇으로? (권장: 확장, 하위호환)
- [ ] DOCX 연령분포를 **표만** vs **임베드 차트(matplotlib/PIL 신규)** 중? (의존성·복잡도 trade-off)
- [ ] raw_data 표 row 스키마를 `market_models.py` Pydantic으로 형식화 vs 자유 dict? (TS 타입 동기화 비용)
- [ ] "전국 대비 소득 %" 벤치마크 노출 여부(참고용 표기 시 정직성 OK인지 확인).
- [ ] 항목별 과금 단가(coinCost) 재책정 필요 여부 — 현재 분류 단위(sgis/kosis 각 300, katlas 2000)를 항목 단위로 쪼갤지.

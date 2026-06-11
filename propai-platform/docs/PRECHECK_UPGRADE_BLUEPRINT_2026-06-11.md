# PRECHECK 고도화 청사진 (PRECHECK_UPGRADE_BLUEPRINT)

- **문서 버전**: 2026-06-11
- **작성**: PropAI 수석 아키텍처
- **대상**: 90초 사업성 진단(`run_instant_precheck`) 고도화
- **설계 원칙(절대 준수)**: **새 계산/조닝/검증 엔진 0개.** 전부 기존 함수 rewire(재배선). 신규 산출물은 *데이터 매핑 모듈 1개*(`legal_reference_registry.py`, 계산 로직 없음)와 precheck 내부 *조립 헬퍼*만. 응답은 **additive(가산)** — 기존 필드 1개도 제거/변경하지 않는다.

> 본 청사진은 ① 법령 딥링크 리서치(law.go.kr 한글주소 검증)와 ② precheck 아키텍처 설계를 종합한 단일 실행 기준 문서다. 코드베이스 실측으로 모든 심볼/경로/응답 형태를 교차 확인했다(아래 "근거 실측" 참조).

---

## ⓪ 근거 실측 (이 청사진이 가리키는 실제 코드)

블루프린트의 모든 rewire 대상은 현행 코드에 존재함을 실측으로 확인했다.

| 심볼 | 실제 경로 : 라인 | 비고 |
|---|---|---|
| `run_instant_precheck(address, pnu, area_sqm, use_llm)` | `apps/api/app/services/precheck/precheck_service.py:153` | 응답 키 실측: `ok/address/pnu/zone_type/area_sqm/legal_limits/methods/summary/elapsed_ms/sources` (성공시), `ok:false`시 `message` 동반 |
| `_legal_limits(zone_type)` | `precheck/precheck_service.py:48` | **현재 시그니처에 address 없음** → WP에서 가산 |
| `_area_checks(area_sqm, legal)` | `precheck/precheck_service.py:64` | 면적×건폐/용적률 개략 산출 |
| `analyze_by_address(address)` | `zoning/auto_zoning_service.py:45` | geocode→land_info→land_characteristics 체인 보유 |
| `_detect_zone_from_address(address)` | `zoning/auto_zoning_service.py:169` | 폴백(주소 키워드 추론) |
| `applicable_limits_for(...)` | `zoning/legal_zone_limits.py:278` | 조례 실효값 주입 진입점 |
| `get_ordinance_limits(...)` | `land_intelligence/ordinance_service.py:168` | **경로 주의: `land_intelligence/`** (설계 초안의 `ordinance/` 아님) |
| `run_sensitivity_analysis(...)` | `feasibility/sensitivity_engine.py:27` | **경로 주의: `feasibility/`** |
| `aggregate_feasibility(...)` / `determine_grade(profit_rate_pct)` | `feasibility/aggregation_engine.py:38 / :23` | NPV/등급 산식 — 그대로 재사용 |
| `FeasibilityServiceV2` | `feasibility/feasibility_service_v2.py` | ModuleInput→ModuleOutput 계산 |
| 검증 3종 | `data_validation/{validator,calculation_metadata,public_data_registry}.py` | 신선도·메타·하드코딩 경고 |

**현행 할루시네이션 1차 차단 실측 확인**(precheck_service.py:181, :194):
- `zone_type` 미확인 → `ok:false` + "용도지역을 확인할 수 없습니다…"
- `pnu`(필지) 미확인 → `ok:false` + "…필지 미확인 상태에서는 정량 진단을 제공하지 않습니다." — **이 분기를 신규 `data_quality.quantitative_reliable`와 동일 조건으로 재사용**(중복 로직 0).

---

## ① 목표 (고도화가 달성할 5대 가치)

| # | 목표 | 사용자 체감 | 충족 수단(전부 기존 자산 rewire) |
|---|---|---|---|
| **G1. 자동 입력(provenance)** | 주소 1개 입력 → 용도지역·면적·공시지가·PNU·좌표 자동수집 + **필드별 출처/방식 표기** | "내가 입력 안 한 이 값들은 어디서 왔나?"에 즉답 | `analyze_by_address` 체인(이미 자동수집 中) + 누락 시 `get_individual_land_price` 1회 보강. 채워진 키로 `inputs[].source/method/confidence` 판정 |
| **G2. 할루시네이션 검증** | 추정값/하드코딩/신선도 경고를 응답에 표면화, 신뢰불가 시 정량 차단 유지 | "이 진단 믿어도 되나?"에 등급(high/medium/low)·경고·면책으로 답 | `CalculationMetadata`+`PublicDataRegistry`+`FreshnessChecker`를 precheck 끝에서 1회 조립 / 기존 `pnu` 차단 분기 재사용 |
| **G3. 최저·기본·최대 사업성** | best 후보 1건의 NPV·이익률·ROI·등급을 **3시나리오 밴드**로 제시 | "잘되면/보통이면/안되면 얼마?"에 숫자 밴드로 답 | `run_sensitivity_analysis`(±delta 3점) + `FeasibilityServiceV2.calculate` + `aggregate_feasibility`/`determine_grade`. **새 산식 0** |
| **G4. 산출 근거(트레이스)** | "이 수치=입력×산식×법정값" 한 줄 근거를 모든 핵심 수치에 부착 | "용적률 200%가 왜 나왔나?"에 `min(법정250%,조례200%)` 트레이스로 답 | `applicable_limits_for` 반환의 `far_source/sources/ordinance_confirmed`를 evidence로 직렬화 |
| **G5. 법령 원문 링크** | 근거마다 law.go.kr **현행본 딥링크**(한글주소) | 클릭 1회로 제84·85조·제61조 원문 확인 | 신규 `legal_reference_registry.py`가 키→{법령명·조문·title·url} 매핑. URL은 ②의 검증된 규칙으로 주입 |

**불변(절대 깨지 않음)**: 90초 SLA(외부호출 1회 + 선택 LLM 1회, feasibility 밴드는 best 후보 **1건만** 3점 계산), 빈 결과 금지, 필지 미확인 시 정량 차단.

---

## ② 법령 딥링크 URL 규칙 + 법률별 매핑표

### ②-1 검증된 URL 형식 규칙 (법령정보식별주소 = 한글주소)

법제처가 2011년 특허받은 공식 기능. **법령 개정 시 자동으로 현행본을 가리키므로** 사업성 진단 보고서의 영구 인용에 적합하다(버전 고정 `lsiSeq`는 개정마다 변동 → 일반 근거 링크엔 부적합).

명명규칙: **`[대표URL] / 법령(또는 자치법규) / 법령명 / 제N조`**

| 대상 | URL 형식 | 예시 | 검증 |
|---|---|---|---|
| 법령 본문 | `https://www.law.go.kr/법령/{법령명}` | `…/법령/건축법` | ✅ 실접속(타이틀 정상) |
| 특정 조문 | `https://www.law.go.kr/법령/{법령명}/제{N}조` | `…/법령/건축법/제55조` | ✅ 경로 resolve, 다수 교차확인 |
| 가지번호 조문 | `…/제{N}조의{M}` | `…/제29조의2` | ⚠️ KLRI 공식 가이드 형식확인(개별 실접속 미실시) |
| 시행령 | `…/법령/{법령명}시행령` | `…/법령/건축법시행령` | ✅ 실접속 |
| 시행규칙 | `…/법령/{법령명}시행규칙` | `…/법령/건축법시행규칙` | ✅ 실접속 |
| 자치법규(조례) | `…/자치법규/{조례명}` | `…/자치법규/서울특별시도시계획조례` | ✅ 실접속 |

**핵심 규칙**
- 분류 키워드는 **`법령`** 또는 **`자치법규`**(조례·규칙)를 그대로 한글로.
- **공백·가운뎃점 제거해도 정상 resolve**: `건축법 시행령`→`건축법시행령`, `도시 및 주거환경정비법`→`도시및주거환경정비법` 모두 ✅. (안정성 위해 공식 법령명 전체 인코딩 권장)
- 조문은 반드시 **국문 서수 + "조"**(`제55조`). 아라비아 숫자 단독(`/55`), 영문(`/article55`) 불가.
- 항·호(`제1항`,`제2호`) 딥링크는 KLRI 가이드에 **명시 없음** → **조(條) 단위까지만 신뢰**, 이하는 본문 내 스크롤.

### ②-2 URL 인코딩 주의 (저장/전송 시)

- **percent-encoding(UTF-8) 동치**: `…/법령/상법` ≡ `…/%EB%B2%95%EB%A0%B9/%EC%83%81%EB%B2%95`. HTML `href`·JSON에는 **인코딩 형태가 안전**.
- **공백 처리**: 공식명에 공백이 있을 때 (a) 공백제거 ✅ (b) `%20` ✅ (c) `+` 모두 동작하나, **`+`는 일부 환경서 오해 소지** → **`%20` 또는 공백제거형 권장**.
- 가지번호는 `제29조의2`처럼 **"의2" 붙여서**(공백·하이픈 금지).
- 조례는 **지자체명 완전 포함**(`서울특별시도시계획조례`) — 동명 조례 충돌 방지. 조례 조문 딥링크는 루트만 실접속 확인, **조문 단위는 형식검증** → 인용 시 현행 여부 재확인.
- 구형 IE는 "UTF-8 URL 내보내기" 옵션 필요(법제처 안내). 최신 크롬·엣지·웹뷰는 자동 처리.

### ②-3 법률별 공식명 + 핵심 조문 + 딥링크 매핑표 (registry 주입용 마스터)

`url_status`: 실접속 ✅ = `verified`, 형식검증 ⚠️ = `verified_pattern`(최종 게재 전 클릭 1회 점검 권장).

| key | 공식 법령명 | 핵심 조문 | 딥링크(권장: 한글주소·현행본) | url_status |
|---|---|---|---|---|
| `zone_use` | 국토의 계획 및 이용에 관한 법률 | 용도지역 건축물 제한 **제76조** | `https://www.law.go.kr/법령/국토의계획및이용에관한법률/제76조` | ✅ verified |
| `bcr_law` | 국토의 계획 및 이용에 관한 법률 | 건폐율 **제77조** | `https://www.law.go.kr/법령/국토의계획및이용에관한법률/제77조` | ✅ verified |
| `far_law` | 국토의 계획 및 이용에 관한 법률 | 용적률 **제78조** | `https://www.law.go.kr/법령/국토의계획및이용에관한법률/제78조` | ✅ verified |
| `district_unit` | 국토의 계획 및 이용에 관한 법률 | 지구단위계획 **제52조** | `https://www.law.go.kr/법령/국토의계획및이용에관한법률/제52조` | ⚠️ verified_pattern |
| `bcr_limit` | 국토의 계획 및 이용에 관한 법률 시행령 | 용도지역 건폐율 **제84조** | `https://www.law.go.kr/법령/국토의계획및이용에관한법률시행령/제84조` | ⚠️ verified_pattern |
| `far_limit` | 국토의 계획 및 이용에 관한 법률 시행령 | 용도지역 용적률 **제85조**(별표 위임) | `https://www.law.go.kr/법령/국토의계획및이용에관한법률시행령/제85조` | ⚠️ verified_pattern |
| `bldg_bcr` | 건축법 | 건폐율 **제55조** | `https://www.law.go.kr/법령/건축법/제55조` | ✅ verified |
| `bldg_far` | 건축법 | 용적률 **제56조** | `https://www.law.go.kr/법령/건축법/제56조` | ✅ verified |
| `bldg_height` | 건축법 | 일조 등 높이제한 **제61조** | `https://www.law.go.kr/법령/건축법/제61조` | ✅ verified |
| `bldg_open` | 건축법 | 대지 안의 공지 **제58조** | `https://www.law.go.kr/법령/건축법/제58조` | ✅ verified |
| `bldg_height_dec` | 건축법 시행령 | 일조 위임기준 **제86조** | `https://www.law.go.kr/법령/건축법시행령/제86조` | ✅ verified(루트) |
| `housing_approval` | 주택법 | 사업계획승인 **제15조** | `https://www.law.go.kr/법령/주택법/제15조` | ✅ verified(루트) |
| `housing_price_cap` | 주택법 | 분양가상한제 **제57조** | `https://www.law.go.kr/법령/주택법/제57조` | ⚠️ verified_pattern |
| `urban_dev_replot` | 도시개발법 | 환지계획 **제28조** | `https://www.law.go.kr/법령/도시개발법/제28조` | ⚠️ verified_pattern |
| `redev_mgmt` | 도시 및 주거환경정비법 | 관리처분계획 **제74조** | `https://www.law.go.kr/법령/도시및주거환경정비법/제74조` | ✅ verified(루트) |
| `redev_impl` | 도시 및 주거환경정비법 | 사업시행계획인가 **제50조** | `https://www.law.go.kr/법령/도시및주거환경정비법/제50조` | ⚠️ verified_pattern |
| `urban_complex` | 도심 복합개발 지원에 관한 법률 | (2024.8.7 시행 신법) | `https://www.law.go.kr/법령/도심복합개발지원에관한법률` | ✅ verified(루트) · 인용 시 현행본 재확인 |
| `public_housing` | 공공주택 특별법 | 공공주택지구 지정 **제6조** | `https://www.law.go.kr/법령/공공주택특별법/제6조` | ⚠️ verified_pattern |
| `parking` | 주차장법 | 부설주차장 설치·지정 **제19조** | `https://www.law.go.kr/법령/주차장법/제19조` | ✅ 번호 교차확인 |
| `parking_dec` | 주차장법 시행령 | 설치기준 **제6조**(별표1 위임) | `https://www.law.go.kr/법령/주차장법시행령/제6조` | ✅ 교차확인 |
| `acq_tax` | 지방세법 | 취득세율 **제11조** | `https://www.law.go.kr/법령/지방세법/제11조` | ⚠️ verified_pattern |
| `ordinance_bcr` | {sigungu} 도시계획 조례 | 건폐율(지자체별) | `https://www.law.go.kr/자치법규/{조례명}` (조문은 현행 확인) | pending(지자체 동적) |
| `ordinance_far` | {sigungu} 도시계획 조례 | 용적률(지자체별) | `https://www.law.go.kr/자치법규/{조례명}` (조문은 현행 확인) | pending(지자체 동적) |

**조문 매핑 핵심 검증 포인트**
- 국토계획법: **건폐율=제77조(영 제84조), 용적률=제78조(영 제85조)** — 사용자 명시와 일치.
- 건축법: **건폐율=제55조, 용적률=제56조, 일조높이=제61조("일조 등의 확보를 위한 건축물의 높이 제한")**.
- 주차장법: **제19조 + 시행령 제6조 별표1**.
- 도심복합개발법은 **2024 시행 신법** → 조문 구조가 인용 시점마다 다를 수 있어 게재 직전 현행본 재확인 필수.

**조례(동적) 처리**: 시군구별 조례명·조문이 다르므로 registry는 `{sigungu}` 플레이스홀더만 보유하고, 런타임에 `OrdinanceService` 결과의 조례명으로 치환·`url_status:"pending"→"verified"` 전환(URL 확정 시).

---

## ③ 고도화 응답 데이터 모델 (additive 스키마)

`run_instant_precheck` 응답에 **신규 5블록을 가산**. 기존 `ok/address/pnu/zone_type/area_sqm/legal_limits/methods/summary/elapsed_ms/sources`는 **전부 그대로 유지** → 프론트 무수정 동작, 신규 블록은 선택적(optional) 렌더.

```jsonc
{
  // ── 기존 필드 전부 유지 (변경/삭제 0) ──
  "ok": true, "address": "...", "pnu": "11...", "zone_type": "제2종일반주거지역",
  "area_sqm": 660.0, "legal_limits": { /* bcr_pct/far_pct/height_m/source 유지 */ },
  "methods": [ /* M01~M15 신호등 */ ], "summary": { "pass":.., "warn":.., "fail":.., "best":"M06", "llm_note": null },
  "elapsed_ms": 1820, "sources": [ /* 문자열 배열 유지 */ ],

  // ── (1) inputs: 필드별 provenance (G1) ──
  "inputs": {
    "zone_type":             { "value": "제2종일반주거지역", "source": "vworld_land_characteristics(NED)", "method": "auto", "confidence": "high" },
    "area_sqm":              { "value": 660.0,    "source": "vworld_land_characteristics(NED)", "method": "auto", "confidence": "high" },
    "official_price_per_sqm":{ "value": 4120000,  "source": "vworld_individual_land_price",      "method": "auto", "confidence": "high", "base_year": 2025 },
    "pnu":                   { "value": "11...",   "source": "vworld_geocode(PARCEL)",            "method": "auto", "confidence": "high" },
    "sale_price_per_pyeong": { "value": 30000000,  "source": "regional_pricing(시세테이블)",       "method": "estimated", "confidence": "medium" }
    // method ∈ { "auto"(공공API) | "estimated"(테이블/추론) | "user"(사용자입력) | "fallback" }
  },

  // ── (2) data_quality: 할루시네이션 검증 (G2) ──
  "data_quality": {
    "confidence_level": "medium",        // CalculationMetadata 산출 (high|medium|low)
    "quantitative_reliable": true,       // pnu 확인 시 true — 기존 :194 차단분기와 동일 조건
    "warnings": [
      "'construction_unit_costs'은 하드코딩 데이터입니다. 법령/단가 개정 시 수동 업데이트 필요.",
      "공시지가 데이터가 2025년 기준(base_year) — 신선도 확인 권장."
    ],
    "sources_meta": [                    // PublicDataRegistry + FreshnessChecker
      { "name": "vworld_zoning",            "type": "공공API",   "is_live": true,  "fresh": true,  "age_days": 0 },
      { "name": "construction_unit_costs",  "type": "하드코딩", "is_live": false, "fresh": null,  "age_days": null }
    ],
    "disclaimer": "본 진단은 참고용이며, 실제 의사결정 시 전문가 확인을 권장합니다."
  },

  // ── (3) feasibility_band: 최저/기본/최대 (G3) ──
  "feasibility_band": {
    "method_code": "M06", "method_name": "공동주택(아파트)",
    "scenarios": {
      "min":  { "npv_won": -1200000000, "profit_rate_pct": -3.1, "roi_pct": -4.0, "grade": "F",
                "assumptions": { "sale_price_delta_pct": -15, "construction_cost_delta_pct": 10, "sale_ratio": 0.85 } },
      "base": { "npv_won":  3400000000, "profit_rate_pct": 12.4, "roi_pct": 18.0, "grade": "C",
                "assumptions": { "sale_price_delta_pct":   0, "construction_cost_delta_pct":  0, "sale_ratio": 0.95 } },
      "max":  { "npv_won":  7900000000, "profit_rate_pct": 22.1, "roi_pct": 31.0, "grade": "A",
                "assumptions": { "sale_price_delta_pct":  15, "construction_cost_delta_pct": -8, "sale_ratio": 0.98 } }
    },
    "band_drivers": [                    // sensitivity tornado 상위 — 밴드를 만든 변수
      { "variable": "sale_price",        "spread_pct": 25.2, "name": "분양가 변동" },
      { "variable": "construction_cost", "spread_pct": 11.0, "name": "공사비 변동" }
    ],
    "evidence_ref": "ev_feasibility_M06"
  },

  // ── (4) evidence: 산출 근거 트레이스 (G4) ──
  "evidence": [
    { "id": "ev_far", "target": "legal_limits.far_pct",
      "inputs": ["zone_type=제2종일반주거지역", "sigungu=강남구"],
      "formula": "applied_far = min(법정상한 250%, 조례 200%)",
      "result": "200%", "legal_ref_keys": ["far_limit", "ordinance_far"] },
    { "id": "ev_buildable", "target": "methods[].checks.용적률",
      "inputs": ["area_sqm=660", "applied_far=200%"],
      "formula": "연면적 = 대지면적 × 적용용적률 = 660 × 2.0",
      "result": "1,320㎡", "legal_ref_keys": ["far_limit"] },
    { "id": "ev_feasibility_M06", "target": "feasibility_band.base",
      "inputs": ["total_gfa=1320㎡", "분양가=3,000만원/평(강남구 시세)", "공사비단가=하드코딩"],
      "formula": "aggregate_feasibility(revenue - (land+construction+finance+other+tax))",
      "result": "NPV 34억 / 이익률 12.4% / C등급", "legal_ref_keys": [] }
  ],

  // ── (5) legal_refs: 법령 원문링크 (G5, registry 주입) ──
  "legal_refs": [
    { "key": "bcr_limit",     "law_name": "국토의 계획 및 이용에 관한 법률 시행령", "article": "제84조",
      "title": "용도지역 안에서의 건폐율", "url": "https://www.law.go.kr/법령/국토의계획및이용에관한법률시행령/제84조", "url_status": "verified_pattern" },
    { "key": "far_limit",     "law_name": "국토의 계획 및 이용에 관한 법률 시행령", "article": "제85조",
      "title": "용도지역 안에서의 용적률", "url": "https://www.law.go.kr/법령/국토의계획및이용에관한법률시행령/제85조", "url_status": "verified_pattern" },
    { "key": "ordinance_far", "law_name": "강남구 도시계획 조례", "article": "",
      "title": "용적률", "url": "https://www.law.go.kr/자치법규/서울특별시강남구도시계획조례", "url_status": "pending" }
  ]
}
```

**핵심 설계 결정**
- 5블록 전부 **추가 필드** → 기존 `types.ts` 인터페이스 그대로 동작(선택적 필드로 ts 확장). 프론트는 단계적(progressive) 렌더.
- `evidence[].legal_ref_keys` ↔ `legal_refs[].key` 조인 → UI에서 "용적률 200%" 옆에 **[제85조 원문]** 링크.
- `feasibility_band`는 `summary.best` 후보 **1건만** 3점 계산(90초 SLA 보호). 옵션 파라미터로 상위 N 확장 가능.
- `ok:false`(차단) 응답에는 5블록 중 `data_quality.quantitative_reliable=false`만 부착해도 무방(빈 결과 금지·차단 우선).

---

## ④ 재사용 자산 매핑 (기존 함수 → rewire 방식)

| 고도화 항목 | 재사용 기존 자산 (파일:심볼) | rewire 방식(새 엔진 0) |
|---|---|---|
| **G1. 주소 자동입력** | `AutoZoningService.analyze_by_address` (`zoning/auto_zoning_service.py:45`) — geocode→land_info→land_characteristics 체인 보유 | **이미 자동수집 中**. `official_price_per_sqm`가 null일 때만 `VWorldService.get_individual_land_price(pnu)` **1회 추가**(NED, wait_for 가드). 반환 dict의 채워진 키로 `inputs[].source/method` 판정 |
| G1. provenance 출처 판정 | `analyze_by_address` 내부 `warnings[]`/`coordinates` 유무, `_detect_zone_from_address`(`:169` 폴백) | pnu 있으면 `method:auto`; `_detect_zone_from_address` 경로면 `method:fallback`+`confidence:low`. 단 pnu 없으면 `:194`에서 이미 차단되므로 fallback은 실질 zone_type만 |
| **G2. 검증 메타** | `CalculationMetadata` (`data_validation/calculation_metadata.py`) — `add_source/confidence_level/to_dict` | precheck 끝에서 `meta = CalculationMetadata("precheck")` → 사용 소스마다 `add_source(name,type,is_live)`. 하드코딩 소스는 자동 경고 + confidence 강등 |
| G2. 신선도·소스상태 | `PublicDataRegistry.get_instance()` + `get_hardcoded_warnings()` / `FreshnessChecker.check` (`data_validation/{public_data_registry,validator}.py`) | `data_quality.sources_meta`를 레지스트리에서 조회. `construction_unit_costs`/`zone_bcr_far_limits`(하드코딩) 경고 자동 표면화 |
| G2. pnu 실패 신뢰불가 | `precheck_service.py:194` 기존 `ok:false` 분기 | **유지**. `data_quality.quantitative_reliable=false`를 **같은 조건**으로 세팅(중복 로직 0) |
| **G3. 최저/기본/최대** | `run_sensitivity_analysis` (`feasibility/sensitivity_engine.py:27`) + `FeasibilityServiceV2` (`feasibility/feasibility_service_v2.py`) | best 후보를 `ModuleInput`으로 구성 → `calculate_fn(values)` 클로저로 감싸 `run_sensitivity_analysis` 호출. min=하방·base=delta0·max=상방 추출 |
| G3. NPV/이익률/등급 | `aggregate_feasibility` + `determine_grade` (`feasibility/aggregation_engine.py:38/:23`) | `calculate_fn` 내부에서 ModuleInput→`FeasibilityServiceV2.calculate`→ModuleOutput(npv_won/profit_rate_pct/grade) 매핑. **새 산식 0** |
| G3. 밴드 변수(±) | `DEFAULT_SCENARIOS`(`sensitivity_engine.py`) `sale_price/construction_cost`, `regional_pricing`(시세) | 90초용 간이 **3점**(deltas `[-15,0,+15]`)만 사용 — 커스텀 시나리오. tornado로 `band_drivers` 산출. (선택)`run_monte_carlo`는 무거우므로 **상세 분석 탭에만**, precheck 기본은 3점 |
| **G4. 산출 근거** | `applicable_limits_for` (`zoning/legal_zone_limits.py:278`) 반환의 `far_source/sources/ordinance_confirmed` | evidence의 `formula/inputs/result`를 이 함수 결과로 채움. `min(법정,조례)` 트레이스를 `far_source` 그대로 인용 |
| G4. 조례 실효값 | `OrdinanceService.get_ordinance_limits(address, zone_type)` (`land_intelligence/ordinance_service.py:168`) → `effective_bcr/far` | `applicable_limits_for`에 `regulation_payload`로 주입. 법제처 API/캐시/법정상한 3단 폴백 그대로 |
| **G5. 법령 원문링크** | `LEGAL_BASIS`/`ZONE_LIMITS`(`legal_zone_limits.py`), `legal_basis`(`ordinance_service.py`) 문자열 | **신규 `legal_reference_registry.py`**가 이 문자열들을 `{key→{law_name,article,url}}`로 구조화. URL은 ②-3 검증표 주입. precheck/입지/법규 공용 |

---

## ⑤ 워크패키지 목록 (파일·스펙·하위호환·웨이브)

### 웨이브 개요 (의존 순서)

| Wave | 목표 | WP | 산출 |
|---|---|---|---|
| **W0** | 데이터 기반 마련(신규 모듈 1개 + 조문키 노출) | WP-1, WP-2 | registry + ref-key. **응답 변화 0**(준비만) |
| **W1** | 검증·자동입력 표면화 | WP-3, WP-4 | `inputs` + `data_quality` |
| **W2** | 조례 적용 + 근거 트레이스 + 법령링크 | WP-5, WP-6 | `legal_limits` 조례화 + `evidence` + `legal_refs` |
| **W3** | 최저/기본/최대 밴드 | WP-7 | `feasibility_band` |
| **W4** | 프론트 점진 렌더 + 회귀 | WP-8, WP-9 | UI 카드 + 골든 테스트 |

각 웨이브는 **독립 배포 가능**(additive). 중단해도 직전 웨이브까지 정상.

---

### WP-1 · 신규 모듈 `legal_reference_registry.py` (데이터 매핑만, 계산 0)
**파일**: `apps/api/app/services/data_validation/legal_reference_registry.py` (신규)

```python
# {근거 키 → 법령명·조문·title·url}. ②-3 검증표가 마스터.
LEGAL_REFERENCES: dict[str, dict[str, str]] = {
    "zone_use":      {"law_name": "국토의 계획 및 이용에 관한 법률",       "article": "제76조", "title": "용도지역에서의 건축물 제한",      "url": "https://www.law.go.kr/법령/국토의계획및이용에관한법률/제76조"},
    "bcr_law":       {"law_name": "국토의 계획 및 이용에 관한 법률",       "article": "제77조", "title": "용도지역의 건폐율",                "url": "https://www.law.go.kr/법령/국토의계획및이용에관한법률/제77조"},
    "far_law":       {"law_name": "국토의 계획 및 이용에 관한 법률",       "article": "제78조", "title": "용도지역의 용적률",                "url": "https://www.law.go.kr/법령/국토의계획및이용에관한법률/제78조"},
    "bcr_limit":     {"law_name": "국토의 계획 및 이용에 관한 법률 시행령", "article": "제84조", "title": "용도지역 안에서의 건폐율",        "url": "https://www.law.go.kr/법령/국토의계획및이용에관한법률시행령/제84조"},
    "far_limit":     {"law_name": "국토의 계획 및 이용에 관한 법률 시행령", "article": "제85조", "title": "용도지역 안에서의 용적률",        "url": "https://www.law.go.kr/법령/국토의계획및이용에관한법률시행령/제85조"},
    "bldg_bcr":      {"law_name": "건축법",                                "article": "제55조", "title": "건축물의 건폐율",                  "url": "https://www.law.go.kr/법령/건축법/제55조"},
    "bldg_far":      {"law_name": "건축법",                                "article": "제56조", "title": "건축물의 용적률",                  "url": "https://www.law.go.kr/법령/건축법/제56조"},
    "bldg_height":   {"law_name": "건축법",                                "article": "제61조", "title": "일조 등의 확보를 위한 높이제한",  "url": "https://www.law.go.kr/법령/건축법/제61조"},
    "parking":       {"law_name": "주차장법",                              "article": "제19조", "title": "부설주차장의 설치·지정",          "url": "https://www.law.go.kr/법령/주차장법/제19조"},
    # … ②-3 매핑표 전체 수록 (입지·법규 분석 공용 키 포함) …
    "ordinance_bcr": {"law_name": "{sigungu} 도시계획 조례", "article": "", "title": "건폐율", "url": ""},
    "ordinance_far": {"law_name": "{sigungu} 도시계획 조례", "article": "", "title": "용적률", "url": ""},
}

def get_legal_refs(keys: list[str], *, sigungu: str | None = None) -> list[dict]:
    """key→레코드. url_status = 'verified' if url else 'pending'. {sigungu} 치환."""

def inject_urls(url_map: dict[str, str]) -> None:
    """조례 등 동적 URL 주입(런타임 갱신)."""
```
- **스펙**: 순수 dict + 2 함수. import 부작용 0.
- **하위호환**: 신규 파일 → 기존 import 영향 **0**. URL 빈 슬롯이어도 `url_status:"pending"`로 안전.
- **Wave**: W0.

---

### WP-2 · `legal_zone_limits.py` — 조문키 노출 (가산만)
**파일**: `apps/api/app/services/zoning/legal_zone_limits.py`
- `LEGAL_BASIS` 옆에 `LEGAL_REF_KEYS = {"bcr": "bcr_limit", "far": "far_limit", "use": "zone_use"}` 상수 추가.
- `applicable_limits_for(...)` 반환 dict에 `"legal_ref_keys": [...]` **키 추가**(기존 키 전부 유지).
- **하위호환**: 추가 키만 → 기존 호출부(검증기 등) 무영향.
- **Wave**: W0.

---

### WP-3 · `precheck_service.py` — provenance(`inputs`) 조립 헬퍼
**파일**: `apps/api/app/services/precheck/precheck_service.py`
- 신규 내부 헬퍼 `_build_inputs(zoning_result, resolved_pnu, resolved_area, price_result) -> dict` 추가.
- `analyze_by_address` 반환의 채워진 키 + `coordinates`/`warnings` 유무로 `method/source/confidence` 판정.
- `official_price_per_sqm` null 시 `get_individual_land_price(pnu)` **1회 보강**(wait_for 가드, 실패 시 `method:"fallback"`).
- 응답에 `"inputs": _build_inputs(...)` **가산**.
- **하위호환**: 신규 키 1개 가산. 기존 응답 불변. SLA: 보강 호출은 가격 누락 시에만 → 평시 외부호출 1회 유지.
- **Wave**: W1.

---

### WP-4 · `precheck_service.py` — 검증(`data_quality`) 조립 헬퍼
**파일**: `apps/api/app/services/precheck/precheck_service.py`
- 신규 헬퍼 `_build_data_quality(used_sources, quantitative_reliable) -> dict`.
- `CalculationMetadata("precheck")`에 사용 소스 `add_source`, `PublicDataRegistry`/`FreshnessChecker`로 `sources_meta`·`warnings`·`disclaimer` 채움.
- `quantitative_reliable`은 **기존 `pnu` 차단 분기(:194)와 동일 조건** 재사용.
- 응답에 `"data_quality": _build_data_quality(...)` **가산**.
- **하위호환**: 신규 키 1개 가산. `ok:false` 응답에도 `quantitative_reliable:false`만 부착 가능.
- **Wave**: W1.

---

### WP-5 · `precheck_service.py` — `_legal_limits` 조례 적용형 rewire + `legal_refs`
**파일**: `apps/api/app/services/precheck/precheck_service.py`
- 시그니처 **확장**: `def _legal_limits(zone_type)` → `async def _legal_limits(zone_type, address)` (조례 조회에 address·sigungu 필요).
  - 내부: `OrdinanceService().get_ordinance_limits(address, zone_type)` → `applicable_limits_for(zone_type, sigungu, regulation_payload=ord_result)`.
  - **기존 반환 키 `bcr_pct/far_pct/height_m/source` 유지** + `applied_bcr_pct/applied_far_pct/ordinance_confirmed/far_source/legal_ref_keys` 가산.
- 호출부(:205) `legal = _legal_limits(zone_type)` → `legal = await _legal_limits(zone_type, address)`로 1줄 수정.
- 응답에 `legal_refs = get_legal_refs(legal["legal_ref_keys"], sigungu=...)` **가산**.
- **하위호환**: 반환 키 가산만(기존 4키 보존) → `_area_checks`(`bcr_pct/far_pct` 의존)·프론트 무영향. 조례 미확인 시 `applied_*`는 법정상한으로 폴백(현행 동작과 동일값).
- **위험/완화**: `get_ordinance_limits`는 외부 API 가능 → 조례 조회 실패 시 **법정상한 폴백**(추가 외부호출은 캐시/타임아웃 가드, SLA 내). 보수적: 조례 확인 안 되면 `ordinance_confirmed:false`로 표기.
- **Wave**: W2.

---

### WP-6 · `precheck_service.py` — 근거 트레이스(`evidence`) 조립 헬퍼
**파일**: `apps/api/app/services/precheck/precheck_service.py`
- 신규 헬퍼 `_build_evidence(legal, area_checks, feasibility_base|None) -> list[dict]`.
- `applicable_limits_for` 결과의 `far_source/sources`를 `formula/inputs/result`로 직렬화. `legal_ref_keys`로 `legal_refs`와 조인.
- feasibility 밴드 미산출(W2 시점) 시 `ev_feasibility_*`는 생략(W3에서 추가).
- 응답에 `"evidence": _build_evidence(...)` **가산**.
- **하위호환**: 신규 키 1개 가산.
- **Wave**: W2.

---

### WP-7 · `precheck_service.py` — 최저/기본/최대(`feasibility_band`)
**파일**: `apps/api/app/services/precheck/precheck_service.py`
- 신규 헬퍼 `_build_feasibility_band(best_code, zone_type, legal, inputs) -> dict | None`.
  - best 후보→`ModuleInput` 구성(`FeasibilityServiceV2`의 typical 헬퍼 활용). `calculate_fn(values)` 클로저→`FeasibilityServiceV2.calculate`→`aggregate_feasibility`/`determine_grade`.
  - `run_sensitivity_analysis`에 **deltas `[-15,0,+15]` 3점**(`sale_price`,`construction_cost`) 전달 → min/base/max 추출, tornado로 `band_drivers`.
- best가 없거나(`summary.best=None`) 정량 신뢰불가면 **None**(밴드 생략) — 빈 결과 금지·과장 금지.
- 응답에 `"feasibility_band": _build_feasibility_band(...)` **가산**, evidence에 `ev_feasibility_*` 추가.
- **하위호환**: 신규 키 1개 가산. best 후보 **1건만** 3점 → 90초 SLA 보호. Monte Carlo는 상세 탭으로 분리(precheck 기본 제외).
- **Wave**: W3.

---

### WP-8 · 프론트 — 점진 렌더 (선택적 필드)
**파일**: 프론트 precheck 타입/컴포넌트(예: `apps/web/.../precheck` 타입 모듈 + 결과 카드).
- 응답 타입에 5블록을 **optional 필드**로 확장(`inputs?`,`data_quality?`,`feasibility_band?`,`evidence?`,`legal_refs?`).
- UI 카드: ① 자동입력 출처 배지(`method` 색상), ② 데이터 품질/면책 패널, ③ 최저·기본·최대 밴드 차트, ④ 수치 옆 [원문] 링크(`evidence.legal_ref_keys`↔`legal_refs.key` 조인).
- **하위호환**: optional → 백엔드가 블록 누락해도 기존 화면 정상. 백엔드 웨이브와 **독립 배포**.
- **Wave**: W4.

---

### WP-9 · 회귀·골든 테스트
**파일**: `apps/api/.../tests/` (precheck 관련).
- **골든 응답 스냅샷**: 기존 9키가 1개도 빠지지 않음을 보장하는 회귀 테스트(additive 불변식).
- 차단 분기(`zone_type`/`pnu` 미확인) `ok:false` + message 유지 검증.
- `inputs.method` 판정·`data_quality.quantitative_reliable`=pnu 조건 일치·`feasibility_band` 3점 단조성(min≤base≤max NPV) 검증.
- `legal_refs` URL 형식(②-1 규칙: `제N조`·한글주소) lint.
- 90초 SLA: 외부호출 횟수(평시 1회, 가격 누락 시 +1, 조례 조회 캐시) 검증.
- **Wave**: W4.

---

## 부록 A · additive 불변식 (모든 WP 공통 게이트)

1. 기존 응답 9키(`ok/address/pnu/zone_type/area_sqm/legal_limits/methods/summary/elapsed_ms/sources`) **제거·의미변경 금지**. `legal_limits` 내부 `bcr_pct/far_pct/height_m/source`도 보존.
2. 신규 산출물은 **데이터 매핑 모듈 1개**(WP-1) + **precheck 내부 헬퍼**만. **새 계산/조닝/검증 엔진 0개.**
3. 모든 신규 블록은 **선택적** — 누락/실패해도 기존 화면·계약 정상.
4. 빈 결과 금지·필지 미확인 시 정량 차단·90초 SLA **불변**.
5. feasibility 밴드는 best **1건만** 3점 계산(SLA 보호). Monte Carlo는 상세 탭 분리.

## 부록 B · 법령링크 게재 전 체크리스트

- `url_status:"verified_pattern"`(⚠️) 항목은 게재 직전 **클릭 1회 점검**(도시개발법·공공주택특별법·지방세법 본문, 각 시행령 개별 조문, 조례 조문).
- 조례는 **지자체명 완전 포함** 확인 + 현행 여부 재확인.
- 도심복합개발법(2024 신법)은 **현행본 조문구조 재확인**.
- 저장/전송 형태는 **percent-encoding 또는 공백제거형**(`+` 지양).

---

### 출처(법령 딥링크 검증)
- 법제처 보도자료 — 법령정보식별주소
- 한국법제연구원(KLRI) 한글주소 사용법 가이드 (`openlaw.klri.re.kr/service/hanguide`)
- 국가법령정보 공동활용 OPEN API 안내
- law.go.kr 한글주소 실접속/교차확인: 국토계획법 제78조, 건축법 제61조, 주차장법 제19조 외

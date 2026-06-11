# 플랫폼 공통 인프라 시너지 청사진 (PLATFORM_INFRA_SYNERGY)

- **문서 버전**: 2026-06-11
- **작성**: PropAI 수석 아키텍트
- **대상**: 3축 분석(신뢰·근거 / 데이터흐름·자동입력 / 페이지 시너지)에서 도출된 공통 인프라 후보의 종합·중복제거·우선순위화
- **설계 원칙(절대 준수)**: **새 엔진 0개 · 기존 자산 재사용 · additive(가산)**. 신규 산출물은 *데이터 매핑 모듈*과 *조립 헬퍼*, *공통 컴포넌트 추출*에 한정한다. 기존 응답 필드·store 키·계약을 1개도 제거/변경하지 않는다.
- **정합 기준 문서**: `PRECHECK_UPGRADE_BLUEPRINT_2026-06-11.md`(90초 진단 고도화), `PLATFORM_FEATURE_AUDIT_2026-06-11.md`(기능 실사). 본 문서의 모든 인프라는 두 문서와 모순 없이 결합되도록 설계됐다.

> 본 청사진은 11개 인프라 후보를 4개 레이어로 수렴시킨다. 후보들은 서로 다른 이름으로 동일한 근본 문제를 가리키고 있었다 — **"같은 부지·같은 법조·같은 수치가 모듈마다 따로 해석되고, 한쪽의 분석 결과가 다른 쪽으로 흐르지 않는다."** 이를 *부지 해석*·*신뢰 표식*·*프론트 공통 부품*·*시너지 결선*의 4개 횡단 인프라로 1벌화한다.

---

## ① 핵심 통찰 — 지금 무엇이 모듈마다 중복/단절인가

실사(`PLATFORM_FEATURE_AUDIT`)의 한 줄 진단은 **"계산 엔진은 충실하나 연결 고리가 끊긴 플랫폼"** 이다. 11개 후보를 가로질러 보면 중복·단절은 **4가지 구조 패턴**으로 압축된다.

### 통찰 1 — 법조 표기가 producer마다 자유문자열이라 동일 법조차 불일치한다

같은 법조가 코드 위치마다 다른 문자열로 적혀 있다:

| 위치 | 표기 |
|---|---|
| `regulation_service.py:38` | `국토의 계획 및 이용에 관한 법률 시행령 제71조` |
| `regulation_service.py:47·56·65` | `국토계획법 시행령 제71조` |
| `ordinance_service.py:199` | `국토의 계획 및 이용에 관한 법률 시행령 제84조, 제85조` |
| `legal_zone_limits.py:22 LEGAL_BASIS` | `국토계획법 시행령 제84·85조` |

모델 default 컬럼(`v58_extensions.py:56·70·97`, `esg.py:41`, `tax_regional.py:35·98`, `project.py:85`)과 서비스 8경로(`design_review_service.py`, `alris_service.py:104`, `smart_city_service.py:27`, `special_project_service.py:23`, `disaster_risk_service.py:36`, `upzoning_potential.py:46~90`)까지 **전부 자유문자열**. law.go.kr 딥링크는 user-facing 0건이다(`ordinance_service`의 `MOLEG_ORDIN_*_URL`은 조례본문 fetch용 내부 API). → **클릭 가능한 단일 근거(SSOT)가 없다.**

### 통찰 2 — "수치 → 근거" 자산이 만들어져 있는데 화면에 도달하지 못한다

신뢰의 3요소(법령·계산·출처)가 **백엔드엔 존재하나 단절**돼 있다:

- **계산 트레이스**: `calc_ledger.py`(용적률/순이익/수익률/평당공사비/취득세 6종 결정론 재계산)는 완성됐으나 `VerificationBadge` 경유로만 노출되고 화면 일부에만 배치.
- **계산 메타**: `calculation_metadata.CalculationMetadata`(출처·신선도·confidence·disclaimer)는 `revenue_engine.py:136`·`tax_ai_service.py` 4곳만 부착 — 38종 세금·12단계 원가·DCF·ESG 대부분 미부착. 프론트에서 `_metadata`가 구조적으로 렌더되는 곳이 사실상 없음(`DeskAppraisalReportClient.tsx:461`의 disclaimer 텍스트만).
- **신선도**: `public_data_registry.PublicDataRegistry`(17개 소스 health)·`validator.FreshnessChecker`(거래30일/공시지가365일/조례90일)는 `data_integrity.py`에서만 소비되고 **분석 응답에 주입 안 됨**(`auction_service.py` 1곳만 추가 사용).
- **프론트 provenance**: `FieldSourceBadge.tsx`(파랑=수동/회색=자동)·`DataLineageTooltip.tsx`·store `manualFields`(`FieldProvenance`)는 잘 구축됐으나 `ProvenanceModule`이 `siteAnalysis`|`cost` **2개뿐** — design·tax·esg 미등록. `AutoZoningBadge.tsx`는 `zone_limits.legal_basis`를 받고도 **미표시**.

→ **부품은 다 있는데, "이 숫자가 언제·어디서·어떤 산식·어떤 법으로 나왔나"가 모듈마다 따로 처리되거나 누락된다.**

### 통찰 3 — 동일 부지가 화면마다 다른 깊이로 해석되고, 입력이 SSOT에 환류되지 않는다

- **부지 해석 진입점 분산**: 주소→PNU→용도지역·면적·공시지가·조례 해석이 20개+ 소비처에 흩어져 경량/종합 선택·PNU 폴백·필드 매핑이 제각각. `bcode→PNU` 구성이 `auto_zoning.py:39-59`와 `regulation.py:50-55`에 **중복**.
- **자동입력 손코딩**: SSOT store는 76개 파일이 소비하나 패턴이 페이지마다 손코딩(`siteAnalysis` 직접 구조분해 + `addr||siteAnalysis?.address` 폴백). `PreCheckWorkspace`는 store **미연결**(bare `useState`)이라 90초 진단 결과가 SSOT에 환류되지 않는다 — *"한 번 입력, 전 모듈 자동"* 원칙의 최대 단절점.
- **프로젝트 선택 UI 3원화**: `ProjectAddressInput` 임베드 picker(14곳)·`ProjectSwitcher`(스튜디오 2곳, 복원 로직 없음)·precheck(picker 전무)로 분기. `ProjectSwitcher`는 `setProject`만 호출해 스냅샷 복원/주소 보강을 안 함(동작 불일치).
- **캐스케이드 수동 등록**: `MODULE_UPSTREAM`이 닫힌 enum 기반 하드코딩 Record(`useProjectContextStore.ts:209-228`)라 신규 모듈은 5곳을 수동 편집해야 합류 — 누락 시 조용히 stale 추적에서 빠진다.

### 통찰 4 — 한쪽 페이지의 정밀 분석이 다른 페이지로 1g도 흐르지 않는다 (끊긴 시너지)

깔때기 진입(`GlobalAddressSearch→/zoning/comprehensive`)은 ordinance·PNU·용도지역을 SSOT에 써넣어 하류가 자동 재사용한다. 그러나 **독립 메뉴는 read만 하고 write-back을 안 한다**:

- `RegulationsWorkspaceClient` — ordinance writer 부재
- `PermitAiWorkspaceClient` — `updateComplianceData` 호출 0
- `MarketInsightsWorkspaceClient` — store write 0
- 수지의 핵심 변수 **평당 분양가**는 시세 AI(`MarketInsights`)·`PricingConfigPanel`이 산출하는데도 `ModuleInputForm.tsx:242-243`에서 **수동 NumberInput** — 사용자가 같은 숫자를 화면 3개에 손으로 옮긴다.
- **중앙분석센터는 집계·교차검증 허브가 아니다** — 홈은 히어로+KPI일 뿐, 모듈 간 정합 체크(법정한도↔설계 FAR↔수지 가정 FAR, 공사비 개산↔수지 주입액)가 어디에도 없다.

> **종합 결론**: 신규 엔진 개발이 아니라 **공통 인프라 4레이어로 "배선 복원 + 표식 통일"** 이 최우선이다. 11개 후보는 이 4레이어로 무손실 수렴한다.

---

## ② 기반 인프라 레이어 설계

4개 횡단 레이어. 각 레이어는 후보 JSON을 흡수하며, 모두 *기존 자산 재사용 + additive* 원칙을 따른다.

### (a) 부지 컨텍스트 해석기 — **SiteResolver** + useSiteContext + ProjectPicker + 모듈 레지스트리

> 흡수 후보: `SiteResolver`(단일 파사드), `useSiteContext`(자동입력 훅), `ProjectPicker`(3원화 통합), `모듈 의존성 레지스트리`(staleness 자동 등록), `SSOT 라이트백 어댑터`.

**백엔드 — SiteResolver 단일 파사드 (신규 엔진 0)**

- `LandInfoService.collect_comprehensive`(`land_info_service.py:284-596`)가 이미 종합 파사드 역할 → 여기에 **`resolve(address, pnu, depth=lite|full)` 단일 시그니처**를 씌운다.
- `AutoZoningService.analyze_by_address`(`auto_zoning_service.py:45`)를 내부 `lite` 경로로 흡수.
- `bcode→PNU` 구성(`_build_pnu_from_bcode`)을 SiteResolver 정적 헬퍼로 **1벌화**(현재 `auto_zoning.py`/`regulation.py` 중복 제거).
- 인프로세스 TTL 캐시(`_COMP_CACHE`, `land_info_service.py:28-46`)를 파사드 레벨로 끌어올려 한 세션 내 중복 VWorld/MOLIT 호출을 전 모듈에서 제거(지연·과금 동시 절감).
- **결과**: 9종 백엔드 소비처(`project_pipeline.py` L458·646·658·880·907, `feasibility_service_v2.py:102`, `regulation_analysis_service.py:68`, `precheck_service.py:169·312`, `permit_analysis_service.py:155`, `market_report_service.py:163·187`, `scenario_simulator.py:193·242` 등)가 **동일 PNU·동일 용도지역·동일 zone_limits**를 보장받는다.

**프론트 — useSiteContext 공통 훅 (3줄 자동입력)**

- `useProjectContextStore`의 `updateSiteAnalysis`(meta provenance 포함, `:657-702`)·`setProject` 스냅샷 복원을 래핑.
- `ProjectAddressInput.tsx:65-87`의 *"컨텍스트 주소 자동 반영 + 이전 프로젝트 복원"* 패턴을 훅으로 추출.
- 반환: `{ address, pnu, zone, area, ordinance, provenance, resolve() }` → 신규 페이지가 **3줄로 자동입력 + 수동값(source:user) 보호 + staleness 연동**을 동시 획득.
- `PreCheckWorkspace`(store 미연결)를 이 훅으로 연결 → precheck 결과를 `resolve()`로 SSOT에 **환류** → 진단→부지분석→설계가 입력 1회로 자동 시드.

**프론트 — ProjectPicker 공통 컴포넌트 (3원화 통합)**

- `ProjectAddressInput.handleSelectProject`(`:73-87` — `setProject`로 스냅샷 복원 후 레코드값 보강)를 **정본**으로 채택.
- `ProjectSwitcher`(design-studio·bim-studio)를 이 컴포넌트로 대체 → 어느 페이지에서 고르든 동일하게 스냅샷·주소·면적·PNU 보강.
- precheck에 picker 신설 → 기존 프로젝트로 90초 재진단 가능(진단↔프로젝트 양방향).

**모듈 의존성 레지스트리 — 캐스케이드 자동 등록**

- `MODULE_UPSTREAM` 그래프와 `isStale`/`isReadyForFirstCompute`(`:851-872`)는 유지(회귀 테스트 `cascade.test.ts`로 고정됨).
- `registerModule({ key, upstream, readyFn })` 진입점을 추가해 `isModuleReady`/`isStageDataReady` switch 분기들을 **데이터화** → 신규 모듈 추가가 **1엔트리**로 끝나고 누락 버그 원천 차단.

**SSOT 라이트백 어댑터 — 독립 페이지 환류 (통찰 4 해소)**

- 각 독립 페이지 분석 성공 시 **1줄 환류** 추가: `RegulationsWorkspaceClient`→`updateSiteAnalysis(ordinance)`, `PermitAiWorkspaceClient`→`updateComplianceData`, `MarketInsightsWorkspaceClient`→분양가 write.
- `manualFields`(source:'user') 가드가 이미 있어 사용자 입력은 보호됨. `GlobalAddressSearch.tsx:91-122`의 write 패턴을 그대로 복제.

### (b) 신뢰 레이어 — legal_reference_registry + 근거트레이스 + provenance + 할루시네이션 검증

> 흡수 후보: `legal_reference_registry`(law.go.kr SSOT), `CalcTrace 응답계약 + 공통 근거 패널`, `데이터 출처·신선도 공통 컴포넌트 + provenance 확장`. **PRECHECK_UPGRADE_BLUEPRINT의 WP-1과 동일 모듈을 공유한다.**

**b-1. legal_reference_registry — law.go.kr 딥링크 단일 SSOT**

- **신규 파일**(계산 0): `apps/api/app/services/data_validation/legal_reference_registry.py`. `{ key → {law_name, article, title, url, url_status} }` 순수 dict + `get_legal_refs(keys, sigungu)` / `inject_urls(url_map)` 2함수.
- 마스터 데이터는 PRECHECK 블루프린트 **②-3 검증표**(법령정보식별주소 = law.go.kr 한글주소, 개정 시 자동 현행본). `legal_zone_limits.py:22 LEGAL_BASIS`와 `upzoning_potential.py` path별 `legal_basis` 딕셔너리를 **시드로 흡수**.
- `building_compliance.py`가 이미 룰별 `legal_basis`를 직렬화(`:421·499`)하므로 **레지스트리 키로 치환만** 하면 됨.
- `ordinance_service`의 law.go.kr API 연동 코드는 그대로 두고 *표시용 딥링크* 매핑만 신설.
- **결과**: 9개 producer(규제·진단·인허가·설계법규·세금·ESG·상향개발·조례·감정보고서)가 동일한 정규 `{law_id, 조문, 표준명칭, URL}`로 수렴.

**b-2. 근거 트레이스 응답계약 (CalcTrace contract) + 공통 근거 패널**

- 분리된 두 트레이스 자산을 **단일 응답 계약**으로 통합: `{ 값, 입력, 산식, 법정값/근거, 출처 }`.
- 백본 재사용: `calc_ledger.run_calc_checks`(6종 산식·`_CHECKS` 테이블)와 `calculation_metadata.to_dict()`를 그대로 사용 — **새 계산 로직 0**.
- 프론트: `VerificationBadge.tsx`의 calc_checks 렌더 블록(`:136-150`, `name(formula) · 출력≠계산`)을 추출해 **독립 `EvidencePanel` 컴포넌트화**(`AnalysisVerdict.tsx` 재사용).
- 점진 부착: 현재 4곳만 붙은 `_metadata`를 38종 세금·원가·DCF·ESG로 확산(엔진 무변경, 출력에 메타만 가산).

**b-3. 데이터 출처·신선도 공통 컴포넌트 + provenance 모듈 확장**

- 완성품 재사용: `FieldSourceBadge.tsx`·`DataLineageTooltip.tsx`·store `manualFields`/`getFieldProvenance`/`revertFieldToAuto`(`:202·296`).
- `ProvenanceModule` 유니온에 **design·tax·esg 추가**(현재 siteAnalysis·cost 2개뿐) → 신규 페이지에 배지/툴팁만 배치.
- 백엔드: `PublicDataRegistry.get_status()`·`FreshnessChecker.check()`를 분석 응답 메타에 주입하는 **어댑터만 신설**(엔진 로직 무변경).

**b-4. 색 체계 통일 (3요소를 하나의 시각 언어로)**

`calculation_metadata.confidence_level`(하드코딩→medium 강등)과 `FieldSourceBadge`의 user/auto를 **같은 색 체계(파랑=신뢰/직접, 회색=자동/추정, 황·적=경고/강등)** 로 통일 → 진단→설계→수지 전 모듈이 동일한 *신뢰 표식 언어*를 공유.

### (c) 공통 프론트 컴포넌트 — ProjectPicker · EvidencePanel · LegalRefChip · FieldSourceBadge

4개 공통 컴포넌트로 모든 분석 페이지가 동일 UX 부품을 공유한다.

| 컴포넌트 | 추출 출처(재사용) | 역할 | 결합 데이터 |
|---|---|---|---|
| **ProjectPicker** | `ProjectAddressInput.handleSelectProject:73-87` | 프로젝트 선택 시 스냅샷 복원+주소·면적·PNU 보강 (3원화 통합) | useSiteContext / snapshots |
| **EvidencePanel** | `VerificationBadge.tsx:136-150` + `AnalysisVerdict.tsx` | 수치별 `{값·입력·산식·법정값·출처}` 트레이스 렌더 + 신선도 경고 | CalcTrace 응답계약 (b-2) |
| **LegalRefChip** | `AutoZoningBadge.tsx`(legal_basis 미표시 → 클릭 칩으로) | 법조를 클릭 가능한 law.go.kr 딥링크 칩으로 표시 | legal_reference_registry (b-1) |
| **FieldSourceBadge** | `FieldSourceBadge.tsx`·`DataLineageTooltip.tsx`(완성품) | 필드 출처/방식(파랑=수동·회색=자동)·수집시각·신선도 표시 | provenance + FreshnessChecker (b-3) |

**핵심 결합**: `EvidencePanel`의 한 칩에서 세 인프라가 수렴한다 —
> *"제시 350% = 입력(연면적/대지) 산출 ÷ 법정상한 300%([국토계획법 시행령 제85조 원문](LegalRefChip)) 초과 · 공시지가 base_year 2025([FieldSourceBadge])"*

`calc_ledger`의 `용적률=연면적/대지×100` 산식(b-2) + `legal_zone_limits` 제84·85조 상한(b-1) + 신선도(b-3)가 **하나의 패널**에서 완결된다.

---

## ③ 인프라 × 페이지 적용 매트릭스

행=인프라, 열=페이지. ●=핵심 적용(첫 파일럿/주 소비), ○=적용, ·=해당 없음. **P**=파일럿 첫 적용처.

| 인프라 \ 페이지 | 90초진단(precheck) | 규제연동(regulations) | 부지분석/진단 | 인허가(permit) | 설계(design) | 수지/세금(feasibility) | 공사비/적산(cost) | 시장·시세(market) | ESG | 보고서 | 중앙분석센터 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **SiteResolver**(파사드) | ●P | ● | ● | ● | ○ | ● | ○ | ● | ○ | ○ | ○ |
| **useSiteContext**(훅) | ●P | ● | ● | ○ | ○ | ● | ○ | ○ | ○ | · | ○ |
| **ProjectPicker** | ●P | ○ | ○ | ○ | ●(스튜디오) | ○ | ○ | ○ | ○ | ○ | ● |
| **모듈 레지스트리** | ○ | ○ | ● | ○ | ● | ● | ● | ○ | ● | ○ | ● |
| **라이트백 어댑터** | ●P | ●P | ● | ● | ○ | ● | ○ | ●P | ○ | · | ○ |
| **legal_reference_registry** | ●P | ●P | ○ | ● | ● | ○ | · | · | ○ | ○ | ○ |
| **CalcTrace + EvidencePanel** | ●P | ○ | ○ | ○ | ○ | ● | ● | ○ | ○ | ● | ● |
| **provenance + 신선도** | ●P | ○ | ● | ○ | ○ | ● | ● | ○ | ○ | ○ | ○ |
| **LegalRefChip** | ●P | ●P | ● | ● | ● | ○ | · | · | ○ | ○ | ○ |
| **FieldSourceBadge** | ●P | ○ | ● | ○ | ○ | ● | ● | ○ | ○ | ○ | ○ |

**판독**: precheck(90초 진단)와 regulations(규제연동)가 거의 모든 인프라의 **첫 적용처(P)** 다. 이는 PRECHECK_UPGRADE_BLUEPRINT가 이미 이 두 흐름에서 registry·provenance·evidence·legal_refs를 가산하도록 설계됐기 때문 — **인프라를 별도로 만드는 것이 아니라 블루프린트의 WP들이 곧 인프라의 파일럿 구현**이 된다.

---

## ④ 시너지 묶음 Top 5

각 묶음은 *복수 인프라가 결합될 때 1+1>2가 되는* 지점. 우선순위순.

### 묶음 1 — 법정한도 단일근거 체인 (규제→90초진단→설계 하드캡→수지)

`SiteResolver`로 모든 페이지가 동일 zone_limits를 받고, `legal_reference_registry`가 그 한도에 클릭 가능한 근거를 붙이며, `EvidencePanel`이 `min(법정,조례)` 트레이스를 렌더한다. precheck의 `/precheck/instant`가 자체 산출하던 법정한도를 SiteResolver 단일 경로로 합치면 **진단↔규제↔설계 하드캡↔수지 FAR가 모순 없는 한 근거를 공유**한다. → 블루프린트 WP-2·WP-5·WP-6와 동일.

### 묶음 2 — EvidencePanel = 세 인프라 수렴 칩 (법령·계산·출처)

`legal_reference_registry`(법령) + `calc_ledger`(계산 트레이스) + `FreshnessChecker`(출처·신선도)가 **하나의 EvidencePanel 칩**으로 표출. "용적률 200%가 왜 나왔나"에 산식·법정상한·법령원문·base_year가 한 패널에서 답한다. → 신뢰 서사의 완성, 블루프린트 G4·G5.

### 묶음 3 — 시세↔수지 revenue 양방향 결선 (분양가 수동 재입력 제거)

`라이트백 어댑터`로 `MarketInsights`의 AI 분양가(`avm.estimated_price`)·`PricingConfigPanel`의 LLM 제안이 수지 `avg_sale_price_per_pyeong`에 자동 시드. `모듈 레지스트리`가 시세 갱신 시 feasibility staleness를 자동 발화 → 매출·UnitMix·ROI 재계산. **"시장조사→사업성"이 끊김 없는 한 흐름.**

### 묶음 4 — 입력 1회 → 전 페이지 자동 (useSiteContext + ProjectPicker + 라이트백)

`useSiteContext` 훅으로 신규 페이지가 3줄로 자동입력, `ProjectPicker`로 어디서든 동일 복원, `라이트백 어댑터`로 독립 페이지 분석이 SSOT에 환류. precheck를 store에 연결하는 순간 **여정 입구(90초 진단)가 SSOT에 합류**해 진단→부지분석→설계→수지가 입력 1회로 시드된다.

### 묶음 5 — 중앙분석센터 = 교차검증 허브

`모듈 레지스트리`의 완성도 셀렉터(`projectCompleteness` 7단계·`feasibilityCompleteness` 4단계)와 `EvidencePanel`의 교차검증 표시를 포트폴리오 레벨로 승격. **법정한도↔설계 FAR**, **공사비 개산↔수지 주입액** 정합 체크를 더하면 대시보드가 *오류·과대평가 조기경보 허브*가 된다(수지 계산 이원화 불일치도 자동 표면화).

---

## ⑤ 구현 로드맵 — 파일럿→확산 웨이브

**파일럿 = 90초 진단(precheck) + 규제연동(regulations)**. 이 두 흐름은 PRECHECK_UPGRADE_BLUEPRINT가 이미 WP로 분해해 둔 곳이므로, **블루프린트 실행이 곧 인프라의 첫 구현**이다. 이후 동일 부품을 나머지 페이지로 확산한다. 모든 웨이브 additive·독립 배포.

### Wave 0 — 데이터 기반 (응답 변화 0, 준비만)

| 산출 | 인프라 | 블루프린트 정합 |
|---|---|---|
| `legal_reference_registry.py` 신규(②-3 마스터) | legal_reference_registry | **WP-1과 동일 모듈** |
| `legal_zone_limits.py`에 `LEGAL_REF_KEYS` + `legal_ref_keys` 가산 | legal_reference_registry | **WP-2와 동일** |
| `SiteResolver.resolve()` 시그니처 + `bcode→PNU` 1벌화 | SiteResolver | 신규(블루프린트 비파괴) |
| `registerModule()` 진입점(switch 데이터화) | 모듈 레지스트리 | `cascade.test.ts` 회귀 유지 |

### Wave 1 — 파일럿: 90초 진단에 신뢰 표식 표면화

- `inputs`(provenance) + `data_quality`(할루시네이션 검증) 가산 → **블루프린트 WP-3·WP-4와 동일**.
- 프론트 `FieldSourceBadge`·provenance를 precheck에 첫 적용. `ProvenanceModule`에 precheck 등록.
- `PreCheckWorkspace`를 `useSiteContext`로 store 연결(환류 시작).

### Wave 2 — 파일럿: 규제연동 + 근거·법령링크

- precheck `_legal_limits` 조례 적용형 rewire + `evidence` + `legal_refs` 가산 → **블루프린트 WP-5·WP-6와 동일**.
- `regulations` 페이지: `SiteResolver` 경유 통일 + `LegalRefChip`·`EvidencePanel` 첫 적용 + 라이트백(ordinance writer 신설).
- `AutoZoningBadge`의 미표시 `legal_basis`를 `LegalRefChip`로 전환.

### Wave 3 — 파일럿: 최저/기본/최대 밴드 + 교차검증 씨앗

- precheck `feasibility_band` 가산 → **블루프린트 WP-7와 동일**(best 1건 3점, 90초 SLA 보호).
- `EvidencePanel`에 `ev_feasibility_*` 트레이스 결합(묶음 2 완성).

### Wave 4 — 확산: 수지·설계·시장으로

- `CalcTrace + EvidencePanel`을 수지(38종 세금·DCF)·공사비(평당공사비 검증)·설계(FAR/BCR)로 확산.
- `라이트백 어댑터`: 시세→수지 분양가 결선(묶음 3), 인허가→completeness 자동완료.
- `ProvenanceModule` design·tax·esg 등록 완료.
- `ProjectPicker`로 design-studio·bim-studio `ProjectSwitcher` 대체.

### Wave 5 — 확산: 중앙분석센터 교차검증 허브 (묶음 5)

- `projectCompleteness`/`feasibilityCompleteness`를 포트폴리오로 승격, 모듈 간 정합 체크(법정한도↔설계 FAR, 공사비↔수지) 추가.

### 웨이브 의존도

```
W0(registry·SiteResolver·레지스트리) ─┬─> W1(precheck provenance/검증)
                                      ├─> W2(규제 조례·근거·법령링크)  ──> W3(밴드+근거결합)
                                      └─> W4(수지·설계·시장 확산) ──> W5(교차검증 허브)
```

각 웨이브 중단해도 직전까지 정상. W1~W3은 PRECHECK_UPGRADE_BLUEPRINT의 W1~W3와 **1:1 정합**(인프라가 그 WP를 재사용 가능한 공통 부품으로 추출하는 차이만).

---

## 부록 — additive 불변식 (모든 웨이브 공통 게이트)

1. **새 엔진 0개**: 신규 산출물은 `legal_reference_registry.py`(매핑) + `SiteResolver` 파사드(기존 `collect_comprehensive` 위 시그니처) + `registerModule()` 진입점 + 프론트 컴포넌트 추출만. 계산/조닝/검증 엔진 무신설.
2. **기존 자산 재사용**: `calc_ledger`·`CalculationMetadata`·`PublicDataRegistry`·`FreshnessChecker`·`FieldSourceBadge`·`DataLineageTooltip`·`VerificationBadge`·`manualFields`·`MODULE_UPSTREAM`은 백본 그대로 사용.
3. **additive**: 응답 신규 키·store 신규 모듈·컴포넌트 신규 prop은 전부 **가산·선택적(optional)**. 기존 응답 키·`types.ts` 인터페이스·store 계약·`cascade.test.ts` 회귀 불변.
4. **provenance 가드**: 라이트백·자동입력은 `manualFields(source:'user')`를 항상 보호.
5. **SLA·차단 우선**: 90초 SLA, 빈 결과 금지, 필지 미확인 정량 차단(블루프린트 부록 A)은 SiteResolver 도입 후에도 불변.
6. **PRECHECK 정합**: precheck 관련 모든 변경은 PRECHECK_UPGRADE_BLUEPRINT의 WP 번호·웨이브와 충돌 없이 동일 모듈을 공유한다.

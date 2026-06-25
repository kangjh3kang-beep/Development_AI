# 실무형 건축개요·설계 자동화 시스템 고도화 — 통합 구현계획 (2026-06-25)

3개 OMC 조사(외부플랫폼·한국실무/법규·코드감사) 통합. 사용자 지적("round(far/30) 권장층수는 비실무·유형별 목적함수가 다름") + 목표 파이프라인 반영.

## 0. 진단 (조사 근거)

### 외부 플랫폼 (전이 기법 Top)
- 유형별 목적함수 차등을 명시한 곳은 드묾(Delve·DBF 멀티오브젝티브 정도) → **우리 차별화 빈틈**.
- 차용: ①유형별 솔버 프리셋/타이폴로지 스키마(TestFit·Archistar) ②정북일조·동간거리 하드제약 역산(텐일레븐 GA+레이캐스트 특허 KR101674970B1) ③envelope 추출 후 패킹(Archistar·Lendlease 특허 US11727173B2 그리디 유닛믹스) ④높이↔건폐율 트레이드오프 멀티오브젝티브+사용자가중(Delve) ⑤일조 ML 대리모델(DBF 선형회귀 96.7%) ⑥용도별 재무 pro-forma(Deepblocks) ⑦함수합성 DAG(Hypar). ★딥RL(스페이스워크)은 검색공간 10^210급에서만 정당화 — 우리는 규칙기반+경량최적화로 실무괴리 해소 충분.

### 한국 실무·법규 (코드화 결정론 규칙)
- **공동주택**: 채광인동간격(§86③ 0.5H·나목 max(10,0.5H_low)·라목8m·마목4m)+동지 9~15시 연속2h가 binding → "높이↑·건폐율↓"는 명령이 아니라 인동간격·일조 충족의 **결과**(비워진 지상=동간/조경/통경축). 판상=일조균일, 탑상=풍환경.
- **빌라/도생/연립**: 정북일조사선(§61①/§86①: 10m↓ 1.5m / 10m초과 0.5H)이 층수 지배 → 건폐율 최대(제2종60%)+북측 계단식후퇴. 필로티 1층주차=주택층수 제외(다세대4층/다가구3층 요건).
- **상업**: 건폐·용적 동시최대(포디움+타워). 정북일조 원칙 미적용(인접 주거면 적용).
- **★주상복합/준주거**: 비주거 의무비율 2트랙(상업지=연면적 20%→2025 10% / 준주거=용적률10% 2025폐지). 오피스텔 비주거 인정 **지자체 편차**(서울·부천·하남 불인정 / 인천 50% / 대전 인정방향) — 디벨로퍼 핵심.
- 미확인 정직표기: 별표3 비주거 구간별 차등용적률 수치·수원/고양 비주거 등은 원문 추가확인 필요.

### 코드 감사 (현 갭)
- ★매싱이 **건축유형 무차별**: building_use(3종)·massing_kind(형상4종)는 입력 파라미터일 뿐 **목적함수 아님**. 빌라/주상복합/오피스텔/상업 목적함수 부재.
- ★주력 BIM 경로 `design_v61.py:862 _resolve_mass`가 SiteInput에 `building_use`조차 미전달 → `/mass`·`/bim/*`이 전부 default 공동주택+auto+84A.
- `compute_optimal_mass`(auto_design_engine:372)는 건폐율을 **항상 max**(단일전략). `solar_envelope`(:324) round(far/30~20) 하드코딩. `composition` 분동은 공동주택만.
- 유형인지 토대 `ALLOWED_USES_BY_ZONE`(design_geometry:151) 존재하나 **미사용**(참조목록뿐).
- 재사용 자산: resolve_zone_limits(23종 fail-closed)·legal_limits_for·detect_special_parcel·max_height_for_north_distance_m/compute_north_step_profile·solar_placement(천문식)·floor_type_generator(1층 근생 분기)·upzoning_potential·development_methods/scenarios·unit_mix_optimizer·design_drawings retrieval·feasibility v2·nearby-map.

## 1. 목표 파이프라인 (사용자 정의)
법규분석(현재속성+달성가능속성) → 건축가능항목 선정(인허가가능성·가용용적률 순) → 유사건축물 시장조사·사업성 → **병행** 토지모양·특성·법규 기반 설계도면 선정·배치 → 구역도 위 배치도.

## 2. 단계별 구현계획 (기존 시스템 보완·업그레이드·통합)

### Stage 0 — 토지속성 확정 엔진 (현재 + 달성가능)
- 현재속성: detect_special_parcel·resolve_zone_limits·legal_reference_registry(재사용).
- ★달성가능속성: 지구단위계획·도시군관리계획 기반 "인허가 절차로 달성가능한 속성"(종상향·용도지역변경·주상복합/오피스텔 가능여부 검증). upzoning_potential + development_methods/scenarios 재사용 + 지구단위 데이터(토지이음 deep-link) 검증.
- ★`classify_building_type(zone, building_use, scale, district_plan)` 자동분류 헬퍼 신설(아파트/주상복합/오피스텔/빌라/연립/상업). design_change_predictor 상수 재사용.
- 산출 계약 `TerrainAttributes{current:{zone,bcr,far,special}, achievable:[{type, via_permit, achievable_far, feasibility}], building_type}`.

### Stage 1 — 건축가능항목 선정·랭킹
- 달성가능속성별 건축가능분류 매핑(ALLOWED_USES_BY_ZONE를 결정입력으로 승격).
- ★랭킹: **인허가가능성(permit gate) × 가용용적률(달성가능 far)** 내림차순 → 최우선 사업유형.
- 산출 `BuildableOptions[]`(유형·달성far·인허가난이도·근거).

### Stage 2 — 유형별 매싱 전략 (★핵심·단순산식 대체)
- ★신규 공용 SSOT `app/services/cad/massing_strategy.py: resolve_massing_objective(building_type, zone, district) -> MassingObjective{objective, target_bcr_ratio, preferred_massing_kind, commercial_podium_ratio, max_dong_length_m, daylight_mode}`.
- 목적함수:
  - 공동주택: `maximize height + minimize coverage` s.t. 정북일조·인동간격·동지연속2h → footprint를 bcr 상한보다 작게(예 target_bcr_ratio) 잡아 층수↑.
  - 빌라/도생: `maximize coverage` s.t. 정북사선·필로티 → 건폐율 max + 사선 역산 층수.
  - 상업: `maximize bcr+far` s.t. 가로구역높이.
  - 주상복합: `maximize 주거far` s.t. 지자체 비주거의무비율(연면적/용적률 트랙)·오피스텔 비주거인정 파라미터(지자체 테이블) → commercial_podium_ratio.
- 배선(공용 단일경유): ①compute_optimal_mass footprint 계수 ②solar_envelope recommended_floors 분모(유형별 쾌적건폐율) ③composition 분동·동간.
- ★선결 배선: `_resolve_mass`에 building_use/massing_kind/building_type 전달(진입점, 안 고치면 BIM 경로 미도달).
- 정북일조·동간거리 하드제약 = 기존 solar_placement·north-setback 헬퍼 결합.

### Stage 3 — 유사건축물 시장조사·사업성
- 유사건축물: design_drawings retrieval(1,019 시드)·nearby-map 실거래·유사 용도/규모 검색.
- 용도별 재무모델(분양역산/임대NOI/주상복합 용도믹스별) = feasibility v2 연동.
- senior financial 평가기 게이트(이미 배선) + ROI 비현실 차단.

### Stage 4 — 설계도면 선정·배치 (구역도 위 배치도)
- 토지모양(parcel 폴리곤)·향·접도 → buildable footprint(세트백 오프셋·envelope 추출) → 동배치 멀티오브젝티브 그리드샘플링(일조준수율·조망개방성·yield 다축 스코어, 무거운 GA 회피) → 구역도(parcel-boundaries) 위 배치도 렌더.
- design_geometry SSOT·composition·ParcelBoundaryMap 결합.
- LLM 부지맞춤 미세조정(llm_adjust_unit_plan 패턴·RLVR 검증게이트) — 유기적 조정은 LLM, 계산·배치는 결정론.

## 3. 교차트랙 — senior/LLM 모세혈관 심화 (사용자 msg1)
- urban/legal 정량 verdict 입력매핑 정교화: comprehensive→hook에 far/bcr/일조/높이 표준입력 전달 → urban evaluator가 준수 verdict(PASS/WARN/BLOCK) 산출.
- attach_senior_consultation 추가배선: 인허가(permit→legal+urban)·시장(market→financial)·규제(regulation→legal/urban) 플로우.
- deliberation 엔진 활성화: decision_brief `_run_specialists`에 심의·설계 도메인 추가(엔진 168.x 라이브·타임아웃 게이트).

## 4. 구현순서 (OMC·성장루프 9.5게이트·라이브검증·무회귀)
- **P0**(최고ROI): Stage0 building_type 자동분류 + Stage2 massing_strategy SSOT + 진입점 배선(_resolve_mass) + 3소비처 공용배선. → 단순산식 즉시 대체.
- **P1**: 교차트랙 senior 심화(msg1) — urban/legal verdict·permit/market/regulation·deliberation.
- **P2**: Stage1 건축가능항목 랭킹 + Stage3 유사건축물 재무연동.
- **P3**: Stage4 배치 멀티오브젝티브 + LLM 부지맞춤 조정 + 구역도 배치도.
- 각 단계: 코드리뷰 9.5 + 라이브검증 + 무회귀(선택kwargs·graceful) + 기록.

## 5. 정직성·경계
- 무날조: 미확인 법규수치(별표3 차등·지자체 비주거)는 정직표기·verified만 링크.
- 무회귀: 신규 전부 선택kwargs·기본 기존동작 보존.
- DRY: 신규는 massing_strategy + classify_building_type 2개 결정론 헬퍼 위주, 나머지 기존 블록 조합.
- 멀티세션: design/cad는 design-generation-foundation 세션 활성 가능 → 보드 note·충돌회피(공용 헬퍼는 additive).

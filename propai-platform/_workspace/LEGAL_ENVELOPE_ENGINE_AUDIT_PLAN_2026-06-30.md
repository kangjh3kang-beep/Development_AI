# Legal Envelope Engine Audit And Rebuild Plan

작성일: 2026-06-30
대상: 사통팔땅 법령엔진, 설계스튜디오, 후보지/사업성/인허가 파이프라인

## 1. 결론

현재 엔진은 자연녹지지역과 계획관리지역의 법정 건폐율/용적률 기본값은 보유하고 있다. 그러나 `effective_far_pct`가 "법정/조례/계획상한 적용 용적률"과 "층수, 건폐율, 일조, 도로, 주차, 필지형상까지 반영한 실제 설계 가능 용적률"을 동시에 의미하는 것처럼 사용되고 있다. 이 때문에 자연녹지지역처럼 법정 용적률 100%이지만 4층 이하 및 건폐율 20%로 실현 용적률이 80% 수준에 묶이는 경우 화면과 엔진 사이에서 혼선이 발생한다.

해결 방향은 단순 테이블 보강이 아니라 "법정 상한"과 "설계 실현 한도"를 분리하는 새 계약을 도입하는 것이다.

## 2. 법규 해석 원칙

1. 자연녹지지역과 계획관리지역은 서로 다른 용도지역이다.
   - 자연녹지지역: 법정 건폐율 20%, 법정 용적률 상한 100%.
   - 계획관리지역: 법정 건폐율 40%, 법정 용적률 상한 100%.
   - 한 필지가 여러 용도지역에 걸치면 "자연녹지라도 계획관리"로 합치는 것이 아니라, 필지 폴리곤을 용도지역 폴리곤과 교차해 면적별로 분리 산정해야 한다.

2. 자연녹지지역의 핵심 리스크는 "법정 FAR 100%"와 "실현 FAR 80%"의 분리다.
   - 건폐율 20%에서 지상 4층이면 바닥면적 누적은 80%다.
   - 법정 용적률 100%를 모두 쓰려면 단순 계산상 5층 상당이 필요하지만, 자연녹지 4층 이하 조건, 높이, 건축물 용도, 도로, 주차, 개발행위허가, 조례, 지구단위계획 등이 추가로 제약한다.
   - 따라서 화면은 "법정 용적률 100%"과 "층수·건폐율 실현 한도 80%"를 반드시 분리 표기해야 한다.

3. 계획관리지역은 기본 건폐율 40%라 3개층 이하에서도 용적률 100%에 접근할 수 있다.
   - 단, 이것도 자동 확정이 아니라 해당 지자체 도시계획조례, 성장관리계획, 지구단위계획, 개발행위허가 기준, 도로 접도, 주차장, 배수/하수, 농지/산지/환경/문화재/군사 등 중첩 규제 확인 후 확정해야 한다.

## 3. 현재 코드 감사 결과

### 3.1 올바르게 들어간 부분

- `apps/api/app/services/zoning/auto_zoning_service.py`
  - 자연녹지지역: 20 / 100.
  - 계획관리지역: 40 / 100.
  - 관리지역, 농림지역, 자연환경보전지역도 기본표에 포함되어 있다.

- `apps/api/app/services/zoning/legal_zone_limits.py`
  - 국토계획법 시행령 제84조, 제85조 기준의 법정 범위와 조례/계획상한 계층을 다루는 구조가 있다.
  - `legal_limits_for()`와 `applicable_limits_for()`는 법정값, 조례값, 도시군관리계획/지구단위계획 상한을 분리하려는 방향이 맞다.

- `apps/api/app/services/cad/auto_design_engine.py`
  - CAD 쪽은 실제 footprint와 최대 용적률을 이용해 `max_floors_by_far`를 계산하는 구조가 이미 있다.
  - 정북일조 단계후퇴 계산도 별도 보유하고 있다.

### 3.2 현재 오류/혼선 원인

- `apps/api/app/services/land_intelligence/far_tier_service.py`
  - `calc_effective_far()`가 `effective_far_pct = min(법정, 조례, 계획상한)`으로만 산정한다.
  - 여기에는 `건폐율 × 최대층수`, 필지형상, 일조, 도로, 주차, 높이, 용도제한이 반영되지 않는다.
  - 그런데 필드명이 "effective"라서 UI와 후속 엔진이 "실제로 지을 수 있는 용적률"로 오인한다.

- `apps/web/components/design/DesignStudio.tsx`
  - `siteAnalysis.effectiveFarPct`를 총연면적 계산에 바로 사용한다.
  - 자연녹지 100%가 들어오면 프론트는 100%를 기준으로 연면적을 잡고, 별도 로직이 없으면 4층 구속의 80% 효과를 안정적으로 반영하지 못한다.

- `apps/api/app/services/land_intelligence/ordinance_service.py`
  - `NATIONAL_LIMITS`에는 자연녹지/계획관리 값이 있지만, 정적 `ORDINANCE_CACHE["용인시"]`에는 주거지역만 있고 자연녹지지역/계획관리지역이 빠져 있다.
  - 실시간 법제처 API가 실패하면 용인시 자연녹지/계획관리 조례값이 "법정 폴백"으로 처리될 수 있다. 폴백 자체는 안전하지만, "조례 확인 완료"로 보이면 안 된다.

- `apps/api/app/services/permit/building_code_rules.py`
  - 검증용 `ZONE_DEFAULTS`에는 녹지/관리/농림/자연환경보전 계열이 빠져 있다.
  - 일부 인허가 검증 경로에서 자연녹지/계획관리 필지가 일반 기본값 또는 누락 상태로 통과될 위험이 있다.

- `apps/web/lib/kr-building-regulations.ts`
  - 프론트에 별도 용도지역 표가 있어 백엔드 SSOT와 중복된다.
  - 새 용도지역이나 조례/층수 구속을 한쪽만 수정하면 화면과 API가 서로 다른 결과를 낼 수 있다.

## 4. 새 데이터 계약

기존 `effective_far_pct` 중심 계약을 다음처럼 분해한다.

```ts
type LegalEnvelopeResult = {
  zone_type: string;
  pnu?: string;
  land_area_sqm: number;

  legal_bcr_cap_pct: number;
  legal_far_cap_pct: number;
  legal_far_range_pct?: [number, number];

  ordinance_bcr_cap_pct?: number;
  ordinance_far_cap_pct?: number;
  ordinance_confirmed: boolean;

  plan_bcr_cap_pct?: number;
  plan_far_cap_pct?: number;
  district_plan_confirmed: boolean;

  max_floor_cap?: number;
  floor_bcr_far_cap_pct?: number;      // bcr cap * max floor cap

  road_access_cap?: ConstraintCap;
  daylight_cap?: ConstraintCap;
  height_cap?: ConstraintCap;
  parking_cap?: ConstraintCap;
  geometry_cap?: ConstraintCap;
  use_permission_cap?: ConstraintCap;

  envelope_far_cap_pct: number;        // 물리/형상/일조/도로/주차 반영 한도
  realizable_far_pct: number;          // 최종 설계 적용 용적률
  realizable_gfa_sqm: number;          // 용적률 산입 연면적 기준
  gross_floor_area_sqm?: number;       // 지하주차장 등 용적률 제외면적 포함 총연면적

  binding_constraints: string[];
  evidence: EvidenceRef[];
  warnings: string[];
  confidence: "verified" | "partial" | "needs_review";
};
```

핵심 산식:

```text
base_far_cap = min(legal_far_cap, ordinance_far_cap, plan_far_cap if exists)
floor_bcr_far_cap = legal_or_ordinance_bcr_cap * max_floor_cap
realizable_far_pct = min(
  base_far_cap,
  floor_bcr_far_cap,
  envelope_far_cap,
  use_permission_cap,
  road_access_cap,
  daylight_cap,
  parking_cap,
  geometry_cap
)
```

자연녹지 예:

```text
legal_bcr_cap_pct = 20
legal_far_cap_pct = 100
max_floor_cap = 4
floor_bcr_far_cap_pct = 80
realizable_far_pct <= 80 before further constraints
```

계획관리 예:

```text
legal_bcr_cap_pct = 40
legal_far_cap_pct = 100
max_floor_cap = none or ordinance/development-rule dependent
floor_bcr_far_cap_pct = not binding by default
realizable_far_pct can reach 100 only if use, road, parking, development permit, geometry, district plan all pass
```

## 5. 법령엔진 모듈 설계

1. `national_zone_limit_rule`
   - 국토계획법 시행령 제84조, 제85조.
   - 모든 용도지역 21종 이상 법정 건폐율/용적률 범위.

2. `local_ordinance_rule`
   - 해당 지자체 도시계획조례.
   - 용인시 등 주요 시군구의 자연녹지/계획관리 누락을 우선 보강.
   - 실시간 조회 실패 시 "조례 미확인"으로 표시하고 절대 확정값처럼 쓰지 않는다.

3. `land_use_permission_rule`
   - 국토계획법 제76조, 시행령 별표, 건축물 용도별 허용/불허/조건부.
   - 추천 건축물 종류 Top 3의 1차 필터.

4. `floor_and_height_rule`
   - 용도지역별 층수 제한, 가로구역별 최고높이, 자연녹지 4층 이하 등.
   - `floor_bcr_far_cap_pct` 산정.

5. `road_access_rule`
   - 건축법 접도, 도로폭, 건축선, 소방 진입, 맹지/법정도로 여부.

6. `daylight_shadow_rule`
   - 건축법 제61조, 시행령 제86조.
   - 주거지역 정북일조, 공동주택 인동거리, 동지 일영.

7. `parking_rule`
   - 주차장법, 지자체 주차장 조례.
   - 용도별 주차대수와 지하층/램프 현실성.

8. `special_parcel_rule`
   - 농지, 산지, 개발제한구역, 군사시설, 문화재, 하천, 상수원, 환경영향, 재해, 도시계획시설.

9. `geometry_envelope_rule`
   - 실제 필지 폴리곤, 대지 폭/깊이, 세장비, 도로 접면, 불규칙도, 다필지 결합 가능성.

10. `top3_program_rule`
    - 법규 통과 + 시장성 + 분양성 + 사업기간 + 인허가 가능성으로 건축물 종류 3순위 추천.

## 6. 설계 스튜디오 워크플로우

한 화면에서 다음 3단을 유지하되 페이지 이동 없이 진행한다.

1. 조건 확인
   - 주소/PNU/지도 선택.
   - 용도지역, 지목, 면적, 도로, 공시지가, 중첩규제 자동 수집.
   - 법정/조례/계획/실현 한도 카드 분리 표시.

2. 추천안 만들기
   - 건축물 종류 Top 3 추천.
   - 각 추천안별 건폐율, 법정 FAR, 실현 FAR, 건축가능 연면적, 예상 층수, 주차, 인허가 리스크, 분양성 점수 표시.

3. 도면 편집
   - 선택한 추천안을 즉시 CAD/BIM 캔버스에 반영.
   - 텍스트/음성 명령으로 "동 배치 변경", "층수 낮추기", "주차 늘리기", "코어 이동" 같은 수정 수행.
   - 수정 시 법규엔진이 즉시 재검증하고 바인딩 제약을 표시.

## 7. UI 표기 원칙

현재처럼 하단에 `용적률 100%`만 표시하면 안 된다. 다음처럼 분리해야 한다.

- 법정 용적률: 100%
- 조례 적용 용적률: 확인 전 또는 100%
- 층수·건폐율 실현 한도: 80%
- 일조/도로/주차/형상 반영 한도: 산정값
- 최종 설계 적용 용적률: 예 80% 이하

자연녹지 화면 문구 예:

```text
법정 용적률은 100%이나, 자연녹지 4층 이하 및 건폐율 20% 기준으로
층수·건폐율 실현 한도는 80%입니다. 조례, 도로, 주차, 일조, 개발행위허가
검토 후 최종 설계 적용값을 확정합니다.
```

## 8. 검증 계획

### 골든 테스트

- 자연녹지지역 12,079㎡
  - 법정 BCR 20, 법정 FAR 100, max floors 4.
  - floor_bcr_far_cap = 80.
  - realizable_gfa <= 9,663.2㎡ before further constraints.

- 계획관리지역 12,079㎡
  - 법정 BCR 40, 법정 FAR 100.
  - 층수 제한이 별도로 없다면 floor_bcr_far_cap은 기본 바인딩 아님.
  - realizable_gfa는 도로/주차/개발행위/조례/형상 검토 후 12,079㎡ 이하에서 확정.

- 용인시 자연녹지/계획관리
  - 조례 조회 성공 시 ordinance_confirmed=true.
  - 실패 시 ordinance_confirmed=false, confidence=needs_review.
  - 법정 폴백값은 "확정 조례값"으로 표시 금지.

### 회귀 테스트

- `calc_effective_far()`는 법정/조례/계획 상한만 반환.
- 새 `derive_legal_envelope()`는 실현 한도까지 반환.
- 프론트는 `effectiveFarPct` 대신 `realizableFarPct`를 설계 총연면적에 사용.
- 자연녹지에서 화면 어디에도 "실효 용적률 100%"가 최종 설계 적용값처럼 표시되지 않아야 한다.

## 9. 구현 단계

### Stage 1. 용어/계약 수정

- `effective_far_pct`를 `applied_far_cap_pct`로 재명명하거나 하위호환 별칭으로 유지.
- 새 필드 `realizable_far_pct`, `floor_bcr_far_cap_pct`, `binding_constraints` 도입.
- 디자인 스튜디오 카드 표기 분리.

### Stage 2. LegalEnvelopeEngine 추가

- `apps/api/app/services/legal/legal_envelope_engine.py` 신설.
- `legal_limits_for`, `ordinance_service`, `solar_envelope_service`, `special_parcel`, `parking`, `geometry`를 통합.
- 결정론 결과만 산출하고 AI 설명은 후단에서 근거 요약만 담당.

### Stage 3. 지자체 조례 보강

- 용인시 자연녹지/계획관리 우선 보강.
- 전국 주요 지자체 녹지/관리/농림/자연환경보전 계열 캐시 확대.
- 법제처 API 실패 시 캐시, 캐시 실패 시 법정범위 + 확인필요 플래그.

### Stage 4. 프론트/설계엔진 배선

- DesignStudio는 `realizable_far_pct`로 GFA 계산.
- 법정/조례/계획/실현 한도 카드를 별도 표시.
- 하단 sticky summary도 `법정 100 / 설계실효 80` 형식으로 변경.

### Stage 5. Top 3 추천 및 CAD 연동

- 1차 법규분석 결과로 건축물 종류 Top 3 추천.
- 2차 추천안별 건축개요 생성.
- 3차 확보 CAD/매스 템플릿과 필지형상 조합으로 기본 도면 생성.
- 텍스트/음성 명령은 같은 캔버스에서 수정/재검증.

### Stage 6. 테스트/빌드/라이브검증

- Pytest: 자연녹지, 계획관리, 용인시, 조례 미확인, 다용도지역 분할.
- Frontend unit: 설계스튜디오 표시값 분리.
- Playwright: `/ko/design-studio`에서 자연녹지 카드가 법정 100/실현 80을 분리 표기.
- API contract test: `LegalEnvelopeResult` 스키마와 근거 출처 필수.

## 10. 근거 출처

- 국가법령정보센터: 국토의 계획 및 이용에 관한 법률 시행령 제84조, 제85조.
- 국가법령정보센터: 건축법 제61조 및 건축법 시행령 제86조.
- 국가법령정보센터: 용인시 도시계획 조례.

공식 법령/조례 링크는 구현 시 `legal_reference_registry.py`의 `EvidenceRef`로 고정해 모든 수치 옆에 조문, 버전, 조회일을 함께 저장한다.

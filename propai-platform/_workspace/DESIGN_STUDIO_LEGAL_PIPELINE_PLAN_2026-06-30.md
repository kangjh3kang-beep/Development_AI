# Design Studio Legal Pipeline Plan — 2026-06-30

## 0. 확인 결론

현재 `자연녹지지역` 경고의 직접 원인은 법규 데이터 부재가 아니라 설계엔진 키 매핑 누락이었다.
다만 사용자가 지적한 대로 설계 판단의 최종 기준은 국계법 시행령 상한표가 아니라 지자체 도시계획조례
또는 도시·군계획조례, 지구단위계획, 완화/인센티브, 건축조례의 세부 건축조건,
시행령·시행규칙·관계법까지 반영한 법령엔진의 실효값이다.

정리:

- `national/max_*`: 국토계획법·시행령 상한. 임의 상향을 막는 safety cap.
- `ordinance_*`: 지자체 도시계획조례/도시·군계획조례 확인값. 용적률·건폐율은 이 경로가 중심이며,
  건축조례는 주차·대지안 공지·일조·높이 등 건축법 세부조건과 함께 별도 제약으로 결합한다.
- `effective_*`: 법정범위 -> 조례 -> 도시·군관리계획/지구단위계획 -> 인센티브를 반영한 설계·수지 계산값.
- CAD/매스/사업성 엔진은 `effectiveFarPct/effectiveBcrPct`를 우선 사용하고, 미확보 시에만 national cap으로 폴백해야 한다.

## 1. 현재 구축현황

이미 존재하는 진실원천/배선:

- `apps/api/app/services/land_intelligence/ordinance_service.py`
  - 법제처/자치법규 API -> 정적 캐시 -> 법정상한 순으로 조례 한도 조회.
  - `(sigungu, zone_type)` 저장본을 재사용하고 `force_refresh` 때 재조사.
- `apps/api/app/services/land_intelligence/far_tier_service.py`
  - `calc_effective_far()`가 법정범위, 조례, 계획상한, 인센티브를 계층화해 `effective_far_pct/effective_bcr_pct` 산출.
- `apps/web/store/useProjectContextStore.ts`
  - `nationalFarPct/nationalBcrPct`, `effectiveFarPct/effectiveBcrPct`, `integratedFarEffPct/integratedBcrEffPct`, `ordinance` 보존.
- `apps/web/lib/zoning-ssot.ts`
  - 하류는 `resolveFarPct/resolveBcrPct`로 통합 실효 > 단일 실효 > 법정 순서로 읽도록 설계됨.
- `apps/web/components/design/DesignStudio.tsx`
  - 로컬 설계 조건 계산은 이미 `resolveFarPct/resolveBcrPct`를 우선 적용.
- `apps/api/app/services/cad/auto_design_engine.py`
  - `SiteInput.ordinance_far_percent/ordinance_bcr_percent`와 `min(법정, 조례, 목표)` 클램프 존재.

이번 단계에서 보강한 부분:

- CAD 설계엔진이 표준 한글 용도지역 21종을 인식.
- `자연녹지지역`이 기본 2R로 폴백되지 않음.
- `seed-design` 매스 비교 API가 `effective_far_pct/effective_bcr_pct`를 받아 설계엔진의 조례/실효 한도 입력으로 전달.
- 프론트 매스 비교 카드 명칭을 `법정 최대`에서 `적용 한도 최대`로 교정.

## 2. 남은 구조적 문제

설계 화면은 아직 완전한 통합 워크플로우가 아니다.

- `DesignWorkspace.tsx`는 1/2/3단계 패널을 hidden 토글로 유지한다. 사용자는 여전히 "다음 단계 화면"처럼 느낀다.
- 텍스트 CAD 명령 파서(`cad-command-parser.ts`), 음성 STT 훅(`use-speech-to-text.ts`), 백엔드 `DesignOperator`가 있지만 도면편집 주 작업면에 일관되게 노출되지 않는다.
- 설계 스튜디오의 법규/사업성/매스/도면 정보가 좌측 카드, 우측 캔버스, 하단 메트릭바로 파편화되어 있다.
- 유사도면/매스 백본/실측 전형은 존재하지만 “1차 법규분석 -> Top3 전략 -> Top3 건축개요 -> CAD 초안 -> 명령 편집”으로 한 화면에서 이어지지 않는다.

## 3. 목표 워크플로우

도면편집 화면 하나를 `Design Operations Canvas`로 재구성한다.

1. 부지 입력/선택
   - 주소/PNU/지도/엑셀 다필지 입력을 이미 구축 중인 통합 지도 파이프라인에서 확정.
   - 결과는 `siteAnalysis` SSOT에 저장.

2. 1차 법규·토지속성 분석
   - `effectiveFarPct/effectiveBcrPct`, 용도지역, 지구단위, 접도, 일조, 주차, 특이부지, 개발행위허가 리스크를 한 번에 산출.
   - 산출물: 법규 추적표, 제한/완화 근거, 인허가 가능성, 추정 사업기간, 분양성.

3. Top3 토지·건축물 종류 추천
   - 점수축: 실현 가능 용적률, 인허가 가능성, 예상 사업기간, 시장성/분양성, 수익성, 리스크.
   - 출력: 1/2/3순위 추천 카드. 각 카드는 "왜 이 용도인가"를 근거값과 함께 표시.

4. Top3 건축개요 생성
   - 각 추천안별 대지면적, 적용 FAR/BCR, 층수, 연면적, 건축면적, 주차, 세대/전용률, 사업기간 추정.
   - 1안 선택 시 2안/3안은 비교 탭으로 유지하고 캔버스에서 즉시 전환.

5. CAD·매스 초안 생성
   - 매스 백본 + 지역 실측 전형 + 참조 CAD/도면 + 법규 커널을 조합.
   - 2D 배치도, 기본 평면, 3D 매스, QTO/BIM seed를 같은 기하 SSOT로 생성.

6. 통합 편집
   - 중앙 캔버스: 지도/배치도/CAD/BIM 전환.
   - 우측 인스펙터: 선택 대안의 법규·사업성·인허가·분양성 수치.
   - 하단 명령바: 텍스트/음성 명령, 실행 이력, undo/redo, 법규 재검증.
   - 페이지 이동 없이 명령 한 번으로 대안 수정 -> 법규/수지/도면 즉시 재계산.

## 4. 참고 플랫폼에서 얻은 UX 원칙

- Snaptrude: Site Analysis, Programming, Massing, BIM, Presentation을 하나의 AI-native workspace에 연결하고, mass-to-BIM 전환을 한 흐름으로 제공.
- Finch: 많은 설계안을 빠르게 생성하고 실시간 데이터로 trade-off를 비교.
- TestFit: zoning, unit mix, parking, pro forma, design intent를 한 번에 최적화하고 즉시 편집/내보내기.
- Autodesk Forma: 초기 기획 단계에서 AI 분석과 site/massing 자동화를 결합해 빠른 대안 평가.

우리 적용 원칙:

- 기능명이 아니라 산출물 중심으로 진입한다.
- 사용자는 "무엇을 만들까"를 고르고, 시스템은 필요한 법규/사업성/CAD 단계를 자동 실행한다.
- 숫자는 항상 법령엔진/계산커널 출처를 가진다. LLM은 의도 파싱과 설명만 맡는다.
- 도면 생성·수정은 중앙 캔버스와 하단 명령바에서 끝난다.

## 5. 단계별 구현계획

### Phase A — 법규 SSOT 고정

- 표준 용도지역 21종 인식 완료.
- `seed-design`에 실효 한도 배선 완료.
- 다음 보강:
  - `auto_design_engine.get_legal_limits()` 명칭을 `engine_base_limits`와 `statutory/national`로 분리.
  - `DesignSpec.to_site_input()`에 ordinance/effective limits 전달 필드 추가.
  - `GenerativeDesignPanel`, `DesignStudio`, `CadBimIntegrationPanel`이 모두 `resolveFarPct/resolveBcrPct`만 읽도록 통일.

### Phase B — Top3 전략 엔진

- API: `/api/v1/design-strategy/top3`
- 입력: `siteAnalysis`, 법규 추적표, 시장/분양/공시지가, 개발계획, 특이부지, 건축물 허용용도.
- 출력: land/building-use 전략 3개, 점수, 근거, 리스크, 예상 사업기간.
- 검증: 허용용도 미확인 시 추천 금지, "검토 필요"로 강등.

### Phase C — 통합 설계 오퍼레이션 캔버스

- 기존 `site/generate/draw` 단계 UI를 하나의 3열 레이아웃으로 재구성.
- 좌측: 부지·Top3 전략·대안 목록.
- 중앙: 지도/CAD/BIM 캔버스.
- 우측: 법규·사업성·인허가·분양성 인스펙터.
- 하단: 텍스트/음성 명령바 + 이력.

### Phase D — 명령 기반 도면 편집 배선

- 기존 `cad-command-parser.ts`를 CAD 편집 화면 하단 명령바에 연결.
- 기존 `use-speech-to-text.ts`를 명령바 마이크 버튼에 연결.
- 백엔드 `DesignOperator`는 자연어 의도 -> `DesignSpec` 편집 -> 커널 재생성 -> 검증 결과 반환으로 사용.
- 명령 예:
  - "자연녹지 기준으로 건폐율 18% 안에서 4층 공동주택 3개 대안"
  - "1안에서 주차 20대 늘리고 북측 이격 2m 추가"
  - "타워형 대신 판상형으로 변경하고 법규 재검토"

### Phase E — CAD 초안 생성 고도화

- 매스 백본, 실측 전형, 업로드 CAD/DXF, 참조 평면을 후보 pool로 구성.
- 선택 전략별 `DesignGeometry` 생성.
- 2D 배치, 층별 평면 seed, 3D mass, QTO/BIM seed를 하나의 geometry contract로 저장.

### Phase F — 검증/배포

- 코드리뷰 기준: 미인식 폴백 제거, 법규 출처 표시, 조례 미확인 정직 고지, LLM 수치 생성 금지.
- 테스트:
  - 자연녹지/계획관리/상업/공업 등 표준 21종 회귀.
  - 조례 실효값이 seed/design/CAD/feasibility로 전파되는지.
  - 명령바 텍스트/음성 편집이 undo/redo와 법규 재검증을 깨지 않는지.
- 라이브 검증:
  - `/ko/design-studio` 자연녹지 프로젝트에서 경고 미표시.
  - 적용 한도 카드가 실효 FAR/BCR 기준으로 계산.
  - Top3 대안 -> CAD 초안 -> 명령 수정이 한 화면에서 완료.

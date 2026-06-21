# 설계 도면 분류 택소노미 (실무 전수조사 근거)

설계생성 인제스트/검색의 도면 분류 체계. **단일 출처는 코드**:
`apps/api/app/services/design_ingest/design_spec.py`의 `DRAWING_TYPE_META`
(code → 한국어명·분야·세트·탐지 키워드). 프론트는 `GET /api/v1/design-gen/drawing-types`로 소비.

## 조사 근거 (유사플랫폼·법규·기술자료)
- **건축법 시행규칙 별표2**(건축허가 신청 설계도서) — 인허가 기본세트의 법적 최소 도면.
- **건축물의 설계도서 작성기준**(국토부 고시) — 기획/기본/실시설계 단계, 분야 구분
  (건축·구조·기계[급배수위생/냉난방]·전기·통신·소방·토목·조경).
- **주택의 설계도서 작성기준** 별표3 — 기본/실시설계 작성기준.
- **국제표준/플랫폼**: US National CAD Standard(NCS)·AIA discipline designator(A/S/M/E/P/FP/C/L),
  ISO 13567, IFC discipline 분류, Autodesk(Revit/AutoCAD) sheet 카테고리, BIM 플랫폼 도면 분류.

## 구조
- **분야(discipline)** 10: 공통·건축·구조·전기·기계설비·급배수위생·소방·토목·조경·통신.
- **세트(set)**: 인허가(법정 제출) · 실시설계(시공도면) · 상세 · 공통.
- **코드 41종**(`unknown` 포함). 기존 5종(site_plan/floor_plan/section/elevation/parking)은
  하위호환 유지하고 분야별 도면을 확장.

## 자동 분류(detect_drawing_type) 원칙
- 파일명+내용 힌트의 키워드 매칭. **탐지 우선순위 = META 삽입 순서.**
- ★분야별/복합 키워드(구조평면·천장도·급배수·창호일람 등)를 **일반 건축(평면/단면/입면/배치)보다 먼저**
  둬 "X평면도"가 floor_plan으로 오분류되지 않게 한다.
- 공용 일반어 충돌 해소: 전기에서 "계통도" 제외(급배수/소방 공용), 급배수위생에서 bare "배수" 제외
  (토목 우배수 충돌). → 급배수위생계통도·토목우배수도 정확 분류.
- 못 맞추면 `unknown`(추정 금지).

## 대표 코드 (분야별 일부)
- 공통: cover(표지·도면목록), general_notes, bim, bim_clash(간섭검토), spec_sheet
- 건축: site_plan, floor_plan, unit_plan(단위세대), elevation, section, wall_section(주단면),
  ceiling_plan(천장도), interior_elevation(전개도), finish_schedule(마감표),
  window_door_schedule(창호일람), area_diagram(구적/면적산출), daylight_analysis(일조),
  fire_egress_plan(방화구획·피난), accessibility_plan(BF), parking(주차계획), perspective(투시·조감),
  detail/stair_detail/waterproof_detail/insulation_detail(상세)
- 구조: structural_plan(골조), foundation_plan(기초), rebar_detail(배근·부재일람)
- 전기: electrical_plan(전기 평면·간선계통)
- 기계설비: hvac_plan(공조·환기·덕트)
- 급배수위생: plumbing_plan(급배수·위생)
- 소방: fire_protection_plan(소화·제연·방재설비)
- 토목: civil_plan(토공·우배수·도로·옹벽)
- 조경: landscape_plan(식재·포장)
- 통신: telecom_plan(구내통신·방송)

> 향후 확장은 `DRAWING_TYPE_META`에만 추가하면 `DRAWING_TYPES`·`_TYPE_KEYWORDS`·엔드포인트·프론트가
> 자동 반영된다(단일 출처). 분류는 실무 도면명을 따르며 미상은 정직하게 unknown으로 둔다.

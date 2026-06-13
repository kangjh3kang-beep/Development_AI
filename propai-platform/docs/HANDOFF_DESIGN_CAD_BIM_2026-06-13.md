# 새 세션 인계 — 설계/CAD/BIM/IFC 실상태 감사 + 매스 형상(2026-06-13)

> 본 문서는 ①적산(BOQ) 자동화 마무리 ②설계·CAD·BIM·IFC 서브시스템의 **정직한 실상태 감사** ③매스 형상(massing_kind) 1차 구현을 인계한다.
> 51-에이전트 감사 워크플로 + 적대적 검증으로 도출한 **built/partial/stub** 판정이 핵심이며, §4 로드맵이 다음 구현 대상이다.

## 0. 한 줄 요약

적산은 백엔드 N1·N2·N3 + 프론트 정합까지 **완성·검증·푸시**(3300 pytest·tsc·build 그린). 설계/CAD/BIM은 **상당 부분 실구현**(IFC/DXF 분석·8엔진 법규검증·BIM read/view/generate). 매스 재생성(§4-A `ff3b8bc`)·참조설계 피드백루프(§4-B `5df33cf`)·도면 법규주석(§4-C `33202cd`)·IFC 내보내기(§4-E `db6c9d1`)·BIM 3D 단면(§4-E `34e7ae6`)·지자체 조례 한도(§4-B `7fec04e` — 엔진이 OrdinanceService 실효 한도 사용)까지 **완결·검증·푸시**(백엔드 전체회귀 3382 pytest + 프론트 tsc·build·vitest 그린).

⚠️**§3/§4 감사 정정(코드 직접 검증)** — 51-에이전트 §3 감사가 '없다'고 한 것 다수가 실제로는 이미 존재(허위 갭). 검증 워크플로+직접 grep으로 확인: **DXF DIMENSION 존재**(`parametric_cad_service.py:86 add_linear_dim`·`:984 add_aligned_dim` — §4-D '임베디드 텍스트뿐' 주장 거짓)·**IFC export 존재**(이미 §4-E에서 해소)·**Kakao OAuth 존재**(`auth.py:380/411`)·**조례 소스 존재**(OrdinanceService). 남은 **진짜 갭**(좁음, 검증됨): ① audit 워크스페이스 findings→도면 배선(양 끝 존재·호출 1곳) ② DXF HATCH 엔티티(`add_hatch` 호출 0건) ③ 평면도 findings 주석 ④ RCP/MEP/구조상세 생성기(전무·대형) ⑤ 3D 요소 이동/회전 gizmo·측정(TransformControls 0건).

## 1. 불변 규칙 (위반 금지)

1. **브랜치**: `feature/trust-infra-2026-06-11` 작업. **main 직접 푸시 금지**(remote: `git@github.com:kangjh3kang-beep/Development_AI.git`). main 머지·Oracle 배포는 다른 Claude. 운영(4t8t.net)은 main 기준 — 본 브랜치 수정은 배포 전까지 prod 미반영.
2. **additive·하위호환**: 기존 응답 키·store·테스트 계약 0개 변경. 신규는 옵셔널 키로만 가산.
3. **정직 표기**: 가짜·날조·할루시네이션 금지. 추정은 '추정'/basis 명시, 데이터 없으면 "데이터 없음". 부분 커버리지는 그대로 표기.
4. **결정론**: 엔지니어링/법규/매스/단가/병합 모두 규칙 기반(LLM 0). LLM은 설명문구에만.
5. **검증(WSL)**: `cd ~/My_Projects/Development_AI/propai-platform/apps/api && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest ...`. 프론트: `apps/web`에서 `pnpm exec tsc --noEmit && pnpm build`.
6. **서버 기동**: 플랫폼 루트에서 `PYTHONPATH=.:apps/api apps/api/.venv/bin/uvicorn apps.api.main:app --port 89xx`. (apps/api 직접 기동은 `No module named packages/app` — 함정).
7. **전체 회귀 시 2건 무관 제외**: `--ignore=tests/test_auction_demock_court.py --ignore=tests/test_molit_client.py` (다른 세션 경매·molit 커밋으로 수집부터 깨짐, 본 작업 무관).

## 2. 현재 상태 (커밋 기준, 전부 origin 푸시됨)

| 커밋 | 내용 |
|------|------|
| `f70b42d` | 적산 N3 단가결합·N2 BIM병합·N1 N건회귀 인프라(백엔드) |
| `3e76d1f` | BOQ 워크스페이스 실제 백엔드 정합 + N3 금액/N2 BIM 모드 UI |
| `0060d08` | 설계/CAD: 매싱 선택(시각)·2D3D 겹침·Top3 안내·메뉴명(설계안AI심사→AI설계분석)·엔지니어링 도면 렌더러 |
| `3f2313b` | BIM: `parse_ifc_metadata` 하드코딩 stub→실제 ifcopenshell |
| `27bad73` | BOQ from-project e2e 계약 완화(허위 bim만 금지, user 허용) |
| `11bc342` | **설계: `massing_kind` 엔진 파라미터(판상/타워/ㄱ자/중정 결정론 매스 변형)** |
| `ff3b8bc` | **설계: 매스 형상 재생성 배선(§4-A 완결) — 라우터 massing_kind 수용·대안별 형상(A=입력/auto·B=tower·C=lshape)·프론트 선택→재생성** |
| `5df33cf` | **설계: 참조설계 피드백루프(§4-B 완결) — find_similar 기하 종횡비를 합성 매스에 결정론 주입(엔진 reference_mass·서비스 derive_reference_mass_hint·라우터 opt-in use_references·프론트 토글/칩), 적대적 4-렌즈 리뷰 통과** |
| `33202cd` | **설계: 도면 법규주석(§4-C 완결) — audit↔drawing 연결. annotate_site_plan(findings→배치도 색/범례/정북일조)·POST /annotated-site-plan·프론트 AnnotatedSitePlanCard(Blob-img 안전 렌더)·legalAnnotation 순수모듈+vitest. 적대적 리뷰 must-fix 2건(solar_envelope 엔진명·multi-word 라벨 dead-path) 수정** |
| `db6c9d1` | **설계: IFC(.ifc) 내보내기(§4-E) — POST /drawing/export-ifc(param-based·RFC5987 파일명·501/400/422 정직)·프론트 'IFC(BIM) 내보내기' 버튼. 적대적 리뷰 must-fix 3건(결정론 과장표기 정직화·501 경로 검증·파일명 강화). ※project-based /design/{id}/bim/export-ifc는 기존 존재(§3 정정) — 갭은 UI 미배선·param 변형** |
| `34e7ae6` | **설계: BIM 3D 단면 슬라이서(§4-E) — R3F 전역 클립평면으로 건물 절단·층별 내부 보기. 순수코어 bimSection(절단높이↔가시층)+vitest 12·토글/슬라이더/'보이는 층 N/M' 라벨. 적대적 리뷰 must-fix(서버 glTF Y중심화 base 미접지 → minY 실측 접지로 클립·라벨 정직) 수정** |
| `7fec04e` | **설계: 지자체 조례 한도(§4-B) — 엔진이 기존 OrdinanceService(법제처 API) 실효 한도를 min(법정,조례,목표)로 사용. 라우터 use_ordinance+address 조회·엔진 법정으로 정규화(호도 방지)·정직 degrade·B/C 전파. 프론트 토글·OrdinanceNote. 테스트 17(본체 6분기 직접). ※§4-B '조례 DB 적재' 오기재 정정 — 소스는 기존 존재, 갭은 엔진 미반영뿐** |

검증 베이스라인: pytest **3358 passed / 0 failed**(22:29, `apps/api/tests` 2건 제외, `INTERP_REDIS_CACHE=0`으로 미가동 Redis 캐시 우회 — 테스트 로직 불변), tsc·build·vitest 그린. (§4-A 시점 3320 + §4-B 신규 24 + §4-C 신규 14.)

> 검증 주의: 전체회귀는 **`pytest tests/` (apps/api/tests, 메인 204파일)**를 타깃해야 한다. 인자 없는 `pytest`는 `pyproject testpaths=["../../tests"]`(통합·load·벤치 83파일)를 수집하며, 이쪽엔 본 작업과 무관한 사전존재 환경실패(Molit XML·Sentry·IFC 온보딩 샘플 등)가 있다 — §4-A 변경 무관.

## 3. 서브시스템 실상태 감사 (51-에이전트 워크플로 + 적대적 검증, 정직 판정)

### ✅ BUILT (실구현 확인)
- **IFC/DXF 분석(=AI설계분석)** — 메뉴명 변경 완료. IFC(ifcopenshell)·DXF(ezdxf, 손상복구·단위환산) **실 파싱**. `design_audit_orchestrator`의 **8엔진**(건폐율·용적률·일조[정북사선 시뮬]·주차·피난[change_risk]·인근사례비교·인센티브경로·법규근거링크) 전부 **규칙기반**. 71 design_audit 테스트 통과. 근거링크는 검증 레지스트리만(할루시네이션 금지). → **사용자 요구 "IFC/DXF 첨부→정밀 공학/법규/건축 분석" 실질 충족.**
- **설계 편집 UI** — 2D/3D 토글 겹침 수정(`CadBimIntegrationPanel` `pt-16`+`flex-wrap`, 토글 `z-30`). 매싱 카드 선택 상태·'추정' 정직라벨. (단, Playwright 시각회귀 테스트 없음 — 뷰포트별 스냅샷 권장.)
- **Top3/단일 자동설계 생성** — `/drawing/design-alternatives`(3개 랭킹·점수·compliance-first)·`/drawing/auto-design` 실동작. 0세대 시 정직 안내. → **prod에서 Top3 미생성은 배포갭**(feature 브랜치엔 있음, main 미배포).
- **BIM read/view/generate** — IFC read·물량추출·work_code 매핑·파라미터→IFC 생성·IFC→glTF·R3F 3D뷰·`/bim` API.

### ✅ BUILT 추가 (§4-A 완결, ff3b8bc)
- **매스 선택→재생성**: 엔진 `massing_kind`(11bc342) + 라우터 수용·대안별 형상·프론트 선택→재생성(ff3b8bc)까지 **배선 완료**. `/auto-design`·`/design-alternatives`가 옵셔널 massing_kind를 수용(미정의→auto 폴백·하위호환), `generate_alternatives`는 A=입력형상(None=auto)·B=tower·C=lshape로 매스 다양화(법규 준수 유지), 프론트 `GenerativeDesignPanel`에 형상 선택 UI + 적용 형상 라벨 칩. 테스트: `test_drawing_massing_router.py`(7) + `test_massing_kind.py` 대안형상(4).

### ✅ BUILT 추가 (§4-B 완결, 5df33cf)
- **CAD 참조설계 피드백루프**(stub→built): 합성 경로(`AutoDesignEngine.generate`)가 이제 `find_similar` 유사 사례의 기하 종횡비를 결정론으로 매스에 주입한다. 엔진 `SiteInput.reference_mass`(명시 형상>참조 비례>auto 우선순위·클램프 정직 표기), 서비스 `derive_reference_mass_hint`(기하 결측/무효 건너뛰기·없으면 정직 used=False), 라우터 opt-in `use_references`(기본 False·조회실패 정직 흡수), 프론트 토글/칩. 적대적 4-렌즈 리뷰(계약·정직·정확·커버리지) 위반 0. ※전체 기하 이식 `assemble_from_reference`(사용자가 ID 선택)는 기존 별도 경로 — 본 변경은 합성 경로 비례 주입(비중복).

### ⚠️ PARTIAL / STUB (미완 — §4 대상)
- **지자체 조례 한도**(§4-B `7fec04e` ✅ 완료): 엔진이 OrdinanceService(법제처 API→캐시→법정상한) 실효 한도를 min(법정,조례,목표)로 사용. ⚠️§3 정정 — "데이터 소스 부재"는 거짓이었다(OrdinanceService·land_info 연동 기존 존재). 진짜 갭은 'auto_design 엔진 미반영'뿐이었고 배선으로 해소. ZONE_LIMITS(SSOT)는 그대로(법정상한 폴백) — 조례는 라우터 주입·엔진 정규화로 additive.
- **실무 도면 등급**(partial): 전체 도면셋(B-01~C-03)·**정식 ezdxf DIMENSION**(`add_linear_dim`/`add_aligned_dim`)·SVG 해칭은 BUILT. ⚠️§3 정정 — "DXF DIMENSION 아님(임베디드 텍스트)"은 **거짓**(코드 직접 확인: `parametric_cad_service.py:86/984`). 진짜 미완은 **DXF HATCH 엔티티(`add_hatch` 0건)·RCP(천장)·MEP(설비)·단면 구조상세(철근배근)** — 신규 생성기 필요(§4-D, 대형).
- **BIM 소프트웨어 완전성**(partial): read/view/generate + **IFC export 됨** + **3D 단면(slicer) 됨**. ⚠️§3 원감사 정정 — "IFC export 없음(read-only)"은 부정확했다(적대적 리뷰가 발견): project-based `POST /design/{id}/bim/export-ifc`가 이미 있었고, §4-E(`db6c9d1`)가 param-based + UI 버튼을, `34e7ae6`이 3D 단면을 추가해 **export·단면은 완료**. 남은 미완은 **3D 요소 선택·이동/회전/스케일·측정도구**(프론트 R3F 인터랙션 중심 — §4-E 잔여).

## 4. 다음 단계 로드맵 (추천 순서 — 가치·실현성 순)

### A. 매스 선택→재생성 완결 ✅ 완료 (11bc342 + ff3b8bc)
- **완료(11bc342)**: `SiteInput.massing_kind`(slab/tower/lshape/court) + `MASSING_FORMS`(종횡비·플로어플레이트) + `compute_optimal_mass` 형상 변형 + summary `massing_kind`/`massing_label` + `DesignSpec→SiteInput` 배선 + `test_massing_kind`(8건). None=자동(기존 불변).
- **완료(ff3b8bc)**: ① `/drawing/auto-design`·`/drawing/design-alternatives`(정본 라우터 `apps/api/routers/drawing.py`)가 옵셔널 `massing_kind`를 수용해 SiteInput에 전달(additive·미정의→auto 폴백). ② `generate_alternatives` 대안별 형상 배정 — A=입력형상(None=auto), B=tower, C=lshape(다양화 고정·summary 키 불변·3대안 법규 준수 유지). ③ 프론트 매스 형상 선택 UI는 **백엔드 재생성 컴포넌트 `GenerativeDesignPanel`**에 배선(단일/Top3 호출에 massing_kind 전송 + 적용 형상 라벨 칩). ※ `DesignStudio`(독립 로컬계산 화면)는 백엔드 생성 경로가 없어 대상에서 제외 — 실 재생성 surface는 `GenerativeDesignPanel`. ④ 검증: `test_drawing_massing_router.py`(7) + `test_massing_kind` 대안형상(4) + 전체회귀 3320 그린 + tsc/build 그린.

### B. CAD 참조설계 피드백루프 ✅ 완료 (5df33cf)
- **완료**: `derive_reference_mass_hint`가 `find_similar(building_use, area_sqm, unit_types, zone_code)` 상위 후보 중 기하 보유·치수 유효 사례의 종횡비를 도출하고, `compute_optimal_mass`가 BCR footprint를 유지한 채 종횡비만 참조 쪽으로 편향(대지 유효치 클램프). 기하 결측/정규화 실패/치수 무효는 건너뛰어 다음 후보로 재탐색. 라우터 opt-in `use_references`(기본 False)·조회 실패 정직 흡수·프론트 토글/칩. 결정론(LLM 0). 테스트 22건 + 적대적 4-렌즈 리뷰.
- **조례 한도 ✅ 완료(`7fec04e`)**: 핸드오프의 '조례 DB 적재 필요'는 오기재였다 — OrdinanceService(법제처 API)·land_info 연동이 이미 있었고, 진짜 갭은 엔진 미반영뿐. 라우터 use_ordinance+address→OrdinanceService→엔진 정규화(min(법정,조례,목표)) 배선으로 해소.

### C. 도면 법규주석 ✅ 완료 (33202cd)
- **완료**: `SVGDrawingService.annotate_site_plan(findings, verdict)`가 8엔진 audit/설계 compliance를 배치도에 결정론 주석화 — footprint 최악 status 색칠(✓녹/⚠황/✗적)·범례(라벨·현재/한도)·정북일조(solar_envelope) 북측 적색 점선. 판정가능 finding(pass/warning/fail)만 반영(skipped/info 제외·가짜 적합 금지). `POST /drawing/annotated-site-plan`(DB-free). 프론트 `AnnotatedSitePlanCard`(Blob-URL `<img>` 안전 렌더)를 `GenerativeDesignPanel`에 배선(설계 compliance→finding). 정직 로직 순수모듈 `legalAnnotation`+vitest 10. 적대적 4-렌즈 리뷰 must-fix 2건(solar 엔진명 실데이터 dead-path·multi-word 라벨) 수정·검증.
- **남은 partial+(후속)**: 평면도(floor-plan)에 피난동선/실별 주석은 미구현 — 현재 배치도(site-plan) 수준. 8엔진 audit 워크스페이스(design-audit)에 주석 도면을 띄우려면 geometry 스레딩 필요(audit 리포트가 치수 미보유) — 현재는 설계패널(실 geometry 보유)에서 시연.

### D. 실무 도면 등급 (partial→실무, 대형·장기) — ⚠️범위 정정
- ✅이미 있음: 정식 ezdxf `DIMENSION`(`parametric_cad_service.py:86 add_linear_dim`·`:984 add_aligned_dim`, 평면/단면/입면/배치 전반), SVG 재료 해칭(콘크리트/단열재/지반).
- 진짜 미완: **DXF HATCH 엔티티**(`add_hatch` 호출 0건 — HATCH 레이어만 정의), **RCP(반사천장도)**, **MEP(설비 배관/덕트)**, **단면 구조상세(철근배근·콘크리트 두께)**. → DXF HATCH는 배선만(즉시), RCP/MEP/구조상세는 신규 생성기(대형·다회 세션).

### E. BIM 편집/저작 (export ✅ db6c9d1 · 단면 ✅ 34e7ae6 / 요소편집 후속)
- **완료(export)**: `POST /drawing/export-ifc`(param-based·DB-free) — build_ifc_from_mass로 설계 매스를 IFC4(.ifc) 다운로드. RFC 5987 파일명(한글 보존·헤더 안전)·501(ifcopenshell 누락)/400/422 정직. 프론트 'IFC(BIM) 내보내기' 버튼(CadBimIntegrationPanel). ※project-based `/design/{id}/bim/export-ifc`는 기존 존재 — 본 작업은 param-based 변형 + UI 배선(export-dxf 이중성 미러).
- **완료(단면, `34e7ae6`)**: R3F 전역 클립평면으로 건물 수평 절단 → 층별 내부 보기. 순수코어 `bimSection`(절단높이↔가시층)+vitest, 토글/슬라이더/'보이는 층 N/M' 라벨. 서버 glTF Y중심화 base 미접지 문제는 modelDims.minY 실측 접지로 해결(절차·glTF 모두 정직).
- **후속(요소 편집)**: 3D 뷰어 요소 선택(raycast)·이동/회전/스케일(gizmo)·측정도구(점-점 거리), 대형모델 증분 스트리밍 — R3F 인터랙션 중심이라 Playwright 시각검증 권장·별도 세션. 단면 절단면 cap(스텐실)도 후속 nit. (export_bim_ifc raw 헤더·try/except 부재 하드닝도 후보 — task_39e60d9e.)

## 5. 새 세션 첫 메시지 예시

> §4-A~§4-E의 매스재생성·참조피드백·도면주석·IFC export·3D단면·조례한도가 **완결**됐다(백엔드 3382 + 프론트 그린). **⚠️먼저: 갭 판정은 반드시 실제 propai-platform 코드 grep/read 증거(file:line)로 — §3 51-에이전트 감사가 스펙문서/없는 파일을 보고 EXISTS를 MISSING으로 반복 오판했다(조례 소스·DXF DIMENSION·IFC export·Kakao OAuth 모두 '없다' 오판).** `propai-platform/docs/HANDOFF_DESIGN_CAD_BIM_2026-06-13.md`를 읽고 §0의 검증된 '진짜 갭'부터 추천순으로 구현해줘:
> 1. **audit 워크스페이스 findings→도면 배선**(1순위·배선만): AnnotatedSitePlanCard·`/annotated-site-plan`은 이미 있음 — `DesignAuditWorkspace.tsx`에서 audit findings(params_used 치수 포함)를 카드로 렌더하는 호출만 추가.
> 2. **DXF HATCH 엔티티**(배선만): `parametric_cad_service.py`에 `msp.add_hatch()`+set_pattern_fill 호출 추가(레이어 이미 정의).
> 3. **평면도 findings 주석**: `generate_detailed_floor_plan`에 findings 파라미터 가산(배치도 패턴 이식).
> 4. **3D 요소 gizmo/측정**(신규): drei `TransformControls`+raycast 선택, 점-점/면적 측정 순수코어 vitest.
> (5. RCP/MEP/구조상세는 대형·다회 세션.) §1 불변규칙 준수, 검증(프론트 vitest/tsc/build; 백엔드 변경 시 `INTERP_REDIS_CACHE=0` 전체회귀) 후 작업 브랜치 커밋·푸시. main 푸시 금지.

(검증: `apps/api`에서 신규/관련 pytest + **전체회귀는 `pytest tests/ --ignore=tests/test_auction_demock_court.py --ignore=tests/test_molit_client.py`**(메인 204파일 타깃 — 인자 없는 pytest는 testpaths의 통합 스위트를 수집해 사전존재 환경실패가 섞임) → `apps/web` tsc·build → 그린이면 `git push origin feature/trust-infra-2026-06-11`. 커밋 말미 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` — 모델은 실행 세션 기준.)

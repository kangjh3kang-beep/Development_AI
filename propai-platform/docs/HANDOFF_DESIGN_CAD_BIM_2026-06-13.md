# 새 세션 인계 — 설계/CAD/BIM/IFC 실상태 감사 + 매스 형상(2026-06-13)

> 본 문서는 ①적산(BOQ) 자동화 마무리 ②설계·CAD·BIM·IFC 서브시스템의 **정직한 실상태 감사** ③매스 형상(massing_kind) 1차 구현을 인계한다.
> 51-에이전트 감사 워크플로 + 적대적 검증으로 도출한 **built/partial/stub** 판정이 핵심이며, §4 로드맵이 다음 구현 대상이다.

## 0. 한 줄 요약

적산은 백엔드 N1·N2·N3 + 프론트 정합까지 **완성·검증·푸시**(3300 pytest·tsc·build 그린). 설계/CAD/BIM은 **상당 부분 실구현**(IFC/DXF 분석·8엔진 법규검증·BIM read/view/generate)이나, **매스 선택→재생성·참조설계 피드백루프·실무 도면등급·BIM 편집/IFC export** 4개가 미완(partial/stub). 매스 형상 엔진 파라미터(`massing_kind`)는 1차 구현 완료.

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

검증 베이스라인: pytest **3300 passed / 0 failed**(34:51), tsc·build 그린, 설계/CAD/BOQ 서브셋 466 passed.

## 3. 서브시스템 실상태 감사 (51-에이전트 워크플로 + 적대적 검증, 정직 판정)

### ✅ BUILT (실구현 확인)
- **IFC/DXF 분석(=AI설계분석)** — 메뉴명 변경 완료. IFC(ifcopenshell)·DXF(ezdxf, 손상복구·단위환산) **실 파싱**. `design_audit_orchestrator`의 **8엔진**(건폐율·용적률·일조[정북사선 시뮬]·주차·피난[change_risk]·인근사례비교·인센티브경로·법규근거링크) 전부 **규칙기반**. 71 design_audit 테스트 통과. 근거링크는 검증 레지스트리만(할루시네이션 금지). → **사용자 요구 "IFC/DXF 첨부→정밀 공학/법규/건축 분석" 실질 충족.**
- **설계 편집 UI** — 2D/3D 토글 겹침 수정(`CadBimIntegrationPanel` `pt-16`+`flex-wrap`, 토글 `z-30`). 매싱 카드 선택 상태·'추정' 정직라벨. (단, Playwright 시각회귀 테스트 없음 — 뷰포트별 스냅샷 권장.)
- **Top3/단일 자동설계 생성** — `/drawing/design-alternatives`(3개 랭킹·점수·compliance-first)·`/drawing/auto-design` 실동작. 0세대 시 정직 안내. → **prod에서 Top3 미생성은 배포갭**(feature 브랜치엔 있음, main 미배포).
- **BIM read/view/generate** — IFC read·물량추출·work_code 매핑·파라미터→IFC 생성·IFC→glTF·R3F 3D뷰·`/bim` API.

### ⚠️ PARTIAL / STUB (미완 — §4 대상)
- **매스 선택→재생성**(partial): 카드 선택은 시각만, 백엔드 재생성 미배선. → **11bc342로 엔진 `massing_kind` 추가**(아래 §4-A 잔여).
- **CAD 참조설계 피드백루프**(stub): 업로드/저장(Supabase `propai-design-refs`)/검색/조립은 BUILT이나, **생성기가 합성 시 유사 사례를 참조하지 않음**(`find_similar` 결과가 생성에 미투입). 법규지식도 하드코딩 `ZONE_LIMITS`(지자체 조례 DB 미연동).
- **실무 도면 등급**(partial): 치수·포셰벽·KS 문/창 기호·전체 도면셋(B-01~C-03)은 BUILT이나 **스키매틱 수준** — 진짜 DXF DIMENSION 엔티티 아님(임베디드 텍스트), 재료 해칭·RCP·MEP·단면 상세·법규위반 도면주석 없음. **AutoCAD 실무 워킹드로잉 등급은 미달**(기술적 한계 아닌 미구현 — §4-D).
- **BIM 소프트웨어 완전성**(partial): read/view/generate는 되나 **IFC export/저작 없음(read-only)**, 3D 편집(이동/회전/스케일)·단면뷰·측정도구 없음.

## 4. 다음 단계 로드맵 (추천 순서 — 가치·실현성 순)

### A. 매스 선택→재생성 완결 (시작됨, 잔여 배선)
- **완료(11bc342)**: `SiteInput.massing_kind`(slab/tower/lshape/court) + `MASSING_FORMS`(종횡비·플로어플레이트) + `compute_optimal_mass` 형상 변형 + summary `massing_kind`/`massing_label` + `DesignSpec→SiteInput` 배선 + `test_massing_kind`(8건). None=자동(기존 불변).
- **잔여**: ① `/drawing/auto-design`·`/drawing/design-alternatives` 라우터가 `massing_kind`를 요청에서 받아 SiteInput에 전달(라우터는 `app/routers/drawing.py`). ② `generate_alternatives`가 대안별 형상 배정(A=auto/slab, B=tower, C=lshape) — **기존 대안 테스트 영향 확인 후**. ③ 프론트 `DesignStudio` 매싱 카드 선택 → `massing_kind`로 재생성 호출(현 선택은 시각만). ④ 검증: 라우터 테스트 + tsc/build.

### B. CAD 참조설계 피드백루프 (stub→built)
- `AutoDesignEngine` 생성 시 `design_reference_service.find_similar(site_area, zone_code, building_use, unit_types)` 상위 N건의 기하를 **참조 입력**으로 주입(대입·조합). 조립실패(footprint 초과) 시 더 타이트한 필터로 재탐색. 결정론 규칙 우선(LLM은 설명만).
- 지자체 조례 DB: `design_references`/별도 테이블에 `zone_code→local_bcr/far/height` 적재 후 `ZONE_LIMITS` 하드코딩 대체.

### C. 도면 법규주석 (stub→partial+)
- 8엔진 audit 위반/통과를 SVG 도면에 주석화(피난로 적색, 일조 미달 경고, 건폐/용적 ✓/✗). audit↔drawing 연결.

### D. 실무 도면 등급 (partial→실무, 대형·장기)
- 진짜 DXF `DIMENSION`/`LEADER` 엔티티(ISO 128), 재료 해칭(콘크리트/조적/석고), 1:50 상세(문/창 콜아웃), RCP·MEP 평면, 단면 구조부재. → 별도 다회 세션 권장. **"완벽한 AutoCAD 실무 도면 자동생성"은 현 스키매틱에서 점진 확장 대상이며 1세션 완성 불가 — 정직.**

### E. BIM 편집/저작 (partial→built)
- IFC export 엔드포인트, 3D 뷰어 요소 선택·이동/회전/스케일, 단면(slicer)·측정도구, 대형모델 증분 스트리밍.

## 5. 새 세션 첫 메시지 예시

> `propai-platform/docs/HANDOFF_DESIGN_CAD_BIM_2026-06-13.md`를 읽고, §4-A 잔여(라우터 massing_kind 수용 + 대안별 형상 + 프론트 매싱 선택→재생성)부터 추천순서로 구현해줘. §1 불변규칙 준수, §5 검증 통과 후 작업 브랜치 커밋·푸시. main 푸시 금지.

(검증: `apps/api`에서 신규/관련 pytest + 전체회귀(2건 제외) → `apps/web` tsc·build → 그린이면 `git push origin feature/trust-infra-2026-06-11`. 커밋 말미 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` — 모델은 실행 세션 기준.)

# QA 교차검증 — Flagship A (90초 AI PreCheck + 조닝 시그널)

- 대상 커밋: `90b2450` (HEAD, 풀스택 9파일 / +1416 라인)
- 검증자: qa-validator (읽기 검증 전용, 코드/배포/push 미수행)
- 검증 일시: 2026-06-05
- 검증 방법: 계약서 06 ↔ 백엔드 응답 ↔ 프론트 types.ts 교차대조, 재사용 함수 시그니처 실측,
  실제 venv 임포트 스모크, 전역 `tsc --noEmit`, 신규파일 `eslint`

---

## 1. 항목별 판정표

| # | 검증 항목 | 판정 | 핵심 근거 |
|---|-----------|------|-----------|
| 1 | 계약 정합(필드/중첩/타입/enum) | **PASS** | A·B 응답 ↔ types.ts ↔ 계약서 06 전필드 일치, enum 양측 동일 |
| 2 | 경로 정합(404 위험) | **PASS** | apiClient `/precheck/*` +자동 `/api/v1` ↔ mount `prefix=/api/v1/precheck` ↔ route `/instant`·`/zoning-signals` |
| 3 | 백엔드 로직 정확성(signal/한도/재사용) | **PASS** | signal 규칙·ZONE_LIMITS 매핑·재사용 함수 시그니처 전부 실측 일치 |
| 4 | 90초 SLA·가드 | **PASS** | 모든 외부호출 `asyncio.wait_for`, `time.perf_counter` elapsed_ms, LLM은 use_llm시·실패시 None |
| 5 | 엣지/에러 경로 | **PASS** | 422·ok:false+message·signals:[]+note·geojson null 백엔드/프론트 양측 처리 |
| 6 | 프론트 품질(토큰/ssr/린트/타입) | **PASS** | 의미색 토큰 일관, Leaflet dynamic ssr:false, apiClient import 보존, tsc 0 / eslint 0 |
| 7 | 회귀(main/layout/기존엔드포인트) | **PASS** | main.py +2라인 추가만, layout +1 메뉴(삭제0), 기존 라우터 무변경 |
| — | 임포트 루트 정합(혼합 스타일) | **PASS(주의)** | 코드베이스 기존 컨벤션과 동일, 듀얼루트 런타임에서 실임포트 검증 OK |

**종합: GO (배포 가능)** — 블로커 0건. 운영 주의 1건(WARN, 배포 차단 아님).

---

## 2. 항목별 상세 근거

### 1) 계약 정합 — PASS
A. `/instant` 성공 응답(precheck_service.py:226-237) 필드 = 계약서 06 줄11-26 = types.ts `InstantPreCheckResponse`(types.ts:51-64) 완전 일치:
`ok, address, pnu, zone_type, area_sqm, legal_limits{bcr_pct,far_pct,height_m,source}, methods[], summary{pass,warn,fail,best,llm_note}, elapsed_ms, sources[]`.
- method 카드(precheck_service.py:145-150) = types.ts:24-33 `PreCheckMethod`: `code,name,signal,permitted,complexity,complexity_label,checks[],reason` 일치.
- check 항목(precheck_service.py:78-103,117-136) = types.ts:18-22 `PreCheckRuleResult{rule,status,detail}` 일치.

B. `/zoning-signals` 성공 응답(precheck_service.py:384-391) = 계약서 줄38-45 = types.ts:103-112 `ZoningSignalsResponse`:
`ok, target{pnu,zone_type,address}, signals[], geojson|null, sources[]` (+ ok:false에서 message, 빈경로 note — types.ts:110-111에 optional로 선언). 일치.
- signal(precheck_service.py:415-421 등) = types.ts:88-94 `ZoningSignal{type,score,level,parcels[],rationale}` 일치.
- parcel(precheck_service.py:407-409) = types.ts:82-86 `{pnu,zone_type,adjacent}` 일치.

enum 양측 동일:
- signal/status = `pass|warn|fail` (types.ts:8, precheck_service 산정값 동일).
- level = `high|mid|low` (types.ts:80, precheck_service.py:418,426,437,447,456 산정값 동일).
- type = `통합개발후보|용도상향기회|역세권개발|저밀재건축` (types.ts:74-78 ↔ precheck_service.py:416,433,443,453 동일).

→ 필드명/중첩/타입/enum 전부 일치. 깨질 화면값 없음.

### 2) 경로 정합 — PASS
- 프론트: `apiClient.post("/precheck/instant")`, `("/precheck/zoning-signals")` (PreCheckWorkspace.tsx:113,137).
- api-client getRequestUrl(api-client.ts:52-72): 상대경로에 `/api/v1` 자동 prefix(prod는 `https://api.4t8t.net/api/v1` + path).
- 백엔드: `app.include_router(precheck.router, prefix="/api/v1/precheck")` (main.py:403), route `/instant`·`/zoning-signals` (precheck.py:37,58).
- 최종 URL = `…/api/v1/precheck/instant`·`…/zoning-signals` → 양측 정확 매칭. **404 위험 0.**

### 3) 백엔드 로직 정확성 — PASS
- signal 산정(precheck_service.py:118-150): 불허→`fail`(125-130), 허용+복잡도≤3→`pass`, 허용+4~5→`warn`(139). 계약서 줄31 정확 구현.
- legal_limits(precheck_service.py:48-61): ZONE_LIMITS의 `max_bcr/max_far/max_height_m`→`bcr_pct/far_pct/height_m` 매핑(실측 auto_zoning_service.py:12-30 키와 일치).
- 면적 미입력→check `warn`("면적 미입력 — 정량 검토 보류", precheck_service.py:95-96). 계약 일치.
- 재사용 함수 시그니처 실측 일치:
  - `get_permitted_types(zone)->list[str]` (permit_validator.py:54), `get_permit_complexity(dev)->int` (67), `DEVELOPMENT_TYPE_NAMES`(46), `PERMIT_COMPLEXITY`(28) — 전부 존재·호출형 일치.
  - `AutoZoningService().analyze_by_address(addr)` 반환 `zone_type/pnu/land_area_sqm/coordinates{lat,lon}` (auto_zoning_service.py:43,56-60,90) ↔ precheck_service.py:171-174,304-305 사용 키 일치.
  - `ZONE_LIMITS`(auto_zoning_service.py:12) import OK.
  - `vworld.geocode_address`→`{lat,lon,pnu,address}`(vworld_service.py:123) ↔ precheck_service.py:313-314 일치.
  - `vworld.get_parcels_in_bbox(min_lon,min_lat,max_lon,max_lat,max_count)`(vworld_service.py:210-214) ↔ precheck 호출 `(lon-deg,lat-deg,lon+deg,lat+deg,max_count=80)`(344-346) 위치인자 정렬 정확.
  - `_parcel_adjacency(geoms)->{contiguous,components,note}`(auto_zoning.py:264,296-300) ↔ precheck_service.py:369-370 `.get("contiguous")` 사용 일치.
- 실 임포트 스모크: `run_instant_precheck`·`run_zoning_signals` callable, 재사용 심볼 전부 RESOLVED 확인.

### 4) 90초 SLA·가드 — PASS
- 외부호출 전부 `asyncio.wait_for` 가드: zoning analyze(168), geocode(311), bbox(343), LLM(261).
- 타임아웃 상수: ZONING 30s / BBOX 25s / LLM 25s(precheck_service.py:29-31) — 직렬 최악도 90s 내.
- elapsed_ms = `time.perf_counter` 차분(160,188,235).
- LLM은 `use_llm=True`에서만 호출(218), 실패/타임아웃 시 `_llm_one_liner`가 None 반환(267-268) → 룰체크 결과 무손상.

### 5) 엣지/에러 — PASS
- pnu/address 모두 없음→422: `/instant`은 address 필수+빈문자 가드 422(precheck.py:45-46); `/zoning-signals`은 model_validator로 둘 다 없으면 ValidationError(precheck.py:30-34, FastAPI 422).
- 용도지역 미확인→ok:false+message(빈결과 금지): instant(precheck_service.py:181-190), zoning(318-325). 빈 PDF/빈200 없음.
- 주변 필지 0→signals:[]+note+ok:true(precheck_service.py:355-363).
- geojson null 허용(334) / 좌표 미확보시 ok:true+signals:[]+note(329-337).
- 프론트 처리: ok:false→amber 안내(PreCheckWorkspace.tsx:299-305,496-502), 빈 신호→note 표시(522-525), 408/타임아웃 등 ApiClientError→message/detail 파싱(94-100). 모두 처리됨.

### 6) 프론트 품질 — PASS
- 신호등 의미색: emerald/amber/rose 일관(SIGNAL_STYLE PreCheckWorkspace.tsx:44-66), 카드·점·칩·체크 동일 팔레트. 저대비 하드코딩 우회 없음(나머지는 `var(--*)` 토큰).
- Leaflet: `dynamic(... { ssr:false, loading })`(PreCheckWorkspace.tsx:30-33), ZoningSignalMap "use client"+window 가드(ZoningSignalMap.tsx:22).
- apiClient import 보존(PreCheckWorkspace.tsx:17) — 린터 삭제 회귀 함정 통과(eslint 0).
- 검증 신뢰성 재확인: 전역 `npx tsc --noEmit` **exit 0 / error 0**(precheck 포함). 신규 4파일 `eslint` **exit 0**. 커밋 메시지의 "tsc 0 / eslint 0" 주장 = 사실로 재현됨.

### 7) 회귀 — PASS
- main.py: import에 `precheck` 1줄 추가(80), mount 1줄 추가(403). 기타 라우터 순서·prefix 무변경.
- layout.tsx: '프로젝트 분석' 그룹에 `/precheck` 1개 추가(110 부근), 삭제·재배치 0. 기존 메뉴 무파괴.
- 백엔드 기존 엔드포인트 무변경(permit_validator/auto_zoning/vworld는 import만, 수정 0).

### (주의) 임포트 루트 정합 — PASS(WARN)
- precheck_service.py는 `from app.services...`(21,26) + 지연 `from routers.auto_zoning import _parcel_adjacency`(366) 바(bare) 임포트 사용.
- main.py는 `from apps.api.routers import ...`(29) 풀패스 사용 → 런타임에 **두 sys.path 루트(레포루트 + apps/api)** 가 모두 필요.
- 실측: 코드베이스 203개 파일이 동일한 bare `app.*` 컨벤션을 사용하며 프로덕션 부팅이 라이브 검증됨(메모리: 8라우트 부팅 PASS). 듀얼루트 조건에서 지연임포트 `routers.auto_zoning._parcel_adjacency` 실제 임포트·실행 성공 확인(`adjacency([])`={contiguous:True…}).
- 결론: 본 커밋이 도입한 결함 아님. 기존 컨벤션과 동일. **배포 차단 아님.** 단, 단일루트(레포루트만) 환경에서 `routers/auto_zoning.py`의 `from apps.api.app.services…`가 깨지는 것은 전 코드베이스 공통 특성이므로, 향후 임포트 루트 표준화는 별도 리팩토링 과제로 권고.

---

## 3. FAIL/WARN별 수정지시

- **FAIL: 없음.**
- **WARN(권고, 배포 비차단):** 임포트 스타일 혼재.
  - 권고: precheck_service.py:366 `from routers.auto_zoning import _parcel_adjacency` →
    `from apps.api.routers.auto_zoning import _parcel_adjacency` 로 통일하면 단일/듀얼루트 모두 견고.
  - 단, 현 운영 런타임에서 동작 확인됨. 즉시 수정 불요(전 코드베이스 일괄 표준화 시 함께 처리 권장).

---

## 4. 종합 판정

**GO — 배포 가능.**

근거: 계약↔백엔드↔프론트 전필드/enum 정합, 경로 404 위험 0, 재사용 함수 시그니처 실측 일치,
90초 SLA 가드 완비, 엣지/에러 경로 양측 처리, 전역 tsc 0·신규 eslint 0 재현, 회귀 무.
블로커 0건. 임포트 스타일 WARN 1건은 기존 컨벤션 동일·런타임 검증 통과로 배포 비차단.

**검증 명령 출력(신선):**
- `npx tsc --noEmit` → exit 0 (precheck 포함 error 0)
- `eslint` (신규 4파일) → exit 0
- venv 실임포트: precheck_service/router/재사용심볼 전부 RESOLVED, 지연 routers 임포트 듀얼루트 OK
